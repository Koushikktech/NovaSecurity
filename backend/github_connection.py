"""Single-operator GitHub App authorization; secrets stay in server memory."""

import base64
import hashlib
import os
import secrets
import threading
import time
from contextvars import ContextVar
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/api/v1/github", tags=["GitHub"])
review_token: ContextVar[str] = ContextVar("github_review_token", default="")
_lock = threading.Lock()
_pending = {}
_connection = {}


def connection_token():
    with _lock:
        if _connection.get("expires", 0) > time.time():
            return _connection.get("token", "")
    return ""


def api(path, params=None):
    token = connection_token()
    if not token:
        raise HTTPException(401, "Connect GitHub again to browse repositories")
    try:
        response = httpx.get(
            "https://api.github.com" + path,
            params=params,
            headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "GitHub is unavailable; retry shortly") from exc
    if response.status_code >= 400:
        raise HTTPException(
            429 if response.status_code == 429 or response.headers.get("x-ratelimit-remaining") == "0" else 403,
            "GitHub access failed. Check repository permissions or reconnect; rate limits may apply.",
        )
    return response.json()


@router.get("/status")
def status():
    return {
        "configured": bool(os.getenv("GITHUB_APP_CLIENT_ID") and os.getenv("GITHUB_APP_CLIENT_SECRET")),
        "connected": bool(connection_token()),
        "login": _connection.get("login"),
        "installation_url": os.getenv("GITHUB_APP_INSTALL_URL", ""),
    }


@router.post("/connect")
def connect():
    if not status()["configured"]:
        raise HTTPException(
            503,
            "GitHub connection needs setup. See docs/github-connection.md; URL and folder reviews are available now.",
        )
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    with _lock:
        for key in list(_pending):
            if _pending[key][0] < time.time():
                del _pending[key]
        _pending[state] = (time.time() + 600, verifier)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return {
        "url": "https://github.com/login/oauth/authorize?"
        + urlencode(
            {
                "client_id": os.environ["GITHUB_APP_CLIENT_ID"],
                "redirect_uri": callback_url(),
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    }


def callback_url():
    return os.getenv("GITHUB_APP_CALLBACK_URL", "http://localhost:8000/api/v1/github/callback")


@router.get("/callback")
def callback(state: str = "", code: str = "", error: str = ""):
    with _lock:
        pending = _pending.pop(state, None)
    if not pending or pending[0] < time.time():
        raise HTTPException(400, "Expired or invalid GitHub connection request; start again")
    if error or not code:
        raise HTTPException(400, "GitHub connection was declined; start again")
    try:
        response = httpx.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            json={
                "client_id": os.environ["GITHUB_APP_CLIENT_ID"],
                "client_secret": os.environ["GITHUB_APP_CLIENT_SECRET"],
                "code": code,
                "redirect_uri": callback_url(),
                "code_verifier": pending[1],
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise ValueError("No token")
        user = httpx.get("https://api.github.com/user", headers={"Authorization": "Bearer " + token}, timeout=20)
        user.raise_for_status()
        with _lock:
            _connection.update(
                token=token, login=user.json()["login"], expires=time.time() + int(data.get("expires_in", 28800))
            )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "GitHub authorization failed; reconnect") from exc
    return RedirectResponse(
        os.getenv("PROOFLINE_FRONTEND_URL", "http://localhost:3000") + "/?github=connected", status_code=303
    )


@router.post("/disconnect")
def disconnect():
    with _lock:
        _connection.clear()
    return {"connected": False}


@router.get("/repositories")
def repositories(page: int = Query(1, ge=1)):
    # GitHub App user tokens are restricted to repositories granted to the app.
    data = api("/user/repos", {"per_page": 50, "page": page, "sort": "updated"})
    return {
        "items": [
            {"name": r["full_name"], "url": r["html_url"], "branch": r["default_branch"], "private": r["private"]}
            for r in data
        ],
        "has_more": len(data) == 50,
    }


@router.get("/repositories/{owner}/{repo}/{kind}")
def targets(owner: str, repo: str, kind: str, page: int = Query(1, ge=1)):
    import re

    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) for x in (owner, repo)) or kind not in {
        "branches",
        "pulls",
        "commits",
    }:
        raise HTTPException(422, "Invalid repository or target type")
    data = api(f"/repos/{owner}/{repo}/{kind}", {"per_page": 50, "page": page})
    items = []
    for item in data:
        if kind == "branches":
            items.append(
                {"label": item["name"], "revision": item["commit"]["sha"], "url": f"https://github.com/{owner}/{repo}"}
            )
        elif kind == "pulls":
            items.append({"label": f"#{item['number']} {item['title']}", "url": item["html_url"], "revision": ""})
        else:
            items.append(
                {
                    "label": item["sha"][:7] + " " + item["commit"]["message"].splitlines()[0],
                    "url": item["html_url"],
                    "revision": "",
                }
            )
    return {"items": items, "has_more": len(data) == 50}
