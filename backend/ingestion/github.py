from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from runtime_budget import remaining_time


class ParsedGitHubTarget(BaseModel):
    is_pr: bool
    owner: str
    repo: str
    pr_number: int | None = None
    canonical_url: str
    repository_url: str = ""
    kind: str = "repo"
    revision: str | None = None
    base_ref: str | None = None
    head_ref: str | None = None
    merge_base: bool = False


def parse_github_url(url: str) -> ParsedGitHubTarget:
    """Parse and validate GitHub repository or pull request URL."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)

    # Validate scheme and host
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid URL scheme: only http and https are allowed")

    host = parsed.netloc.lower()
    if "@" in host:
        raise ValueError("URLs with embedded credentials are not allowed")

    # Only allow github.com (or localhost/127.0.0.1 for local integration tests)
    allowed_hosts = {"github.com", "www.github.com"}
    host_without_port = host.split(":")[0]
    if host_without_port not in allowed_hosts:
        raise ValueError(f"Host '{host}' is not allowed. Only public GitHub URLs are supported.")

    from urllib.parse import unquote

    parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
    if parsed.port not in (None, 443) or parsed.query or parsed.fragment:
        raise ValueError("Ports, queries and fragments are not supported")
    if len(parts) < 2:
        raise ValueError("URL must include owner and repository name")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if not all(re.fullmatch(r"[a-zA-Z0-9_.-]+", p) and p not in {".", ".."} for p in (owner, repo)):
        raise ValueError("Invalid owner/repository name")
    repository = f"https://github.com/{owner}/{repo}"
    common = dict(owner=owner, repo=repo, repository_url=repository)
    if len(parts) == 2:
        return ParsedGitHubTarget(is_pr=False, canonical_url=repository, **common)
    if len(parts) == 4 and parts[2] == "pull":
        if not parts[3].isdigit() or int(parts[3]) < 1:
            raise ValueError("Invalid PR number")
        return ParsedGitHubTarget(
            is_pr=True, kind="pr", pr_number=int(parts[3]), canonical_url=repository + "/pull/" + parts[3], **common
        )
    if len(parts) == 4 and parts[2] == "commit" and re.fullmatch(r"[0-9a-fA-F]{7,64}", parts[3]):
        return ParsedGitHubTarget(
            is_pr=False, kind="commit", revision=parts[3], canonical_url=repository + "/commit/" + parts[3], **common
        )
    if len(parts) >= 4 and parts[2] == "tree":
        revision = "/".join(parts[3:])
        return ParsedGitHubTarget(
            is_pr=False, kind="tree", revision=revision, canonical_url=repository + "/tree/" + revision, **common
        )
    if len(parts) >= 4 and parts[2] == "compare":
        comparison = "/".join(parts[3:])
        if "..." not in comparison:
            raise ValueError("Comparison URL must contain base...head")
        base, head = comparison.split("...", 1)
        if not base or not head or ":" in base + head:
            raise ValueError("Cross-fork comparison URLs require a PR URL instead")
        return ParsedGitHubTarget(
            is_pr=False,
            kind="compare",
            base_ref=base,
            head_ref=head,
            merge_base=True,
            canonical_url=repository + "/compare/" + comparison,
            **common,
        )
    raise ValueError("Use a repository, branch/tree, commit, comparison or pull-request URL")


class GitHubMetadataFetcher:
    def __init__(self, token: str | None = None):
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Proofline-Code-Reviewer/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def fetch_pr_metadata(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR metadata including base/head SHAs and repository info."""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            with httpx.Client(timeout=remaining_time(15.0), headers=self.headers) as client:
                res = client.get(api_url)
                if res.status_code == 404:
                    raise ValueError(f"Pull request #{pr_number} not found in {owner}/{repo}")
                if res.status_code == 403:
                    raise ValueError("GitHub API rate limit exceeded or access forbidden")
                res.raise_for_status()
                data = res.json()

                return {
                    "pr_number": pr_number,
                    "title": data.get("title", ""),
                    "body": data.get("body", ""),
                    "state": data.get("state", "open"),
                    "base_ref": data["base"]["ref"],
                    "base_sha": data["base"]["sha"],
                    "base_repo_url": data["base"]["repo"]["clone_url"],
                    "head_ref": data["head"]["ref"],
                    "head_sha": data["head"]["sha"],
                    "head_repo_url": data["head"]["repo"]["clone_url"],
                    "changed_files_count": data.get("changed_files", 0),
                    "additions": data.get("additions", 0),
                    "deletions": data.get("deletions", 0),
                }
        except httpx.RequestError as exc:
            raise ValueError(f"GitHub API request failed: {exc}")
