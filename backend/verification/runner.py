"""Run operator-owned test oracles in disposable, resource-limited containers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from config import settings
from remediation.patcher import apply_edits_to_text
from schemas.contracts import Patch, PatchCheckResult, PatchStatus

from .process import bounded_capture
from .profiles import get_profile


def parse_junit(text: str) -> dict[str, str]:
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("DTD and entity declarations are not accepted in test reports")
    root = ET.fromstring(text)
    results = {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        if name in results:
            raise ValueError("Ambiguous test names")
        failure = case.find("failure")
        if case.find("error") is not None:
            state = "error"
        elif case.find("skipped") is not None:
            state = "skipped"
        elif failure is not None:
            state = (
                "assertion_failure"
                if "AssertionError" in (failure.get("message", "") + (failure.text or "") + failure.get("type", ""))
                else "error"
            )
        else:
            state = "passed"
        results[name] = state
    if not results:
        raise ValueError("No tests collected")
    return results


class VerificationRunner:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def _execute(self, work_dir, profile, phase, patch):
        name = "proofline-" + uuid.uuid4().hex
        image = os.environ[profile.image_env]
        oracle = Path(__file__).resolve().parents[2] / profile.oracle_dir
        if not oracle.is_dir():
            raise ValueError("Trusted oracle unavailable")
        with tempfile.TemporaryDirectory(prefix="proofline-results-") as tmp:
            uid, gid = os.getuid(), os.getgid()
            if uid == 0:
                uid = gid = 65534
                os.chown(tmp, uid, gid)
            os.chmod(tmp, 0o700)
            cmd = [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                f"--user={uid}:{gid}",
                "--log-driver=none",
                "--ulimit=fsize=2097152:2097152",
                "--memory=256m",
                "--cpus=1",
                "--pids-limit=64",
                "--tmpfs",
                "/tmp:rw,size=32m",
                "-e",
                "PYTHONPATH=/work",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-v",
                f"{work_dir}:/work:ro",
                "-v",
                f"{oracle}:/oracle:ro",
                "-v",
                f"{tmp}:/results:rw",
                "-w",
                "/work",
                image,
                "python",
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--junitxml=/results/report.xml",
                "/oracle/" + profile.oracle_file,
            ]
            if profile.runtime == "node":
                cmd = cmd[: cmd.index(image) + 1] + [
                    "node",
                    "--test",
                    "--test-reporter=junit",
                    "/oracle/" + profile.oracle_file,
                ]
            if profile.container_command:
                cmd = cmd[: cmd.index(image) + 1] + profile.container_command
            start = time.monotonic()
            try:
                proc = bounded_capture(cmd, profile.timeout_seconds, {"PATH": os.environ.get("PATH", "")})
                output = proc.stdout
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False)
            report = Path(tmp) / "report.xml"
            if profile.runtime == "node":
                report.write_text(output)
            if not report.exists() or report.stat().st_size > 2_000_000:
                raise ValueError("Missing or oversized JUnit report")
            states = parse_junit(report.read_text())
            patch.checks.append(
                PatchCheckResult(
                    check_name=phase,
                    command=cmd,
                    exit_code=proc.returncode,
                    duration_ms=int((time.monotonic() - start) * 1000),
                    status="passed" if proc.returncode == 0 else "failed",
                    stdout_snippet=output[:16000],
                    stderr_snippet="",
                )
            )
            return proc.returncode, states

    def verify_patch(self, patch: Patch, profile_id: str, target_dir: Path | None = None):
        profile = get_profile(profile_id)
        if not profile or not settings.execution_enabled or not shutil.which("docker"):
            patch.status = PatchStatus.INCONCLUSIVE
            return False, "Enabled Docker execution and an approved profile are required"
        if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", os.environ.get(profile.image_env, "")):
            patch.status = PatchStatus.INCONCLUSIVE
            return False, "Configure an approved digest-pinned verification image"
        source = (target_dir or self.workspace_root).resolve()
        patch.checks = []
        patch.status = PatchStatus.VALIDATION_RUNNING
        try:
            with tempfile.TemporaryDirectory(prefix="proofline-verify-") as tmp:
                work = (Path(tmp) / "work").resolve()
                # Reject symlinks rather than copying host targets into the container.
                if any(p.is_symlink() for p in source.rglob("*")):
                    raise ValueError("Symlinks are not allowed in verification snapshots")
                shutil.copytree(
                    source, work, ignore=shutil.ignore_patterns(".git", ".env", ".venv", "node_modules", "__pycache__")
                )
                updates = {}
                for edit in patch.edits:
                    path = (work / edit.path).resolve()
                    if not path.is_relative_to(work) or edit.path.startswith(("tests/", ".github/")):
                        raise ValueError("Protected or escaping patch path")
                    original = updates.get(path, path.read_text())
                    updated, error = apply_edits_to_text(original, [edit])
                    if error:
                        raise ValueError(error)
                    updates[path] = updated
                if not updates:
                    raise ValueError("Empty patch")
                if profile.require_base:
                    base = source.parent / "base"
                    if not base.is_dir() or any(p.is_symlink() for p in base.rglob("*")):
                        raise ValueError("Pinned base snapshot required for differential verification")
                    base_code, base_states = self._execute(base, profile, "base", patch)
                    if base_code != 0 or not base_states or any(v != "passed" for v in base_states.values()):
                        raise ValueError("Base oracle did not pass; regression attribution inconclusive")
                _, before = self._execute(work, profile, "before", patch)
                if (
                    before.get(profile.regression_test_id) != "assertion_failure"
                    or any(v in {"error", "skipped"} for v in before.values())
                    or before.get(profile.happy_path_test_id) != "passed"
                ):
                    raise ValueError(
                        "Intended assertion failure was not reproduced; infrastructure errors are inconclusive"
                    )
                if any(name != profile.regression_test_id and state != "passed" for name, state in before.items()):
                    raise ValueError("Unrelated head test failures prevent isolated regression attribution")
                patch.before_test_passed = False
                for path, content in updates.items():
                    path.write_text(content)
                code, after = self._execute(work, profile, "after", patch)
                patch.after_test_passed = after.get(profile.regression_test_id) == "passed"
                patch.happy_path_passed = after.get(profile.happy_path_test_id) == "passed"
                if (
                    code == 0
                    and patch.after_test_passed
                    and patch.happy_path_passed
                    and all(v == "passed" for v in after.values())
                ):
                    patch.status = PatchStatus.CHECKS_PASSED
                    return True, "Independent regression assertion failed before and passed after; happy path passed"
                patch.status = PatchStatus.CHECKS_FAILED
                return False, "Patch did not pass the protected regression and happy-path checks"
        except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError) as exc:
            patch.status = PatchStatus.INCONCLUSIVE
            return False, f"Verification inconclusive: {exc}"
