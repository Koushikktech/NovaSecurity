from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import git

from graph import extract_code_for_finding
from nova import (
    NOVA_LITE_4B,
    get_call_log,
    nova_call_reasoning,
    reset_call_log,
)


_MAX_CONTEXT_FILES = 4
_MAX_CONTEXT_CHARS = 60000


def _remove_tree(path: str) -> None:
    if not os.path.exists(path):
        return

    def handle_remove_readonly(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except Exception:
            pass

    try:
        shutil.rmtree(path, onexc=handle_remove_readonly)
    except TypeError:
        shutil.rmtree(path, onerror=handle_remove_readonly)


def _load_prompt(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(__file__).parent / path
    with open(candidate, "r", encoding="utf-8") as handle:
        return handle.read()


def _slugify(value: str, fallback: str = "security-fix") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def _match_file(target: str, files: list[dict[str, Any]]) -> dict[str, Any] | None:
    target_norm = os.path.normpath(target)
    for file_info in files:
        candidate = os.path.normpath(file_info["relative_path"])
        if candidate == target_norm:
            return file_info
    for file_info in files:
        candidate = os.path.normpath(file_info["relative_path"])
        if candidate.endswith(target_norm) or target_norm.endswith(candidate):
            return file_info
    return None


def _extract_related_paths(finding: dict[str, Any]) -> list[str]:
    ordered: list[str] = []

    primary = str(finding.get("file", "") or "").strip()
    if primary:
        ordered.append(primary)

    for node_id in finding.get("path", []) or []:
        if not isinstance(node_id, str):
            continue
        candidates = [node_id]
        if "::" in node_id:
            candidates.extend(part.strip() for part in node_id.split("::"))

        for candidate in candidates:
            if (
                candidate
                and candidate not in {"SOURCE", "SINK", "SANITIZER"}
                and not re.fullmatch(r"L\d+", candidate)
                and candidate not in ordered
            ):
                ordered.append(candidate)

    return ordered


def select_fix_context_files(
    finding: dict[str, Any],
    files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered_paths = _extract_related_paths(finding)
    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    total_chars = 0

    for rel_path in ordered_paths[:_MAX_CONTEXT_FILES * 2]:
        file_info = _match_file(rel_path, files)
        if not file_info:
            continue

        normalized = os.path.normpath(str(file_info.get("relative_path", "") or ""))
        if not normalized or normalized in seen_paths:
            continue

        content = file_info.get("content", "")
        content_len = len(content)
        if selected and total_chars + content_len > _MAX_CONTEXT_CHARS:
            continue

        selected.append(file_info)
        seen_paths.add(normalized)
        total_chars += content_len
        if len(selected) >= _MAX_CONTEXT_FILES:
            break

    if not selected and ordered_paths:
        fallback = _match_file(ordered_paths[0], files)
        if fallback:
            selected.append(fallback)

    return selected


def prepare_fix_workspace(repo_path: str, scan_id: str, fix_id: str) -> str:
    repo_root = Path(repo_path).resolve()
    workspace_root = repo_root.parent / "_nova_fixes"
    workspace_root.mkdir(parents=True, exist_ok=True)

    workspace_path = workspace_root / f"{repo_root.name}-{scan_id}-{fix_id}"
    _remove_tree(str(workspace_path))
    shutil.copytree(repo_root, workspace_path)
    return str(workspace_path)


def cleanup_fix_workspace(workspace_path: str | None) -> None:
    if not workspace_path:
        return
    _remove_tree(workspace_path)


def detect_base_branch(repo: git.Repo) -> str:
    try:
        return repo.active_branch.name
    except Exception:
        pass

    try:
        origin_head = repo.git.symbolic_ref("refs/remotes/origin/HEAD")
        if origin_head:
            return origin_head.rsplit("/", 1)[-1]
    except Exception:
        pass

    for candidate in ("main", "master"):
        if candidate in repo.heads:
            return candidate

    if repo.heads:
        return repo.heads[0].name

    raise RuntimeError("Could not determine the repository base branch")


def checkout_fix_branch(repo: git.Repo, base_branch: str, branch_name: str) -> None:
    if base_branch in repo.heads:
        repo.git.checkout(base_branch)
    else:
        repo.git.checkout("-B", base_branch, f"origin/{base_branch}")

    repo.git.checkout("-B", branch_name)


def build_fix_prompt(
    repo_url: str,
    finding: dict[str, Any],
    codebase_summary: str,
    context_files: list[dict[str, Any]],
    relevant_code: str,
) -> str:
    prompt = _load_prompt("prompts/fix_vulnerability.txt")

    allowed_files = "\n".join(
        f"- {file_info['relative_path']}" for file_info in context_files
    ) or "- None"

    context_blocks = []
    for file_info in context_files:
        context_blocks.append(
            f"=== FILE: {file_info['relative_path']} ===\n{file_info['content']}"
        )

    return prompt.format(
        repo_url=repo_url,
        vulnerability_type=finding.get("vulnerability_type", "Unknown"),
        severity=finding.get("severity", "Unknown"),
        file=finding.get("file", ""),
        line=finding.get("line", 0),
        description=finding.get("description", ""),
        validation_status=finding.get("validation_status", "Unknown"),
        red_team_poc=finding.get("red_team_poc") or "None",
        blue_team_defense=finding.get("blue_team_defense") or "None",
        relevant_code=relevant_code or "No focused snippet available.",
        codebase_summary=(codebase_summary or "Unavailable.")[:10000],
        allowed_files=allowed_files,
        context_blocks="\n\n".join(context_blocks) or "No file context available.",
    )


def request_fix_plan(prompt: str) -> dict[str, Any] | None:
    reset_call_log()
    response = nova_call_reasoning(
        prompt,
        nova_model=NOVA_LITE_4B,
        reasoning_effort="high",
        max_tokens=50000,
    )
    if response is not None:
        return response

    attempts = get_call_log()
    last_attempt = attempts[-1] if attempts else {}
    error = str(last_attempt.get("error") or "").strip()
    if error:
        raise RuntimeError(
            f"NOVA remediation call failed after {len(attempts) or 1} attempt(s): {error}"
        )

    raw_response = str(last_attempt.get("raw_response") or "").strip()
    if raw_response:
        preview = raw_response.replace("\r", " ").replace("\n", " ")[:220]
        raise RuntimeError(
            "NOVA returned an unparseable remediation plan"
            f" after {len(attempts) or 1} attempt(s): {preview}"
        )

    raise RuntimeError("NOVA did not return a remediation plan")


def apply_fix_response(
    workspace_path: str,
    allowed_paths: set[str],
    response: dict[str, Any],
) -> list[str]:
    if not response:
        raise ValueError("NOVA did not return a remediation plan")

    if not response.get("can_fix", True):
        reason = response.get("reason") or "NOVA could not produce a safe fix"
        raise ValueError(str(reason))

    updates = response.get("files")
    if not isinstance(updates, list) or not updates:
        raise ValueError("NOVA did not return any updated files")

    workspace_root = Path(workspace_path).resolve()
    changed_files: list[str] = []

    for item in updates:
        if not isinstance(item, dict):
            continue

        rel_path = str(item.get("path", "") or "").strip()
        if not rel_path:
            continue

        rel_path = rel_path.replace("/", os.sep).replace("\\", os.sep)
        normalized = os.path.normpath(rel_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            raise ValueError(f"Unsafe output path returned: {rel_path}")

        if normalized not in allowed_paths:
            raise ValueError(
                f"NOVA attempted to modify {rel_path}, which was outside the allowed file set"
            )

        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError(f"NOVA did not return valid file content for {rel_path}")

        destination = (workspace_root / normalized).resolve()
        if workspace_root not in destination.parents and destination != workspace_root:
            raise ValueError(f"Resolved path escaped the workspace: {rel_path}")

        existing = ""
        if destination.exists():
            existing = destination.read_text(encoding="utf-8", errors="replace")

        if existing == content:
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        changed_files.append(normalized.replace("\\", "/"))

    if not changed_files:
        raise ValueError("The remediation plan did not change any file contents")

    return changed_files


def commit_fix(repo: git.Repo, commit_message: str) -> str:
    repo.git.add(A=True)
    if not repo.is_dirty(untracked_files=True):
        raise ValueError("No git changes were produced by the remediation plan")

    commit = repo.index.commit(commit_message)
    return commit.hexsha


def generate_diff(repo: git.Repo) -> str:
    return repo.git.show("HEAD", "--format=", "--unified=3")


def build_compare_url(
    repo_url: str,
    base_branch: str,
    branch_name: str,
    title: str,
    body: str,
) -> str | None:
    match = re.search(
        r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$",
        repo_url.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None

    owner = match.group("owner")
    repo = match.group("repo")
    return (
        f"https://github.com/{owner}/{repo}/compare/"
        f"{quote_plus(base_branch)}...{quote_plus(branch_name)}"
        f"?expand=1&quick_pull=1&title={quote_plus(title)}&body={quote_plus(body)}"
    )


def create_pr_metadata(
    response: dict[str, Any],
    finding: dict[str, Any],
    branch_name: str,
) -> tuple[str, str]:
    title = str(response.get("pr_title") or "").strip()
    if not title:
        vuln = finding.get("vulnerability_type") or "security issue"
        title = f"fix: remediate {vuln.lower()}"

    body = str(response.get("pr_body") or "").strip()
    if not body:
        body = (
            "## Summary\n"
            f"- Fixes `{finding.get('vulnerability_type', 'security issue')}` in `{finding.get('file', 'unknown')}`\n"
            f"- Generated by NOVA on branch `{branch_name}`\n"
        )

    return title, body


def attempt_create_github_pr(
    workspace_path: str,
    branch_name: str,
    base_branch: str,
    title: str,
    body: str,
    compare_url: str | None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"

    push = subprocess.run(
        ["git", "push", "-u", "origin", branch_name],
        cwd=workspace_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if push.returncode != 0:
        raise RuntimeError((push.stderr or push.stdout).strip() or "git push failed")

    gh_path = shutil.which("gh")
    if not gh_path:
        if compare_url:
            return {
                "status": "compare_ready",
                "url": compare_url,
                "error": "GitHub CLI is not installed, so NOVA pushed the branch and prepared the compare page instead.",
            }
        raise RuntimeError("GitHub CLI is not installed on the server")

    pr = subprocess.run(
        [
            gh_path,
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--head",
            branch_name,
            "--base",
            base_branch,
        ],
        cwd=workspace_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if pr.returncode != 0:
        error = (pr.stderr or pr.stdout).strip() or "gh pr create failed"
        if compare_url:
            return {
                "status": "compare_ready",
                "url": compare_url,
                "error": error,
            }
        raise RuntimeError(error)

    url = None
    for line in reversed(pr.stdout.splitlines()):
        line = line.strip()
        if line.startswith("http://") or line.startswith("https://"):
            url = line
            break

    return {
        "status": "created",
        "url": url,
        "error": None,
    }


def build_fix_artifacts(
    repo_url: str,
    finding: dict[str, Any],
    files: list[dict[str, Any]],
    codebase_summary: str,
    scan_id: str,
    fix_id: str,
    repo_path: str,
) -> dict[str, Any]:
    workspace_path = prepare_fix_workspace(repo_path, scan_id, fix_id)
    repo = git.Repo(workspace_path)
    base_branch = detect_base_branch(repo)

    slug = _slugify(finding.get("vulnerability_type", "security-fix"))
    branch_name = f"nova/{slug}-{fix_id}"
    checkout_fix_branch(repo, base_branch, branch_name)

    context_files = select_fix_context_files(finding, files)
    if not context_files:
        raise ValueError("Could not locate any file context for the selected finding")

    relevant_code = extract_code_for_finding(finding, files)
    prompt = build_fix_prompt(
        repo_url=repo_url,
        finding=finding,
        codebase_summary=codebase_summary,
        context_files=context_files,
        relevant_code=relevant_code,
    )
    response = request_fix_plan(prompt)
    allowed_paths = {
        os.path.normpath(file_info["relative_path"]) for file_info in context_files
    }
    changed_files = apply_fix_response(workspace_path, allowed_paths, response or {})

    pr_title, pr_body = create_pr_metadata(response or {}, finding, branch_name)
    commit_sha = commit_fix(repo, pr_title)
    diff = generate_diff(repo)
    compare_url = build_compare_url(
        repo_url=repo_url,
        base_branch=base_branch,
        branch_name=branch_name,
        title=pr_title,
        body=pr_body,
    )

    return {
        "workspace_path": workspace_path,
        "base_branch": base_branch,
        "branch_name": branch_name,
        "changed_files": changed_files,
        "diff": diff,
        "summary": response.get("summary") if response else None,
        "rationale": response.get("rationale") if response else None,
        "tests_to_run": response.get("tests_to_run") if response else [],
        "pr_title": pr_title,
        "pr_body": pr_body,
        "compare_url": compare_url,
        "commit_sha": commit_sha,
    }
