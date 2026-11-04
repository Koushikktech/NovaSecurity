"""Record a bounded real review and model repairs of an authored expense-app change."""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import git

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from providers.codex_cli import CodexCLIProvider
from remediation.patcher import Patcher, apply_edits_to_text
from review.harness import RunConfig
from review.orchestrator import ReviewOrchestrator

OUT = ROOT / "evals/results/expense-story.json"


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live", action="store_true", help="Authorize up to four review and two patch invocations on authored fixtures"
    )
    if not parser.parse_args().live:
        parser.error("Pass --live to authorize real provider usage")
    with tempfile.TemporaryDirectory(prefix="expense-story-") as t:
        root = Path(t) / "repo"
        shutil.copytree(ROOT / "fixtures/expense-story/base", root)
        repo = git.Repo.init(root)
        actor = git.Actor("Proofline fixture", "demo@example.invalid")
        repo.index.add(["."])
        base = repo.index.commit("Working expense app", author=actor, committer=actor).hexsha
        shutil.copytree(ROOT / "fixtures/expense-story/head", root, dirs_exist_ok=True)
        repo.index.add(["."])
        head = repo.index.commit("Search and save refactor", author=actor, committer=actor).hexsha
        p = CodexCLIProvider(default_model="gpt-5.6-sol", reasoning="high", max_attempts=1, enabled=True)
        config = RunConfig(
            provider="codex_cli",
            model="gpt-5.6-sol",
            max_model_calls=4,
            investigation_rounds=1,
            max_attempts=1,
            deadline_seconds=480,
        )

        def progress(e):
            if e.get("event_type") == "stage_progress":
                print(json.dumps({k: e[k] for k in ["stage", "status"] if k in e}), flush=True)

        run, findings = ReviewOrchestrator(provider=p, run_config=config, event_callback=progress).execute_review(
            str(root), local_dir=str(root), base_sha=base, head_sha=head, mode="compare"
        )
        result = {
            "provenance": "Authored demo, not independent evaluation. Reviewed snapshots contain no bug-label comments.",
            "run": run.model_dump(mode="json"),
            "findings": [f.model_dump(mode="json") for f in findings],
            "patches": [],
        }
        OUT.write_text(json.dumps(result, indent=2) + "\n")
        dest = ROOT / "fixtures/expense-story/repaired"
        shutil.copytree(ROOT / "fixtures/expense-story/head", dest, dirs_exist_ok=True)
        for path in ["repositories/expenses.py", "client/save.js"]:
            f = next((f for f in findings if f.primary_location.path == path), None)
            if not f:
                continue
            patch_provider = CodexCLIProvider(
                default_model="gpt-5.6-sol", reasoning="high", max_attempts=1, enabled=True
            )
            repair = Patcher(patch_provider).propose_patch(
                f,
                root,
                relevant_context="Preserve normal search and user isolation; await all item saves before resolving. Fix only the cited issue.",
            )
            if repair.success:
                patched, error = apply_edits_to_text((root / path).read_text(), repair.patch.edits)
                if not error:
                    (dest / path).write_text(patched)
                    result["patches"].append(repair.patch.model_dump(mode="json"))
            else:
                result.setdefault("repair_errors", []).append(repair.error)
            result.setdefault("repair_activity", []).extend(patch_provider.api_log)
            OUT.write_text(json.dumps(result, indent=2) + "\n")
        result["activity"] = p.api_log
        OUT.write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps({"status": run.status.value, "findings": len(findings), "patches": len(result["patches"])}),
            flush=True,
        )


if __name__ == "__main__":
    main()
