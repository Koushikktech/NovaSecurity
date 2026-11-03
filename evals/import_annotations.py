"""Reconcile independent blind labels without silently rewriting the ground truth."""

import argparse
import hashlib
import json
from pathlib import Path


def reconcile(corpus_path, map_path, annotations_path):
    raw = Path(corpus_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    corpus = json.loads(raw)
    blind = json.loads(Path(map_path).read_text())
    supplied = json.loads(Path(annotations_path).read_text())
    if blind.get("corpus_hash") != digest or supplied.get("corpus_hash") != digest:
        raise ValueError("Annotation/corpus hash mismatch; do not mix packet versions")
    reviewer = supplied.get("reviewer", "").strip()
    if not reviewer:
        raise ValueError("Named independent reviewer required")
    cases = {case["id"]: case for case in corpus["cases"]}
    mapping = blind["mapping"]
    if set(mapping.values()) != set(cases) or len(mapping) != len(cases):
        raise ValueError("Incomplete or duplicated blind mapping")
    seen = set()
    rows = []
    for item in supplied.get("annotations", []):
        identifier = item.get("blind_id")
        if identifier not in mapping or identifier in seen:
            raise ValueError("Unknown or duplicate blind case")
        seen.add(identifier)
        verdict = item.get("verdict", "")
        if verdict not in {"", "issue", "clean", "uncertain"}:
            raise ValueError("Unknown annotation verdict")
        notes = item.get("notes", "").strip()
        if verdict in {"issue", "uncertain"} and not notes:
            raise ValueError("Issue and uncertain decisions require evidence/assumptions")
        case = cases[mapping[identifier]]
        author_positive = bool(case["expected_issues"])
        status = (
            "unreviewed"
            if not verdict
            else "uncertain"
            if verdict == "uncertain"
            else ("presence_agrees" if (verdict == "issue") == author_positive else "label_disagreement")
        )
        rows.append(
            {
                "case_id": case["id"],
                "split": case["split"],
                "reviewer": reviewer,
                "verdict": verdict,
                "notes": notes,
                "label_status": status,
                "issue_alignment": "Manual issue-level alignment still required" if verdict == "issue" else None,
            }
        )
    for identifier, case_id in mapping.items():
        if identifier not in seen:
            rows.append(
                {
                    "case_id": case_id,
                    "split": cases[case_id]["split"],
                    "reviewer": reviewer,
                    "verdict": "",
                    "notes": "",
                    "label_status": "unreviewed",
                }
            )
    return {
        "corpus_hash": digest,
        "reviewer": reviewer,
        "rows": rows,
        "counts": {
            status: sum(row["label_status"] == status for row in rows)
            for status in ["presence_agrees", "label_disagreement", "uncertain", "unreviewed"]
        },
        "ready_for_model_quality_scoring": False,
        "next_step": "Resolve disagreements/uncertainty and align each issue to a stable expected issue ID before adjudicating model findings. No accuracy inferred from label agreement.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--corpus", default=str(Path(__file__).parent / "corpus/authored-v1.json"))
    parser.add_argument("--map", default=str(Path(__file__).parent / "annotation/blind-map.json"))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = reconcile(args.corpus, args.map, args.annotations)
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report["counts"]))
