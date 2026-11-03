from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from providers.gemini import GeminiProvider, provider_retry_delay
from schemas.provider import StructuredGenerationRequest


class Answer(BaseModel):
    answer: str


def request():
    return StructuredGenerationRequest(
        run_id="transport-test",
        stage="review",
        model_role="review",
        system_instruction="Review supplied source",
        context="safe source",
        deadline_ms=2000,
        max_output_tokens=512,
    )


def provider(generate, **options):
    result = GeminiProvider(api_key="test", default_model="gemini-3-transport-test", max_attempts=1, **options)
    result._client = SimpleNamespace(interactions=SimpleNamespace(create=generate))
    return result


def test_interactions_are_stateless_bounded_and_account_for_thought_tokens():
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output_text='{"answer":"ok"}',
            usage=SimpleNamespace(
                total_input_tokens=10,
                total_output_tokens=4,
                total_tokens=20,
                total_cached_tokens=3,
                total_thought_tokens=6,
            ),
        )

    engine = provider(generate, thinking="low")
    result = engine.generate_structured(request(), Answer)
    assert result.success and result.data.answer == "ok"
    call = calls[0]
    assert call["store"] is False and call["automatic_continuation"] is False
    assert call["background"] is False and call["stream"] is False
    assert "tools" not in call and "previous_interaction_id" not in call
    assert 0 < call["timeout"] <= 2
    assert call["generation_config"] == {"max_output_tokens": 512, "thinking_level": "low"}
    assert call["response_format"]["schema"] == Answer.model_json_schema()
    assert result.usage.model_dump(exclude={"cost_estimated_usd"}) == {
        "prompt_tokens": 10,
        "candidate_tokens": 4,
        "total_tokens": 20,
        "cached_content_token_count": 3,
        "thought_tokens": 6,
    }
    assert engine.api_log[-1]["api_mode"] == "interactions"


@pytest.mark.parametrize("status", ["in_progress", "requires_action", "requires_continuation", "failed", None])
def test_incomplete_interaction_never_passes_even_with_valid_json(status):
    engine = provider(
        lambda **kw: SimpleNamespace(
            status=status, output_text='{"answer":"ok"}', usage=SimpleNamespace(total_tokens=11)
        )
    )
    result = engine.generate_structured(request(), Answer)
    assert not result.success and "INTERACTION_" in result.error
    assert result.usage.total_tokens == 11
    assert engine.api_attempts == 1


def test_interactions_never_return_thought_text_as_structured_answer():
    engine = provider(
        lambda **kw: SimpleNamespace(
            status="completed",
            usage=None,
            steps=[
                SimpleNamespace(type="thought", content=[SimpleNamespace(type="text", text='{"answer":"private"}')]),
                SimpleNamespace(
                    type="model_output", content=[SimpleNamespace(type="text", text='{"answer":"public"}')]
                ),
            ],
        )
    )
    result = engine.generate_structured(request(), Answer)
    assert result.success and result.data.answer == "public"
    assert "private" not in result.raw_text


def test_interactions_validation_rejects_wrong_shape():
    engine = provider(lambda **kw: SimpleNamespace(status="completed", output_text='{"wrong":true}', usage=None))
    assert not engine.generate_structured(request(), Answer).success


def test_transport_selection_preserves_classic_compatibility():
    engine = provider(lambda **kw: None)
    assert engine._api_for_model("gemini-2.5-flash") == "generate_content"
    assert engine._api_for_model("gemini-3.8-flash") == "interactions"
    engine.api_mode = "generate_content"
    assert engine._api_for_model("gemini-3.8-flash") == "generate_content"


def test_interactions_http_errors_do_not_retry_permanent_failure():
    class StatusError(Exception):
        status_code = 404
        body = {"error": {"message": "model retired"}}

    def generate(**kw):
        raise StatusError("model retired")

    engine = provider(generate)
    engine.max_attempts = 3
    result = engine.generate_structured(request(), Answer)
    assert not result.success and engine.api_attempts == 1
    assert engine.api_log[-1]["error_code"] == 404
    assert engine.api_log[-1]["retryable"] is False
    error = StatusError()
    error.body = {"error": {"details": [{"@type": "google.rpc.RetryInfo", "retryDelay": "60s"}]}}
    assert provider_retry_delay(error) == (60, None)


def test_historic_resume_does_not_silently_switch_transport():
    from review.harness import RunConfig

    assert RunConfig().api_mode == "auto"
    assert RunConfig.model_validate({"version": "3"}).api_mode == "generate_content"
    assert RunConfig.model_validate({"version": "3", "api_mode": "interactions"}).api_mode == "interactions"


def test_incompatible_thinking_is_rejected_before_api_attempt():
    engine = provider(lambda **kw: pytest.fail("must not contact provider"), api_mode="interactions", thinking="low")
    engine.default_model = engine.override_model = "gemini-2.5-flash"
    result = engine.generate_structured(request(), Answer)
    assert not result.success and engine.api_attempts == 0
    assert "require generate_content" in result.error
