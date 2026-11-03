from __future__ import annotations

import asyncio
import json
import threading
import uuid

_JOB_SLOTS = threading.BoundedSemaphore(2)
from collections.abc import AsyncGenerator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from config import settings
from github_connection import connection_token, review_token
from ingestion.github import parse_github_url
from persistence import (
    get_events,
    get_finding,
    get_findings,
    get_patch,
    get_run,
    save_event,
    save_findings,
    save_patch,
    save_run,
    update_finding_disposition,
)
from providers import CodexCLIProvider, GeminiProvider
from providers.codex_cli import codex_default_model, codex_models, codex_status
from providers.unavailable import UnavailableProvider
from remediation import Patcher
from review import ReviewOrchestrator
from routes.publication_guard import publication_guard
from runtime_budget import remaining_time
from schemas.contracts import (
    Disposition,
    Finding,
    FindingCategory,
    InputMode,
    Patch,
    PatchStatus,
    ReviewRun,
    RunStatus,
    Severity,
    StageStatus,
)
from verification import TRUSTED_PROFILES, VerificationRunner

router = APIRouter(prefix="/api/v1", tags=["Proofline v1"])

# Global active orchestrators map for cancellation
_ACTIVE_ORCHESTRATORS: dict[str, ReviewOrchestrator] = {}


ModelId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.\-]*$", max_length=100)]


class ModelControls(BaseModel):
    provider: Literal["gemini", "codex_cli"] = Field(default_factory=lambda: settings.llm_provider)
    role_models: dict[Literal["review", "patch", "verify_reasoning"], ModelId] = Field(default_factory=dict)
    model: ModelId | None = None
    api_mode: Literal["auto", "generate_content", "interactions"] = "auto"
    thinking: Literal["default", "low", "high"] = "default"
    codex_reasoning: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    max_attempts: int = Field(default_factory=lambda data: 1 if data.get("provider") == "codex_cli" else 3, ge=1, le=5)

    @model_validator(mode="after")
    def matching_model_provider(self):
        for model in [self.model, *self.role_models.values()]:
            if model and (
                (self.provider == "gemini" and not model.startswith("gemini-"))
                or (self.provider == "codex_cli" and not model.startswith(("gpt-", "o1", "o3", "o4")))
            ):
                raise ValueError("Model ID does not match the selected provider")
        return self


def require_local_provider(request: Request, name: str):
    if name == "codex_cli":
        if not settings.codex_cli_enabled:
            raise HTTPException(403, "Local Codex is disabled by server policy")
        if not request.client or request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(403, "ChatGPT subscription mode is restricted to localhost")


class CreateReviewRequest(ModelControls):
    repo_url: str = Field(min_length=1, max_length=2048)
    base_sha: str | None = None
    head_sha: str | None = None
    local_dir: str | None = None
    mode: Literal["auto", "project", "commit", "compare", "pr", "working"] = "auto"
    revision: str | None = Field(default=None, max_length=200)
    depth: Literal["quick", "deep"] = "quick"


class UpdateDispositionRequest(BaseModel):
    disposition: Disposition
    reason: str | None = None


class VerifyPatchRequest(BaseModel):
    profile_id: str


def _run_review_background(
    run_id: str,
    target_url: str,
    base_sha: str | None,
    head_sha: str | None,
    local_dir: str | None,
    mode: str = "auto",
    revision: str | None = None,
    depth: str = "quick",
    github_credential: str = "",
    model: str | None = None,
    thinking: str = "default",
    max_attempts: int = 3,
    resume_from: str | None = None,
    config_override: dict | None = None,
    role_models: dict | None = None,
    api_mode: str = "auto",
    provider_name: str | None = None,
    codex_reasoning: str = "high",
):
    def event_cb(evt: dict[str, Any]):
        save_event(run_id, evt.get("event_type", "message"), evt)
        snapshot = get_run(run_id)
        if snapshot and snapshot.status != RunStatus.CANCELLED:
            snapshot.status = RunStatus.RUNNING
            if evt.get("event_type") in {
                "tool_started",
                "tool_completed",
                "checkpoint_restored",
                "budget_exhausted",
                "model_request_started",
                "model_request_completed",
                "model_request_failed",
            }:
                snapshot.coverage.setdefault("investigation_events", []).append(evt)
            if evt.get("model_activity"):
                snapshot.coverage["model_activity"] = evt["model_activity"]
            if evt.get("batch"):
                snapshot.coverage["progress"] = {"batch": evt["batch"], "batches": evt["batches"]}
            if "total_files" in evt:
                snapshot.coverage["total_files"] = evt["total_files"]
            if evt.get("target"):
                target = evt["target"]
                snapshot.review_mode = target["mode"]
                snapshot.review_depth = target["depth"]
                snapshot.base_sha, snapshot.head_sha = target.get("base_sha"), target.get("head_sha")
                snapshot.coverage["target"] = target
            if evt.get("stage") and evt.get("status"):
                snapshot.stage_statuses[evt["stage"]] = StageStatus(evt["status"])
            save_run(snapshot, preserve_cancelled=True)

    credential_context = review_token.set(github_credential)
    try:
        queued = get_run(run_id)
        if queued and queued.status == RunStatus.CANCELLED:
            return
        selected_provider = (
            (config_override or {}).get("provider", "gemini")
            if config_override
            else (provider_name or settings.llm_provider)
        )
        provider = (
            CodexCLIProvider(reasoning=codex_reasoning, max_attempts=max_attempts)
            if selected_provider == "codex_cli"
            else GeminiProvider()
            if settings.gemini_api_key
            else UnavailableProvider()
        )
        if isinstance(provider, (GeminiProvider, CodexCLIProvider)):
            provider.role_models = role_models or {}
            if isinstance(provider, GeminiProvider):
                provider.api_mode = api_mode
                provider.thinking = thinking
            provider.max_attempts = max_attempts
            provider.event_callback = event_cb
            if model:
                provider.default_model = model
                provider.override_model = model
        from review.harness import RunConfig

        orch = ReviewOrchestrator(
            provider=provider,
            event_callback=event_cb,
            run_config=RunConfig.model_validate(config_override) if config_override else None,
        )
        _ACTIVE_ORCHESTRATORS[run_id] = orch
        queued = get_run(run_id)
        if queued and queued.status == RunStatus.CANCELLED:
            orch.cancel_run(run_id)

        run, findings = orch.execute_review(
            target_url=target_url,
            run_id=run_id,
            base_sha=base_sha,
            head_sha=head_sha,
            local_dir=local_dir,
            mode=mode,
            revision=revision,
            depth=depth,
            resume_from=resume_from,
        )
        live = get_run(run_id)
        if live and live.coverage.get("model_activity"):
            run.coverage["model_activity"] = live.coverage["model_activity"]
        from persistence.database import previous_review
        from review.lifecycle import reconcile

        previous = previous_review(run)
        reconcile(run, findings, previous, get_findings(previous.id) if previous else [])
        save_run(run, preserve_cancelled=True)
        save_findings(run_id, findings)
    except Exception as exc:
        from ingestion.redactor import redact_secrets

        message = redact_secrets(str(exc))[0][:2000]
        failed = get_run(run_id)
        if failed:
            if failed.status != RunStatus.CANCELLED:
                failed.status = RunStatus.FAILED
            failed.errors.append(message)
            save_run(failed, preserve_cancelled=True)
            save_event(run_id, "run_failed", {"error": message})
    finally:
        review_token.reset(credential_context)
        _ACTIVE_ORCHESTRATORS.pop(run_id, None)
        _JOB_SLOTS.release()


@router.get("/capabilities")
def get_capabilities() -> dict[str, Any]:
    cli_status = codex_status()
    cli_models = codex_models() if cli_status["enabled"] and cli_status["chatgpt_signed_in"] else []
    return {
        "product": "Proofline",
        "version": "1.0.0",
        "review_modes": ["project", "commit", "compare", "pr", "local_folder", "working_tree_cli"],
        "project_depths": ["quick", "deep"],
        "languages": ["python", "javascript", "typescript"],
        "language_capabilities": {
            "python": ["static", "contextual"],
            "javascript": ["parser", "selected_rules", "signature_compatibility", "contextual"],
            "typescript": ["parser", "selected_rules", "signature_compatibility", "contextual"],
        },
        "analyzers": ["ruff", "bandit", "typescript-parser", "typescript-project-checker", "gemini", "codex_cli"],
        "models": {
            "review": settings.gemini_review_model,
            "patch": settings.gemini_patch_model,
            "reasoning": settings.gemini_reasoning_model,
        },
        "default_provider": settings.llm_provider,
        "providers": {
            "gemini": {"configured": bool(settings.gemini_api_key), "model": settings.gemini_review_model},
            "codex_cli": {
                **cli_status,
                "model": codex_default_model() if cli_models else settings.codex_model,
                "models": cli_models,
                "reasoning": settings.codex_reasoning,
                "local_only": True,
            },
        },
        "live_gemini_configured": bool(settings.gemini_api_key),
        "gemini_api_modes": ["auto", "generate_content", "interactions"],
        "gemini_api_mode": settings.gemini_api_mode,
        "execution_enabled": settings.execution_enabled,
        "trusted_verification_profiles": list(TRUSTED_PROFILES.keys()),
        "github_publish_enabled": settings.github_publish_enabled,
    }


@router.post("/reviews", status_code=202)
def create_review(req: CreateReviewRequest, bg_tasks: BackgroundTasks, request: Request) -> dict[str, Any]:
    require_local_provider(request, req.provider)
    if req.base_sha and not req.head_sha and req.mode in {"auto", "compare"}:
        raise HTTPException(422, "Provide both base and head revisions for comparison")
    if not req.local_dir:
        try:
            parsed = parse_github_url(req.repo_url)
            if req.mode == "pr" and not parsed.is_pr:
                raise ValueError("PR mode requires a PR URL")
            if req.mode == "commit" and not (req.revision or req.head_sha or parsed.revision):
                raise ValueError("Commit mode requires a commit URL or revision")
            if req.mode == "compare" and not ((req.base_sha and req.head_sha) or parsed.kind == "compare"):
                raise ValueError("Provide both base and head revisions")
            if req.mode == "working":
                raise ValueError("Working-tree review is available through the local CLI")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not _JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Review queue is full; retry after an active review completes")
    try:
        run_id = str(uuid.uuid4())
        run = ReviewRun(
            id=run_id,
            canonical_repo=req.repo_url,
            provider=req.provider,
            input_mode=InputMode.LOCAL_DIFF
            if req.local_dir
            else (InputMode.PR if "/pull/" in req.repo_url else InputMode.REPO),
            status=RunStatus.QUEUED,
            base_sha=req.base_sha,
            head_sha=req.head_sha,
        )
        save_run(run)

        bg_tasks.add_task(
            _run_review_background,
            run_id,
            req.repo_url,
            req.base_sha,
            req.head_sha,
            req.local_dir,
            req.mode,
            req.revision,
            req.depth,
            connection_token(),
            req.model,
            req.thinking,
            req.max_attempts,
            role_models=req.role_models,
            api_mode=req.api_mode,
            provider_name=req.provider,
            codex_reasoning=req.codex_reasoning,
        )

        return {"run_id": run_id, "status": "queued", "canonical_repo": req.repo_url}

    except Exception as exc:
        _JOB_SLOTS.release()
        raise HTTPException(503, "Could not persist or enqueue the review; retry after storage is available") from exc


@router.get("/reviews/{run_id}")
def get_review_run(run_id: str) -> ReviewRun:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run {run_id} not found")
    return run


@router.get("/reviews/{run_id}/events")
async def get_review_events(
    run_id: str,
    request: Request,
    last_event_id: int = Query(0, alias="after", ge=0, le=9223372036854775807),
    header_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Server-Sent Events stream for real-time progress with reconnection support."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Review run {run_id} not found")

    cursor_start = last_event_id
    if header_event_id is not None:
        if not header_event_id.isascii() or not header_event_id.isdigit() or len(header_event_id) > 19:
            raise HTTPException(400, "Last-Event-ID must be a nonnegative event ID")
        header_cursor = int(header_event_id)
        if header_cursor > 9223372036854775807:
            raise HTTPException(400, "Last-Event-ID is outside the supported range")
        cursor_start = max(cursor_start, header_cursor)

    async def event_generator() -> AsyncGenerator[str, None]:
        import time

        cursor = cursor_start
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            events = get_events(run_id, after_event_id=cursor)
            for evt in events:
                cursor = evt["event_id"]
                yield f"id: {cursor}\nevent: {evt['event_type']}\ndata: {json.dumps(evt)}\n\n"

            current_run = get_run(run_id)
            if current_run and current_run.status in (
                RunStatus.COMPLETED,
                RunStatus.PARTIAL,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.INTERRUPTED,
            ):
                yield f"event: complete\ndata: {json.dumps({'status': current_run.status.value})}\n\n"
                break

            if time.monotonic() - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/reviews/{run_id}/cancel")
def cancel_review(run_id: str) -> dict[str, str]:
    from persistence.database import cancel_review_run

    run = cancel_review_run(run_id)
    if not run:
        raise HTTPException(404, "Review not found")
    if run.status == RunStatus.CANCELLED:
        orch = _ACTIVE_ORCHESTRATORS.get(run_id)
        if orch:
            orch.cancel_run(run_id)
    return {"run_id": run_id, "status": run.status.value}


@router.get("/reviews/{run_id}/findings")
def list_findings(
    run_id: str,
    category: FindingCategory | None = None,
    severity: Severity | None = None,
    disposition: Disposition | None = None,
) -> list[Finding]:
    findings = get_findings(run_id)
    if category:
        findings = [f for f in findings if f.category == category]
    if severity:
        findings = [f for f in findings if f.severity == severity]
    if disposition:
        findings = [f for f in findings if f.disposition == disposition]
    return findings


@router.patch("/findings/{finding_id}/disposition")
def update_disposition(finding_id: str, req: UpdateDispositionRequest) -> dict[str, Any]:
    ok = update_finding_disposition(finding_id, req.disposition.value, req.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"finding_id": finding_id, "disposition": req.disposition.value, "reason": req.reason}


@router.post("/findings/{finding_id}/patches")
def generate_patch(finding_id: str, request: Request) -> Patch:
    finding = get_finding(finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    parent_run = get_run(finding.run_id)
    config = parent_run.coverage.get("run_config", {}) if parent_run else {}
    selected_provider = config.get("provider", "gemini")
    require_local_provider(request, selected_provider)
    provider = (
        CodexCLIProvider(reasoning=config.get("codex_reasoning", "high"))
        if selected_provider == "codex_cli"
        else GeminiProvider()
        if settings.gemini_api_key
        else UnavailableProvider()
    )
    if isinstance(provider, (GeminiProvider, CodexCLIProvider)):
        from review.harness import RunConfig

        if isinstance(provider, GeminiProvider):
            provider.api_mode = RunConfig.model_validate(config).api_mode
            provider.thinking = config.get("thinking", "default")
        provider.max_attempts = config.get("max_attempts", 3)
        provider.role_models = config.get("models", {})
        if config.get("model"):
            provider.default_model = provider.override_model = config["model"]
    patcher = Patcher(provider=provider)

    workspace_dir = settings.workspace_dir / finding.run_id / "head"
    context = []
    allowed = set(parent_run.coverage.get("source_files", [])) if parent_run else set()
    paths = list(dict.fromkeys([finding.primary_location.path] + [loc.path for loc in finding.related_locations]))[:4]
    for relative in paths:
        if relative not in allowed:
            continue
        for side in ("base", "head"):
            root = settings.workspace_dir / finding.run_id / side
            source = (root / relative).resolve()
            if source.is_relative_to(root.resolve()) and source.is_file() and not source.is_symlink():
                context.append(f"{side} snapshot / {relative}:\n" + source.read_text()[:4000])
    res = patcher.propose_patch(finding, workspace_head_dir=workspace_dir, relevant_context="\n\n".join(context))
    if not res.success or not res.patch:
        raise HTTPException(status_code=400, detail=f"Patch generation failed: {res.error}")

    patch = res.patch
    save_patch(patch)
    finding.patch_id = patch.id
    finding.patch_status = PatchStatus.PROPOSED
    save_findings(finding.run_id, [finding])

    return patch


@router.get("/patches/{patch_id}")
def get_patch_details(patch_id: str) -> Patch:
    patch = get_patch(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")
    return patch


@router.post("/patches/{patch_id}/verify")
def verify_patch_execution(patch_id: str, req: VerifyPatchRequest) -> dict[str, Any]:
    patch = get_patch(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    if not settings.execution_enabled:
        raise HTTPException(status_code=403, detail="Isolated execution is disabled")
    workspace_dir = settings.workspace_dir / patch.run_id / "head"
    runner = VerificationRunner(workspace_root=workspace_dir)

    success, message = runner.verify_patch(patch, profile_id=req.profile_id)
    save_patch(patch)

    finding = get_finding(patch.finding_id)
    if finding:
        finding.patch_status = patch.status
        save_findings(finding.run_id, [finding])

    return {
        "patch_id": patch_id,
        "verified": success,
        "status": patch.status.value,
        "message": message,
        "before_test_passed": patch.before_test_passed,
        "after_test_passed": patch.after_test_passed,
        "happy_path_passed": patch.happy_path_passed,
        "checks": [c.model_dump() for c in patch.checks],
    }


@router.get("/reviews/{run_id}/export")
def export_review(run_id: str, format: str = Query("json", pattern="^(json|markdown)$")) -> Any:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Review run not found")
    findings = get_findings(run_id)

    if format == "json":
        return {
            "run": run.model_dump(),
            "findings": [f.model_dump() for f in findings],
        }

    # Markdown export
    lines = [
        f"# Proofline Review Report: {run.canonical_repo}",
        f"- **Run ID:** `{run.id}`",
        f"- **Status:** `{run.status.value}`",
        f"- **Completed:** {run.completed_at or 'In Progress'}",
        f"- **Findings Summary:** {run.findings_count}",
        "",
        "## Findings",
    ]
    for i, f in enumerate(findings):
        lines.extend(
            [
                f"### {i + 1}. [{f.severity.value.upper()}] {f.title}",
                f"- **Rule:** `{f.rule_id}` {f'({f.cwe_id})' if f.cwe_id else ''}",
                f"- **Location:** `{f.primary_location.path}` (lines {f.primary_location.start_line}-{f.primary_location.end_line})",
                f"- **Relation:** `{f.change_relation.value}` | **Status:** `{f.analysis_status.value}`",
                f"- **Explanation:** {f.explanation}",
                f"- **Impact:** {f.user_impact}",
                f"- **Remedy:** {f.proposed_remedy or 'Review code'}",
                "",
            ]
        )

    return {"markdown": "\n".join(lines)}


@router.get("/reviews/{run_id}/evidence/{evidence_id}")
def get_evidence_item(run_id: str, evidence_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Review run not found")
    findings = get_findings(run_id)

    for finding in findings:
        for idx, ev in enumerate(finding.evidence_items):
            ev_id = f"{finding.id}-ev-{idx}"
            if evidence_id in (ev_id, str(idx), ev.tool_or_profile, ev.kind):
                return {
                    "evidence_id": evidence_id,
                    "run_id": run_id,
                    "finding_id": finding.id,
                    "finding_title": finding.title,
                    "kind": ev.kind,
                    "tool_or_profile": ev.tool_or_profile,
                    "command": ev.command,
                    "exit_code": ev.exit_code,
                    "duration_ms": ev.duration_ms,
                    "output_snippet": ev.output_snippet,
                    "input_revision": ev.input_revision or run.head_sha,
                }

    raise HTTPException(status_code=404, detail=f"Evidence item {evidence_id} not found for run {run_id}")


@router.post("/reviews/{run_id}/publish")
def publish_review(run_id: str) -> dict[str, Any]:
    with publication_guard("review", run_id):
        return _publish_review_locked(run_id)


def _publish_review_locked(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Review run not found")
    findings = [f for f in get_findings(run_id) if f.disposition != Disposition.DISMISSED]

    if not settings.github_publish_enabled or not settings.github_token:
        return {
            "run_id": run_id,
            "published": False,
            "status": "disabled",
            "message": "GitHub review publishing is disabled in server policy. Set PROOFLINE_GITHUB_PUBLISH_ENABLED=true and GITHUB_TOKEN to publish live reviews.",
            "target_repo": run.canonical_repo,
            "inline_comments_count": min(len(findings), 5),
            "findings_count": run.findings_count,
        }

    import httpx

    from ingestion.github import GitHubMetadataFetcher, parse_github_url

    target = parse_github_url(run.canonical_repo)
    if not target.is_pr or not run.head_sha:
        raise HTTPException(409, "Publication requires a pinned pull-request review")
    if run.status not in {RunStatus.COMPLETED, RunStatus.PARTIAL}:
        raise HTTPException(409, "Finish the review before publishing")
    fetcher = GitHubMetadataFetcher(settings.github_token)
    meta = fetcher.fetch_pr_metadata(target.owner, target.repo, target.pr_number)
    if meta["head_sha"] != run.head_sha:
        raise HTTPException(409, "PR changed since review; rerun before publishing")
    marker = f"<!-- proofline:{run.id} -->"
    endpoint = f"https://api.github.com/repos/{target.owner}/{target.repo}/pulls/{target.pr_number}/reviews"
    with httpx.Client(headers=fetcher.headers, timeout=20) as client:
        for page in range(1, 101):
            existing = client.get(endpoint, params={"per_page": 100, "page": page}, timeout=remaining_time(20))
            existing.raise_for_status()
            rows = existing.json()
            for row in rows:
                if marker in (row.get("body") or ""):
                    return {"published": True, "review_id": row["id"], "url": row["html_url"], "reused": True}
            if len(rows) < 100:
                break
        else:
            raise HTTPException(409, "Review history exceeds safe deduplication limit")
        body = marker + "\n## Proofline review\n" + str(run.coverage.get("review_summary", ""))
        for finding in findings[:20]:
            body += f"\n- **{finding.category.value}: {finding.title}** ({finding.primary_location.path}:{finding.primary_location.start_line}): {finding.explanation}"
        # Inline comments must point to added lines in the reviewed diff.
        from ingestion import parse_unified_diff

        diff = parse_unified_diff(run.coverage.get("diff", ""))
        added = {file.new_path: set(file.added_lines_head) for file in diff.files}
        comments = []
        for finding in findings:
            loc = finding.primary_location
            if loc.start_line in added.get(loc.path, set()) and len(comments) < 20:
                comments.append(
                    {
                        "path": loc.path,
                        "line": loc.start_line,
                        "side": "RIGHT",
                        "body": f"**{finding.severity.value}: {finding.title}**\n\n{finding.explanation}\n\nImpact: {finding.user_impact}\n\nSuggested action: {finding.proposed_remedy or 'Inspect the cited behavior.'}"[
                            :6000
                        ],
                    }
                )
        from ingestion.redactor import redact_secrets

        for comment in comments:
            comment["body"] = redact_secrets(comment["body"])[0]
        result = client.post(
            endpoint,
            json={
                "commit_id": run.head_sha,
                "body": redact_secrets(body[:60000])[0],
                "event": "COMMENT",
                "comments": comments,
            },
            timeout=remaining_time(20),
        )
        result.raise_for_status()
        data = result.json()
        return {"published": True, "review_id": data["id"], "url": data["html_url"]}


@router.post("/patches/{patch_id}/publish")
def publish_patch(patch_id: str) -> dict[str, Any]:
    with publication_guard("patch", patch_id):
        return _publish_patch_locked(patch_id)


def _publish_patch_locked(patch_id: str) -> dict[str, Any]:
    patch = get_patch(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    if not settings.github_publish_enabled or not settings.github_token:
        return {
            "patch_id": patch_id,
            "published": False,
            "status": "disabled",
            "branch_name": patch.branch_name,
            "message": "GitHub fix branch publishing is disabled in server policy. Patch is available for local download.",
            "diff_preview": patch.diff,
        }

    from remediation.publish import publish_fix

    run = get_run(patch.run_id)
    if not run:
        raise HTTPException(404, "Review missing")
    try:
        url = publish_fix(run, patch, settings.workspace_dir / patch.run_id / "head", settings.github_token)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    patch.published_pr_url = url
    save_patch(patch)
    return {"published": True, "pr_url": url, "branch_name": patch.branch_name}


@router.get("/examples")
def list_recorded_examples() -> list[dict[str, Any]]:
    return [
        {
            "id": "example-expense-service",
            "name": "Expense Service Cross-File SQL Injection & Mutable Default",
            "repo_url": "https://github.com/proofline/demo-expense-service/pull/4",
            "description": "Realistic PR introducing cross-file SQL injection in search routes, mutable default argument bug, and Ruff style formatting issue.",
            "sample_findings": [
                {
                    "title": "SQL Injection in Search Query Construction",
                    "severity": "critical",
                    "category": "security",
                    "file": "repositories/expenses.py",
                    "line": 42,
                },
                {
                    "title": "Mutable Default Parameter in Filter Accumulation",
                    "severity": "medium",
                    "category": "bug",
                    "file": "services/search.py",
                    "line": 18,
                },
                {
                    "title": "Unused Import `typing.Optional`",
                    "severity": "low",
                    "category": "style",
                    "file": "routes/search.py",
                    "line": 3,
                },
            ],
        },
        {
            "id": "example-lets-be-bad-guys",
            "name": "lets-be-bad-guys (mpirnat)",
            "repo_url": "https://github.com/mpirnat/lets-be-bad-guys",
            "description": "Intentionally vulnerable Django application demonstration with OWASP Top 10 vulnerabilities.",
            "sample_findings": [
                {
                    "title": "SQL Injection via string formatting in custom raw SQL",
                    "severity": "critical",
                    "category": "security",
                    "file": "bad/views.py",
                    "line": 29,
                }
            ],
        },
        {
            "id": "example-vulpy",
            "name": "vulpy (fportantier)",
            "repo_url": "https://github.com/fportantier/vulpy",
            "description": "Vulnerable Flask application with SQL injection, insecure deserialization, and weak session secrets.",
            "sample_findings": [
                {
                    "title": "SQL Injection in user authentication query",
                    "severity": "critical",
                    "category": "security",
                    "file": "bad/login.py",
                    "line": 15,
                }
            ],
        },
    ]


@router.get("/patches/{patch_id}/download")
def download_patch(patch_id: str):
    from fastapi.responses import PlainTextResponse

    patch = get_patch(patch_id)
    if not patch:
        raise HTTPException(404, "Patch not found")
    return PlainTextResponse(patch.diff, headers={"Content-Disposition": 'attachment; filename="proofline.patch"'})


@router.get("/reviews/{run_id}/source")
def review_source(run_id: str, path: str):
    from ingestion.redactor import redact_secrets
    from ingestion.repo import Workspace
    from ingestion.source_policy import sensitive_source_path

    if sensitive_source_path(path):
        raise HTTPException(404, "Source unavailable")
    if not get_run(run_id):
        raise HTTPException(404, "Review not found")
    try:
        resolved = Workspace(run_id).resolve_safe_path(path)
        if not resolved.is_file() or resolved.stat().st_size > 512000:
            raise ValueError("Unavailable source")
        content, _ = redact_secrets(resolved.read_text())
        return {"path": path, "content": content}
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "Source unavailable") from exc


def _start_fixture_review(
    bg_tasks: BackgroundTasks, request: Request, controls: ModelControls | None = None, fixture_name="reviewer"
):
    """Build a real local PR-shaped diff from operator-owned fixtures, with no fake model."""
    import shutil
    from pathlib import Path

    import git

    label = "Checkout regression demo" if fixture_name == "flagship" else "Controlled reviewer example"
    controls = controls or ModelControls()
    require_local_provider(request, controls.provider)
    if not _JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Review queue full")
    run_id = str(uuid.uuid4())
    root = settings.workspace_dir / (run_id + "-fixture")
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / fixture_name
    try:
        shutil.copytree(fixture / "base", root)
        repo = git.Repo.init(root)
        actor = git.Actor("Proofline fixture", "fixture@example.invalid")
        repo.index.add(["."])
        base = repo.index.commit("Fixture base", author=actor, committer=actor).hexsha
        shutil.copytree(fixture / "head", root, dirs_exist_ok=True)
        repo.index.add(["."])
        head = repo.index.commit("Fixture proposed change", author=actor, committer=actor).hexsha
        save_run(
            ReviewRun(
                id=run_id,
                canonical_repo=label,
                input_mode=InputMode.LOCAL_DIFF,
                provider=controls.provider,
            )
        )
        bg_tasks.add_task(
            _run_review_background,
            run_id,
            label,
            base,
            head,
            str(root),
            model=controls.model,
            thinking=controls.thinking,
            max_attempts=controls.max_attempts,
            role_models=controls.role_models,
            api_mode=controls.api_mode,
            provider_name=controls.provider,
            codex_reasoning=controls.codex_reasoning,
        )
        return {"run_id": run_id, "status": "queued"}
    except Exception:
        _JOB_SLOTS.release()
        raise


@router.post("/examples/reviewer", status_code=202)
def start_reviewer_example(bg_tasks: BackgroundTasks, request: Request, controls: ModelControls | None = None):
    return _start_fixture_review(bg_tasks, request, controls)


@router.post("/examples/checkout", status_code=202)
def start_checkout_example(bg_tasks: BackgroundTasks, request: Request, controls: ModelControls | None = None):
    return _start_fixture_review(bg_tasks, request, controls, "flagship")


class UploadFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=512000)


class FolderReviewRequest(ModelControls):
    files: list[UploadFile] = Field(min_length=1, max_length=2000)
    depth: Literal["quick", "deep"] = "quick"


@router.post("/reviews/folder", status_code=202)
def review_folder(req: FolderReviewRequest, bg_tasks: BackgroundTasks, request: Request):
    require_local_provider(request, req.provider)
    import shutil
    from pathlib import Path, PurePosixPath

    from analysis.languages import SUPPORTED
    from ingestion.source_policy import sensitive_source_path

    allowed = set(SUPPORTED) | {".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".md"}
    seen = set()
    total = 0
    for item in req.files:
        parts = PurePosixPath(item.path).parts
        if (
            not parts
            or item.path.startswith("/")
            or "\\" in item.path
            or any(p in {".", "..", ".git", "node_modules", ".venv"} for p in parts)
        ):
            raise HTTPException(422, "Unsafe or excluded upload path")
        if sensitive_source_path(item.path):
            raise HTTPException(422, "Credential files are excluded from source review")
        if item.path.casefold() in seen:
            raise HTTPException(422, "Duplicate upload path")
        seen.add(item.path.casefold())
        if Path(item.path).suffix.lower() not in allowed:
            raise HTTPException(422, "Unsupported upload file type")
        total += len(item.content.encode())
    if total > 20 * 1024 * 1024:
        raise HTTPException(413, "Folder source limit is 20 MiB")
    if not _JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Review queue full")
    run_id = str(uuid.uuid4())
    root = settings.workspace_dir / (run_id + "-upload")
    try:
        root.mkdir(parents=True)
        for item in req.files:
            destination = root / item.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(item.content)
        save_run(
            ReviewRun(
                id=run_id,
                canonical_repo="Uploaded folder",
                input_mode=InputMode.UPLOAD,
                review_mode="project",
                provider=req.provider,
            )
        )
        bg_tasks.add_task(
            _run_review_background,
            run_id,
            "Uploaded folder",
            None,
            None,
            str(root),
            "project",
            None,
            req.depth,
            "",
            req.model,
            req.thinking,
            req.max_attempts,
            role_models=req.role_models,
            api_mode=req.api_mode,
            provider_name=req.provider,
            codex_reasoning=req.codex_reasoning,
        )
        return {"run_id": run_id, "status": "queued", "uploaded_files": len(req.files)}
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        _JOB_SLOTS.release()
        raise


@router.post("/reviews/{run_id}/resume", status_code=202)
def resume_review(run_id: str, bg_tasks: BackgroundTasks, request: Request):
    from review.snapshots import load_snapshot

    original = get_run(run_id)
    if not original:
        raise HTTPException(404, "Review not found")
    require_local_provider(request, original.coverage.get("run_config", {}).get("provider", "gemini"))
    if original.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
        raise HTTPException(409, "Cancel or finish the active review before resuming")
    try:
        load_snapshot(settings.workspace_dir / original.id)
    except (OSError, ValueError, KeyError):
        raise HTTPException(409, "No intact source checkpoint is available; start a new review")
    if not _JOB_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Review queue full")
    new_id = str(uuid.uuid4())
    config = original.coverage.get("run_config", {})
    try:
        save_run(
            ReviewRun(
                id=new_id,
                canonical_repo=original.canonical_repo,
                provider=original.provider,
                model_id=original.model_id,
                input_mode=original.input_mode,
                status=RunStatus.QUEUED,
                coverage={"resumed_from": original.id},
            )
        )
        bg_tasks.add_task(
            _run_review_background,
            new_id,
            original.canonical_repo,
            original.base_sha,
            original.head_sha,
            None,
            original.review_mode,
            None,
            original.review_depth,
            "",
            config.get("model"),
            config.get("thinking", "default"),
            config.get("max_attempts", 3),
            original.id,
            config_override=config,
        )
    except Exception:
        _JOB_SLOTS.release()
        raise
    return {"run_id": new_id, "resumed_from": original.id, "status": "queued"}
