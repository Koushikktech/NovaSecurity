"""Run operator-owned regression contracts on the authored expense story snapshots."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
result = {
    "scope": "Local subprocess execution of authored Python/SQLite and Node contracts; not Docker isolation or an accuracy benchmark.",
    "phases": {},
}
for phase in ["base", "head", "repaired"]:
    root = ROOT / "fixtures/expense-story" / phase
    env = {**os.environ, "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    commands = [
        (
            "search",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                str(ROOT / "fixtures/expense-story/oracle/test_search.py"),
            ],
        ),
        ("save", ["node", str(ROOT / "fixtures/expense-story/oracle/save.cjs"), str(root / "client/save.js")]),
    ]
    result["phases"][phase] = {}
    for name, cmd in commands:
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd="/private/tmp", timeout=30)
        result["phases"][phase][name] = {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
output = ROOT / "evals/results/expense-story-execution.json"
output.write_text(json.dumps(result, indent=2) + "\n")
for phase in result["phases"]:
    for name, item in result["phases"][phase].items():
        print(phase, name, item["exit_code"])
        assert item["exit_code"] == (1 if phase == "head" else 0), (phase, name, item)
print("All expected original / changed / repaired outcomes verified.")
