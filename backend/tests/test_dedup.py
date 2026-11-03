from review.dedup import merge_signals
from review.lifecycle import stable_identity
from schemas.contracts import Disposition, EvidenceItem, Finding, FindingCategory, Location, Severity


def make(rule, line=1, source="ruff"):
    return Finding(
        run_id="test",
        stable_fingerprint="test",
        category=FindingCategory.BUG,
        rule_id=rule,
        title="Mutable default",
        explanation="Shared state",
        user_impact="Cross-call state",
        severity=Severity.MEDIUM,
        primary_location=Location(path="app.py", start_line=line, end_line=line),
        analysis_sources=[source],
        evidence_items=[
            EvidenceItem(kind="static_analysis" if source == "ruff" else "gemini_review", tool_or_profile=source)
        ],
    )


def test_known_equivalent_mutable_default_signals_share_identity():
    static = make("ruff:B006")
    model = make("proofline:python/mutable-default-argument", source="gemini_review")
    files = {"app.py": "def collect(items=[]):\n    return items\n"}
    assert stable_identity(static, files, []) == stable_identity(model, files, [])
    merge_signals(static, model)
    assert set(static.analysis_sources) == {"ruff", "gemini_review"}
    assert len(static.evidence_items) == 2
    assert len(static.verification_assessment["merged_signals"]) == 2


def test_distinct_rules_and_positions_are_not_merged():
    files = {"app.py": "first = 1\nsecond = 2\n"}
    assert stable_identity(make("ruff:B006"), files, []) != stable_identity(make("proofline:unrelated-bug"), files, [])
    assert stable_identity(make("ruff:B006"), files, []) != stable_identity(make("ruff:B006", line=2), files, [])


def test_disagreement_is_visible_and_static_observation_remains_open():
    first = make("ruff:B006")
    first.evidence_status = "source_supported"
    second = make("proofline:mutable-default", source="gemini_review")
    second.evidence_status = "refuted"
    second.disposition = Disposition.DISMISSED
    merge_signals(first, second)
    assert first.evidence_status == "insufficient_evidence"
    assert first.disposition == Disposition.OPEN
    assert any("disagree" in limitation for limitation in first.limitations)


def test_conflicting_assessment_is_not_erased_by_a_later_supporting_signal():
    first = make("ruff:B006")
    first.evidence_status = "source_supported"
    other = make("proofline:mutable-default", source="gemini_review")
    other.evidence_status = "refuted"
    merge_signals(first, other)
    final = make("proofline:mutable-default-argument", source="gemini_review")
    final.evidence_status = "source_supported"
    merge_signals(first, final)
    assert first.evidence_status == "insufficient_evidence"


def test_actual_pipeline_merges_known_static_and_model_duplicate(tmp_path):
    from providers.fake import FakeLLMProvider
    from review.harness import RunConfig
    from review.orchestrator import ReviewOrchestrator

    (tmp_path / "app.py").write_text("def collect(item, items=[]):\n    items.append(item)\n    return items\n")
    provider = FakeLLMProvider()
    provider.register_response(
        "project_review",
        {
            "review_summary": "Mutable state is shared across calls",
            "findings": [
                {
                    "category": "bug",
                    "rule_id": "python/mutable-default-argument",
                    "title": "Shared default list",
                    "explanation": "Repeated calls reuse the default list",
                    "user_impact": "Items from earlier calls remain",
                    "severity": "medium",
                    "primary_location": {"path": "app.py", "start_line": 1, "end_line": 1},
                    "trigger_condition": "Call collect without an items argument twice",
                    "proposed_remedy": "Use None and initialize per call",
                }
            ],
        },
    )
    run, findings = ReviewOrchestrator(provider=provider, run_config=RunConfig(strategy="context")).execute_review(
        str(tmp_path), local_dir=str(tmp_path)
    )
    merged = [f for f in findings if "ruff" in f.analysis_sources and "gemini_review" in f.analysis_sources]
    assert run.status.value == "completed", run.errors
    assert len(merged) == 1
    assert len([f for f in findings if f.rule_id == "ruff:B006" or "mutable-default" in f.rule_id]) == 1
    assert len(merged[0].evidence_items) >= 2


def test_relative_indentation_is_preserved_in_location_validation():
    from review.dedup import snippet_matches_location

    source = "def trim(values):\n    for key in values:\n        if values[key] is None:\n            del values[key]\n"
    quote = "for key in values:\n    if values[key] is None:\n        del values[key]"
    assert snippet_matches_location(quote, source, 2, 4)
    assert not snippet_matches_location(quote, source, 1, 3)
    assert not snippet_matches_location(quote.replace("None", "False"), source, 2, 4)
    assert not snippet_matches_location(quote.replace("    if", "if"), source, 2, 4)


def test_pipeline_keeps_dedented_quote_and_exposes_fabricated_quote(tmp_path):
    from providers.fake import FakeLLMProvider
    from review.harness import RunConfig
    from review.orchestrator import ReviewOrchestrator

    source = (
        "def prune(values):\n    for key in values:\n        if values[key] is None:\n            del values[key]\n"
    )
    (tmp_path / "app.py").write_text(source)
    candidate = {
        "category": "bug",
        "rule_id": "mapping-mutation",
        "title": "Mutation during iteration",
        "explanation": "Deleting a key invalidates iteration",
        "user_impact": "Raises during pruning",
        "severity": "high",
        "primary_location": {
            "path": "app.py",
            "start_line": 2,
            "end_line": 4,
            "snippet": "for key in values:\n    if values[key] is None:\n        del values[key]",
        },
        "trigger_condition": "A dict contains None values",
        "proposed_remedy": "Iterate over copied keys",
    }
    provider = FakeLLMProvider()
    provider.register_response("project_review", {"review_summary": "Mapping regression", "findings": [candidate]})
    run, findings = ReviewOrchestrator(provider=provider, run_config=RunConfig(strategy="context")).execute_review(
        str(tmp_path), local_dir=str(tmp_path)
    )
    assert any(f.rule_id == "proofline:mapping-mutation" for f in findings)
    assert not run.coverage["validation_rejections"]
    candidate["primary_location"]["snippet"] = "invented_source()"
    provider = FakeLLMProvider()
    provider.register_response("project_review", {"review_summary": "Bad quotation", "findings": [candidate]})
    run, findings = ReviewOrchestrator(provider=provider, run_config=RunConfig(strategy="context")).execute_review(
        str(tmp_path), local_dir=str(tmp_path)
    )
    assert not any(f.rule_id == "proofline:mapping-mutation" for f in findings)
    assert run.status.value == "partial"
    assert run.coverage["validation_rejections"][0]["reason"] == "Quotation does not match its cited source range"
