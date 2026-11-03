
import git
import pytest
from fastapi.testclient import TestClient

from api import app
from config import settings
from ingestion.repo import Workspace
from ingestion.source_policy import sensitive_source_path
from ingestion.targets import export_snapshot
from review.snapshots import load_snapshot, save_snapshot


def test_local_project_containing_outputs_copies_only_source_and_preserves_original(tmp_path, monkeypatch):
    source = tmp_path / "project"
    source.mkdir()
    (source / "app.py").write_text("value = 1\n")
    (source / ".env").write_text("CUSTOM_SECRET=never-copy-this\n")
    (source / ".env.production").write_text("CUSTOM_SECRET=never-copy-this\n")
    (source / ".env.example").write_text("CUSTOM_SECRET=replace-me\n")
    (source / "huge.py").write_bytes(b"x" * (501 * 1024))
    (source / ".ssh").mkdir()
    (source / ".ssh/config").write_text("private host configuration")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside source")
    (source / "link.py").symlink_to(outside)
    workspaces = source / "outputs/workspaces"
    artifacts = source / "outputs/artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "prior.json").write_text("private prior review")
    database = source / "outputs/reviews.db"
    database.write_text("private database")
    monkeypatch.setattr(settings, "workspace_dir", workspaces)
    monkeypatch.setattr(settings, "artifact_dir", artifacts)
    monkeypatch.setattr(settings, "database_url", "sqlite:///" + str(database))
    workspace = Workspace("current")
    workspace.initialize()
    workspace.clone_or_checkout(str(source))
    copied = {str(p.relative_to(workspace.head_dir)) for p in workspace.head_dir.rglob("*") if p.is_file()}
    assert copied == {"app.py", ".env.example"}
    assert (source / ".env").read_text().startswith("CUSTOM_SECRET")
    assert (artifacts / "prior.json").exists() and database.exists()
    omissions = {(row["path"], row["reason"]) for row in workspace.omitted_files}
    assert (".env", "credential path") in omissions
    assert ("outputs/workspaces", "configured review output") in omissions
    assert ("outputs/artifacts", "configured review output") in omissions
    assert ("outputs/reviews.db", "configured review output") in omissions
    assert ("huge.py", "file exceeds 500 KiB") in omissions
    assert ("link.py", "symlink") in omissions


def test_same_source_destination_is_rejected_before_removing_source(tmp_path):
    workspace = Workspace("run", base_dir=tmp_path)
    workspace.initialize()
    original = workspace.head_dir / "app.py"
    original.write_text("do_not_delete = True\n")
    with pytest.raises(ValueError, match="Source cannot be the destination"):
        workspace.clone_or_checkout(str(workspace.head_dir))
    assert original.read_text() == "do_not_delete = True\n"


def test_git_export_and_diff_never_admit_credential_paths(tmp_path):
    source = tmp_path / "repo"
    repo = git.Repo.init(source)
    (source / "app.py").write_text("value = 1\n")
    (source / ".env").write_text("UNRECOGNIZED=private-base\n")
    (source / ".env.example").write_text("UNRECOGNIZED=placeholder\n")
    repo.index.add(["."])
    actor = git.Actor("Fixture", "fixture@example.invalid")
    base = repo.index.commit("base", author=actor, committer=actor).hexsha
    (source / "app.py").write_text("value = 2\n")
    (source / ".env").write_text("UNRECOGNIZED=private-head\n")
    repo.index.add(["."])
    head = repo.index.commit("head", author=actor, committer=actor).hexsha
    workspace = Workspace("run", base_dir=tmp_path / "workspaces")
    export_snapshot(source, base, workspace.base_dir, workspace)
    export_snapshot(source, head, workspace.head_dir, workspace)
    assert not (workspace.head_dir / ".env").exists()
    assert (workspace.head_dir / ".env.example").exists()
    diff = workspace.compute_git_diff()
    assert "private-base" not in diff and "private-head" not in diff
    assert "+value = 2" in diff
    assert {row["side"] for row in workspace.omitted_files if row["path"] == ".env"} == {"base", "head"}


def test_unsafe_historic_checkpoint_requires_fresh_ingestion(tmp_path):
    save_snapshot(tmp_path, {}, [{"relative_path": ".env", "content": "secret"}], [], "")
    with pytest.raises(ValueError, match="excluded credential path"):
        load_snapshot(tmp_path)


def test_cloud_credential_upload_is_rejected_before_scheduling():
    response = TestClient(app).post(
        "/api/v1/reviews/folder", json={"files": [{"path": ".aws/config.json", "content": "{}"}]}
    )
    assert response.status_code == 422 and "Credential files" in response.json()["detail"]


def test_sensitive_path_policy_retains_templates_and_ordinary_source():
    for path in [
        "backend/.env",
        ".env.production",
        "keys/server.PEM",
        "settings/.netrc",
        ".aws/config.json",
        "application_default_credentials.json",
    ]:
        assert sensitive_source_path(path)
    for path in ["backend/.env.example", ".env.sample", ".env.template", "environment.py", "settings.json"]:
        assert not sensitive_source_path(path)
