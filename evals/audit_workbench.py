"""Prepare explicit human decisions and summarize execution; never fabricate quality labels."""

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path


def summarize(path):
    report = json.loads(Path(path).read_text())
    rows = report["results"]
    times = sorted(r["elapsed_seconds"] for r in rows)
    states = {}
    for row in rows:
        status = row["run"]["status"]
        states[status] = states.get(status, 0) + 1
    trace = [
        event for row in rows for event in row["run"].get("coverage", {}).get("investigation", {}).get("trace", [])
    ]
    observations = []
    for event in trace:
        if event.get("event_type") != "tool_completed":
            continue
        raw = event.get("observation", {}).get("output", "{}")
        try:
            observations.append(json.loads(raw) if isinstance(raw, str) else raw)
        except (ValueError, TypeError):
            observations.append({"error": "Unparseable recorded tool response"})
    retrieval = {
        "observations": len(observations),
        "errors": sum(bool(x.get("error")) for x in observations),
        "empty_collections": sum(
            any(key in x for key in ("symbols", "references", "matches", "paths"))
            and not any(x.get(key) for key in ("symbols", "references", "matches", "paths"))
            for x in observations
        ),
    }
    return {
        "tool_retrieval": retrieval,
        "recorded_model_requests": sum(event.get("event_type") == "model_request_started" for event in trace),
        "file": str(path),
        "variant": report["variant"],
        "cases": len(rows),
        "statuses": states,
        "median_seconds": statistics.median(times) if times else None,
        "p95_seconds": times[max(0, math.ceil(0.95 * len(times)) - 1)] if times else None,
        "tokens": sum(r["run"].get("usage", {}).get("total_tokens", 0) or 0 for r in rows),
        "quality": "pending explicit label alignment and finding adjudication",
    }


def prepare(corpus, results, output):
    raw = Path(corpus).read_bytes()
    cases = json.loads(raw)["cases"]
    digest = hashlib.sha256(raw).hexdigest()
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    alignment = {
        "corpus_hash": digest,
        "reviewer_relationship": "",
        "cases": [
            {
                "case_id": c["id"],
                "reviewer": "",
                "evidence": "",
                "decision": "",
                "aligned_issue_ids": [],
                "expected_issues_for_alignment": c["expected_issues"],
            }
            for c in cases
        ],
    }
    target = directory / "label-alignment.template.json"
    if not target.exists():
        target.write_text(json.dumps(alignment, indent=2) + "\n")
    summaries = []
    for path in results:
        r = json.loads(Path(path).read_text())
        if r["corpus_hash"] != digest:
            raise ValueError("Corpus mismatch")
        decisions = []
        for row in r["results"]:
            for f in row["findings"]:
                if f["disposition"] == "dismissed":
                    continue
                decisions.append(
                    {
                        "finding_id": f["id"],
                        "issue_id": None,
                        "reviewer": "",
                        "reason": "",
                        "case_id": row["case_id"],
                        "finding": f,
                    }
                )
        target = directory / (Path(path).stem + ".adjudications.template.json")
        if not target.exists():
            target.write_text(json.dumps(decisions, indent=2) + "\n")
        summaries.append(summarize(path))
    (directory / "execution-summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default=str(Path(__file__).parent / "corpus/authored-v1.json"))
    p.add_argument("--results", nargs="+", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    prepare(args.corpus, args.results, args.output)
