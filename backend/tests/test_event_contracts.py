import pytest
from pydantic import ValidationError

from schemas.events import HarnessEvent, ModelAttempt


def test_tool_events_require_observation_provenance():
    with pytest.raises(ValidationError):
        HarnessEvent(event_type="tool_completed", role="review")
    event = HarnessEvent(
        event_type="tool_completed",
        role="review",
        observation={"snapshot": "a" * 64, "tool": {"name": "read_file", "path": "app.py"}, "output": "1: value = 1"},
    )
    assert event.observation.snapshot == "a" * 64


def test_provider_event_rejects_impossible_state():
    with pytest.raises(ValidationError):
        ModelAttempt(model="gemini-test", role="review", attempt=0, state="silently_successful")
