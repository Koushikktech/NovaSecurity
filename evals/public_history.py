"""Review advisory-backed pinned snapshots; never execute historical project code."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from providers.unavailable import UnavailableProvider
from review.orchestrator import ReviewOrchestrator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--revision", choices=["vulnerable", "fixed"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = json.loads((Path(__file__).parent / "corpus/public-history-v1.json").read_text())
    case = next(c for c in manifest["cases"] if c["id"] == args.case)
    sha = case[args.revision + "_sha"]
    engine = ReviewOrchestrator(provider=UnavailableProvider())
    run, findings = engine.execute_review(case["repository"], mode="project", revision=sha, static_only=True)
    report = {
        "case_id": case["id"],
        "revision_kind": args.revision,
        "expected_sha": sha,
        "environment_constraint": case["environment"],
        "advisory": case["advisory"],
        "run": run.model_dump(),
        "findings": [f.model_dump() for f in findings],
        "quality_metrics": "Not computed; all observations require issue-level adjudication",
    }
    Path(args.output).write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "status": run.status.value,
                "sha": run.head_sha,
                "files": run.coverage.get("total_files"),
                "findings": len(findings),
                "errors": run.errors,
            }
        )
    )
    return 0 if run.head_sha == sha and run.status.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
