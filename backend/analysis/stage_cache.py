"""Replay deterministic analyzer stages only for matching source, tools and implementation."""

import importlib.metadata
import uuid
from pathlib import Path

from analysis.cache import AnalysisCache
from analysis.static_tools import run_all_static_analyzers
from schemas.contracts import Finding


def cached_static_analysis(directory, files, run_id, event=None):
    root = Path(__file__).parent
    implementation = (
        b"".join(path.read_bytes() for path in sorted(root.glob("static*.py"))) + (root / "bandit.ini").read_bytes()
    )
    versions = {}
    for tool in ("ruff", "bandit"):
        try:
            versions[tool] = importlib.metadata.version(tool)
        except importlib.metadata.PackageNotFoundError:
            versions[tool] = "unavailable"
    key = {"files": [(f["relative_path"], f["content"]) for f in files], "tools": versions}
    cache = AnalysisCache("static-stage-v1", implementation, key)
    saved = cache.read()
    if saved is None:
        findings, coverage = run_all_static_analyzers(directory, run_id=run_id)
        if not any(v.get("status") == "failed" for v in coverage.values()):
            cache.write(
                {"findings": [f.model_dump() for f in findings], "coverage": coverage, "original_run_id": run_id}
            )
        return findings, coverage
    findings = [Finding.model_validate(item) for item in saved["findings"]]
    for finding in findings:
        finding.id = str(uuid.uuid4())
        finding.run_id = run_id
        for evidence in finding.evidence_items:
            evidence.id = str(uuid.uuid4())
            evidence.kind = "cached_static_analysis"
    for tool in saved["coverage"].values():
        tool["cache_reused"] = True
        tool["original_run_id"] = saved.get("original_run_id", "unrecorded")
    if event:
        event({"event_type": "checkpoint_restored", "stage": "static_analysis", "cache_key": cache.path.stem})
    return findings, saved["coverage"]
