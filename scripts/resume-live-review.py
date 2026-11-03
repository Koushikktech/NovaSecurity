"""Resume a recorded benchmark snapshot with the same configuration, without a Git fetch."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from providers.gemini import GeminiProvider
from review.harness import RunConfig
from review.orchestrator import ReviewOrchestrator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model")
    parser.add_argument("--api-mode", choices=["auto", "generate_content", "interactions"])
    parser.add_argument("--investigation-rounds", type=int, choices=range(1, 7))
    parser.add_argument("--attempts", type=int, choices=range(1, 4))
    parser.add_argument("--max-model-calls", type=int, choices=range(1, 41))
    args = parser.parse_args()
    prior = json.loads(Path(args.input).read_text())["results"][0]["run"]
    config = RunConfig.model_validate(prior["coverage"]["run_config"])
    if args.max_model_calls:
        config.max_model_calls = args.max_model_calls
    if args.api_mode:
        config.api_mode = args.api_mode
    if args.model:
        config.model = args.model
        config.models = {role: args.model for role in ("review", "patch", "verify_reasoning")}
    if args.investigation_rounds:
        config.investigation_rounds = args.investigation_rounds
    if args.attempts:
        config.max_attempts = args.attempts
    provider = GeminiProvider(
        max_attempts=config.max_attempts, thinking=config.thinking, default_model=config.model, api_mode=config.api_mode
    )
    engine = ReviewOrchestrator(provider=provider, run_config=config)
    run, findings = engine.execute_review(prior["canonical_repo"], resume_from=prior["id"])
    result = {"run": run.model_dump(), "findings": [f.model_dump() for f in findings]}
    Path(args.output).write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                "status": run.status.value,
                "stages": run.stage_statuses,
                "tokens": run.usage.get("total_tokens"),
                "model_error": run.coverage.get("model_review_error"),
                "challenge_error": run.coverage.get("challenge_error"),
                "tool_calls": run.coverage.get("investigation", {}).get("tool_calls"),
                "finding_evidence": [f.evidence_status for f in findings],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
