"""Run review ablations; quality scores require explicit human adjudication."""

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

import git

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from providers.codex_cli import CodexCLIProvider
from providers.gemini import GeminiProvider
from providers.unavailable import UnavailableProvider
from review.harness import RunConfig
from review.orchestrator import ReviewOrchestrator


def run(
    corpus_path,
    output,
    variant="static",
    split="development",
    limit=36,
    attempts=1,
    provider_name="gemini",
    model=None,
    reasoning="high",
    max_calls=4,
    deadline=600,
    resume=False,
    case_ids=None,
):
    raw = Path(corpus_path).read_bytes()
    corpus = json.loads(raw)
    configuration = {
        "provider": provider_name,
        "model": model,
        "reasoning": reasoning,
        "max_calls": max_calls,
        "deadline": deadline,
        "attempts": attempts,
        "case_selection": sorted(case_ids) if case_ids else None,
    }
    results = []
    if resume and Path(output).exists():
        old = json.loads(Path(output).read_text())
        if (
            old.get("configuration") != configuration
            or old.get("variant") != variant
            or old.get("split") != split
            or old.get("corpus_hash") != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("Resume configuration/corpus mismatch")
        results = old["results"]
    if case_ids and not set(case_ids) <= {c["id"] for c in corpus["cases"] if c["split"] == split}:
        raise ValueError("Unknown case selection")
    done = {row["case_id"] for row in results}

    for case in [c for c in corpus["cases"] if c["split"] == split and (not case_ids or c["id"] in case_ids)][:limit]:
        if case["id"] in done:
            continue
        with tempfile.TemporaryDirectory(prefix="proofline-bench-") as directory:
            root = Path(directory)
            repo = git.Repo.init(root)
            repo.git.config("core.hooksPath", "/dev/null")
            actor = git.Actor("Benchmark", "benchmark@example.invalid")
            for path, content in case["base_files"].items():
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            repo.index.add(list(case["base_files"]))
            base = repo.index.commit("Base", author=actor, committer=actor).hexsha
            for path, content in case["files"].items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(content)
            repo.index.add(list(case["files"]))
            head = repo.index.commit("Change", author=actor, committer=actor).hexsha
            config = RunConfig(
                strategy=variant if variant != "static" else "verified",
                provider=provider_name,
                model=model,
                codex_reasoning=reasoning,
                deadline_seconds=deadline,
                max_model_calls=max_calls,
                investigation_rounds=1,
                max_attempts=attempts,
                thinking="low",
            )
            provider = (
                UnavailableProvider()
                if variant == "static"
                else (
                    CodexCLIProvider(default_model=model, reasoning=reasoning, max_attempts=attempts, enabled=True)
                    if provider_name == "codex_cli"
                    else GeminiProvider(default_model=model, max_attempts=attempts, thinking="low")
                )
            )
            engine = ReviewOrchestrator(provider=provider, run_config=config)
            started = time.monotonic()
            review, findings = engine.execute_review(
                str(root),
                local_dir=str(root),
                mode="compare",
                base_sha=base,
                head_sha=head,
                static_only=variant == "static",
            )
            print(
                json.dumps(
                    {
                        "case": case["id"],
                        "variant": variant,
                        "status": review.status.value,
                        "seconds": round(time.monotonic() - started, 1),
                    }
                ),
                flush=True,
            )
            results.append(
                {
                    "case_id": case["id"],
                    "variant": variant,
                    "elapsed_seconds": time.monotonic() - started,
                    "run": review.model_dump(),
                    "findings": [f.model_dump() for f in findings],
                }
            )
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(
                json.dumps(
                    {
                        "configuration": configuration,
                        "corpus_hash": hashlib.sha256(raw).hexdigest(),
                        "variant": variant,
                        "split": split,
                        "quality_metrics": "not_computed_without_adjudication",
                        "results": results,
                    },
                    indent=2,
                )
            )
    print(json.dumps({"cases": len(results), "variant": variant, "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default=str(Path(__file__).parent / "corpus/authored-v1.json"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--variant", choices=["static", "diff", "context", "investigate", "verified"], default="static")
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--limit", type=int, default=36)
    parser.add_argument("--attempts", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--provider", choices=["gemini", "codex_cli"], default="codex_cli")
    parser.add_argument("--model")
    parser.add_argument("--reasoning", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    parser.add_argument("--max-calls", type=int, default=4)
    parser.add_argument("--deadline", type=int, default=600)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--case-ids", nargs="+")
    args = parser.parse_args()
    run(
        args.corpus,
        args.output,
        args.variant,
        args.split,
        args.limit,
        args.attempts,
        args.provider,
        args.model,
        args.reasoning,
        args.max_calls,
        args.deadline,
        args.resume,
        args.case_ids,
    )
