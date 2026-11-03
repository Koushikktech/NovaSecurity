"""Explicit finding-level judgments. Never infer correctness from matching words."""

import argparse
import json
import math
from pathlib import Path


def wilson(successes, total):
    if not total:
        return None
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    width = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - width), min(1, center + width)]


def validate_label_review(corpus, alignment):
    import hashlib

    raw = Path(corpus).read_bytes()
    expected = {c["id"]: c for c in json.loads(raw)["cases"]}
    review = json.loads(Path(alignment).read_text())
    if review.get("corpus_hash") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Label alignment corpus mismatch")
    if review.get("reviewer_relationship") not in {"builder", "independent", "ai_assisted_builder"}:
        raise ValueError("Declare reviewer relationship: builder, independent, or ai_assisted_builder")
    rows = review.get("cases", [])
    if len(rows) != len(expected) or {r["case_id"] for r in rows} != set(expected):
        raise ValueError("Complete unique case alignment required")
    for row in rows:
        if not row.get("reviewer") or not row.get("evidence", "").strip() or row.get("decision") != "confirmed":
            raise ValueError("Unresolved label: " + row["case_id"])
        ids = [i["id"] for i in expected[row["case_id"]]["expected_issues"]]
        if sorted(row.get("aligned_issue_ids", [])) != sorted(ids):
            raise ValueError("Issue disagreement requires a versioned corpus, not silent relabeling")
    return {"relationship": review["reviewer_relationship"], "cases": len(rows)}


def score(corpus, result, adjudications):
    import hashlib

    raw = Path(corpus).read_bytes()
    report = json.loads(Path(result).read_text())
    if hashlib.sha256(raw).hexdigest() != report["corpus_hash"]:
        raise ValueError("Corpus hash mismatch")
    cases = {c["id"]: c for c in json.loads(raw)["cases"]}
    decisions = json.loads(Path(adjudications).read_text())
    judgments = {d["finding_id"]: d for d in decisions}
    if len(judgments) != len(decisions):
        raise ValueError("Duplicate adjudication")
    tp = fp = fn = duplicates = 0
    clean_fp_cases = clean_cases = 0
    localization = []
    for row in report["results"]:
        case = cases[row["case_id"]]
        expected = {issue["id"]: issue for issue in case["expected_issues"]}
        matched = set()
        case_fp = False
        for finding in row["findings"]:
            if finding["disposition"] == "dismissed":
                continue
            judgment = judgments.get(finding["id"])
            if not judgment or not judgment.get("reviewer") or not judgment.get("reason"):
                raise ValueError("Missing reviewer adjudication for " + finding["id"])
            issue = judgment.get("issue_id")
            if issue is None:
                fp += 1
                case_fp = True
            elif issue in expected:
                # Multiple comments about one issue count once as detection, extras as duplicate noise.
                if issue not in matched:
                    tp += 1
                    matched.add(issue)
                    location = finding["primary_location"]
                    localization.append(
                        location["path"] == expected[issue]["path"]
                        and abs(location["start_line"] - expected[issue]["line"]) <= 2
                    )
                else:
                    fp += 1
                    duplicates += 1
                    case_fp = True
            else:
                raise ValueError("Unknown issue ID: annotate the corpus and rerun scoring with a versioned result")
        fn += len(set(expected) - matched)
        if not expected:
            clean_cases += 1
            clean_fp_cases += case_fp
    return {
        "tp": tp,
        "duplicate_comments": duplicates,
        "cases": len(report["results"]),
        "review_statuses": {
            status: sum(r.get("run", {}).get("status", "unrecorded") == status for r in report["results"])
            for status in {r.get("run", {}).get("status", "unrecorded") for r in report["results"]}
        },
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "precision_95_wilson": wilson(tp, tp + fp),
        "recall_95_wilson": wilson(tp, tp + fn),
        "clean_change_false_positive_rate": clean_fp_cases / clean_cases if clean_cases else None,
        "localization_within_two_lines": sum(localization) / len(localization) if localization else None,
        "limitations": "Authored synthetic corpus; inspect reviewer provenance, not presumed independent. Cases within families are correlated. Intervals are descriptive.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--adjudications", required=True)
    parser.add_argument("--label-review")
    args = parser.parse_args()
    result = score(args.corpus, args.results, args.adjudications)
    result["label_validation"] = (
        validate_label_review(args.corpus, args.label_review)
        if args.label_review
        else {"status": "author labels only; independent validation not supplied"}
    )
    print(json.dumps(result, indent=2))
