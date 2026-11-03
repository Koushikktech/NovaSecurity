import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("audit_adjudicate", root / "evals/adjudicate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_label_review_requires_evidence_and_issue_alignment(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"cases": [{"id": "one", "expected_issues": [{"id": "bug"}]}]}))
    report = {
        "corpus_hash": hashlib.sha256(corpus.read_bytes()).hexdigest(),
        "reviewer_relationship": "builder",
        "cases": [
            {"case_id": "one", "reviewer": "A", "evidence": "", "decision": "confirmed", "aligned_issue_ids": ["bug"]}
        ],
    }
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="Unresolved"):
        module.validate_label_review(corpus, path)
    report["cases"][0]["evidence"] = "The call omits the required parameter."
    path.write_text(json.dumps(report))
    assert module.validate_label_review(corpus, path)["relationship"] == "builder"
    report["cases"][0]["aligned_issue_ids"] = []
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="disagreement"):
        module.validate_label_review(corpus, path)
