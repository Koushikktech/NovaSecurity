import threading

from fastapi.testclient import TestClient

from api import app
from config import settings
from persistence.database import init_database


def test_provider_initialization_failure_releases_review_slot(tmp_path, monkeypatch):
    import routes.v1 as routes

    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "reviews.db"))
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspaces")
    init_database()
    monkeypatch.setattr(routes, "_JOB_SLOTS", threading.BoundedSemaphore(1))

    class BrokenProvider:
        def __init__(self):
            raise ValueError("deliberate provider initialization failure")

    monkeypatch.setattr(routes, "UnavailableProvider", BrokenProvider)
    client = TestClient(app)
    payload = {"files": [{"path": "app.py", "content": "value = 1\n"}]}
    for _ in range(2):
        created = client.post("/api/v1/reviews/folder", json=payload)
        assert created.status_code == 202, created.text
        run = client.get("/api/v1/reviews/" + created.json()["run_id"]).json()
        assert run["status"] == "failed"
        assert "provider initialization failure" in run["errors"][0]
    assert not routes._ACTIVE_ORCHESTRATORS


def test_persistence_failure_does_not_exhaust_review_slots(monkeypatch):
    import routes.v1 as routes

    monkeypatch.setattr(routes, "_JOB_SLOTS", threading.BoundedSemaphore(1))

    def fail(_):
        raise OSError("storage unavailable")

    monkeypatch.setattr(routes, "save_run", fail)
    client = TestClient(app)
    for _ in range(2):
        response = client.post("/api/v1/reviews", json={"repo_url": "https://github.com/example/project"})
        assert response.status_code == 503, response.text
        assert "storage" in response.json()["detail"]
