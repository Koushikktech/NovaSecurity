"""Cross-run finding continuity without treating incomplete review as resolution."""

import hashlib
import json

from schemas.contracts import Disposition

from .dedup import canonical_rule


def stable_identity(finding, files, symbols):
    loc = finding.primary_location
    content = files.get(loc.path, "").splitlines()
    line = content[loc.start_line - 1].strip() if 0 < loc.start_line <= len(content) else ""
    owners = [s for s in symbols if s["path"] == loc.path and s["start"] <= loc.start_line <= s["end"]]
    owner = min(owners, key=lambda s: s["end"] - s["start"])["name"] if owners else "module"
    return hashlib.sha256(
        json.dumps([loc.path, owner, finding.category.value, canonical_rule(finding.rule_id), line]).encode()
    ).hexdigest()[:24]


def reconcile(run, findings, previous, previous_findings):
    old = {f.stable_fingerprint: f for f in previous_findings}
    current = {f.stable_fingerprint: f for f in findings}
    changes = []
    for fingerprint, finding in current.items():
        former = old.get(fingerprint)
        if former and former.disposition == Disposition.DISMISSED:
            finding.disposition = former.disposition
            finding.disposition_reason = former.disposition_reason
        changes.append(
            {
                "finding_id": finding.id,
                "previous_finding_id": former.id if former else None,
                "state": "persisting" if former else "new",
                "fingerprint": fingerprint,
            }
        )
    for fingerprint, former in old.items():
        if fingerprint in current:
            continue
        tool = former.rule_id.split(":")[0]
        covered = (
            tool in {"ruff", "bandit"}
            and run.coverage.get("static_tools", {}).get(tool, {}).get("status") == "executed"
            and former.primary_location.path in run.coverage.get("source_files", [])
            and former.primary_location.path not in run.coverage.get("excluded_files", [])
        )
        changes.append(
            {
                "previous_finding_id": former.id,
                "fingerprint": fingerprint,
                "state": "resolved_static_rule" if covered else "not_redetected",
                "reason": "Deterministic rule completed without this match"
                if covered
                else "Absence is not proof of resolution",
            }
        )
    run.coverage["finding_lifecycle"] = {"previous_run_id": previous.id if previous else None, "changes": changes}
