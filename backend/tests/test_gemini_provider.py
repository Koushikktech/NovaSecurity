from __future__ import annotations

from providers.fake import FakeLLMProvider
from schemas.provider import (
    CandidateFinding,
    CandidateLocation,
    ReviewCandidatesResult,
    StructuredGenerationRequest,
)


def test_fake_provider_structured_generation():
    provider = FakeLLMProvider()

    req = StructuredGenerationRequest(
        run_id="run-123",
        stage="review",
        model_role="review",
        system_instruction="Analyze code",
        context="print('hello')",
    )

    resp = provider.generate_structured(req, ReviewCandidatesResult)
    assert resp.success is True
    assert resp.data is not None
    assert isinstance(resp.data, ReviewCandidatesResult)
    assert resp.usage.total_tokens > 0


def test_fake_provider_registered_canned_response():
    provider = FakeLLMProvider()

    canned = ReviewCandidatesResult(
        findings=[
            CandidateFinding(
                category="security",
                rule_id="CWE-89",
                cwe_id="CWE-89",
                title="SQL Injection",
                explanation="Raw f-string query execution",
                user_impact="Data leakage",
                severity="critical",
                primary_location=CandidateLocation(
                    path="repositories/expenses.py",
                    start_line=15,
                    end_line=16,
                ),
                trigger_condition="User input in search query",
                proposed_remedy="Use parameterized queries",
            )
        ],
        review_summary="Found 1 SQL injection",
    )
    provider.register_response("review", canned)

    req = StructuredGenerationRequest(
        run_id="run-456",
        stage="review",
        model_role="review",
        system_instruction="",
        context="",
    )

    resp = provider.generate_structured(req, ReviewCandidatesResult)
    assert resp.success is True
    assert len(resp.data.findings) == 1
    assert resp.data.findings[0].rule_id == "CWE-89"


def test_fake_provider_error_and_timeout_simulation():
    provider = FakeLLMProvider()
    provider.simulate_error = "Rate limit 429 quota exceeded"

    req = StructuredGenerationRequest(
        run_id="run-err",
        stage="review",
        model_role="review",
        system_instruction="",
        context="",
    )
    resp = provider.generate_structured(req, ReviewCandidatesResult)
    assert resp.success is False
    assert "quota exceeded" in resp.error

    provider.simulate_error = None
    provider.simulate_timeout = True
    resp_timeout = provider.generate_structured(req, ReviewCandidatesResult)
    assert resp_timeout.success is False
    assert "Timeout" in resp_timeout.error


def test_native_gemini_adapter_validates_response_without_network(monkeypatch):
    from types import SimpleNamespace

    from providers.gemini import GeminiProvider
    from schemas.provider import ReviewCandidatesResult, StructuredGenerationRequest

    provider = GeminiProvider(api_key="not-a-real-key", default_model="test-model", api_mode="generate_content")
    response = SimpleNamespace(
        text='{"findings":[],"review_summary":"No supported issues"}', usage_metadata=None, candidates=[]
    )
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: response))
    result = provider.generate_structured(
        StructuredGenerationRequest(
            run_id="r", stage="review", model_role="review", system_instruction="review", context="safe source"
        ),
        ReviewCandidatesResult,
    )
    assert result.success and result.data.review_summary == "No supported issues"


def test_native_adapter_rejects_truncated_response(monkeypatch):
    from types import SimpleNamespace

    from config import settings
    from providers.gemini import GeminiProvider
    from schemas.provider import ReviewCandidatesResult, StructuredGenerationRequest

    monkeypatch.setattr(settings, "llm_max_attempts", 1)
    provider = GeminiProvider(api_key="not-a-real-key", default_model="test-model", api_mode="generate_content")
    response = SimpleNamespace(
        text='{"findings":[]}',
        usage_metadata=None,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name="MAX_TOKENS"))],
    )
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: response))
    result = provider.generate_structured(
        StructuredGenerationRequest(
            run_id="r", stage="review", model_role="review", system_instruction="review", context="source"
        ),
        ReviewCandidatesResult,
    )
    assert not result.success
