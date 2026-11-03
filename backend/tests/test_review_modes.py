import git
import pytest

from ingestion.github import parse_github_url
from ingestion.repo import Workspace
from ingestion.targets import TargetRequest, ingest_target
from providers.fake import FakeLLMProvider
from providers.unavailable import UnavailableProvider
from review.orchestrator import ReviewOrchestrator
from review.scope import project_batches, review_project
from schemas.provider import ReviewCandidatesResult


@pytest.fixture
def history(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    repo = git.Repo.init(root)
    actor = git.Actor("Fixture", "fixture@example.invalid")
    (root / "service.py").write_text("def load(page):\n    return page\n")
    (root / "caller.py").write_text("from service import load\nload(1)\n")
    repo.index.add(["."])
    first = repo.index.commit("root", author=actor, committer=actor).hexsha
    (root / "service.py").write_text("def load(page, size):\n    return page\n")
    repo.index.add(["."])
    second = repo.index.commit("change", author=actor, committer=actor).hexsha
    repo.create_tag("v1", first)
    return root, repo, first, second


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://github.com/acme/app", "repo"),
        ("https://github.com/acme/app/pull/4", "pr"),
        ("https://github.com/acme/app/commit/abcdef1", "commit"),
        ("https://github.com/acme/app/tree/feature/pagination", "tree"),
        ("https://github.com/acme/app/compare/main...feature/pagination", "compare"),
    ],
)
def test_target_urls(url, kind):
    result = parse_github_url(url)
    assert result.kind == kind
    assert result.repository_url == "https://github.com/acme/app"


def test_commit_and_root_commit_scopes(history, tmp_path):
    root, _, first, second = history
    for revision, base in [(first, None), (second, first)]:
        workspace = Workspace("case-" + revision, base_dir=tmp_path / "jobs")
        workspace.initialize()
        meta, head, before = ingest_target(
            workspace, str(root), TargetRequest(mode="commit", revision=revision), str(root), ""
        )
        assert meta["head_sha"] == revision and meta["base_sha"] == base
        assert bool(before) == bool(base)
        assert head
        assert ".git" not in workspace.compute_git_diff()


def test_whole_project_has_no_artificial_changes(history):
    root, _, first, _ = history
    run, findings = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
        str(root), local_dir=str(root), mode="project", revision="v1", static_only=True
    )
    assert run.status.value == "completed", run.errors
    assert run.head_sha == first and run.base_sha is None
    assert run.review_mode == "project"
    assert run.coverage["diff"] == "" and run.coverage["changed_files"] == []
    assert "service.py" in run.coverage["source_files"]


def test_commit_and_compare_find_changed_callers(history):
    root, _, first, second = history
    for options in [dict(mode="commit", revision=second), dict(mode="compare", base_sha=first, head_sha=second)]:
        run, findings = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
            str(root), local_dir=str(root), static_only=True, **options
        )
        assert run.status.value == "completed", run.errors
        assert run.base_sha == first and run.head_sha == second
        assert any(f.rule_id == "python:changed-signature" for f in findings)


def test_working_tree_includes_untracked_files_without_mutating_repo(history):
    root, repo, _, second = history
    (root / "untracked.ts").write_text("export const value = 2;\n")
    (root / "service.py").write_text("def load(page):\n    return page\n")
    run, _ = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
        str(root), local_dir=str(root), mode="working", static_only=True
    )
    assert run.base_sha == second and run.head_sha is None
    assert set(run.coverage["changed_files"]) == {"service.py", "untracked.ts"}
    assert repo.head.commit.hexsha == second
    assert "size" not in (root / "service.py").read_text()


def test_invalid_revision_is_explicit_failure(history):
    root, _, _, _ = history
    run, _ = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
        str(root), local_dir=str(root), mode="commit", revision="does-not-exist", static_only=True
    )
    assert run.status.value == "failed"


def test_deep_coverage_accounts_for_budget_and_failed_batches():
    files = [{"relative_path": f"m{i}.py", "content": "value = " + str(i) + "\n"} for i in range(5)]
    batches, omitted = project_batches(files, "deep", 40, 2)
    assert len(batches) == 2 and len(omitted) == 3
    provider = FakeLLMProvider()
    provider.register_response("project_review", ReviewCandidatesResult(review_summary="Source assessed"))
    result, coverage = review_project(provider, "r", files, "deep", 40, 2, "Review")
    assert result.success and len(coverage["reviewed_files"]) == 2 and len(coverage["omitted_files"]) == 3


def test_api_rejects_invalid_modes_and_upload_traversal():
    from fastapi.testclient import TestClient

    from api import app

    client = TestClient(app)
    assert (
        client.post("/api/v1/reviews", json={"repo_url": "https://github.com/acme/app", "mode": "commit"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/reviews", json={"repo_url": "https://github.com/acme/app", "mode": "compare", "base_sha": "main"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v1/reviews/folder", json={"files": [{"path": "../escape.py", "content": "x=1"}]}).status_code
        == 422
    )


def test_browser_folder_review_is_real_snapshot(monkeypatch):
    from fastapi.testclient import TestClient

    import routes.v1 as routes
    from api import app

    monkeypatch.setattr(routes, "GeminiProvider", UnavailableProvider)
    client = TestClient(app)
    response = client.post(
        "/api/v1/reviews/folder",
        json={
            "files": [
                {
                    "path": "src/app.ts",
                    "content": "export async function run(items: string[]) { items.forEach(async x => { await fetch(x); }); }",
                }
            ]
        },
    )
    assert response.status_code == 202, response.text
    run = client.get("/api/v1/reviews/" + response.json()["run_id"]).json()
    assert run["review_mode"] == "project" and run["head_sha"] is None
    assert run["coverage"]["target"]["snapshot_id"]
    assert run["coverage"]["diff"] == ""
    findings = client.get("/api/v1/reviews/" + run["id"] + "/findings").json()
    assert any(f["rule_id"] == "js:async-foreach" for f in findings)


def test_remote_branch_snapshot_resolves_origin_ref(history, tmp_path, monkeypatch):
    import ingestion.targets as targets

    root, repo, first, _ = history
    repo.create_head("feature/pagination", first)
    real_git = targets.git

    def local_remote(directory, *args, **kwargs):
        if args and args[0] == "clone":
            args = (*args[:-2], str(root), args[-1])
        return real_git(directory, *args, **kwargs)

    monkeypatch.setattr(targets, "git", local_remote)
    workspace = Workspace("remote", base_dir=tmp_path / "jobs")
    workspace.initialize()
    meta, files, _ = ingest_target(
        workspace, "https://github.com/acme/app/tree/feature/pagination", TargetRequest(), None, ""
    )
    assert meta["head_sha"] == first
    assert any(f["relative_path"] == "service.py" for f in files)


def test_failed_deep_batch_preserves_partial_results():
    from schemas.provider import ProviderResponse

    class Mixed(FakeLLMProvider):
        n = 0

        def generate_structured(self, *args):
            self.n += 1
            if self.n == 1:
                return ProviderResponse(
                    success=True, model_id="fake", data=ReviewCandidatesResult(review_summary="Batch complete")
                )
            return ProviderResponse(success=False, model_id="fake", error="Timed out")

    files = [{"relative_path": f"m{i}.py", "content": "value = 1\n"} for i in range(2)]
    response, coverage = review_project(Mixed(), "r", files, "deep", 40, 2, "Review")
    assert not response.success
    assert response.data.review_summary.strip() == "Batch complete"
    assert coverage["reviewed_files"] == ["m0.py"] and coverage["omitted_files"] == ["m1.py"]


def test_merge_commit_uses_first_parent(history, tmp_path):
    root, repo, first, second = history
    actor = git.Actor("Fixture", "fixture@example.invalid")
    merged = repo.index.commit(
        "merge fixture", parent_commits=[repo.commit(second), repo.commit(first)], author=actor, committer=actor
    ).hexsha
    workspace = Workspace("merge", base_dir=tmp_path / "jobs")
    workspace.initialize()
    meta, _, _ = ingest_target(workspace, str(root), TargetRequest(mode="commit", revision=merged), str(root), "")
    assert meta["base_sha"] == second and meta["head_sha"] == merged
    assert meta["merge_commit"] is True


def test_python_index_does_not_resolve_same_name_in_wrong_module():
    from analysis.graph_context import CodebaseGraph

    files = [
        {"relative_path": "caller.py", "content": "from correct import load\ndef run():\n    return load()\n"},
        {"relative_path": "wrong.py", "content": "def load():\n    return 0\n"},
        {"relative_path": "correct.py", "content": "def load():\n    return 1\n"},
    ]
    graph = CodebaseGraph()
    graph.build_from_files(files)
    assert graph.graph.has_edge("caller.py::run", "correct.py::load")
    assert not graph.graph.has_edge("caller.py::run", "wrong.py::load")


def test_large_python_index_exits_cleanly_without_native_parser():
    import subprocess
    import sys

    code = """
from pathlib import Path
from analysis.graph_context import CodebaseGraph
import sys
files=[{'relative_path':p.name,'content':p.read_text()} for p in Path('backend').glob('*.py')]
g=CodebaseGraph();g.build_from_files(files)
assert len(g.symbol_lookup)>20
assert 'tree_sitter' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
