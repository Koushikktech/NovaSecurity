"""Validated event contracts for investigation and provider activity."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas.provider import ProviderUsage


class ToolInvocation(BaseModel):
    name: Literal["read_file", "search_code", "get_symbol", "find_references", "get_diff", "find_related_tests"]
    query: str = ""
    path: str = ""
    start_line: int = Field(default=1, ge=1)
    end_line: int = Field(default=100, ge=1)


class ToolObservation(BaseModel):
    snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    tool: ToolInvocation
    output: str


class HarnessEvent(BaseModel):
    event_type: Literal[
        "budget_exhausted",
        "model_request_started",
        "model_request_completed",
        "model_request_failed",
        "checkpoint_saved",
        "checkpoint_restored",
        "tool_started",
        "tool_completed",
    ]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    stage: str | None = None
    request_id: str | None = None
    call: int | None = Field(default=None, ge=1)
    model: str | None = None
    usage: ProviderUsage | None = None
    retries: int | None = Field(default=None, ge=0)
    error: str | None = None
    key: str | None = None
    tool: ToolInvocation | None = None
    observation: ToolObservation | None = None
    role: Literal["review", "verify_reasoning"] | None = None

    @model_validator(mode="after")
    def required_payload(self):
        required = {
            "tool_started": ["tool", "role"],
            "tool_completed": ["observation", "role"],
            "model_request_started": ["request_id", "stage", "call"],
            "model_request_completed": ["request_id", "stage", "model"],
            "model_request_failed": ["request_id", "stage", "model"],
            "checkpoint_saved": ["key", "stage"],
            "checkpoint_restored": ["key", "stage"],
            "budget_exhausted": ["stage"],
        }
        for name in required[self.event_type]:
            if getattr(self, name) is None:
                raise ValueError(f"{self.event_type} requires {name}")
        return self


class ModelAttempt(BaseModel):
    provider: Literal["gemini", "codex_cli"] = "gemini"
    api_mode: Literal["generate_content", "interactions", "codex_cli"] | None = None
    model: str
    role: Literal["review", "patch", "verify_reasoning"]
    attempt: int = Field(ge=1)
    state: Literal["requesting", "succeeded", "failed", "retry_scheduled", "rate_limit_wait", "deferred"]
    warning: str | None = None
    error: str | None = None
    error_code: int | None = None
    retryable: bool | None = None
    next_retry_seconds: float | None = Field(default=None, ge=0)


class ModelActivity(BaseModel):
    provider: Literal["gemini", "codex_cli"] = "gemini"
    attempts: int = Field(ge=0)
    failures: int = Field(ge=0)
    tokens: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    thinking: str
    max_attempts: int = Field(ge=1, le=5)
    log: list[ModelAttempt] = Field(max_length=60)
