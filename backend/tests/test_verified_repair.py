from __future__ import annotations

from pathlib import Path

from providers.fake import FakeLLMProvider
from remediation.patcher import Patcher, apply_edits_to_text
from schemas.contracts import (
    FileEdit,
    Finding,
    FindingCategory,
    Location,
    Patch,
    PatchStatus,
    Severity,
)
from schemas.provider import PatchFileEdit, PatchProposalResult
from verification.runner import VerificationRunner


def test_apply_edits_to_text_unit():
    source = "def calc(a, b):\n    return a + b\n"
    # Valid replacement
    res, err = apply_edits_to_text(source, [FileEdit(path="calc.py", old_content="a + b", replacement="a * b", rationale="")])
    assert err is None
    assert "return a * b" in res

    # Stale base
    res2, err2 = apply_edits_to_text(source, [FileEdit(path="calc.py", old_content="missing content", replacement="xyz", rationale="")])
    assert err2 is not None
    assert "Target content not found" in err2

    # No-op edit
    res3, err3 = apply_edits_to_text(source, [FileEdit(path="calc.py", old_content="a + b", replacement="a + b", rationale="")])
    assert err3 is not None
    assert "No-op edit detected" in err3


def test_patcher_rejects_protected_files():
    provider = FakeLLMProvider()
    provider.register_response(
        "patch",
        PatchProposalResult(
            edits=[
                PatchFileEdit(
                    path=".github/workflows/deploy.yml",
                    old_content="runs-on: ubuntu-latest",
                    replacement="runs-on: self-hosted",
                    rationale="Malicious workflow tampering",
                )
            ],
            summary="Tamper CI",
            rationale="Tampering",
            tests_to_run=[],
        ),
    )

    patcher = Patcher(provider=provider)
    dummy_finding = Finding(
        run_id="run-test",
        stable_fingerprint="fp1",
        category=FindingCategory.SECURITY,
        rule_id="SEC001",
        title="CI tampering attempt",
        explanation="Testing protected path rejection",
        user_impact="High",
        severity=Severity.HIGH,
        primary_location=Location(path="routes/search.py", start_line=1, end_line=2),
    )

    demo_dir = Path(__file__).resolve().parents[2] / "fixtures" / "demo-api"
    res = patcher.propose_patch(dummy_finding, workspace_head_dir=demo_dir)
    assert res.success is False
    assert "protected file" in res.error or "cited target" in res.error


def test_verified_repair_red_to_green_protocol():
    import os

    import pytest
    if not os.environ.get("PROOFLINE_VERIFICATION_IMAGE"):
        pytest.skip("Requires approved digest-pinned isolated verification image")
    """Verify flagship M4 capability:
    1. Pre-check fails (RED) on buggy head due to unauthorized data leak
    2. Surgical patch applied
    3. Post-check passes (GREEN) and happy path passes
    4. Test collection count > 0 verified
    """
    demo_api_dir = Path(__file__).resolve().parents[2] / "fixtures" / "demo-api"

    # Surgical repair: replace raw f-string with parameter binding
    old_code = (
        "        sql = f\"SELECT id, user, amount, description FROM expenses WHERE user = '{user}' AND description LIKE '%{query}%'\"\n"
        "        cursor.execute(sql)"
    )
    new_code = (
        "        sql = \"SELECT id, user, amount, description FROM expenses WHERE user = ? AND description LIKE ?\"\n"
        "        cursor.execute(sql, (user, f\"%{query}%\"))"
    )

    patch = Patch(
        id="patch-expense-test",
        finding_id="finding-sql-001",
        run_id="run-demo-001",
        status=PatchStatus.PROPOSED,
        branch_name="proofline/fix/test1234",
        edits=[
            FileEdit(
                path="repositories/expenses.py",
                old_content=old_code,
                replacement=new_code,
                rationale="Replace unparameterized f-string query with parameter binding tuple",
            )
        ],
    )

    runner = VerificationRunner(workspace_root=demo_api_dir)
    success, message = runner.verify_patch(
        patch,
        profile_id="expense_service_sql",
        target_dir=demo_api_dir,
    )

    assert success is True, f"Verification failed: {message}"
    assert patch.status == PatchStatus.CHECKS_PASSED
    assert patch.before_test_passed is False, "Expected pre-check to fail on buggy head (RED)"
    assert patch.after_test_passed is True, "Expected post-check to pass on patched head (GREEN)"
    assert patch.happy_path_passed is True, "Expected normal searches to continue passing"
    assert len(patch.checks) == 2  # pre_check and post_check
