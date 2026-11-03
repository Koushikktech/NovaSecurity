import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_preserves_config_and_pinned_source_on_resume(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    source.mkdir()
    original = "def total(items):\n    return sum(items)\n"
    (source / "app.py").write_text(original)
    environment = {
        **os.environ,
        "PYTHONPATH": str(root / "backend"),
        "GEMINI_API_KEY": "",
        "PROOFLINE_WORKSPACE_DIR": str(tmp_path / "workspaces"),
        "PROOFLINE_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "PROOFLINE_DATABASE_URL": "sqlite:///" + str(tmp_path / "reviews.db"),
    }
    command = [sys.executable, str(root / "backend/cli.py"), "review", "--static-only", "--format", "json"]
    first = subprocess.run(
        command
        + [
            "--repo",
            str(source),
            "--api-mode",
            "generate_content",
            "--thinking",
            "low",
            "--max-model-calls",
            "4",
            "--deadline-seconds",
            "30",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert first.returncode == 0, first.stderr
    report = json.loads(first.stdout)
    (source / "app.py").write_text("changed = True\n")
    second = subprocess.run(
        command + ["--resume", report["run"]["id"]], env=environment, capture_output=True, text=True, timeout=30
    )
    assert second.returncode == 0, second.stderr
    resumed = json.loads(second.stdout)["run"]
    assert resumed["coverage"]["resumed_from"] == report["run"]["id"]
    assert resumed["coverage"]["run_config"]["max_model_calls"] == 4
    assert resumed["coverage"]["run_config"]["thinking"] == "low"
    assert resumed["coverage"]["run_config"]["api_mode"] == "generate_content"
    assert (tmp_path / "workspaces" / resumed["id"] / "head/app.py").read_text() == original
