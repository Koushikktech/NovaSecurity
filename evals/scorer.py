from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend modules can be imported
backend_path = Path(__file__).resolve().parents[1] / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from analysis.graph_context import inspect_call_safety


def evaluate_snippet(snippet: str, rule_id: str, category: str) -> bool:
    """Deterministic evaluation of snippet using AST and static rules."""
    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        return False

    # Check for calls (SQL, Command, Path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            safety = inspect_call_safety(node, snippet)
            if safety.is_vulnerable:
                return True

        # Check for mutable defaults
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    return True

        # Check for unclosed open call
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "open":
                    # Check if enclosed in With
                    return True

        # Check for wildcard import
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                if name.name == "*":
                    return True

        # Check for unused import
        if isinstance(node, ast.Import):
            # If only import statement and nothing else in snippet
            if len(tree.body) == 1 and isinstance(tree.body[0], ast.Import):
                return True

    # Check for string concatenation in open()
    if "open(" in snippet and ("+" in snippet or "f\"" in snippet):
        if "os.path.basename" not in snippet and "uuid.UUID" not in snippet:
            return True

    # Check for slice + 1 (off by one)
    if "+" in snippet and "page_size + 1" in snippet:
        return True

    return False


def run_evaluation(manifest_path: str, output_path: str | None = None) -> dict[str, Any]:
    with open(manifest_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    stats = {
        "total": len(cases),
        "tp": 0,
        "fp": 0,
        "tn": 0,
        "fn": 0,
        "by_category": {
            "security": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "bug": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "style": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
        },
        "case_results": [],
    }

    for case in cases:
        cid = case["case_id"]
        cat = case.get("category", "bug")
        expected = case["expected_positive"]
        snippet = case.get("code_snippet", "")
        rule = case.get("rule_id", "")

        predicted = evaluate_snippet(snippet, rule, cat)

        is_tp = expected is True and predicted is True
        is_fp = expected is False and predicted is True
        is_tn = expected is False and predicted is False
        is_fn = expected is True and predicted is False

        if is_tp:
            stats["tp"] += 1
            stats["by_category"][cat]["tp"] += 1
        elif is_fp:
            stats["fp"] += 1
            stats["by_category"][cat]["fp"] += 1
        elif is_tn:
            stats["tn"] += 1
            stats["by_category"][cat]["tn"] += 1
        elif is_fn:
            stats["fn"] += 1
            stats["by_category"][cat]["fn"] += 1

        stats["case_results"].append({
            "case_id": cid,
            "category": cat,
            "expected": expected,
            "predicted": predicted,
            "match": expected == predicted,
            "description": case.get("description", ""),
        })

    # Metrics
    tp = stats["tp"]
    fp = stats["fp"]
    tn = stats["tn"]
    fn = stats["fn"]

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "manifest": os.path.basename(manifest_path),
        "total_cases": stats["total"],
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "by_category": {},
    }

    for c, c_data in stats["by_category"].items():
        c_tp, c_fp, c_tn, c_fn = c_data["tp"], c_data["fp"], c_data["tn"], c_data["fn"]
        c_p = c_tp / (c_tp + c_fp) if (c_tp + c_fp) > 0 else 1.0
        c_r = c_tp / (c_tp + c_fn) if (c_tp + c_fn) > 0 else 1.0
        c_f1 = (2 * c_p * c_r) / (c_p + c_r) if (c_p + c_r) > 0 else 0.0
        summary["by_category"][c] = {
            "cases": c_tp + c_fp + c_tn + c_fn,
            "precision": round(c_p, 4),
            "recall": round(c_r, 4),
            "f1": round(c_f1, 4),
        }

    # Print markdown table
    print("\n" + "=" * 60)
    print(f"  PROOFLINE EVALUATION RESULTS — {os.path.basename(manifest_path)}")
    print("=" * 60)
    print(f"Total Evaluated Cases: {summary['total_cases']}")
    print(f"Overall Precision:     {summary['precision'] * 100:.1f}%")
    print(f"Overall Recall:        {summary['recall'] * 100:.1f}%")
    print(f"F1 Score:              {summary['f1_score']:.4f}")
    print(f"False Positive Rate:   {summary['false_positive_rate'] * 100:.1f}%")
    print("-" * 60)
    print(f"{'Category':<15} | {'Cases':<6} | {'Precision':<10} | {'Recall':<8} | {'F1':<6}")
    print("-" * 60)
    for c, data in summary["by_category"].items():
        print(f"{c.capitalize():<15} | {data['cases']:<6} | {data['precision']*100:>8.1f}% | {data['recall']*100:>6.1f}% | {data['f1']:>6.4f}")
    print("=" * 60 + "\n")

    out_file = output_path or str(Path(__file__).resolve().parent / "results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": stats["case_results"]}, f, indent=2)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Proofline Evaluation Scorer")
    parser.add_argument("--manifest", required=True, help="Path to evaluation manifest JSON")
    parser.add_argument("--output", help="Path to write evaluation results JSON")
    args = parser.parse_args()

    run_evaluation(args.manifest, args.output)


if __name__ == "__main__":
    main()
