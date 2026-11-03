from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import settings
from providers import CodexCLIProvider, GeminiProvider
from providers.codex_cli import codex_status
from providers.unavailable import UnavailableProvider
from review import ReviewOrchestrator
from review.harness import RunConfig
from review.snapshots import load_snapshot
from schemas.contracts import FindingCategory, Severity


def doctor_command() -> int:
    """Check environment, installed static tools, and model configuration."""
    print("=== Proofline Doctor ===")
    print(f"Python Runtime: {sys.version.split()[0]}")
    print(f"Operating System: {sys.platform}")

    # Check static analyzers
    ruff_ok = os.path.exists(Path(sys.prefix) / "bin" / "ruff") or bool(os.system("which ruff >/dev/null 2>&1") == 0)
    bandit_ok = os.path.exists(Path(sys.prefix) / "bin" / "bandit") or bool(
        os.system("which bandit >/dev/null 2>&1") == 0
    )
    semgrep_ok = os.path.exists(Path(sys.prefix) / "bin" / "semgrep") or bool(
        os.system("which semgrep >/dev/null 2>&1") == 0
    )

    print(f"Ruff Linter: {'AVAILABLE [✓]' if ruff_ok else 'MISSING [✗]'}")
    print(f"Bandit Security: {'AVAILABLE [✓]' if bandit_ok else 'MISSING [✗]'}")
    print(f"Semgrep (optional, not in active pipeline): {'AVAILABLE [✓]' if semgrep_ok else 'MISSING [✗]'}")

    # Check Gemini Configuration
    has_key = bool(settings.gemini_api_key)
    print(f"Gemini API Key: {'CONFIGURED [✓]' if has_key else 'UNSET (static-only; contextual stage unavailable) [!]'}")
    print(f"Default provider: {settings.llm_provider}")
    print("Local Codex: " + json.dumps(codex_status()))
    print(f"Review Model: {settings.gemini_review_model}")
    print(f"Patch Model: {settings.gemini_patch_model}")
    print(f"Database: {settings.database_url}")
    print("Inspect capabilities and run tests before enabling live model/publishing/execution.")
    return 0


def review_command(args: argparse.Namespace) -> int:
    """Run code review on PR or repository."""
    target_url = args.pr or args.repo
    restored = None
    if args.resume:
        import uuid

        try:
            identifier = str(uuid.UUID(args.resume))
            args.resume = identifier
            restored, _ = load_snapshot(settings.workspace_dir / identifier)
        except (ValueError, OSError, KeyError):
            print("Error: No valid sealed source checkpoint exists for that run ID.", file=sys.stderr)
            return 2
        target_url = restored["metadata"]["repository"]
    if not target_url:
        print("Error: Provide --repo, --pr or --resume.", file=sys.stderr)
        return 2
    config = (
        RunConfig.model_validate(restored["metadata"].get("run_config", {}))
        if restored
        else RunConfig(
            provider=args.provider or settings.llm_provider,
            api_mode=settings.gemini_api_mode,
            codex_reasoning=settings.codex_reasoning,
            max_attempts=settings.llm_max_attempts,
            max_model_calls=settings.max_model_calls_per_run,
            deadline_seconds=settings.review_deadline_seconds,
        )
    )
    original_provider = config.provider
    for field in (
        "model",
        "provider",
        "codex_reasoning",
        "api_mode",
        "thinking",
        "max_attempts",
        "max_model_calls",
        "max_tool_calls",
        "deadline_seconds",
        "strategy",
    ):
        value = getattr(args, field, None)
        if value is not None:
            setattr(config, field, value)
    if config.provider != original_provider:
        config.models = {}
        config.model = args.model
    if args.model:
        config.models = {role: args.model for role in ("review", "patch", "verify_reasoning")}
    if args.verifier_model:
        config.models["verify_reasoning"] = args.verifier_model
    if args.repair_model:
        config.models["patch"] = args.repair_model
    if config.provider == "codex_cli" and not restored:
        if args.deadline_seconds is None:
            config.deadline_seconds = 600
        if args.max_attempts is None:
            config.max_attempts = 1
    provider = (
        CodexCLIProvider(default_model=config.model, reasoning=config.codex_reasoning, max_attempts=config.max_attempts)
        if config.provider == "codex_cli" and not args.static_only
        else GeminiProvider(
            default_model=config.model,
            thinking=config.thinking,
            max_attempts=config.max_attempts,
            api_mode=config.api_mode,
        )
        if settings.gemini_api_key and not args.static_only
        else UnavailableProvider()
    )
    orchestrator = ReviewOrchestrator(provider=provider, run_config=config)

    try:
        run, findings = orchestrator.execute_review(
            target_url=target_url,
            base_sha=args.base,
            head_sha=args.head,
            local_dir=target_url if os.path.isdir(target_url) else None,
            static_only=args.static_only,
            mode=args.mode,
            revision=args.revision,
            depth=args.depth or (restored["metadata"].get("depth", "quick") if restored else "quick"),
            resume_from=args.resume,
        )
    except Exception as exc:
        print(f"Error executing review: {exc}", file=sys.stderr)
        return 2

    # Formatting output
    if args.format == "json":
        output_data = {
            "run": run.model_dump(),
            "findings": [f.model_dump() for f in findings],
        }
        print(json.dumps(output_data, indent=2))
    else:
        # Markdown / human readable
        print(f"\n# Proofline Review Report: {target_url}")
        print(f"- Run ID: `{run.id}`")
        print(f"- Status: `{run.status.value}`")
        print(
            f"- Scope: {run.coverage.get('total_files', 0)} files analyzed ({run.coverage.get('python_files', 0)} Python)"
        )
        print(
            f"- Findings: {run.findings_count['total']} total "
            f"({run.findings_count['security']} security, {run.findings_count['bug']} bug, {run.findings_count['style']} style)\n"
        )

        if not findings:
            print("✓ No policy-blocking issues found in the analyzed scope.")
        else:
            for i, f in enumerate(findings):
                print(f"### {i + 1}. [{f.severity.value.upper()}] {f.title}")
                print(f"- **Rule:** `{f.rule_id}` | **Category:** `{f.category.value}`")
                print(f"- **Location:** `{f.primary_location.path}`:{f.primary_location.start_line}")
                print(f"- **Explanation:** {f.explanation}")
                if f.proposed_remedy:
                    print(f"- **Suggested Fix:** {f.proposed_remedy}")
                print()

    if run.status.value in ("partial", "failed", "interrupted"):
        return 2

    # Determine exit code based on policy:
    # Exit 1 if any Critical or High security findings exist
    blocking_findings = [
        f
        for f in findings
        if f.category == FindingCategory.SECURITY and f.severity in (Severity.CRITICAL, Severity.HIGH)
    ]
    if blocking_findings:
        return 1
    return 0


def evaluate_command(args: argparse.Namespace) -> int:
    """Run legacy snippet heuristic, never report it as model accuracy."""
    print("Legacy snippet heuristic only. Use evals/review_benchmark.py for full-pipeline ablations.", file=sys.stderr)
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(f"Error: Manifest file {manifest_path} not found.", file=sys.stderr)
        return 2

    eval_script = Path(__file__).resolve().parents[1] / "evals" / "scorer.py"
    if not eval_script.exists():
        print(f"Error: Scorer script not found at {eval_script}", file=sys.stderr)
        return 2

    import subprocess

    cmd = [sys.executable, str(eval_script), "--manifest", str(manifest_path)]
    if args.output:
        cmd.extend(["--output", str(args.output)])

    res = subprocess.run(cmd)
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(prog="proofline", description="Proofline CLI — Evidence-backed AI Code Review")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Doctor
    subparsers.add_parser("doctor", help="Inspect local environment and static analyzers")

    # Review
    rev_parser = subparsers.add_parser("review", help="Review a PR or repository")
    rev_parser.add_argument("--mode", choices=["auto", "project", "commit", "compare", "pr", "working"], default="auto")
    rev_parser.add_argument("--resume", help="Resume a saved run ID from sealed source, without refetching Git")
    rev_parser.add_argument("--provider", choices=["gemini", "codex_cli"])
    rev_parser.add_argument("--codex-reasoning", choices=["low", "medium", "high", "xhigh", "max"])
    rev_parser.add_argument("--model", help="Model override for all roles")
    rev_parser.add_argument("--verifier-model", help="Gemini verifier model override")
    rev_parser.add_argument("--repair-model", help="Gemini repair model override")
    rev_parser.add_argument("--api-mode", choices=["auto", "generate_content", "interactions"])
    rev_parser.add_argument("--thinking", choices=["default", "low", "high"])
    rev_parser.add_argument("--max-attempts", type=int, choices=range(1, 6))
    rev_parser.add_argument("--max-model-calls", type=int, choices=range(1, 41))
    rev_parser.add_argument("--max-tool-calls", type=int, choices=range(1, 101))
    rev_parser.add_argument("--deadline-seconds", type=int, choices=range(10, 901))
    rev_parser.add_argument("--strategy", choices=["diff", "context", "investigate", "verified"])
    rev_parser.add_argument("--revision", help="Branch/tag/commit for project or commit review")
    rev_parser.add_argument("--depth", choices=["quick", "deep"])
    rev_parser.add_argument(
        "--static-only", action="store_true", help="Run deterministic analysis without any model calls"
    )
    rev_parser.add_argument("--repo", help="Repository URL or local path", type=str)
    rev_parser.add_argument("--pr", help="GitHub Pull Request URL", type=str)
    rev_parser.add_argument("--base", help="Base commit SHA", type=str)
    rev_parser.add_argument("--head", help="Head commit SHA", type=str)
    rev_parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Output format")

    # Evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation harness on benchmark manifests")
    eval_parser.add_argument("--manifest", required=True, help="Path to evaluation manifest JSON", type=str)
    eval_parser.add_argument("--output", help="Output directory for raw evaluation artifacts", type=str)

    args = parser.parse_args()

    if args.command == "doctor":
        return doctor_command()
    elif args.command == "review":
        return review_command(args)
    elif args.command == "evaluate":
        return evaluate_command(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
