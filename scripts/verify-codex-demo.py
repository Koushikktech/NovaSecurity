"""Opt-in real subscription review of operator-authored base/head fixtures; never a benchmark score."""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import git

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from providers.codex_cli import CodexCLIProvider
from review.harness import RunConfig
from review.orchestrator import ReviewOrchestrator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Allow up to four CLI inference invocations using subscription quota"
    )
    parser.add_argument("--model")
    parser.add_argument("--reasoning", choices=["low", "medium", "high", "xhigh", "max"], default="high")
    parser.add_argument("--output", default=str(ROOT / "evals/results/codex-cli-review.json"))
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to authorize actual Codex subscription usage on authored fixtures")
    with tempfile.TemporaryDirectory(prefix="proofline-codex-demo-") as tmp:
        source = Path(tmp) / "repo"
        shutil.copytree(ROOT / "fixtures/reviewer/base", source)
        repo = git.Repo.init(source)
        actor = git.Actor("Proofline fixture", "fixture@example.invalid")
        repo.index.add(["."])
        base = repo.index.commit("Fixture base", author=actor, committer=actor).hexsha
        shutil.copytree(ROOT / "fixtures/reviewer/head", source, dirs_exist_ok=True)
        repo.index.add(["."])
        head = repo.index.commit("Fixture head", author=actor, committer=actor).hexsha
        provider = CodexCLIProvider(default_model=args.model, reasoning=args.reasoning, max_attempts=1, enabled=True)
        config = RunConfig(
            provider="codex_cli",
            model=args.model,
            codex_reasoning=args.reasoning,
            max_attempts=1,
            max_model_calls=4,
            investigation_rounds=1,
            deadline_seconds=600,
        )

        def progress(event):
            if event.get("event_type") == "stage_progress":
                print(json.dumps({key: event[key] for key in ("stage", "status") if key in event}), flush=True)

        run, findings = ReviewOrchestrator(
            provider=provider, run_config=config, event_callback=progress
        ).execute_review(str(source), local_dir=str(source), base_sha=base, head_sha=head, mode="compare")
        report = {
            "purpose": "Real CLI subscription pipeline on authored code, not independently adjudicated accuracy",
            "run": run.model_dump(),
            "findings": [finding.model_dump() for finding in findings],
            "cli_activity": provider.api_log,
        }
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": run.status.value,
                    "model": provider.default_model,
                    "usage": run.usage,
                    "stages": run.stage_statuses,
                    "verification": run.coverage.get("verification_coverage"),
                    "model_calls": run.coverage.get("investigation", {}).get("model_calls"),
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
