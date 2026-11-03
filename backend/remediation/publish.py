"""Explicit GitHub publication using atomic Git objects; never shells out with tokens."""

import base64
from pathlib import Path

import httpx

from ingestion.github import GitHubMetadataFetcher, parse_github_url
from remediation.patcher import apply_edits_to_text
from runtime_budget import remaining_time


def publish_fix(run, patch, workspace: Path, token: str):
    target = parse_github_url(run.canonical_repo)
    if not target.is_pr or not run.head_sha:
        raise ValueError("Fix publication requires a pinned PR")
    fetcher = GitHubMetadataFetcher(token)
    meta = fetcher.fetch_pr_metadata(target.owner, target.repo, target.pr_number)
    if meta["head_sha"] != run.head_sha:
        raise ValueError("PR head changed; rerun review")
    # Publish into the PR head repository; token must have explicit write permission.
    head = parse_github_url(meta["head_repo_url"])
    endpoint = f"https://api.github.com/repos/{head.owner}/{head.repo}"
    branch = f"proofline/fix/{patch.id}"
    with httpx.Client(headers=fetcher.headers, timeout=20) as client:

        def get(path, **kwargs):
            r = client.get(endpoint + path, timeout=remaining_time(20), **kwargs)
            r.raise_for_status()
            return r.json()

        def post(path, data):
            r = client.post(endpoint + path, json=data, timeout=remaining_time(20))
            r.raise_for_status()
            return r.json()

        existing = get("/pulls", params={"head": f"{head.owner}:{branch}", "state": "all"})
        if existing:
            return existing[0]["html_url"]
        tree_entries = []
        grouped = {}
        for edit in patch.edits:
            grouped.setdefault(edit.path, []).append(edit)
        for path, edits in grouped.items():
            local = (workspace / path).resolve()
            if not local.is_relative_to(workspace.resolve()) or path.startswith(("tests/", ".github/")):
                raise ValueError("Unsafe patch path")
            remote = get("/contents/" + path, params={"ref": run.head_sha})
            if remote.get("type") != "file":
                raise ValueError("Only regular files can be patched")
            source = base64.b64decode(remote["content"]).decode("utf-8")
            content, error = apply_edits_to_text(source, edits)
            if error:
                raise ValueError(error)
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "content": content})
        if not tree_entries:
            raise ValueError("Empty patch")
        ref = client.get(endpoint + "/git/ref/heads/" + branch, timeout=remaining_time(20))
        if ref.status_code == 404:
            parent = get("/git/commits/" + run.head_sha)
            tree = post("/git/trees", {"base_tree": parent["tree"]["sha"], "tree": tree_entries})
            commit = post(
                "/git/commits",
                {"message": f"Proofline repair {patch.id}", "tree": tree["sha"], "parents": [run.head_sha]},
            )
            post("/git/refs", {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        else:
            ref.raise_for_status()
            commit = get("/git/commits/" + ref.json()["object"]["sha"])
            if commit["message"] != f"Proofline repair {patch.id}":
                raise ValueError("Branch collision")
        return post(
            "/pulls",
            {
                "title": "Proofline: proposed repair",
                "head": branch,
                "base": meta["head_ref"],
                "body": f"Proposed patch for reviewed revision `{run.head_sha}`. Validation status: `{patch.status.value}`. Human review required.",
            },
        )["html_url"]
