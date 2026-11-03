"""Verify an already-running isolated Compose stack with authored fixtures; no external APIs."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", default="proofline-release-check")
    parser.add_argument("--api", default="http://127.0.0.1:8005")
    parser.add_argument("--ui", default="http://127.0.0.1:3005")
    parser.add_argument("--output", default=str(ROOT / "evals/results/container-stack.json"))
    args = parser.parse_args()
    token = os.environ.get("PROOFLINE_CONTAINER_TEST_TOKEN", "")
    if not token:
        raise ValueError("Set PROOFLINE_CONTAINER_TEST_TOKEN to the isolated stack's test operator token")
    command = ["docker", "compose", "--env-file", args.env_file, "-p", args.project]
    report = {
        "scope": "Local locked-dependency containers, non-root read-only runtime, authored static fixtures; no hosted release or live model/GitHub claims"
    }
    started = time.monotonic()
    with httpx.Client(base_url=args.api, headers={"Authorization": "Bearer " + token}, timeout=10) as client:

        def get_run(identifier):
            response = client.get("/api/v1/reviews/" + identifier)
            response.raise_for_status()
            return response.json()

        def wait_run(identifier):
            until = time.monotonic() + 60
            while time.monotonic() < until:
                run = get_run(identifier)
                if run["status"] not in {"queued", "running"}:
                    return run
                time.sleep(0.1)
            raise TimeoutError("Container review did not terminate")

        assert httpx.get(args.api + "/api/v1/capabilities", timeout=5).status_code == 401
        capabilities = client.get("/api/v1/capabilities").json()
        assert capabilities["live_gemini_configured"] is False
        assert capabilities["execution_enabled"] is False
        assert set(capabilities["languages"]) == {"python", "javascript", "typescript"}
        front = httpx.get(args.ui, timeout=5)
        assert front.status_code == 200 and "Proofline" in front.text
        cors = client.options("/api/v1/reviews", headers={"Origin": args.ui, "Access-Control-Request-Method": "POST"})
        assert cors.headers.get("access-control-allow-origin") == args.ui
        response = client.post(
            "/api/v1/reviews/folder",
            json={
                "files": [
                    {
                        "path": "app.py",
                        "content": "def append(value, items=[]):\n    items.append(value)\n    return items\n",
                    },
                    {
                        "path": "worker.js",
                        "content": "export async function run(items) { items.forEach(async item => { await save(item); }); }\n",
                    },
                    {"path": "contract.ts", "content": "export function count(): number { return 'wrong'; }\n"},
                ]
            },
        )
        response.raise_for_status()
        run = wait_run(response.json()["run_id"])
        assert run["status"] == "partial" and run["stage_statuses"]["static_analysis"] == "succeeded"
        findings = client.get(f"/api/v1/reviews/{run['id']}/findings").json()
        rules = sorted({finding["rule_id"] for finding in findings})
        assert {"ruff:B006", "js:async-foreach", "js:type-2322"}.issubset(rules), rules
        exported = client.get(f"/api/v1/reviews/{run['id']}/export").json()
        assert exported["findings"]
        stream = client.get(f"/api/v1/reviews/{run['id']}/events", timeout=5)
        assert "event: complete" in stream.text and '"status": "partial"' in stream.text
        resumed = client.post(f"/api/v1/reviews/{run['id']}/resume")
        resumed.raise_for_status()
        restored = wait_run(resumed.json()["run_id"])
        assert restored["coverage"]["resumed_from"] == run["id"]
        assert restored["status"] == "partial"
        checks = {
            "backend": [
                "python",
                "-c",
                "import os,pathlib; from config import settings; assert os.getuid()!=0; assert not pathlib.Path('/app/backend/.env').exists(); assert not settings.gemini_api_key; assert str(settings.artifact_dir)=='/app/data/artifacts'; print('PASS: nonroot, no source env, no provider key, persistent artifacts')",
            ],
            "frontend": [
                "node",
                "-e",
                "const fs=require('fs'); if(process.getuid()===0||fs.existsSync('/app/.env.local')||fs.existsSync('/app/.env'))process.exit(1); console.log('PASS: nonroot, no source env');",
            ],
        }
        for service, check in checks.items():
            subprocess.run(
                command + ["exec", "-T", service] + check,
                cwd=ROOT,
                check=True,
                timeout=15,
                capture_output=True,
                text=True,
            )
        subprocess.run(command + ["restart", "backend"], cwd=ROOT, check=True, timeout=30, capture_output=True)
        until = time.monotonic() + 60
        while True:
            try:
                persisted = get_run(run["id"])
                assert persisted == run
                break
            except httpx.RequestError:
                if time.monotonic() >= until:
                    raise
                time.sleep(0.2)
        report.update(
            {
                "passed": True,
                "unauthenticated_access": "rejected",
                "cors": "passed",
                "frontend_http": "passed",
                "static_languages": rules,
                "partial_without_model": True,
                "terminal_stream_closed": True,
                "sealed_resume": True,
                "nonroot_and_no_source_env": True,
                "restart_preserved_report": True,
                "duration_seconds": round(time.monotonic() - started, 2),
            }
        )
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
