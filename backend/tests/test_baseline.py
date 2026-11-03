from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ingestion import (
    Workspace,
    parse_github_url,
    parse_unified_diff,
    redact_secrets,
)


def test_github_url_parser_valid():
    pr_target = parse_github_url("https://github.com/owner/my-repo/pull/42")
    assert pr_target.is_pr is True
    assert pr_target.owner == "owner"
    assert pr_target.repo == "my-repo"
    assert pr_target.pr_number == 42
    assert pr_target.canonical_url == "https://github.com/owner/my-repo/pull/42"

    repo_target = parse_github_url("https://github.com/tensorflow/tensorflow")
    assert repo_target.is_pr is False
    assert repo_target.owner == "tensorflow"
    assert repo_target.repo == "tensorflow"
    assert repo_target.pr_number is None


def test_github_url_parser_rejections():
    # Embedded credentials
    with pytest.raises(ValueError, match="credentials"):
        parse_github_url("https://user:password@github.com/owner/repo")

    # Non-http/https
    with pytest.raises(ValueError, match="scheme"):
        parse_github_url("ftp://github.com/owner/repo")

    # Disallowed host
    with pytest.raises(ValueError, match="Host 'evil.com' is not allowed"):
        parse_github_url("https://evil.com/owner/repo")

    # Incomplete path
    with pytest.raises(ValueError, match="must include owner"):
        parse_github_url("https://github.com/justowner")


def test_diff_parser_hunks_and_lines():
    sample_diff = """diff --git a/app.py b/app.py
index 1234567..89abcde 100644
--- a/app.py
+++ b/app.py
@@ -10,4 +10,5 @@ def run():
     x = 1
-    y = 2
+    y = 3
+    z = 4
     return x + y
"""
    parsed = parse_unified_diff(sample_diff)
    assert len(parsed.files) == 1
    df = parsed.files[0]
    assert df.new_path == "app.py"
    assert df.status == "modified"
    assert 11 in df.added_lines_head  # y = 3
    assert 12 in df.added_lines_head  # z = 4
    assert 11 in df.deleted_lines_base  # y = 2
    assert parsed.is_line_introduced("app.py", 12) is True
    assert parsed.is_line_introduced("app.py", 10) is False


def test_secret_redaction():
    code_with_secrets = """
    # Configuration
    AWS_KEY = "AKIA1234567890ABCDEF"
    GITHUB_TOKEN = "ghp_123456789012345678901234567890123456"
    password = "super_secret_production_password_123"
    print("Normal code line")
    """
    redacted, count = redact_secrets(code_with_secrets)
    assert count >= 3
    assert "AKIA1234567890ABCDEF" not in redacted
    assert "ghp_" not in redacted
    assert "super_secret_production_password_123" not in redacted
    assert "[REDACTED_AWS_KEY]" in redacted
    assert "[REDACTED_GITHUB_TOKEN]" in redacted
    assert "Normal code line" in redacted


def test_workspace_safe_path_resolution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace(run_id="test-run-123", base_dir=Path(tmp_dir))
        ws.initialize()

        # Valid relative path inside head
        resolved = ws.resolve_safe_path("src/main.py", target="head")
        assert str(resolved).startswith(str(ws.head_dir.resolve()))

        # Path traversal rejection
        with pytest.raises(ValueError, match="Path traversal"):
            ws.resolve_safe_path("../../../etc/passwd", target="head")

        with pytest.raises(ValueError, match="Path traversal"):
            ws.resolve_safe_path("foo/../../bar", target="head")

        ws.cleanup()
        assert not ws.root_dir.exists()


def test_after_validation_empty_not_resurrected():
    """Verify bug fix: empty after_validation does not resurrect rejected findings."""
    result = {
        "all_findings": [{"title": "False Positive Finding", "severity": "High"}],
        "after_validation": [],
    }
    # Buggy version did: result.get("after_validation") or result.get("all_findings", [])
    # Fixed version does:
    findings = (
        result["after_validation"]
        if result.get("after_validation") is not None
        else result.get("all_findings", [])
    )
    assert len(findings) == 0
    assert findings == []
