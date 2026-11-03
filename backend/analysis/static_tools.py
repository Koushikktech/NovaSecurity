from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from runtime_budget import remaining_time
from schemas.contracts import (
    AnalysisStatus,
    EvidenceItem,
    Finding,
    FindingCategory,
    Location,
    PatchStatus,
    ReproductionStatus,
    Severity,
)

# Convention/style observations are not promoted to runtime bugs by a broad F/B prefix.
CORRECTNESS_RULES = {
    "F601",
    "F602",
    "F621",
    "F622",
    "F631",
    "F632",
    "F633",
    "F634",
    "F701",
    "F702",
    "F704",
    "F706",
    "F707",
    "F722",
    "F821",
    "F822",
    "F823",
    "F901",
    "B002",
    "B005",
    "B006",
    "B008",
    "B012",
    "B016",
    "B020",
    "B023",
    "B029",
    "B030",
    "B031",
    "B032",
    "B034",
}


def _tool_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def _relative_source_path(filename, target_dir):
    root = Path(target_dir).resolve()
    candidate = Path(filename)
    # Bandit emits paths relative to its scan cwd, not to this server process.
    candidate = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Analyzer returned a path outside the reviewed inventory")
    return candidate.relative_to(root).as_posix()


def _get_venv_bin(name: str) -> str:
    """Find executable in active virtual environment or PATH."""
    bin_cand = Path(sys.executable).parent / name
    if bin_cand.exists():
        return str(bin_cand)
    for p in Path(__file__).resolve().parents:
        cand = p / ".venv" / "bin" / name
        if cand.exists():
            return str(cand)
    return name


def _make_fingerprint(path: str, rule_id: str, line: int) -> str:
    norm_path = os.path.normpath(path).lstrip("/")
    raw = f"{norm_path}:{rule_id.upper()}:{line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def run_ruff(target_dir: str, rel_files: list[str] | None = None) -> tuple[list[Finding], dict[str, Any]]:
    """Run Ruff in JSON mode and normalize findings."""
    ruff_bin = _get_venv_bin("ruff")
    cmd = [
        ruff_bin,
        "check",
        "--output-format=json",
        "--isolated",
        "--ignore-noqa",
        "--no-respect-gitignore",
        "--select",
        "E,F,B",
    ]

    if rel_files:
        cmd.extend(rel_files)
    else:
        cmd.append(".")

    env = os.environ.copy()
    findings: list[Finding] = []
    coverage = {"tool": "ruff", "version": _tool_version("ruff"), "status": "executed", "count": 0, "error": None}

    try:
        proc = subprocess.run(
            cmd,
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=remaining_time(30),
        )
        if proc.returncode not in {0, 1}:
            raise ValueError("Analyzer exited unsuccessfully: " + proc.stderr[-1000:])
        raw_output = proc.stdout.strip()
        if not raw_output:
            raise ValueError("Analyzer returned no structured output")

        items = json.loads(raw_output)
        for item in items:
            rule_id = item.get("code", "RUFF")
            message = item.get("message", "")
            fname = item.get("filename", "")
            rel_path = _relative_source_path(fname, target_dir)

            start_row = item.get("location", {}).get("row", 1)
            end_row = item.get("end_location", {}).get("row", start_row)

            category = (
                FindingCategory.BUG
                if rule_id in CORRECTNESS_RULES or rule_id.startswith("E9")
                else FindingCategory.STYLE
            )

            severity = Severity.LOW if category == FindingCategory.STYLE else Severity.MEDIUM

            fix_info = item.get("fix")
            proposed_remedy = fix_info.get("message") if fix_info else None

            ev = EvidenceItem(
                kind="static_analysis",
                tool_or_profile="ruff",
                command=cmd,
                exit_code=proc.returncode,
                output_snippet=message,
            )

            f = Finding(
                run_id="",
                stable_fingerprint=_make_fingerprint(rel_path, rule_id, start_row),
                category=category,
                rule_id=f"ruff:{rule_id}",
                title=f"{rule_id}: {message}",
                explanation=message,
                user_impact=(
                    "The cited rule identifies a potential correctness defect; inspect its trigger and affected callers."
                    if category == FindingCategory.BUG
                    else "A code convention or maintainability issue; this observation does not establish runtime failure."
                ),
                severity=severity,
                primary_location=Location(
                    path=rel_path,
                    start_line=start_row,
                    end_line=end_row,
                    side="head",
                ),
                analysis_sources=["ruff"],
                analysis_status=AnalysisStatus.STATIC_MATCH,
                reproduction_status=ReproductionStatus.NOT_ATTEMPTED,
                patch_status=PatchStatus.NOT_REQUESTED,
                evidence_items=[ev],
                proposed_remedy=proposed_remedy,
            )
            findings.append(f)

        coverage["count"] = len(findings)
        return findings, coverage

    except Exception as exc:
        coverage["status"] = "failed"
        coverage["error"] = str(exc)
        return findings, coverage


def run_bandit(target_dir: str, rel_files: list[str] | None = None) -> tuple[list[Finding], dict[str, Any]]:
    """Run Bandit in JSON mode and normalize findings."""
    bandit_bin = _get_venv_bin("bandit")
    cmd = [bandit_bin, "-f", "json", "-q", "--ini", str(Path(__file__).with_name("bandit.ini")), "--ignore-nosec"]

    if rel_files:
        cmd.extend(rel_files)
    else:
        cmd.extend(["-r", "."])

    env = os.environ.copy()
    findings: list[Finding] = []
    coverage = {"tool": "bandit", "version": _tool_version("bandit"), "status": "executed", "count": 0, "error": None}

    try:
        proc = subprocess.run(
            cmd,
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=remaining_time(45),
        )
        if proc.returncode not in {0, 1}:
            raise ValueError("Analyzer exited unsuccessfully: " + proc.stderr[-1000:])
        raw_output = proc.stdout.strip()
        if not raw_output:
            raise ValueError("Analyzer returned no structured output")

        # Find JSON start in bandit output (it might contain main INFO lines)
        json_start = raw_output.find("{")
        if json_start == -1:
            raise ValueError("Bandit returned no JSON report")

        data = json.loads(raw_output[json_start:])
        if not isinstance(data.get("results"), list):
            raise ValueError("Bandit returned an invalid results array")
        if data.get("errors"):
            coverage["status"] = "failed"
            coverage["error"] = "Bandit could not analyze every file"
            coverage["file_errors"] = data["errors"][:100]
        results = data["results"]

        for res in results:
            test_id = res.get("test_id", "B000")
            test_name = res.get("test_name", "")
            issue_text = res.get("issue_text", "")
            issue_severity = res.get("issue_severity", "MEDIUM").lower()
            fname = res.get("filename", "")
            rel_path = _relative_source_path(fname, target_dir)
            # Filter out B101 (assert_used) in test files — assertions are standard in tests
            if test_id == "B101" and ("test" in rel_path.lower() or "/tests/" in rel_path.lower()):
                continue
            line_no = res.get("line_number", 1)
            line_range = res.get("line_range", [line_no])
            cwe = str(res.get("issue_cwe", {}).get("id", ""))
            code_snippet = res.get("code", "")

            sev_map = {
                "high": Severity.HIGH,
                "medium": Severity.MEDIUM,
                "low": Severity.LOW,
            }
            severity = sev_map.get(issue_severity, Severity.MEDIUM)

            ev = EvidenceItem(
                kind="static_analysis",
                tool_or_profile="bandit",
                command=cmd,
                exit_code=proc.returncode,
                output_snippet=code_snippet.strip() if code_snippet else issue_text,
            )

            f = Finding(
                run_id="",
                stable_fingerprint=_make_fingerprint(rel_path, test_id, line_no),
                category=FindingCategory.SECURITY,
                rule_id=f"bandit:{test_id}",
                cwe_id=f"CWE-{cwe}" if cwe else None,
                title=f"{test_name.replace('_', ' ').capitalize()}: {issue_text}",
                explanation=issue_text,
                user_impact=f"Security risk flagged by Bandit static security analyzer: {test_name}",
                severity=severity,
                primary_location=Location(
                    path=rel_path,
                    start_line=min(line_range) if line_range else line_no,
                    end_line=max(line_range) if line_range else line_no,
                    side="head",
                    snippet=code_snippet,
                ),
                analysis_sources=["bandit"],
                analysis_status=AnalysisStatus.STATIC_MATCH,
                reproduction_status=ReproductionStatus.NOT_ATTEMPTED,
                patch_status=PatchStatus.NOT_REQUESTED,
                evidence_items=[ev],
                proposed_remedy=f"Review security implications for {test_name} ({res.get('more_info', '')})",
            )
            findings.append(f)

        coverage["count"] = len(findings)
        return findings, coverage

    except Exception as exc:
        coverage["status"] = "failed"
        coverage["error"] = str(exc)
        return findings, coverage


def run_semgrep(
    target_dir: str,
    rules_path: str | None = None,
    rel_files: list[str] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Run Semgrep with pinned rules and normalize findings."""
    semgrep_bin = _get_venv_bin("semgrep")
    cmd = [semgrep_bin, "--json", "--quiet"]

    if rules_path and os.path.exists(rules_path):
        cmd.extend(["--config", rules_path])
    else:
        # Default to auto or local rules
        cmd.extend(["--config", "auto"])

    if rel_files:
        cmd.extend(rel_files)
    else:
        cmd.append(".")

    env = os.environ.copy()
    env["HOME"] = "/tmp"

    findings: list[Finding] = []
    coverage = {"tool": "semgrep", "version": "1.183.0", "status": "executed", "count": 0, "error": None}

    try:
        proc = subprocess.run(
            cmd,
            cwd=target_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=remaining_time(45),
        )
        raw_output = proc.stdout.strip()
        if not raw_output:
            return findings, coverage

        data = json.loads(raw_output)
        results = data.get("results", [])

        for res in results:
            check_id = res.get("check_id", "semgrep-rule")
            extra = res.get("extra", {})
            message = extra.get("message", "")
            metadata = extra.get("metadata", {})
            cwe = metadata.get("cwe")
            if isinstance(cwe, list) and cwe:
                cwe_str = str(cwe[0])
            elif cwe:
                cwe_str = str(cwe)
            else:
                cwe_str = None

            raw_sev = extra.get("severity", "WARNING").upper()
            sev_map = {
                "ERROR": Severity.HIGH,
                "WARNING": Severity.MEDIUM,
                "INFO": Severity.LOW,
            }
            severity = sev_map.get(raw_sev, Severity.MEDIUM)

            path = res.get("path", "")
            rel_path = os.path.relpath(path, target_dir) if os.path.isabs(path) else path
            start_line = res.get("start", {}).get("line", 1)
            end_line = res.get("end", {}).get("line", start_line)
            snippet = extra.get("lines", "")

            # Category
            category = FindingCategory.SECURITY if (cwe_str or "security" in check_id.lower()) else FindingCategory.BUG

            ev = EvidenceItem(
                kind="static_analysis",
                tool_or_profile="semgrep",
                command=cmd,
                exit_code=proc.returncode,
                output_snippet=snippet or message,
            )

            f = Finding(
                run_id="",
                stable_fingerprint=_make_fingerprint(rel_path, check_id, start_line),
                category=category,
                rule_id=f"semgrep:{check_id}",
                cwe_id=cwe_str,
                title=f"{check_id}: {message.splitlines()[0] if message else ''}",
                explanation=message,
                user_impact=f"Pattern match by Semgrep rule {check_id}",
                severity=severity,
                primary_location=Location(
                    path=rel_path,
                    start_line=start_line,
                    end_line=end_line,
                    side="head",
                    snippet=snippet,
                ),
                analysis_sources=["semgrep"],
                analysis_status=AnalysisStatus.STATIC_MATCH,
                reproduction_status=ReproductionStatus.NOT_ATTEMPTED,
                patch_status=PatchStatus.NOT_REQUESTED,
                evidence_items=[ev],
            )
            findings.append(f)

        coverage["count"] = len(findings)
        return findings, coverage

    except Exception as exc:
        coverage["status"] = "failed"
        coverage["error"] = str(exc)
        return findings, coverage


def run_all_static_analyzers(
    target_dir: str,
    run_id: str = "",
    rel_files: list[str] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Run Ruff and Bandit, deduplicating and attributing evidence."""
    all_findings: list[Finding] = []
    coverage_report: dict[str, Any] = {}

    # Run Ruff
    ruff_findings, ruff_cov = run_ruff(target_dir, rel_files)
    coverage_report["ruff"] = ruff_cov

    # Run Bandit
    bandit_findings, bandit_cov = run_bandit(target_dir, rel_files)
    coverage_report["bandit"] = bandit_cov

    # Deduplicate static findings by fingerprint
    seen_fingerprints: dict[str, Finding] = {}

    for f in ruff_findings + bandit_findings:
        f.run_id = run_id
        if f.stable_fingerprint in seen_fingerprints:
            existing = seen_fingerprints[f.stable_fingerprint]
            # Merge sources and evidence
            for src in f.analysis_sources:
                if src not in existing.analysis_sources:
                    existing.analysis_sources.append(src)
            existing.evidence_items.extend(f.evidence_items)
        else:
            seen_fingerprints[f.stable_fingerprint] = f
            all_findings.append(f)

    return all_findings, coverage_report
