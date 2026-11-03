import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def importer():
    path = Path(__file__).resolve().parents[2] / "evals/import_annotations.py"
    spec = importlib.util.spec_from_file_location("annotation_import", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independent_disagreement_is_recorded_not_overwritten(tmp_path):
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"cases": [{"id": "a", "split": "heldout", "expected_issues": [{"id": "bug"}]}]}))
    digest = hashlib.sha256(corpus.read_bytes()).hexdigest()
    mapping = tmp_path / "map.json"
    mapping.write_text(json.dumps({"corpus_hash": digest, "mapping": {"blind-1": "a"}}))
    annotation = tmp_path / "annotation.json"
    annotation.write_text(
        json.dumps(
            {
                "corpus_hash": digest,
                "reviewer": "Independent reviewer",
                "annotations": [
                    {"blind_id": "blind-1", "verdict": "clean", "notes": "No failure under documented inputs"}
                ],
            }
        )
    )
    result = importer().reconcile(corpus, mapping, annotation)
    assert result["counts"]["label_disagreement"] == 1
    assert result["ready_for_model_quality_scoring"] is False
    assert json.loads(corpus.read_text())["cases"][0]["expected_issues"] == [{"id": "bug"}]
    mapping.write_text(json.dumps({"corpus_hash": "bad", "mapping": {"blind-1": "a"}}))
    with pytest.raises(ValueError, match="hash mismatch"):
        importer().reconcile(corpus, mapping, annotation)
