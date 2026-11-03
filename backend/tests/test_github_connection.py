import time

import httpx
import pytest
from fastapi import HTTPException

import github_connection as gh


@pytest.fixture(autouse=True)
def clean_connection():
    gh._connection.clear()
    gh._pending.clear()
    yield
    gh._connection.clear()
    gh._pending.clear()


def test_connect_requires_configuration(monkeypatch):
    monkeypatch.delenv("GITHUB_APP_CLIENT_ID", raising=False)
    with pytest.raises(HTTPException) as error:
        gh.connect()
    assert error.value.status_code == 503


def test_state_expiry_and_replay(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "secret")
    from urllib.parse import parse_qs, urlparse
    url = gh.connect()["url"]
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    gh._pending[state] = (time.time() - 1, "verifier")
    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            gh.callback(state=state, code="code")
        assert error.value.status_code == 400


def test_callback_and_disconnect(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "id")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "secret")
    gh._pending["state"] = (time.time()+60, "verifier")
    def post(url, **kwargs):
        assert kwargs["json"]["code_verifier"] == "verifier"
        return httpx.Response(200, json={"access_token": "test-secret", "expires_in": 3600}, request=httpx.Request("POST", url))
    monkeypatch.setattr(gh.httpx, "post", post)
    monkeypatch.setattr(gh.httpx, "get", lambda url, **kwargs: httpx.Response(200, json={"login": "tester"}, request=httpx.Request("GET", url)))
    assert gh.callback("state", "code").status_code == 303
    assert gh.connection_token() == "test-secret"
    assert "test-secret" not in str(gh.status())
    with pytest.raises(HTTPException):
        gh.callback("state", "code")
    gh.disconnect()
    assert not gh.connection_token()


def test_picker_targets(monkeypatch):
    monkeypatch.setattr(gh, "api", lambda *args: [{"name":"main", "commit":{"sha":"a"*40}}])
    target = gh.targets("owner", "repo", "branches", 1)["items"][0]
    assert target["revision"] == "a"*40
    with pytest.raises(HTTPException):
        gh.targets("owner", "repo", "../secrets", 1)


def test_git_credential_not_in_argv(monkeypatch, tmp_path):
    from ingestion.targets import git
    def run(command, **kwargs):
        assert "secret-token" not in str(command)
        assert kwargs["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout=b"ok")
    monkeypatch.setattr("ingestion.targets.subprocess.run", run)
    marker = gh.review_token.set("secret-token")
    try:
        assert git(tmp_path, "status") == b"ok"
    finally:
        gh.review_token.reset(marker)
