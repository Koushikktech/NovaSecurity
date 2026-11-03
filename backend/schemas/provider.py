from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class StructuredGenerationRequest(BaseModel):
    run_id: str
    stage: str
    model_role: Literal["review", "verify_reasoning", "patch"]
    system_instruction: str
    context: str
    schema_version: str = "1.0.0"
    deadline_ms: int = 45000
    max_output_tokens: int = 4096


class ProviderUsage(BaseModel):
    thought_tokens: int = 0
    prompt_tokens: int = 0
    candidate_tokens: int = 0
    total_tokens: int = 0
    cached_content_token_count: int = 0
    cost_estimated_usd: float | None = None


class ProviderResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    raw_text: str | None = None
    model_id: str
    duration_ms: int = 0
    retries: int = 0
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    finish_reason: str | None = None
    error: str | None = None


# Specific typed models for structured Gemini outputs:


class CandidateLocation(BaseModel):
    path: str
    start_line: int
    end_line: int
    snippet: str | None = None


class CandidateFinding(BaseModel):
    category: Literal["security", "bug", "style"]
    rule_id: str
    cwe_id: str | None = None
    title: str
    explanation: str
    user_impact: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    primary_location: CandidateLocation
    related_files: list[str] = Field(default_factory=list)
    trigger_condition: str
    proposed_remedy: str
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ReviewCandidatesResult(BaseModel):
    findings: list[CandidateFinding] = Field(default_factory=list)
    review_summary: str = ""


class AssessmentCitation(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)


class ChallengeAssessment(BaseModel):
    evidence_status: Literal["source_supported", "refuted", "insufficient_evidence"] = "insufficient_evidence"
    citations: list[AssessmentCitation] = Field(default_factory=list)
    unresolved_assumptions: list[str] = Field(default_factory=list)

    rule_id: str
    path: str
    start_line: int
    is_valid: bool
    confidence_assessment: Literal["confirmed", "likely_false_positive", "needs_review"]
    counter_evidence: str | None = None  # Existing guard, sanitizer, parameter binding, etc.
    explanation: str


class ChallengeResult(BaseModel):
    assessments: list[ChallengeAssessment] = Field(default_factory=list)


class PatchFileEdit(BaseModel):
    path: str
    old_content: str
    replacement: str
    rationale: str


class PatchProposalResult(BaseModel):
    edits: list[PatchFileEdit] = Field(default_factory=list)
    summary: str
    rationale: str
    tests_to_run: list[str] = Field(default_factory=list)
