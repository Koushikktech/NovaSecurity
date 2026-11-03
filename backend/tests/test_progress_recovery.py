import threading

import pytest
from fastapi.testclient import TestClient

from api import app
from config import settings
from persistence.database import get_events, get_run, init_database, save_event, save_run
from schemas.contracts import InputMode, ReviewRun, RunStatus


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "reviews.db"))
    init_database()


def review(status):
    run = ReviewRun(canonical_repo="https://github.com/example/project", input_mode=InputMode.REPO, status=status)
    save_run(run)
    return run


@pytest.mark.parametrize("status", [RunStatus.PARTIAL, RunStatus.INTERRUPTED, RunStatus.CANCELLED, RunStatus.COMPLETED])
def test_terminal_progress_stream_closes_and_reconnect_does_not_repeat_events(isolated_database, status):
    run = review(status)
    first = save_event(run.id, "first", {"step": "ingest"})
    second = save_event(run.id, "second", {"step": "analyze"})
    client = TestClient(app)
    response = client.get(f"/api/v1/reviews/{run.id}/events", headers={"Last-Event-ID": str(first)})
    assert response.status_code == 200
    assert f"id: {second}\n" in response.text
    assert f"id: {first}\n" not in response.text
    assert f'"status": "{status.value}"' in response.text
    assert response.text.count("event: complete") == 1
    response = client.get(f"/api/v1/reviews/{run.id}/events?after={second}", headers={"Last-Event-ID": str(first)})
    assert "id: " not in response.text and "event: complete" in response.text


@pytest.mark.parametrize("cursor", ["-1", "bad", "9" * 25, "9223372036854775808"])
def test_invalid_reconnect_cursor_rejected(isolated_database, cursor):
    run = review(RunStatus.PARTIAL)
    response = TestClient(app).get(f"/api/v1/reviews/{run.id}/events", headers={"Last-Event-ID": cursor})
    assert response.status_code == 400


def test_queued_cancellation_prevents_worker_initialization_and_releases_slot(isolated_database, monkeypatch):
    import routes.v1 as routes

    run = review(RunStatus.QUEUED)
    monkeypatch.setattr(routes, "_JOB_SLOTS", threading.BoundedSemaphore(1))
    assert routes._JOB_SLOTS.acquire(blocking=False)
    response = TestClient(app).post(f"/api/v1/reviews/{run.id}/cancel")
    assert response.json()["status"] == "cancelled"

    def forbidden():
        pytest.fail("Cancelled queued job initialized a provider")

    monkeypatch.setattr(routes, "GeminiProvider", forbidden)
    monkeypatch.setattr(routes, "UnavailableProvider", forbidden)
    routes._run_review_background(run.id, run.canonical_repo, None, None, None)
    assert routes._JOB_SLOTS.acquire(blocking=False)
    routes._JOB_SLOTS.release()
    assert get_run(run.id).completed_at
    assert len([event for event in get_events(run.id) if event["event_type"] == "run_cancelled"]) == 1


def test_cancellation_is_idempotent_and_cannot_reclassify_completed_run(isolated_database):
    client = TestClient(app)
    run = review(RunStatus.COMPLETED)
    assert client.post(f"/api/v1/reviews/{run.id}/cancel").json()["status"] == "completed"
    assert get_run(run.id).status == RunStatus.COMPLETED
    assert client.post("/api/v1/reviews/missing/cancel").status_code == 404
    run = review(RunStatus.RUNNING)
    for _ in range(2):
        assert client.post(f"/api/v1/reviews/{run.id}/cancel").json()["status"] == "cancelled"
    assert len(get_events(run.id)) == 1
    stale = run.model_copy(update={"status": RunStatus.COMPLETED})
    save_run(stale, preserve_cancelled=True)
    assert get_run(run.id).status == RunStatus.CANCELLED


def test_actual_app_restart_preserves_results_and_interrupts_orphaned_work(isolated_database):
    active = review(RunStatus.RUNNING)
    complete = review(RunStatus.COMPLETED)
    complete.coverage = {"result": "must survive"}
    save_run(complete)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/reviews/{active.id}").json()["status"] == "interrupted"
        assert client.get(f"/api/v1/reviews/{complete.id}").json()["coverage"] == {"result": "must survive"}
    assert get_run(active.id).completed_at
    assert get_events(active.id)[0]["event_type"] == "run_interrupted"
    with TestClient(app):
        assert len(get_events(active.id)) == 1
