"""Actual local API process crash/restart and bounded-concurrency check; no external APIs."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "evals/results/server-recovery.json"))
    parser.add_argument("--jobs", type=int, default=12, choices=range(4, 41))
    args = parser.parse_args()
    started = time.monotonic()
    process = None
    report = {
        "scope": "Actual single-process API crash/restart and static-only concurrent jobs; no Gemini/GitHub calls",
        "requested_jobs": args.jobs,
    }
    with tempfile.TemporaryDirectory(prefix="proofline-recovery-") as temporary:
        work = Path(temporary)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "backend"),
            "GEMINI_API_KEY": "",
            "GITHUB_TOKEN": "",
            "PROOFLINE_OPERATOR_TOKEN": "",
            "PROOFLINE_EXECUTION_ENABLED": "false",
            "PROOFLINE_GITHUB_PUBLISH_ENABLED": "false",
            "PROOFLINE_GEMINI_REVIEW_MODEL": "",
            "PROOFLINE_DATABASE_URL": "sqlite:///" + str(work / "reviews.db"),
            "PROOFLINE_WORKSPACE_DIR": str(work / "workspaces"),
            "PROOFLINE_ARTIFACT_DIR": str(work / "artifacts"),
        }
        log = (work / "server.log").open("w+")
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=20)

        def boot():
            child = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT / "backend",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            until = time.monotonic() + 30
            while time.monotonic() < until:
                if child.poll() is not None:
                    raise RuntimeError("Isolated API exited before readiness")
                try:
                    if client.get("/healthz", timeout=1).status_code == 200:
                        return child
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
            raise TimeoutError("Isolated API readiness deadline")

        def wait_run(identifier):
            until = time.monotonic() + 45
            while time.monotonic() < until:
                response = client.get("/api/v1/reviews/" + identifier)
                response.raise_for_status()
                run = response.json()
                if run["status"] in TERMINAL:
                    return run
                time.sleep(0.05)
            raise TimeoutError("Static review did not terminate")

        def submit(payload):
            return client.post("/api/v1/reviews/folder", json=payload)

        small = {"files": [{"path": "app.py", "content": "def total(items):\n    return sum(items)\n"}]}
        try:
            process = boot()
            first = submit(small)
            first.raise_for_status()
            saved = wait_run(first.json()["run_id"])
            assert saved["status"] == "partial", saved["status"]  # static succeeds; unavailable AI remains explicit
            saved_findings = client.get(f"/api/v1/reviews/{saved['id']}/findings").json()
            heavy = {
                "files": [
                    {"path": f"module_{i}.py", "content": f"def calculate_{i}(items):\n    return sum(items)\n"}
                    for i in range(1500)
                ]
            }
            active = submit(heavy)
            active.raise_for_status()
            active_id = active.json()["run_id"]
            before = client.get("/api/v1/reviews/" + active_id).json()
            until = time.monotonic() + 15
            while before["status"] == "queued" and time.monotonic() < until:
                time.sleep(0.01)
                before = client.get("/api/v1/reviews/" + active_id).json()
            assert before["status"] == "running", "Crash check missed active work"
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            process = boot()
            interrupted = client.get("/api/v1/reviews/" + active_id).json()
            restored = client.get("/api/v1/reviews/" + saved["id"]).json()
            assert interrupted["status"] == "interrupted" and interrupted["completed_at"]
            assert restored == saved
            assert client.get(f"/api/v1/reviews/{saved['id']}/findings").json() == saved_findings
            events = client.get(f"/api/v1/reviews/{active_id}/events", timeout=3)
            assert "run_interrupted" in events.text and "event: complete" in events.text
            report["restart"] = {
                "passed": True,
                "active_before_crash": before["status"],
                "after_restart": interrupted["status"],
                "completed_report_preserved": True,
                "progress_stream_closed": True,
            }
            with ThreadPoolExecutor(max_workers=6) as pool:
                responses = list(pool.map(lambda _: submit(small), range(args.jobs)))
            accepted = [r.json()["run_id"] for r in responses if r.status_code == 202]
            rejected = [r.status_code for r in responses if r.status_code != 202]
            assert accepted and all(code == 429 for code in rejected), rejected
            outcomes = [wait_run(identifier) for identifier in accepted]
            assert all(r["status"] == "partial" for r in outcomes)
            assert all(r["stage_statuses"]["static_analysis"] == "succeeded" for r in outcomes)
            followup = submit(small)
            followup.raise_for_status()
            assert wait_run(followup.json()["run_id"])["status"] == "partial"
            repeated = 0
            for _ in range(10):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    pair = list(pool.map(lambda _: submit(small), range(2)))
                assert all(response.status_code == 202 for response in pair), [
                    response.status_code for response in pair
                ]
                for response in pair:
                    run = wait_run(response.json()["run_id"])
                    assert run["status"] == "partial" and run["stage_statuses"]["static_analysis"] == "succeeded"
                    repeated += 1
            report["concurrency"] = {
                "passed": True,
                "repeated_completed_reviews": repeated,
                "repeat_rounds": 10,
                "accepted": len(accepted),
                "queue_rejections": len(rejected),
                "completed_static_reviews": len(outcomes),
                "followup_after_release": "passed",
            }
            report["passed"] = True
        except Exception as exc:
            report["passed"] = False
            report["error"] = str(exc)
            raise
        finally:
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            client.close()
            log.close()
            report["duration_seconds"] = round(time.monotonic() - started, 2)
            Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
