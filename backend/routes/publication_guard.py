"""Bounded publication operations for the supported single-process deployment."""

import hashlib
import threading
from contextlib import contextmanager

import httpx
from fastapi import HTTPException

from runtime_budget import reset_deadline, start_deadline

# Fixed stripes avoid retaining one lock for every historical run/patch.
_LOCKS = [threading.Lock() for _ in range(64)]


@contextmanager
def publication_guard(kind: str, identifier: str):
    stripe = int.from_bytes(hashlib.sha256(f"{kind}:{identifier}".encode()).digest()[:4]) % len(_LOCKS)
    lock = _LOCKS[stripe]
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Another publication is in progress; retry this same item after it finishes")
    deadline = start_deadline(60)
    try:
        yield
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {403, 429}:
            delay = exc.response.headers.get("retry-after", "")
            headers = {"Retry-After": delay} if delay.isascii() and delay.isdigit() and len(delay) <= 6 else None
            raise HTTPException(
                503, "GitHub denied or rate-limited publication. Check permissions or retry later.", headers=headers
            ) from exc
        if status in {409, 422}:
            raise HTTPException(
                409,
                "GitHub rejected a conflicting publication. Retry this same item to reconcile existing remote state.",
            ) from exc
        raise HTTPException(
            502,
            "GitHub did not confirm publication. Retry this same item; existing remote markers are checked before another write.",
        ) from exc
    except (httpx.RequestError, TimeoutError) as exc:
        raise HTTPException(
            504,
            "Publication could not be confirmed before its deadline. Retry this same item; do not create a new review or patch.",
        ) from exc
    except ValueError as exc:
        from ingestion.redactor import redact_secrets

        raise HTTPException(409, redact_secrets(str(exc))[0][:1000]) from exc
    finally:
        reset_deadline(deadline)
        lock.release()
