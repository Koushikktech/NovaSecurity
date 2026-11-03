"""Thread-context review deadline shared by ingestion, analyzers and model orchestration."""

import time
from contextvars import ContextVar

_DEADLINE: ContextVar[float | None] = ContextVar("review_deadline", default=None)


def start_deadline(seconds):
    return _DEADLINE.set(time.monotonic() + seconds)


def reset_deadline(token):
    _DEADLINE.reset(token)


def remaining_time(maximum):
    deadline = _DEADLINE.get()
    if deadline is None:
        return maximum
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Review deadline exhausted")
    return min(maximum, remaining)
