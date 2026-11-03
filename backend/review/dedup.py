"""Conservative equivalence for known duplicate rules; retain every underlying signal."""

import re
import textwrap

from schemas.contracts import AnalysisStatus, Disposition, Severity

# Only explicit known aliases are merged. Similar prose is not sufficient evidence.
_EQUIVALENT = {
    "ruff:B006": "python:mutable-default",
    "js:async-foreach": "javascript:async-foreach",
}
_MODEL_ALIASES = {
    "mutabledefaultargument": "python:mutable-default",
    "pythonmutabledefaultargument": "python:mutable-default",
    "mutabledefault": "python:mutable-default",
    "asyncforeach": "javascript:async-foreach",
    "javascriptasyncforeach": "javascript:async-foreach",
    "typescriptasyncforeach": "javascript:async-foreach",
}


def canonical_rule(rule):
    if rule in _EQUIVALENT:
        return _EQUIVALENT[rule]
    if rule.startswith("proofline:"):
        normalized = re.sub("[^a-z0-9]", "", rule.removeprefix("proofline:").lower())
        return _MODEL_ALIASES.get(normalized, rule)
    return rule


def merge_signals(existing, other):
    """Called only for equivalent family/category/source-position identities."""
    previous = list(existing.analysis_sources)
    for source in other.analysis_sources:
        if source not in existing.analysis_sources:
            existing.analysis_sources.append(source)
    ids = {e.id for e in existing.evidence_items}
    existing.evidence_items.extend(e for e in other.evidence_items if e.id not in ids)
    for field in ("assumptions", "limitations"):
        setattr(existing, field, list(dict.fromkeys(getattr(existing, field) + getattr(other, field))))
    for location in other.related_locations:
        if location not in existing.related_locations:
            existing.related_locations.append(location)
    assessments = existing.verification_assessment.setdefault("merged_signals", [])
    if not assessments:
        assessments.append(
            {"rule_id": existing.rule_id, "sources": previous, "evidence_status": existing.evidence_status}
        )
    assessments.append(
        {
            "rule_id": other.rule_id,
            "sources": other.analysis_sources,
            "evidence_status": other.evidence_status,
            "assessment": other.verification_assessment,
        }
    )
    if (
        any(source in other.analysis_sources for source in ("gemini_review", "codex_cli_review"))
        and other.explanation != existing.explanation
    ):
        existing.explanation += "\nContextual assessment: " + other.explanation
        existing.user_impact = other.user_impact
        existing.proposed_remedy = other.proposed_remedy or existing.proposed_remedy
    priority = {
        s: i for i, s in enumerate((Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO))
    }
    if priority[other.severity] < priority[existing.severity]:
        existing.severity = other.severity
    states = {item["evidence_status"] for item in assessments} | {existing.evidence_status, other.evidence_status}
    if {"source_supported", "refuted"} <= states:
        existing.evidence_status = "insufficient_evidence"
        existing.analysis_status = AnalysisStatus.DISPUTED
        message = "Equivalent detector assessments disagree; developer review required"
        if message not in existing.limitations:
            existing.limitations.append(message)
    elif "source_supported" in states:
        existing.evidence_status = "source_supported"
    elif "refuted" in states:
        existing.evidence_status = "refuted"
    elif "insufficient_evidence" in states:
        existing.evidence_status = "insufficient_evidence"
    if any(source in existing.analysis_sources for source in ("ruff", "bandit", "proofline-language")):
        existing.disposition = Disposition.OPEN


def consolidate_signature_findings(findings):
    """Merge only a model signature claim citing the same deterministic call AND callee.

    Caller-specific anchors stay separate, so separate repair sites are not hidden.
    """
    anchors = [f for f in findings if f.rule_id in {"python:changed-signature", "js:changed-signature"}]
    removed = set()
    for model in findings:
        normalized = re.sub("[^a-z]", "", model.rule_id.lower())
        if not model.rule_id.startswith("proofline:") or not any(
            family in normalized for family in ("requiredparameter", "missingargument", "changedsignature")
        ):
            continue
        citations = model.verification_assessment.get("citations", [])
        sites = {(c.get("path"), c.get("start_line")) for c in citations}
        sites.add((model.primary_location.path, model.primary_location.start_line))
        matches = []
        for anchor in anchors:
            call_site = (anchor.primary_location.path, anchor.primary_location.start_line)
            callee_sites = {
                (loc.path, line)
                for loc in anchor.related_locations
                if loc.relationship == "callee"
                for line in loc.lines
            }
            if model.category == anchor.category and call_site in sites and sites & callee_sites:
                matches.append(anchor)
        if len(matches) == 1:
            anchor = matches[0]
            anchor.verification_assessment.setdefault("consolidated_finding_ids", []).append(model.id)
            merge_signals(anchor, model)
            removed.add(model.id)
    return [f for f in findings if f.id not in removed]


def snippet_matches_location(snippet, source, start, end):
    """Allow a uniformly dedented quotation only inside its declared source span."""
    if not snippet or not snippet.strip():
        return True
    lines = source.splitlines()
    if start < 1 or end < start or end > len(lines):
        return False
    quoted = textwrap.dedent(snippet).strip("\n").rstrip()
    selected = "\n".join(lines[start - 1 : end])
    if snippet.strip() in selected:
        return True
    return quoted == textwrap.dedent(selected).strip("\n").rstrip()


def consolidate_compiler_findings(findings):
    """Known semantic aliases at one compiler diagnostic site; never merge prose similarity."""
    aliases = {
        "typescripttypemismatch": "js:type-2322",
        "tstypemismatch": "js:type-2322",
        "nullinputruntimeerror": "js:type-18047",
    }
    removed = set()
    for model in findings:
        if not model.rule_id.startswith("proofline:"):
            continue
        family = re.sub("[^a-z0-9]", "", model.rule_id.removeprefix("proofline:").lower())
        rule = aliases.get(family)
        if not rule:
            continue
        anchors = [
            f
            for f in findings
            if f.rule_id == rule
            and f.category == model.category
            and f.primary_location.path == model.primary_location.path
            and f.primary_location.start_line == model.primary_location.start_line
            and f.primary_location.end_line == model.primary_location.end_line
        ]
        if len(anchors) != 1:
            continue
        anchor = anchors[0]
        anchor.verification_assessment.setdefault("consolidated_finding_ids", []).append(model.id)
        merge_signals(anchor, model)
        removed.add(model.id)
    return [f for f in findings if f.id not in removed]
