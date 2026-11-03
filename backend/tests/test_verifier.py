import json

from review.verifier import verify_candidates
from schemas.contracts import Disposition, Finding, FindingCategory, Location, Severity
from schemas.provider import ChallengeResult, ProviderResponse


def finding(number):
    return Finding(
        run_id="test",
        stable_fingerprint=str(number),
        category=FindingCategory.BUG,
        rule_id="ruff:F841",
        title="Candidate",
        explanation="Check claim",
        user_impact="Possible bug",
        severity=Severity.HIGH,
        primary_location=Location(path=f"f{number}.py", start_line=1, end_line=1),
        analysis_sources=["ruff"],
    )


class Verifier:
    def __init__(self, empty=False):
        self.calls = 0
        self.empty = empty

    def generate_structured(self, request, schema):
        self.calls += 1
        claims = json.loads(request.context.split("CLAIMS:\n")[1].split("\nSOURCE:")[0])
        return ProviderResponse(
            success=True,
            model_id="test",
            data=ChallengeResult(
                assessments=[]
                if self.empty
                else [
                    {
                        "rule_id": c["rule_id"],
                        "path": c["path"],
                        "start_line": c["start_line"],
                        "is_valid": False,
                        "confidence_assessment": "likely_false_positive",
                        "explanation": "Counter-evidence in source",
                        "evidence_status": "refuted",
                        "citations": [{"path": c["path"], "start_line": 1, "quote": "value = 1"}],
                    }
                    for c in claims
                ]
            ),
        )


def test_batches_cover_all_candidates_and_preserve_static_observations():
    candidates = [finding(i) for i in range(9)]
    files = [{"relative_path": f"f{i}.py", "content": "value = 1"} for i in range(9)]
    provider = Verifier()
    coverage, _ = verify_candidates(provider, candidates, files, "test")
    assert coverage["complete"] and coverage["assessed"] == 9 and provider.calls == 3
    assert all(c.evidence_status == "refuted" and c.disposition == Disposition.OPEN for c in candidates)


def test_empty_assessments_do_not_silently_pass_verification():
    candidates = [finding(1)]
    coverage, _ = verify_candidates(
        Verifier(empty=True), candidates, [{"relative_path": "f1.py", "content": "value = 1"}], "test"
    )
    assert not coverage["complete"] and coverage["unassessed_ids"] == [candidates[0].id]
    assert candidates[0].evidence_status == "insufficient_evidence"


def test_wrong_source_quotation_cannot_refute_candidate():
    candidates = [finding(1)]
    coverage, _ = verify_candidates(
        Verifier(), candidates, [{"relative_path": "f1.py", "content": "different = 2"}], "test"
    )
    assert coverage["assessed"] == 1
    assert candidates[0].evidence_status == "insufficient_evidence"
    assert candidates[0].disposition == Disposition.OPEN
