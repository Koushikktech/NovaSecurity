from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import TypeVar

from google import genai
from google.genai import types
from google.genai.errors import APIError
from pydantic import BaseModel

from config import settings
from ingestion.redactor import redact_secrets
from schemas.events import ModelActivity, ModelAttempt
from schemas.provider import ProviderResponse, ProviderUsage

from .base import BaseLLMProvider
from .interactions_adapter import request_interaction

T = TypeVar("T", bound=BaseModel)
_RATE_LOCK = threading.Lock()
_MODEL_REQUESTS = {}
_MODEL_COOLDOWN = {}
_MODEL_RPM = {}


def provider_retry_delay(error):
    details = getattr(error, "details", None) or getattr(error, "body", {})
    entries = details.get("error", details).get("details", []) if isinstance(details, dict) else []
    delay = 0.0
    rpm = None
    for entry in entries:
        if entry.get("@type", "").endswith("RetryInfo"):
            try:
                delay = float(str(entry.get("retryDelay", "0s")).removesuffix("s"))
            except ValueError:
                pass
        for violation in entry.get("violations", []):
            if "PerMinute" in violation.get("quotaId", ""):
                try:
                    rpm = int(violation.get("quotaValue", 0)) or None
                except ValueError:
                    pass
    return delay, rpm


def reserve_model_request(model, deadline, report_wait):
    """Reserve quota capacity atomically so concurrent runs cannot oversubscribe it."""
    while True:
        with _RATE_LOCK:
            now = time.monotonic()
            recent = [stamp for stamp in _MODEL_REQUESTS.get(model, []) if now - stamp < 60]
            _MODEL_REQUESTS[model] = recent
            rpm = _MODEL_RPM.get(model) or int(os.getenv("PROOFLINE_MODEL_REQUESTS_PER_MINUTE", "0"))
            wait = max(0, _MODEL_COOLDOWN.get(model, 0) - now)
            if rpm > 0 and len(recent) >= rpm:
                wait = max(wait, 60 - (now - recent[-rpm]) + 0.1)
            if not wait:
                recent.append(now)
                return None
        if wait >= deadline - time.monotonic():
            message = f"Provider cooldown requires {wait:.1f}s, beyond remaining request deadline; resume later"
            report_wait("deferred", wait, message)
            return message
        report_wait("rate_limit_wait", wait, None)
        time.sleep(wait)


_MODEL_SLOTS = threading.BoundedSemaphore(max(1, settings.llm_max_concurrency))


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(
        self,
        api_key=None,
        default_model=None,
        thinking="default",
        max_attempts=None,
        event_callback=None,
        api_mode=None,
    ):
        self.api_mode = api_mode or settings.gemini_api_mode
        self.api_key = api_key or settings.gemini_api_key
        self.default_model = default_model or settings.gemini_review_model
        self.override_model = default_model
        self.role_models = {}
        self.thinking = thinking
        self.max_attempts = max_attempts or settings.llm_max_attempts
        self.event_callback = event_callback
        self.api_attempts = self.api_failures = self.api_tokens = self.api_elapsed_ms = 0
        self.api_log = []
        self.cancelled = None
        self.run_attempt_limit = settings.max_model_calls_per_run * self.max_attempts
        self._client = (
            genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=settings.llm_request_timeout_seconds * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            if self.api_key
            else None
        )

    def is_available(self):
        return bool(self.api_key and self.default_model and self._client)

    def _select_model(self, role):
        return (
            self.role_models.get(role)
            or self.override_model
            or {
                "patch": settings.gemini_patch_model,
                "verify_reasoning": settings.gemini_reasoning_model,
            }.get(role)
            or self.default_model
        )

    def generate_structured(self, request, response_schema):
        started = time.monotonic()
        if not _MODEL_SLOTS.acquire(timeout=max(0, request.deadline_ms / 1000)):
            return ProviderResponse(
                success=False,
                model_id=self._select_model(request.model_role),
                error="Model concurrency deadline exceeded",
            )
        try:
            remaining = request.deadline_ms - int((time.monotonic() - started) * 1000)
            return self._generate_structured(
                request.model_copy(update={"deadline_ms": max(0, remaining)}), response_schema
            )
        finally:
            _MODEL_SLOTS.release()

    def _generate_structured(self, request, response_schema):
        model = self._select_model(request.model_role)
        usage = ProviderUsage()
        started = time.monotonic()
        deadline = started + request.deadline_ms / 1000
        attempts = 0
        last_error = "Deadline or API attempt budget exhausted"
        if not self.is_available():
            return ProviderResponse(success=False, model_id=model, error="Gemini API key or model is not configured")
        try:
            selected_api = self._api_for_model(model)
            thinking = self._thinking_config(model) if selected_api == "generate_content" else None
            if selected_api == "interactions" and model.startswith("gemini-2.5") and self.thinking != "default":
                raise ValueError("Gemini 2.5 token thinking budgets require generate_content mode; use auto")
        except ValueError as exc:
            return ProviderResponse(success=False, model_id=model, error=str(exc))
        for attempt in range(self.max_attempts):
            if self.cancelled and self.cancelled():
                last_error = "Review cancelled before provider request"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0 or self.api_attempts >= self.run_attempt_limit:
                break
            quota_error = reserve_model_request(
                model,
                deadline,
                lambda state, delay, error: self._report(
                    model, request.model_role, attempt + 1, state, error, next_retry_seconds=round(delay, 1)
                ),
            )
            if quota_error:
                last_error = quota_error
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if self.cancelled and self.cancelled():
                last_error = "Review cancelled before provider request"
                break
            attempts += 1
            attempt_start = time.monotonic()
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=response_schema,
                    system_instruction=request.system_instruction,
                    max_output_tokens=min(request.max_output_tokens, settings.max_output_tokens),
                    temperature=0.1,
                    thinking_config=thinking,
                    http_options=types.HttpOptions(
                        timeout=max(1, int(min(remaining, settings.llm_request_timeout_seconds) * 1000)),
                        retry_options=types.HttpRetryOptions(attempts=1),
                    ),
                )
                self.api_attempts += 1
                self._report(model, request.model_role, attempt + 1, "requesting")
                if selected_api == "interactions":
                    response = request_interaction(
                        self._client,
                        model,
                        request,
                        response_schema,
                        self.thinking,
                        min(remaining, settings.llm_request_timeout_seconds),
                        settings.max_output_tokens,
                    )
                else:
                    response = self._client.models.generate_content(
                        model=model, contents=request.context, config=config
                    )
                meta = getattr(response, "usage_metadata", None)
                if meta:
                    for field, source in [
                        ("prompt_tokens", "prompt_token_count"),
                        ("candidate_tokens", "candidates_token_count"),
                        ("total_tokens", "total_token_count"),
                        ("cached_content_token_count", "cached_content_token_count"),
                        ("thought_tokens", "thoughts_token_count"),
                    ]:
                        value = getattr(meta, source, 0) or 0
                        setattr(usage, field, getattr(usage, field) + value)
                        if field == "total_tokens":
                            self.api_tokens += value
                candidates = getattr(response, "candidates", None)
                reason = candidates[0].finish_reason if candidates else None
                finish = getattr(reason, "name", str(reason or ""))
                if finish not in {"STOP", ""}:
                    raise ValueError("Model generation did not complete: " + finish)
                data = response_schema.model_validate(json.loads(response.text or ""))
                self.api_elapsed_ms += int((time.monotonic() - attempt_start) * 1000)
                self._report(model, request.model_role, attempt + 1, "succeeded")
                return ProviderResponse(
                    success=True,
                    data=data,
                    raw_text=response.text,
                    model_id=model,
                    usage=usage,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    retries=attempt,
                    finish_reason=finish or None,
                )
            except Exception as exc:
                self.api_elapsed_ms += int((time.monotonic() - attempt_start) * 1000)
                last_error = redact_secrets(str(exc))[0][:2000]
                self.api_failures += 1
                code = getattr(exc, "code", None) if isinstance(exc, APIError) else getattr(exc, "status_code", None)
                provider_delay, learned_rpm = provider_retry_delay(exc)
                if code == 429:
                    with _RATE_LOCK:
                        _MODEL_COOLDOWN[model] = time.monotonic() + max(provider_delay, 1)
                        if learned_rpm:
                            _MODEL_RPM[model] = learned_rpm
                retryable = code not in {400, 401, 403, 404} and "SAFETY" not in last_error
                self._report(
                    model, request.model_role, attempt + 1, "failed", last_error, error_code=code, retryable=retryable
                )
                delay = min(2**attempt + random.uniform(0.1, 0.5), max(0, deadline - time.monotonic() - 0.1))
                if not retryable or attempt + 1 >= self.max_attempts or delay <= 0:
                    break
                self._report(
                    model, request.model_role, attempt + 1, "retry_scheduled", next_retry_seconds=round(delay, 2)
                )
                time.sleep(delay)
        return ProviderResponse(
            success=False,
            model_id=model,
            usage=usage,
            duration_ms=int((time.monotonic() - started) * 1000),
            retries=max(0, attempts - 1),
            error="Gemini generation failed: " + last_error,
        )

    def _api_for_model(self, model):
        if self.api_mode not in {"auto", "generate_content", "interactions"}:
            raise ValueError("Unsupported Gemini API mode")
        return (
            ("generate_content" if model.startswith("gemini-2.5") else "interactions")
            if self.api_mode == "auto"
            else self.api_mode
        )

    def _thinking_config(self, model):
        if self.thinking == "default":
            return None
        if model.startswith("gemini-2.5"):
            return types.ThinkingConfig(thinking_budget={"low": 1024, "high": 8192}[self.thinking])
        if model.startswith(("gemini-3", "gemini-4")):
            return types.ThinkingConfig(thinking_level=self.thinking.upper())
        raise ValueError("Thinking override requires Gemini 2.5, 3 or 4; use provider default otherwise")

    def _report(self, model, role, attempt, state, error=None, **details):
        self.api_log.append(
            ModelAttempt(
                model=model,
                role=role,
                attempt=attempt,
                state=state,
                error=error,
                api_mode=self._api_for_model(model),
                **details,
            ).model_dump(exclude_none=True)
        )
        if self.event_callback:
            activity = ModelActivity(
                attempts=self.api_attempts,
                failures=self.api_failures,
                tokens=self.api_tokens,
                elapsed_ms=self.api_elapsed_ms,
                thinking=self.thinking,
                max_attempts=self.max_attempts,
                log=self.api_log[-60:],
            )
            self.event_callback(
                {"event_type": "model_activity", "model_activity": activity.model_dump(exclude_none=True)}
            )
