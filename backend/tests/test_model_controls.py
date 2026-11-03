from types import SimpleNamespace

from pydantic import BaseModel

from providers.gemini import GeminiProvider
from schemas.provider import StructuredGenerationRequest


def test_thinking_settings_are_model_specific():
    provider = GeminiProvider(
        api_mode="generate_content", api_key="test", default_model="gemini-2.5-flash", thinking="low"
    )
    assert provider._thinking_config("gemini-2.5-flash").thinking_budget == 1024
    assert provider._thinking_config("gemini-3-pro-preview").thinking_level == "LOW"
    assert provider._select_model("patch") == "gemini-2.5-flash"


def test_model_activity_counts_failed_and_successful_attempts(monkeypatch):
    class Answer(BaseModel):
        answer: str

    events = []
    provider = GeminiProvider(
        api_mode="generate_content",
        api_key="test",
        default_model="gemini-2.5-flash",
        max_attempts=2,
        event_callback=events.append,
    )
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("temporary unavailable")
        return SimpleNamespace(
            text='{"answer":"ok"}', candidates=[], usage_metadata=SimpleNamespace(total_token_count=12)
        )

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr("providers.gemini.time.sleep", lambda _: None)
    request = StructuredGenerationRequest(
        run_id="test", stage="review", system_instruction="test", context="test", model_role="review"
    )
    result = provider.generate_structured(request, Answer)
    assert result.success
    state = events[-1]["model_activity"]
    assert state["attempts"] == 2 and state["failures"] == 1 and state["tokens"] == 12
    assert [e["state"] for e in state["log"]] == ["requesting", "failed", "retry_scheduled", "requesting", "succeeded"]


def test_usage_includes_truncated_attempt_and_transport_retries_disabled(monkeypatch):
    class Answer(BaseModel):
        answer: str

    provider = GeminiProvider(
        api_mode="generate_content", api_key="test", default_model="gemini-2.5-flash", max_attempts=2
    )
    calls = []

    def generate(**kwargs):
        config = kwargs["config"]
        assert config.http_options.retry_options.attempts == 1
        assert 0 < config.http_options.timeout <= 1000
        calls.append(kwargs)
        reason = "MAX_TOKENS" if len(calls) == 1 else "STOP"
        return SimpleNamespace(
            text='{"answer":"ok"}',
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))],
            usage_metadata=SimpleNamespace(total_token_count=10),
        )

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr("providers.gemini.time.sleep", lambda _: None)
    request = StructuredGenerationRequest(
        run_id="test", stage="review", model_role="review", context="test", system_instruction="test", deadline_ms=1000
    )
    result = provider.generate_structured(request, Answer)
    assert result.success and result.usage.total_tokens == 20 and provider.api_tokens == 20
    assert result.retries == 1


def test_zero_deadline_does_not_contact_provider():
    class Answer(BaseModel):
        answer: str

    provider = GeminiProvider(api_mode="generate_content", api_key="test", default_model="gemini-2.5-flash")
    request = StructuredGenerationRequest(
        run_id="test", stage="review", model_role="review", context="test", system_instruction="test", deadline_ms=0
    )
    result = provider.generate_structured(request, Answer)
    assert not result.success and provider.api_attempts == 0


def test_retry_window_is_read_from_structured_provider_error():
    from google.genai.errors import APIError

    from providers.gemini import provider_retry_delay

    error = APIError(
        429,
        {
            "error": {
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "49.5s"},
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [
                            {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "quotaValue": "5"}
                        ],
                    },
                ]
            }
        },
    )
    assert provider_retry_delay(error) == (49.5, 5)


def test_daily_quota_defers_without_another_network_attempt(monkeypatch):
    from google.genai.errors import APIError

    class Answer(BaseModel):
        answer: str

    events = []
    provider = GeminiProvider(
        api_mode="generate_content",
        api_key="test",
        default_model="gemini-3-quota-test",
        max_attempts=2,
        event_callback=events.append,
    )

    def generate(**kwargs):
        raise APIError(
            429, {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "3600s"}]}}
        )

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    monkeypatch.setattr("providers.gemini.time.sleep", lambda _: None)
    request = StructuredGenerationRequest(
        run_id="test", stage="review", model_role="review", context="test", system_instruction="test", deadline_ms=1000
    )
    result = provider.generate_structured(request, Answer)
    assert not result.success and provider.api_attempts == 1
    assert "cooldown" in result.error
    assert events[-1]["model_activity"]["log"][-1]["state"] == "deferred"


def test_parallel_providers_reserve_model_quota_atomically(monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    class Answer(BaseModel):
        answer: str

    monkeypatch.setenv("PROOFLINE_MODEL_REQUESTS_PER_MINUTE", "1")
    barrier = threading.Barrier(2)
    calls = []

    def execute(_):
        provider = GeminiProvider(
            api_mode="generate_content", api_key="test", default_model="gemini-3-concurrency-test", max_attempts=1
        )

        def generate(**kwargs):
            calls.append(1)
            return SimpleNamespace(text='{"answer":"ok"}', candidates=[], usage_metadata=None)

        provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
        barrier.wait()
        return provider.generate_structured(
            StructuredGenerationRequest(
                run_id="test",
                stage="review",
                model_role="review",
                context="test",
                system_instruction="test",
                deadline_ms=500,
            ),
            Answer,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, range(2)))
    assert len(calls) == 1
    assert sum(result.success for result in results) == 1
    assert any("cooldown" in (result.error or "") for result in results)


def test_cancelled_review_never_contacts_provider():
    class Answer(BaseModel):
        answer: str

    provider = GeminiProvider(api_mode="generate_content", api_key="test", default_model="gemini-2.5-flash")
    provider.cancelled = lambda: True
    result = provider.generate_structured(
        StructuredGenerationRequest(
            run_id="test", stage="review", model_role="review", context="test", system_instruction="test"
        ),
        Answer,
    )
    assert not result.success and provider.api_attempts == 0
    assert "cancelled" in result.error
