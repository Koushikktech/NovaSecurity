from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Any

import git

from config import settings
from ingestion.source_policy import sensitive_source_path


def _safe_rmtree(target: str | Path) -> None:
    p = str(target)
    if not os.path.exists(p):
        return

    def handle_remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    try:
        shutil.rmtree(p, onexc=handle_remove_readonly)
    except TypeError:
        shutil.rmtree(p, onerror=handle_remove_readonly)


SKIP_DIRS = {
    ".git",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "egg-info",
    ".next",
    ".nuxt",
    ".cache",
    ".ruff_cache",
    ".vercel",
}

IGNORED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


class Workspace:
    def __init__(self, run_id: str, base_dir: Path | None = None):
        self.omitted_files = []
        self.run_id = run_id
        self.root_dir = (base_dir or settings.workspace_dir) / run_id
        self.head_dir = self.root_dir / "head"
        self.base_dir = self.root_dir / "base"
        self.patch_dir = self.root_dir / "patch"

    def omit(self, relative_path: str, reason: str, side: str = "head") -> None:
        record = {"path": relative_path, "reason": reason, "side": side}
        if len(self.omitted_files) < 2000 and record not in self.omitted_files:
            self.omitted_files.append(record)

    def initialize(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.head_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.patch_dir.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        _safe_rmtree(self.root_dir)

    def resolve_safe_path(self, relative_path: str, target: str = "head") -> Path:
        """Resolve a relative path safely inside the target directory, preventing path traversal."""
        base_path = self.head_dir if target == "head" else (self.base_dir if target == "base" else self.patch_dir)
        clean_rel = os.path.normpath(relative_path).lstrip("/")
        if clean_rel.startswith("..") or "/../" in clean_rel:
            raise ValueError(f"Path traversal detected: {relative_path}")

        full_path = (base_path / clean_rel).resolve()
        # Ensure resolved path is inside base_path
        if not full_path.is_relative_to(base_path.resolve()):
            raise ValueError(f"Resolved path outside workspace: {relative_path}")

        # Check for symlink escaping outside workspace
        if os.path.islink(full_path):
            real_target = full_path.resolve()
            if not str(real_target).startswith(str(base_path.resolve())):
                raise ValueError(f"Symlink escapes workspace: {relative_path}")

        return full_path

    def clone_or_checkout(
        self,
        repo_url: str,
        commit_sha: str | None = None,
        target: str = "head",
        depth: int = 1,
    ) -> Path:
        """Clone a remote repository or copy a local repository to target dir."""
        dest = self.head_dir if target == "head" else self.base_dir
        source = Path(repo_url).resolve() if Path(repo_url).is_dir() else None
        if source and (source == dest.resolve() or source.is_relative_to(dest.resolve())):
            raise ValueError("Source cannot be the destination workspace or one of its descendants")
        if dest.exists():
            _safe_rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        # Check if local path
        if os.path.exists(repo_url) and os.path.isdir(repo_url):
            # Never copy configured outputs back into a project containing its workspace.
            output_roots = [
                root.resolve()
                for root in (settings.workspace_dir, settings.artifact_dir, self.root_dir, dest)
                if root.resolve() != source and root.resolve().is_relative_to(source)
            ]
            if settings.database_url.startswith("sqlite:///"):
                database = Path(settings.database_url.removeprefix("sqlite:///")).resolve()
                output_roots.extend(
                    path
                    for path in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm"))
                    if path != source and path.is_relative_to(source)
                )
            copied_count = 0
            copied_size = 0

            def ignore_local(directory, names):
                nonlocal copied_count, copied_size
                ignored = []
                for name in names:
                    full = Path(directory) / name
                    relative = full.relative_to(source).as_posix()
                    reason = None
                    if name in SKIP_DIRS:
                        reason = "generated or dependency directory"
                    elif sensitive_source_path(relative):
                        reason = "credential path"
                    elif any(full.is_relative_to(root) for root in output_roots):
                        reason = "configured review output"
                    elif full.is_symlink():
                        reason = "symlink"
                    elif full.is_dir() and name.startswith("."):
                        reason = "hidden or generated directory"
                    elif not full.is_dir():
                        if not full.is_file():
                            reason = "not a regular source file"
                        elif full.suffix.lower() in IGNORED_EXTENSIONS:
                            reason = "binary or archive extension"
                        elif full.stat().st_size > 500 * 1024:
                            reason = "file exceeds 500 KiB"
                        else:
                            copied_count += 1
                            copied_size += full.stat().st_size
                            if copied_count > 2000 or copied_size > 20 * 1024 * 1024:
                                raise ValueError("Repository source inventory limit exceeded before copying")
                    if reason:
                        ignored.append(name)
                        self.omit(relative, reason, target)
                return ignored

            shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=True, ignore=ignore_local)
            return dest

        # Remote git clone
        try:
            if commit_sha:
                # Clone and checkout commit
                repo = git.Repo.clone_from(
                    repo_url,
                    dest,
                    no_single_branch=True,
                    env={"GIT_TERMINAL_PROMPT": "0"},
                )
                repo.git.checkout(commit_sha)
            else:
                git.Repo.clone_from(
                    repo_url,
                    dest,
                    depth=depth,
                    env={"GIT_TERMINAL_PROMPT": "0"},
                )
            return dest
        except Exception as e:
            raise ValueError(f"Git clone/checkout failed for {repo_url}: {e}")

    def list_files(self, target: str = "head", max_file_size_kb: int = 500) -> list[dict[str, Any]]:
        """List and read files from the workspace target, respecting limits and exclusions."""
        base_path = self.head_dir if target == "head" else self.base_dir
        if not base_path.exists():
            return []

        results = []
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext in IGNORED_EXTENSIONS:
                    continue

                full_path = Path(root) / fname
                try:
                    # Skip symlinks pointing outside
                    if full_path.is_symlink():
                        continue

                    size = full_path.stat().st_size
                    if size > max_file_size_kb * 1024:
                        continue

                    rel_path = str(full_path.relative_to(base_path))
                    if sensitive_source_path(rel_path):
                        self.omit(rel_path, "credential path", target)
                        continue
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()

                    if sum(f["size_bytes"] for f in results) + size > 20 * 1024 * 1024 or len(results) >= 2000:
                        raise ValueError("Repository source inventory limit exceeded")
                    results.append(
                        {
                            "path": str(full_path),
                            "relative_path": rel_path,
                            "content": content,
                            "size_bytes": size,
                            "lines": len(content.splitlines()),
                            "extension": ext,
                        }
                    )
                except ValueError:
                    raise
                except OSError:
                    continue

        return results

    def compute_git_diff(self) -> str:
        """Compute git diff between base and head directories."""
        import difflib
        import shlex

        base = {f["relative_path"]: f["content"] for f in self.list_files("base")}
        head = {f["relative_path"]: f["content"] for f in self.list_files("head")}
        parts = []
        for path in sorted(base.keys() | head.keys()):
            if base.get(path) == head.get(path):
                continue
            parts.append("diff --git " + shlex.quote("a/" + path) + " " + shlex.quote("b/" + path) + "\n")
            if path not in base:
                parts.append("new file mode 100644\n")
            elif path not in head:
                parts.append("deleted file mode 100644\n")
            parts.extend(
                difflib.unified_diff(
                    base.get(path, "").splitlines(True),
                    head.get(path, "").splitlines(True),
                    fromfile="a/" + path,
                    tofile="b/" + path,
                )
            )
        return "".join(parts)
