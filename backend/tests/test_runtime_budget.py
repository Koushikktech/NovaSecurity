from concurrent.futures import ThreadPoolExecutor

import pytest

from runtime_budget import remaining_time, reset_deadline, start_deadline


def test_deadline_expiry_and_context_reset(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("runtime_budget.time.monotonic", lambda: clock[0])
    token = start_deadline(10)
    try:
        assert remaining_time(90) == 10
        clock[0] = 111
        with pytest.raises(TimeoutError, match="deadline"):
            remaining_time(90)
    finally:
        reset_deadline(token)
    assert remaining_time(90) == 90


def test_parallel_review_deadlines_are_isolated():
    def job(seconds):
        token = start_deadline(seconds)
        try:
            return remaining_time(100)
        finally:
            reset_deadline(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        short, long = list(pool.map(job, [10, 50]))
    assert 9 < short <= 10 and 49 < long <= 50
    assert remaining_time(100) == 100


def test_orchestrator_deadline_failure_resets_thread_context(tmp_path, monkeypatch):
    from config import settings
    from providers.unavailable import UnavailableProvider
    from review.orchestrator import ReviewOrchestrator

    original_start = start_deadline
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "workspaces")
    monkeypatch.setattr("review.orchestrator.start_deadline", lambda _: original_start(-1))
    root = tmp_path / "source"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n")
    run, _ = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
        str(root), local_dir=str(root), static_only=True
    )
    assert run.status.value == "failed"
    assert any("deadline" in error.lower() for error in run.errors)
    assert remaining_time(100) == 100
