from types import SimpleNamespace

import pytest

from analysis.static_tools import run_bandit, run_ruff
from providers.unavailable import UnavailableProvider
from review.orchestrator import ReviewOrchestrator


def test_real_bandit_findings_survive_orchestration_and_suppressions_cannot_hide_them(tmp_path):
    (tmp_path / "app.py").write_text(
        "import subprocess\ndef run(command):\n    subprocess.run(command, shell=True)  # nosec B602\n"
    )
    (tmp_path / ".bandit").write_text("[bandit]\nexclude=app.py\nskips=B602,B404\n")
    run, findings = ReviewOrchestrator(provider=UnavailableProvider()).execute_review(
        str(tmp_path), local_dir=str(tmp_path), static_only=True
    )
    matches = [finding for finding in findings if finding.rule_id == "bandit:B602"]
    assert matches and matches[0].primary_location.path == "app.py"
    assert matches[0].primary_location.start_line == 3
    assert run.stage_statuses["static_analysis"].value == "succeeded"


def test_ruff_conventions_stay_style_and_noqa_cannot_hide_correctness(tmp_path):
    (tmp_path / "app.py").write_text(
        "import os\ndef collect(item, items=[]):  # noqa: B006\n    items.append(item)\n    return items\n"
    )
    (tmp_path / ".gitignore").write_text("app.py\n")
    findings, coverage = run_ruff(str(tmp_path))
    assert coverage["status"] == "executed"
    unused = next(item for item in findings if item.rule_id == "ruff:F401")
    assert unused.category.value == "style" and unused.severity.value == "low"
    shared = next(item for item in findings if item.rule_id == "ruff:B006")
    assert shared.category.value == "bug" and shared.severity.value == "medium"


@pytest.mark.parametrize("tool", [run_ruff, run_bandit])
def test_tool_failure_with_empty_output_is_not_clean_coverage(tmp_path, monkeypatch, tool):
    monkeypatch.setattr(
        "analysis.static_tools.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=2, stdout="", stderr="configuration failure"),
    )
    findings, coverage = tool(str(tmp_path))
    assert not findings and coverage["status"] == "failed"
    assert "configuration failure" in coverage["error"]


def test_bandit_file_errors_prevent_complete_static_coverage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "analysis.static_tools.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout='{"results":[],"errors":[{"filename":"broken.py","reason":"syntax error"}]}', stderr=""
        ),
    )
    findings, coverage = run_bandit(str(tmp_path))
    assert not findings and coverage["status"] == "failed"
    assert coverage["file_errors"][0]["filename"] == "broken.py"
