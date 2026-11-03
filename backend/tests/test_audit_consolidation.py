import json
from pathlib import Path

from review.dedup import consolidate_signature_findings
from schemas.contracts import Finding


def recorded():
    report = json.loads((Path(__file__).resolve().parents[2] / "evals/results/codex-cli-review.json").read_text())
    return [Finding.model_validate(f) for f in report["findings"]]


def test_actual_cross_location_duplicate_preserves_evidence_and_id():
    findings = recorded()
    before = sum(len(f.evidence_items) for f in findings)
    output = consolidate_signature_findings(findings)
    assert len(output) == 2
    assert sum(len(f.evidence_items) for f in output) == before
    assert any(f.verification_assessment.get("consolidated_finding_ids") for f in output)


def test_missing_caller_citation_does_not_merge():
    findings = recorded()
    model = next(f for f in findings if f.rule_id.startswith("proofline:"))
    model.verification_assessment["citations"] = []
    assert len(consolidate_signature_findings(findings)) == 3


def test_multiple_call_sites_are_not_collapsed():
    findings = recorded()
    anchor = next(f for f in findings if f.rule_id == "python:changed-signature")
    another = anchor.model_copy(deep=True)
    another.id = "another-call"
    another.primary_location.start_line = 12
    another.primary_location.end_line = 12
    findings.append(another)
    assert len(consolidate_signature_findings(findings)) == 3


def test_known_compiler_alias_keeps_original_evidence_and_distinct_sites():
    from review.dedup import consolidate_compiler_findings

    report = json.loads((Path(__file__).resolve().parents[2] / "evals/results/audit-diff-heldout.json").read_text())
    row = next(row for row in report["results"] if row["case_id"] == "assignment-contract-bug")
    findings = [Finding.model_validate(f) for f in row["findings"]]
    assert len(consolidate_compiler_findings([f.model_copy(deep=True) for f in findings])) == 1
    findings[0].primary_location.start_line = 3
    findings[0].primary_location.end_line = 3
    assert len(consolidate_compiler_findings(findings)) == 2


def test_unrecognized_same_line_issue_is_not_a_compiler_duplicate():
    from review.dedup import consolidate_compiler_findings

    report = json.loads((Path(__file__).resolve().parents[2] / "evals/results/audit-diff-heldout.json").read_text())
    row = next(row for row in report["results"] if row["case_id"] == "null-input-bug")
    findings = [Finding.model_validate(f) for f in row["findings"]]
    next(f for f in findings if f.rule_id.startswith("proofline:")).rule_id = "proofline:unrelated-null-logging"
    assert len(consolidate_compiler_findings(findings)) == 2
