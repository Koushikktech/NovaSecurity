"""Resolve review scope once, pin Git revisions, and construct safe source snapshots."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from github_connection import review_token
from ingestion.github import GitHubMetadataFetcher, parse_github_url
from ingestion.repo import Workspace
from runtime_budget import remaining_time

Mode = Literal["auto", "project", "commit", "compare", "pr", "working"]


class TargetRequest(BaseModel):
    mode: Mode = "auto"
    revision: str | None = None
    base: str | None = None
    head: str | None = None
    depth: Literal["quick", "deep"] = "quick"


def validate_ref(ref: str):
    if not ref or len(ref) > 200 or ref.startswith("-") or any(c in ref for c in ("\x00", "\n", "\r")):
        raise ValueError("Invalid Git revision")
    return ref


def git(directory: Path | None, *args: str, input_bytes: bytes | None = None):
    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]
    credential = review_token.get()
    if credential:
        header = base64.b64encode(("x-access-token:" + credential).encode()).decode()
        # Environment config avoids putting credentials in argv, URLs or Git config.
        credential_env = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraHeader",
            "GIT_CONFIG_VALUE_0": "Authorization: Basic " + header,
        }
    else:
        credential_env = {}
    if directory:
        command += ["-C", str(directory)]
    result = subprocess.run(
        command + list(args),
        input=input_bytes,
        capture_output=True,
        timeout=remaining_time(90),
        env={**os.environ, **credential_env, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"},
    )
    if result.returncode:
        raise ValueError("Git could not resolve or read the requested repository/revision")
    return result.stdout


def resolve(repo: Path, ref: str):
    validate_ref(ref)
    try:
        return git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    except ValueError:
        return (
            git(repo, "rev-parse", "--verify", "--end-of-options", "refs/remotes/origin/" + ref + "^{commit}")
            .decode()
            .strip()
        )


def export_snapshot(repo: Path, sha: str, dest: Path, workspace=None):
    """Read regular blobs without checkout hooks, submodules, or symlink traversal."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    total = 0
    selected = []
    for record in git(repo, "ls-tree", "-rlz", sha).split(b"\0"):
        if not record:
            continue
        meta, raw = record.split(b"\t", 1)
        mode, kind, blob, size_raw = meta.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            continue
        path = raw.decode("utf-8", errors="strict")
        from ingestion.source_policy import sensitive_source_path

        if sensitive_source_path(path):
            if workspace:
                workspace.omit(path, "credential path", "base" if dest == workspace.base_dir else "head")
            continue
        target = (dest / path).resolve()
        if not target.is_relative_to(dest.resolve()):
            raise ValueError("Unsafe Git path")
        if any(
            part in {".git", ".venv", "node_modules", "vendor", "dist", "build", "__pycache__"}
            for part in Path(path).parts
        ):
            continue
        size = int(size_raw)
        if size > 500 * 1024:
            continue
        total += size
        if total > 20 * 1024 * 1024 or len(selected) >= 2000:
            raise ValueError("Repository snapshot exceeds source inventory limits")
        selected.append((target, blob, size))
    if not selected:
        return
    output = git(repo, "cat-file", "--batch", input_bytes=b"\n".join(blob for _, blob, _ in selected) + b"\n")
    offset = 0
    for target, blob, size in selected:
        newline = output.index(b"\n", offset)
        header = output[offset:newline].split()
        if header != [blob, b"blob", str(size).encode()]:
            raise ValueError("Invalid Git blob batch response")
        content = output[newline + 1 : newline + 1 + size]
        offset = newline + size + 2
        if b"\0" in content:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def ingest_target(workspace: Workspace, url: str, request: TargetRequest, local_dir: str | None, token: str):
    parsed = None if local_dir else parse_github_url(url)
    mode = request.mode
    if mode == "auto":
        mode = (
            "pr"
            if parsed and parsed.is_pr
            else "commit"
            if parsed and parsed.kind == "commit"
            else "compare"
            if request.base or (parsed and parsed.kind == "compare")
            else "project"
        )
    if mode == "pr" and (not parsed or not parsed.is_pr):
        raise ValueError("PR mode requires a GitHub pull-request URL")
    if parsed and parsed.is_pr and mode != "pr":
        raise ValueError("Use PR mode for a pull-request URL")
    if mode == "working" and not local_dir:
        raise ValueError("Working-tree mode is available through the local CLI only")
    canonical = (
        parsed.repository_url
        if parsed
        else (url if url in {"Uploaded folder", "Controlled reviewer example"} else str(Path(local_dir).resolve()))
    )
    metadata = {
        "mode": mode,
        "depth": request.depth,
        "repository": canonical,
        "input": url,
        "comparison": "snapshot" if mode == "project" else "exact base to head",
        "source_exclusions": workspace.omitted_files,
    }
    if local_dir and mode == "project" and not request.revision and not request.head:
        workspace.clone_or_checkout(local_dir, target="head")
        files = workspace.list_files("head")
        metadata.update(
            {
                "head_sha": None,
                "base_sha": None,
                "snapshot_id": hashlib.sha256(
                    "".join(
                        f["relative_path"] + "\0" + f["content"]
                        for f in sorted(files, key=lambda f: f["relative_path"])
                    ).encode()
                ).hexdigest(),
                "revision_label": "Local files (including uncommitted changes)",
            }
        )
        return metadata, files, []
    repo = Path(local_dir).resolve() if local_dir else workspace.root_dir / "git"
    if not local_dir:
        if repo.exists():
            shutil.rmtree(repo)
        git(None, "clone", "--no-checkout", "--no-hardlinks", "--", canonical + ".git", str(repo))
    base = None
    if mode == "pr":
        pr = GitHubMetadataFetcher(token).fetch_pr_metadata(parsed.owner, parsed.repo, parsed.pr_number)
        # Fork head is fetched explicitly into the trusted clone.
        parse_github_url(pr["head_repo_url"])
        git(repo, "fetch", "--no-tags", pr["head_repo_url"], pr["head_sha"])
        head = resolve(repo, pr["head_sha"])
        git(repo, "fetch", "--no-tags", pr["base_repo_url"], pr["base_sha"])
        base = git(repo, "merge-base", pr["base_sha"], head).decode().strip()
        metadata.update(
            {
                "pr_number": parsed.pr_number,
                "pr_title": pr["title"],
                "base_tip_sha": pr["base_sha"],
                "comparison": "PR merge base to head",
            }
        )
    elif mode == "commit":
        ref = request.revision or request.head or (parsed.revision if parsed else None)
        if not ref:
            raise ValueError("Commit mode requires a commit URL or revision")
        head = resolve(repo, ref)
        parents = git(repo, "rev-list", "--parents", "-n", "1", head).decode().split()[1:]
        base = parents[0] if parents else None
        metadata["comparison"] = "First parent to commit" if parents else "Initial commit against empty tree"
        metadata["merge_commit"] = len(parents) > 1
    elif mode == "compare":
        base_ref = request.base or (parsed.base_ref if parsed else None)
        head_ref = request.head or (parsed.head_ref if parsed else None)
        if not base_ref or not head_ref:
            raise ValueError("Comparison mode requires both base and head revisions")
        base = resolve(repo, base_ref)
        head = resolve(repo, head_ref)
        if parsed and parsed.kind == "compare" and parsed.merge_base:
            base = git(repo, "merge-base", base, head).decode().strip()
            metadata["comparison"] = "GitHub comparison merge base to head"
    elif mode == "working":
        head = resolve(repo, "HEAD")
        base = head
        export_snapshot(repo, base, workspace.base_dir, workspace)
        workspace.clone_or_checkout(local_dir, target="head")
        files = workspace.list_files("head")
        metadata.update(
            {
                "base_sha": base,
                "head_sha": None,
                "revision_label": "Working tree vs HEAD",
                "comparison": "HEAD to local files; includes untracked supported files",
            }
        )
        return metadata, files, workspace.list_files("base")
    else:
        head = resolve(repo, request.revision or request.head or (parsed.revision if parsed else None) or "HEAD")
    export_snapshot(repo, head, workspace.head_dir, workspace)
    if base:
        export_snapshot(repo, base, workspace.base_dir, workspace)
    metadata.update(
        {
            "base_sha": base,
            "head_sha": head,
            "revision_label": request.revision or (parsed.revision if parsed else None) or head,
        }
    )
    return metadata, workspace.list_files("head"), workspace.list_files("base") if base else []
