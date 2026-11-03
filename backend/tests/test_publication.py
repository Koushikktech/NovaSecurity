"""Contract tests with a fake GitHub transport. No real publication occurs."""

import base64

import httpx

from remediation.publish import publish_fix
from schemas.contracts import FileEdit, InputMode, Patch, ReviewRun


def test_fix_publication_uses_real_git_object_api(monkeypatch, tmp_path):
    import remediation.publish as module

    metadata = {"head_sha": "a" * 40, "head_repo_url": "https://github.com/acme/app.git", "head_ref": "feature"}
    monkeypatch.setattr(module.GitHubMetadataFetcher, "fetch_pr_metadata", lambda *a: metadata)
    called = []

    def handler(request):
        import json

        path = request.url.path
        called.append((request.method, path))
        if path.endswith("/pulls") and request.method == "GET":
            return httpx.Response(200, json=[])
        if "/contents/" in path:
            return httpx.Response(200, json={"type": "file", "content": base64.b64encode(b"value=1\n").decode()})
        if "/git/ref/" in path:
            return httpx.Response(404)
        if "/git/commits/" in path:
            return httpx.Response(200, json={"tree": {"sha": "tree0"}})
        if path.endswith("/git/trees"):
            assert json.loads(request.content)["base_tree"] == "tree0"
            return httpx.Response(201, json={"sha": "tree1"})
        if path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "commit1"})
        if path.endswith("/git/refs"):
            return httpx.Response(201, json={})
        if path.endswith("/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/acme/app/pull/10"})
        raise AssertionError(path)

    real = httpx.Client
    monkeypatch.setattr(module.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    run = ReviewRun(input_mode=InputMode.PR, canonical_repo="https://github.com/acme/app/pull/1", head_sha="a" * 40)
    patch = Patch(
        run_id=run.id,
        finding_id="finding",
        edits=[FileEdit(path="app.py", old_content="1", replacement="2", rationale="fix")],
    )
    url = publish_fix(run, patch, tmp_path, "test-token")
    assert url.endswith("/10")
    assert ("POST", "/repos/acme/app/git/refs") in called


def test_fix_publication_rejects_changed_head(monkeypatch, tmp_path):
    import pytest

    import remediation.publish as module

    monkeypatch.setattr(module.GitHubMetadataFetcher, "fetch_pr_metadata", lambda *a: {"head_sha": "new"})
    run = ReviewRun(input_mode=InputMode.PR, canonical_repo="https://github.com/acme/app/pull/1", head_sha="old")
    with pytest.raises(ValueError, match="head changed"):
        publish_fix(run, Patch(run_id=run.id, finding_id="f"), tmp_path, "token")
