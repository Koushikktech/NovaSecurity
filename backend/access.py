"""Single-operator deployment boundary. Local mode is loopback-only."""

import hmac
import os

from fastapi import HTTPException, Request


async def require_operator(request: Request):
    # OAuth callback is authenticated by a single-use, expiring state + PKCE.
    if request.url.path == "/api/v1/github/callback" and request.method == "GET":
        return
    token = os.environ.get("PROOFLINE_OPERATOR_TOKEN", "")
    if token:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied, token):
            raise HTTPException(401, "Operator token required")
    elif not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Configure PROOFLINE_OPERATOR_TOKEN for remote access")
