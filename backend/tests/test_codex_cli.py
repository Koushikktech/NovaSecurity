import json
import sys
import time
from pathlib import Path

import pytest
from pydantic import BaseModel

from providers.codex_cli import CodexCLIProvider, cli_environment, run_codex, strict_schema
from schemas.provider import ReviewCandidatesResult, StructuredGenerationRequest


@pytest.fixture
def available(monkeypatch):
    monkeypatch.setattr("providers.codex_cli.codex_default_model", lambda: "gpt-test")
    monkeypatch.setattr("providers.codex_cli.codex_status", lambda: {"installed": True, "chatgpt_signed_in": True})


def request():
    return StructuredGenerationRequest(
        run_id="test",
        stage="review",
        model_role="review",
        system_instruction="Review",
        context="source",
        deadline_ms=5000,
    )


def fake_run(payload=None, completed=True, native=False):
    def run(command, cwd, prompt, deadline, cancelled, event):
        assert "--ignore-user-config" in command and "--ephemeral" in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert "--dangerously-bypass-approvals-and-sandbox" not in command
        assert Path(cwd).is_dir() and not list(Path(cwd).iterdir())
        assert "source" not in command
        schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
        assert schema["additionalProperties"] is False
        Path(command[command.index("--output-last-message") + 1]).write_text(
            payload or '{"findings":[],"review_summary":"Ready"}'
        )
        if native:
            event({"type": "item.started", "item": {"type": "command_execution", "command": "not allowed"}})
        if completed:
            event(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 20,
                        "output_tokens": 30,
                        "reasoning_output_tokens": 10,
                    },
                }
            )
        else:
            event({"type": "turn.failed", "error": {"message": "Subscription usage limit reached"}})
        return 0, ""

    return run


def test_native_subscription_adapter_structured_output_and_usage(available, monkeypatch):
    monkeypatch.setattr("providers.codex_cli.run_codex", fake_run())
    events = []
    engine = CodexCLIProvider(enabled=True, max_attempts=1, event_callback=events.append)
    result = engine.generate_structured(request(), ReviewCandidatesResult)
    assert result.success and result.data.review_summary == "Ready"
    assert result.usage.total_tokens == 130 and result.usage.cached_content_token_count == 20
    assert result.usage.thought_tokens == 10
    assert events[-1]["model_activity"]["provider"] == "codex_cli"
    assert events[-1]["model_activity"]["attempts"] == 1
    assert events[-1]["model_activity"]["log"][-1]["api_mode"] == "codex_cli"


@pytest.mark.parametrize("payload", ['{"findings":"invalid"}', "not json"])
def test_invalid_output_remains_failed_and_preserves_billed_usage(available, monkeypatch, payload):
    monkeypatch.setattr("providers.codex_cli.run_codex", fake_run(payload))
    result = CodexCLIProvider(enabled=True).generate_structured(request(), ReviewCandidatesResult)
    assert not result.success and result.usage.total_tokens == 130


def test_failed_turn_cannot_pass_with_json_and_usage_limits_do_not_retry(available, monkeypatch):
    monkeypatch.setattr("providers.codex_cli.run_codex", fake_run(completed=False))
    engine = CodexCLIProvider(enabled=True, max_attempts=3)
    result = engine.generate_structured(request(), ReviewCandidatesResult)
    assert not result.success and engine.api_attempts == 1
    assert "usage limit" in result.error.lower()


def test_native_tool_activity_never_counts_as_a_proofline_review(available, monkeypatch):
    monkeypatch.setattr("providers.codex_cli.run_codex", fake_run(native=True))
    result = CodexCLIProvider(enabled=True).generate_structured(request(), ReviewCandidatesResult)
    assert not result.success and "Native Codex tool activity" in result.error


def test_subscription_mode_never_falls_back_to_api_key_auth(monkeypatch):
    monkeypatch.setattr("providers.codex_cli.codex_default_model", lambda: "gpt-test")
    monkeypatch.setattr("providers.codex_cli.codex_status", lambda: {"installed": True, "chatgpt_signed_in": False})
    monkeypatch.setattr("providers.codex_cli.run_codex", lambda *a: pytest.fail("must not launch"))
    result = CodexCLIProvider(enabled=True).generate_structured(request(), ReviewCandidatesResult)
    assert not result.success and "API-key fallback is disabled" in result.error


def test_backend_keys_are_not_inherited_by_cli(monkeypatch):
    for key in ("GEMINI_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.setenv(key, "test-secret-only")
    assert all(
        key not in cli_environment()
        for key in ("GEMINI_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL")
    )


def test_cancelled_and_zero_deadline_requests_never_launch(available, monkeypatch):
    monkeypatch.setattr("providers.codex_cli.run_codex", lambda *a: pytest.fail("must not launch"))
    engine = CodexCLIProvider(enabled=True)
    engine.cancelled = lambda: True
    assert not engine.generate_structured(request(), ReviewCandidatesResult).success
    engine.cancelled = None
    assert not engine.generate_structured(
        request().model_copy(update={"deadline_ms": 0}), ReviewCandidatesResult
    ).success
    assert engine.api_attempts == 0


def test_strict_schema_requires_nested_defaults_without_mutating_pydantic():
    class Child(BaseModel):
        value: str | None = None

    class Root(BaseModel):
        children: list[Child] = []

    converted = strict_schema(Root)
    assert converted["required"] == ["children"]
    assert converted["$defs"]["Child"]["required"] == ["value"]
    assert converted["$defs"]["Child"]["additionalProperties"] is False
    assert "default" in Root.model_json_schema()["$defs"]["Child"]["properties"]["value"]


def test_process_deadline_and_cancellation_stop_the_invocation(tmp_path):
    prompt = tmp_path / "prompt"
    prompt.write_text("test")
    command = [sys.executable, "-c", "import time; time.sleep(10)"]
    with pytest.raises(TimeoutError):
        run_codex(command, tmp_path, prompt, time.monotonic() + 0.05, None, lambda e: None)
    with pytest.raises(ValueError, match="cancelled"):
        run_codex(command, tmp_path, prompt, time.monotonic() + 5, lambda: True, lambda e: None)


def test_nonfatal_cli_startup_diagnostic_does_not_erase_completed_output(available, monkeypatch):
    original = fake_run()

    def with_warning(command, cwd, prompt, deadline, cancelled, event):
        event({"type": "item.completed", "item": {"type": "error", "message": "Native optional tool disabled"}})
        return original(command, cwd, prompt, deadline, cancelled, event)

    monkeypatch.setattr("providers.codex_cli.run_codex", with_warning)
    engine = CodexCLIProvider(enabled=True)
    result = engine.generate_structured(request(), ReviewCandidatesResult)
    assert result.success and result.usage.total_tokens == 130
    assert engine.api_log[-1]["warning"] == "Native optional tool disabled"


def test_quota_stops_later_roles_in_same_run(available, monkeypatch):
    calls = []
    delegate = fake_run(completed=False)

    def limited(*args):
        calls.append(1)
        return delegate(*args)

    monkeypatch.setattr("providers.codex_cli.run_codex", limited)
    provider = CodexCLIProvider(enabled=True, max_attempts=3)
    first = provider.generate_structured(request(), ReviewCandidatesResult)
    second = provider.generate_structured(
        request().model_copy(update={"model_role": "verify_reasoning"}), ReviewCandidatesResult
    )
    assert not first.success and not second.success
    assert first.error == second.error
    assert len(calls) == 1 and provider.api_attempts == 1
    assert second.usage.total_tokens == 0
