"""Opt-in actual review -> model patch -> trusted Docker verification on one checkout change."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import git

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from config import settings
from providers.codex_cli import CodexCLIProvider
from remediation.patcher import Patcher
from review.harness import RunConfig
from review.orchestrator import ReviewOrchestrator
from schemas.contracts import Finding
from schemas.events import ModelActivity
from verification.runner import VerificationRunner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("--live authorizes actual model calls on this authored fixture")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", "proofline-verification:python"]))[0][
        "RepoDigests"
    ][0]
    os.environ["PROOFLINE_VERIFICATION_IMAGE"] = image
    settings.execution_enabled = True
    if args.resume:
        output = ROOT / "evals/results/flagship-checkout.json"
        finish(json.loads(output.read_text()), output)
        return
    with tempfile.TemporaryDirectory(prefix="proofline-checkout-") as temporary:
        root = Path(temporary) / "repo"
        shutil.copytree(ROOT / "fixtures/flagship/base", root)
        repo = git.Repo.init(root)
        actor = git.Actor("Proofline demo", "demo@example.invalid")
        repo.index.add(["."])
        base = repo.index.commit("Checkout with optional discount", author=actor, committer=actor).hexsha
        shutil.copytree(ROOT / "fixtures/flagship/head", root, dirs_exist_ok=True)
        repo.index.add(["."])
        head = repo.index.commit("Require a discount argument", author=actor, committer=actor).hexsha
        provider = CodexCLIProvider(default_model="gpt-5.6-sol", reasoning="high", max_attempts=1, enabled=True)
        config = RunConfig(
            provider="codex_cli",
            model="gpt-5.6-sol",
            max_model_calls=4,
            investigation_rounds=1,
            max_attempts=1,
            deadline_seconds=600,
        )
        run, findings = ReviewOrchestrator(provider=provider, run_config=config).execute_review(
            str(root), local_dir=str(root), base_sha=base, head_sha=head, mode="compare"
        )
        run.coverage["model_activity"] = ModelActivity(
            provider="codex_cli",
            attempts=provider.api_attempts,
            failures=provider.api_failures,
            tokens=provider.api_tokens,
            elapsed_ms=provider.api_elapsed_ms,
            thinking=provider.thinking,
            max_attempts=provider.max_attempts,
            log=provider.api_log[-60:],
        ).model_dump()
        result = {
            "purpose": "One authored checkout change reviewed, repaired by the model and checked against the same trusted oracle; saved evidence, not live replay or accuracy benchmark",
            "run": run.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in findings],
        }
        output = ROOT / "evals/results/flagship-checkout.json"
        output.write_text(json.dumps(result, indent=2) + "\n")
        if run.status.value != "completed":
            raise RuntimeError("Review incomplete; raw result preserved")
        finish(result, output)


def finish(result, output):
    findings = [Finding.model_validate(f) for f in result["findings"]]
    target = next(
        (f for f in findings if f.primary_location.path == "shop/checkout.py" and f.category.value == "bug"), None
    )
    if target is None:
        raise RuntimeError("Expected checkout caller finding unavailable")
    head_dir = settings.workspace_dir / result["run"]["id"] / "head"
    provider = CodexCLIProvider(default_model="gpt-5.6-sol", reasoning="high", max_attempts=1, enabled=True)
    context = (
        "Base pricing contract:\n"
        + (ROOT / "fixtures/flagship/base/shop/pricing.py").read_text()
        + "\nChanged pricing contract:\n"
        + (ROOT / "fixtures/flagship/head/shop/pricing.py").read_text()
    )
    repair = Patcher(provider).propose_patch(target, head_dir, relevant_context=context)
    if not repair.success or not repair.patch:
        raise RuntimeError(repair.error)
    success, message = VerificationRunner(head_dir).verify_patch(repair.patch, "checkout_contract")
    result.update(
        patch=repair.patch.model_dump(mode="json"),
        verification={
            "success": success,
            "message": message,
            "profile": "checkout_contract",
            "image": os.environ["PROOFLINE_VERIFICATION_IMAGE"],
        },
    )
    output.write_text(json.dumps(result, indent=2) + "\n")
    if success:
        from persistence import save_findings, save_patch, save_run
        from persistence.database import init_database
        from schemas.contracts import ReviewRun

        init_database()
        target.patch_id = repair.patch.id
        target.patch_status = repair.patch.status
        save_run(ReviewRun.model_validate(result["run"]))
        save_findings(result["run"]["id"], findings)
        save_patch(repair.patch)

    print(
        json.dumps(
            {
                "status": result["run"]["status"],
                "findings": len(findings),
                "patch": repair.patch.status.value,
                "verified": success,
                "output": str(output),
            }
        ),
        flush=True,
    )
    if not success:
        raise RuntimeError(message)


if __name__ == "__main__":
    main()
