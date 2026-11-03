import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import HTTPException

from config import settings
from persistence.database import init_database, save_run
from schemas.contracts import InputMode, ReviewRun, RunStatus


def setup_run(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(tmp_path / "reviews.db"))
    monkeypatch.setattr(settings, "github_publish_enabled", True)
    monkeypatch.setattr(settings, "github_token", "test-token-only")
    init_database()
    run = ReviewRun(
        canonical_repo="https://github.com/example/app/pull/1",
        input_mode=InputMode.PR,
        head_sha="a" * 40,
        status=RunStatus.COMPLETED,
    )
    save_run(run)
    from ingestion.github import GitHubMetadataFetcher

    monkeypatch.setattr(GitHubMetadataFetcher, "fetch_pr_metadata", lambda *args: {"head_sha": run.head_sha})
    return run


def test_concurrent_review_publication_is_serialized_and_retry_reuses_marker(tmp_path, monkeypatch):
    from routes.v1 import publish_review

    run = setup_run(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    remote = []
    writes = []

    def handler(request):
        if request.method == "GET":
            entered.set()
            assert release.wait(5)
            return httpx.Response(200, json=remote)
        import json

        writes.append(json.loads(request.content))
        remote.append(
            {"id": 91, "html_url": "https://github.com/example/app/pull/1#review-91", "body": writes[-1]["body"]}
        )
        return httpx.Response(201, json=remote[-1])

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(publish_review, run.id)
        try:
            assert entered.wait(5)
            with pytest.raises(HTTPException) as busy:
                publish_review(run.id)
            assert busy.value.status_code == 409
        finally:
            release.set()
        assert first.result(timeout=5)["published"]
    assert publish_review(run.id)["reused"]
    assert len(writes) == 1


def test_ambiguous_timeout_reconciles_remote_success_before_retrying_write(tmp_path, monkeypatch):
    from routes.v1 import publish_review

    run = setup_run(tmp_path, monkeypatch)
    remote = []
    writes = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json=remote)
        import json

        writes.append(1)
        remote.append(
            {
                "id": 1,
                "html_url": "https://github.com/example/app/pull/1#review-1",
                "body": json.loads(request.content)["body"],
            }
        )
        raise httpx.ReadTimeout("response lost after server accepted write", request=request)

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(HTTPException) as unknown:
        publish_review(run.id)
    assert unknown.value.status_code == 504
    assert publish_review(run.id)["reused"]
    assert len(writes) == 1


def test_publication_rate_limit_is_actionable_and_lock_is_released(tmp_path, monkeypatch):
    from routes.v1 import publish_review

    run = setup_run(tmp_path, monkeypatch)
    original = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(
            transport=httpx.MockTransport(lambda req: httpx.Response(429, headers={"retry-after": "60"})), **kw
        ),
    )
    for _ in range(2):
        with pytest.raises(HTTPException) as rate_limit:
            publish_review(run.id)
        assert rate_limit.value.status_code == 503
        assert rate_limit.value.headers == {"Retry-After": "60"}


def test_publication_deadline_expires_between_remote_requests_and_resets(monkeypatch):
    import runtime_budget
    from routes.publication_guard import publication_guard

    now = [100.0]
    monkeypatch.setattr(runtime_budget.time, "monotonic", lambda: now[0])
    with pytest.raises(HTTPException) as expired:
        with publication_guard("test", "deadline"):
            assert runtime_budget.remaining_time(20) == 20
            now[0] += 61
            runtime_budget.remaining_time(20)
    assert expired.value.status_code == 504
    assert runtime_budget.remaining_time(20) == 20
    with publication_guard("test", "deadline"):
        assert runtime_budget.remaining_time(20) == 20
