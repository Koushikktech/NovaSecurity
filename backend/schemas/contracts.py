from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class InputMode(str, Enum):
    REPO = "repo"
    PR = "pr"
    LOCAL_DIFF = "local_diff"
    RECORDED = "recorded"
    COMMIT = "commit"
    COMPARE = "compare"
    WORKING = "working"
    UPLOAD = "upload"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class FindingCategory(str, Enum):
    SECURITY = "security"
    BUG = "bug"
    STYLE = "style"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ChangeRelation(str, Enum):
    INTRODUCED = "introduced"
    PRE_EXISTING = "pre_existing"
    CHANGED_CONTEXT = "changed_context"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


class Disposition(str, Enum):
    OPEN = "open"
    DISMISSED = "dismissed"
    ACCEPTED = "accepted"
    FIXED = "fixed"
    SUPERSEDED = "superseded"


class AnalysisStatus(str, Enum):
    STATIC_MATCH = "static_match"
    CONTEXTUAL_ASSESSMENT = "contextual_assessment"
    DISPUTED = "disputed"
    INSUFFICIENT_CONTEXT = "insufficient_context"


class ReproductionStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    INCONCLUSIVE = "inconclusive"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class PatchStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    PROPOSED = "proposed"
    APPLYING = "applying"
    VALIDATION_RUNNING = "validation_running"
    CHECKS_PASSED = "checks_passed"
    CHECKS_FAILED = "checks_failed"
    INCONCLUSIVE = "inconclusive"
    STALE = "stale"


class Location(BaseModel):
    path: str
    start_line: int
    end_line: int
    side: Literal["base", "head"] = "head"
    commit_sha: str | None = None
    snippet: str | None = None


class RelatedLocation(BaseModel):
    path: str
    lines: list[int] = Field(default_factory=list)
    qualified_symbol: str
    relationship: str  # e.g., "caller", "callee", "sink", "sanitizer", "config"
    snippet: str | None = None


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    kind: str  # "static_analysis", "graph_context", "gemini_review", "test_execution"
    tool_or_profile: str
    input_revision: str | None = None
    command: list[str] | None = None
    exit_code: int | None = None
    stdout_hash: str | None = None
    stderr_hash: str | None = None
    output_snippet: str | None = None
    duration_ms: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    stable_fingerprint: str
    category: FindingCategory
    rule_id: str
    cwe_id: str | None = None
    title: str
    explanation: str
    user_impact: str
    severity: Severity
    primary_location: Location
    related_locations: list[RelatedLocation] = Field(default_factory=list)
    change_relation: ChangeRelation = ChangeRelation.UNKNOWN
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    analysis_sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    disposition: Disposition = Disposition.OPEN
    disposition_reason: str | None = None
    analysis_status: AnalysisStatus = AnalysisStatus.CONTEXTUAL_ASSESSMENT
    evidence_status: Literal["unassessed", "source_supported", "refuted", "insufficient_evidence", "reproduced"] = (
        "unassessed"
    )
    verification_assessment: dict[str, Any] = Field(default_factory=dict)
    reproduction_status: ReproductionStatus = ReproductionStatus.NOT_ATTEMPTED
    patch_status: PatchStatus = PatchStatus.NOT_REQUESTED
    patch_id: str | None = None
    proposed_remedy: str | None = None


class FileEdit(BaseModel):
    path: str
    old_content: str
    replacement: str
    rationale: str


class PatchCheckResult(BaseModel):
    check_name: str
    command: list[str]
    exit_code: int
    duration_ms: int
    status: Literal["passed", "failed", "inconclusive"]
    stdout_snippet: str
    stderr_snippet: str


class Patch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    finding_id: str
    run_id: str
    branch_name: str | None = None
    status: PatchStatus = PatchStatus.PROPOSED
    edits: list[FileEdit] = Field(default_factory=list)
    diff: str = ""
    checks: list[PatchCheckResult] = Field(default_factory=list)
    before_test_passed: bool | None = None  # Expected False on buggy code
    after_test_passed: bool | None = None  # Expected True on patched code
    happy_path_passed: bool | None = None  # Expected True
    published_pr_url: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ReviewRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_session: str = "anonymous"
    input_mode: InputMode
    canonical_repo: str
    review_mode: str = "project"
    review_depth: str = "quick"
    pr_number: int | None = None
    pr_title: str | None = None
    base_sha: str | None = None
    head_sha: str | None = None
    merge_base_sha: str | None = None
    config_version: str = "1.0.0"
    provider: str = "google-genai"
    model_id: str = "unconfigured"
    status: RunStatus = RunStatus.QUEUED
    stage_statuses: dict[str, StageStatus] = Field(default_factory=dict)
    findings_count: dict[str, int] = Field(default_factory=lambda: {"total": 0, "security": 0, "bug": 0, "style": 0})
    coverage: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
