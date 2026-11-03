"""Evaluate actual review orchestration on versioned safe/unsafe repository cases.

Static-only by default (model stage explicitly partial); --live uses configured Gemini.
No labels or expectations are sent to the engine. This is a small integration dataset,
not an independent held-out benchmark or production accuracy estimate.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from providers.unavailable import UnavailableProvider
from review.orchestrator import ReviewOrchestrator

CASES = [
    {
        "id": "python-shell-injection",
        "path": "app.py",
        "code": "import subprocess\ndef run(value):\n    subprocess.run(value, shell=True)\n",
        "rule": "bandit:B602",
        "positive": True,
    },
    {
        "id": "python-safe-argv",
        "path": "app.py",
        "code": "import subprocess\ndef run(value):\n    subprocess.run(['printf', '%s', value], shell=False)\n",
        "rule": "bandit:B602",
        "positive": False,
    },
    {
        "id": "python-mutable",
        "path": "app.py",
        "code": "def collect(item, items=[]):\n    items.append(item)\n    return items\n",
        "rule": "ruff:B006",
        "positive": True,
    },
    {
        "id": "python-safe-default",
        "path": "app.py",
        "code": "def collect(item, items=None):\n    items = [] if items is None else items\n    items.append(item)\n    return items\n",
        "rule": "ruff:B006",
        "positive": False,
    },
    {
        "id": "typescript-async",
        "path": "batch.ts",
        "code": "export function save(urls: string[]) { urls.forEach(async u => { await fetch(u); }); }\n",
        "rule": "js:async-foreach",
        "positive": True,
    },
    {
        "id": "typescript-awaited",
        "path": "batch.ts",
        "code": "export async function save(urls: string[]) { for (const u of urls) await fetch(u); }\n",
        "rule": "js:async-foreach",
        "positive": False,
    },
    {
        "id": "javascript-async",
        "path": "batch.js",
        "code": "export function save(urls) { urls.forEach(async u => { await fetch(u); }); }\n",
        "rule": "js:async-foreach",
        "positive": True,
    },
    {
        "id": "javascript-awaited",
        "path": "batch.js",
        "code": "export async function save(urls) { await Promise.all(urls.map(u => fetch(u))); }\n",
        "rule": "js:async-foreach",
        "positive": False,
    },
    {
        "id": "tsx-syntax",
        "path": "view.tsx",
        "code": "export const View = () => <div>Hello</div>;\n",
        "rule": "js:syntax",
        "positive": False,
    },
    {
        "id": "typescript-syntax",
        "path": "app.ts",
        "code": "export const value: = ;\n",
        "rule": "js:syntax",
        "positive": True,
    },
]


def evaluate(output: Path, live=False):
    results = []
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for case in CASES:
        with tempfile.TemporaryDirectory(prefix="proofline-eval-") as tmp:
            (Path(tmp) / case["path"]).write_text(case["code"])
            start = time.monotonic()
            engine = ReviewOrchestrator() if live else ReviewOrchestrator(provider=UnavailableProvider())
            run, findings = engine.execute_review("evaluation", local_dir=tmp)
            predicted = any(f.rule_id == case["rule"] for f in findings)
            key = ("tp" if predicted else "fn") if case["positive"] else ("fp" if predicted else "tn")
            counts[key] += 1
            results.append(
                {
                    "id": case["id"],
                    "expected": case["positive"],
                    "matched": predicted,
                    "status": run.status.value,
                    "duration_seconds": round(time.monotonic() - start, 3),
                    "run": run.model_dump(),
                    "findings": [f.model_dump() for f in findings],
                }
            )
    precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else 0
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0
    report = {
        "dataset": "controlled-pipeline-v2",
        "scope": "Supported-rule detection through actual ingestion/static/language/citation pipeline; ten development integration cases",
        "mode": "live" if live else "static-only; contextual stage unavailable",
        "counts": counts,
        "precision": precision,
        "recall": recall,
        "cases": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evals/results/pipeline.json"))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    evaluate(args.output, args.live)
