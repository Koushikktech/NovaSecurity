import git
import os
import shutil
import stat


def _safe_rmtree(target: str) -> None:
    if not os.path.exists(target):
        return

    def handle_remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    try:
        shutil.rmtree(target, onexc=handle_remove_readonly)
    except TypeError:
        shutil.rmtree(target, onerror=handle_remove_readonly)


class CodeIngestor:
    def __init__(self, temp_dir="temp"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    def from_git(self, url: str) -> str:
        repo = url.rstrip("/").split("/")[-1].replace(".git", "")
        target = os.path.join(self.temp_dir, repo)

        if os.path.exists(target):
            _safe_rmtree(target)

        try:
            git.Repo.clone_from(url, target)
            return target
        except git.GitCommandError as e:
            raise ValueError(f"Failed to clone repo: {e}")

    def get_python_files(self, repo_path: str) -> list[dict]:
        return self.get_files(repo_path, extensions={".py"})

    def get_files(
        self, repo_path: str, extensions: set[str] | None = None
    ) -> list[dict]:

        ALL_EXTENSIONS = {
            ".py",
            ".js",
            ".ts",
            ".jsx",
            ".tsx",
            ".java",
            ".go",
            ".rb",
            ".php",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".rs",
            ".swift",
            ".kt",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".json",
            ".xml",
            ".env",
            ".html",
            ".css",
            ".sh",
            ".bash",
            ".dockerfile",
            ".md",
            ".txt",
            ".rst",
        }

        target_extensions = extensions or ALL_EXTENSIONS
        collected = []

        dir_skip = {
            "venv",
            ".venv",
            "env",
            "node_modules",
            "__pycache__",
            ".git",
            ".svn",
            ".hg",
            "site-packages",
            "dist-packages",
            "dist",
            "build",
            "egg-info",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".idea",
            ".vscode",
        }

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in dir_skip]

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                grab_names = {
                    "Dockerfile",
                    "Makefile",
                    "Procfile",
                    ".env",
                    ".gitignore",
                }

                should_grab = ext in target_extensions
                if not extensions:
                    should_grab = should_grab or file in grab_names

                if should_grab:
                    filepath = os.path.join(root, file)
                    try:
                        with open(
                            filepath, "r", encoding="utf-8", errors="replace"
                        ) as f:
                            content = f.read()
                        collected.append(
                            {
                                "path": filepath,
                                "relative_path": os.path.relpath(filepath, repo_path),
                                "content": content,
                                "lines": len(content.splitlines()),
                            }
                        )
                    except:
                        continue

        return collected

    def get_full_codebase(self, files: list[dict]) -> str:
        parts = []
        for f in files:
            parts.append(f"#File: {f['relative_path']}\n{f['content']}")
        return "\n\n" + "=" * 50 + "\n\n".join(parts)
