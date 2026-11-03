import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def scorer():
    path = Path(__file__).resolve().parents[2] / "evals/adjudicate.py"
    spec = importlib.util.spec_from_file_location("adjudication", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scoring_requires_complete_human_adjudication(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps({"cases": [{"id": "case", "expected_issues": [{"id": "bug", "path": "a.py", "line": 2}]}]})
    )
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps(
            {
                "corpus_hash": hashlib.sha256(corpus.read_bytes()).hexdigest(),
                "results": [
                    {
                        "case_id": "case",
                        "findings": [
                            {
                                "id": "finding",
                                "disposition": "open",
                                "primary_location": {"path": "a.py", "start_line": 2},
                            }
                        ],
                    }
                ],
            }
        )
    )
    judgments = tmp_path / "judgments.json"
    judgments.write_text("[]")
    with pytest.raises(ValueError, match="Missing reviewer"):
        scorer().score(corpus, results, judgments)
    judgments.write_text(
        json.dumps(
            [
                {
                    "finding_id": "finding",
                    "issue_id": "bug",
                    "reviewer": "test-reviewer",
                    "reason": "Exact source behavior established",
                }
            ]
        )
    )
    report = scorer().score(corpus, results, judgments)
    assert report["precision"] == 1 and report["recall"] == 1
    assert report["localization_within_two_lines"] == 1
    corpus.write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        scorer().score(corpus, results, judgments)
