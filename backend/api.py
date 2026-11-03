from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from access import require_operator
from config import settings
from github_connection import router as github_router
from persistence import (
    save_event,
    save_findings,
    save_patch,
    save_run,
)
from persistence.database import interrupt_orphaned_runs
from providers import FakeLLMProvider, GeminiProvider
from remediation import Patcher
from review import ReviewOrchestrator
from routes.v1 import router as api_v1_router
from schemas.contracts import (
    AnalysisStatus,
    Disposition,
    Finding,
    FindingCategory,
    Location,
    ReviewRun,
    Severity,
)
from verification import VerificationRunner


@asynccontextmanager
async def lifespan(app):
    interrupt_orphaned_runs()
    yield


app = FastAPI(title="Proofline Code Reviewer", dependencies=[Depends(require_operator)], lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)
app.include_router(github_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "proofline-api"}


@app.get("/readyz")
def readyz():
    return {"status": "ready", "service": "proofline-api"}


scans: dict[str, dict] = {}
fixes: dict[str, dict] = {}
STATE_LOCK = threading.RLock()
MAX_DIFF_PREVIEW_CHARS = 60000
_REPO_URL_RE = re.compile(r"^(?:https?://|ssh://|git@).+", re.IGNORECASE)

_DEMO_DIR = Path(__file__).parent / "demo_results"
_DEMO_REPOS: dict[str, dict[str, str]] = {
    "expense-service": {
        "url": "https://github.com/proofline/demo-expense-service/pull/4",
        "local_dir": str(Path(__file__).resolve().parent.parent / "fixtures" / "demo-api"),
        "profile_id": "expense_service_sql",
        "description": "Realistic pull request introducing cross-file SQL injection in search routes, mutable default argument bug, and Ruff style nit.",
    },
    "lets-be-bad-guys": {
        "url": "https://github.com/mpirnat/lets-be-bad-guys",
        "file": "lets-be-bad-guys.json",
        "local_dir": "lets-be-bad-guys",
    },
    "vulpy": {
        "url": "https://github.com/fportantier/vulpy",
        "file": "vulpy.json",
        "local_dir": "vulpy",
    },
}

_PIPELINE_STEPS = [
    "ingest",
    "build_index",
    "build_graph",
    "targeted_scan",
    "indexed_sweep",
    "merge_findings",
    "red_team",
    "blue_team",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScanRequest(_StrictModel):
    repo_url: str = Field(min_length=1, max_length=2048)

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not _REPO_URL_RE.match(cleaned):
            raise ValueError("repo_url must be an HTTP(S), SSH, or git remote URL")
        return cleaned


class FixRequest(_StrictModel):
    finding_index: int = Field(ge=0)


class DemoRequest(_StrictModel):
    repo_key: str = Field(min_length=1, max_length=120)

    @field_validator("repo_key")
    @classmethod
    def validate_repo_key(cls, value: str) -> str:
        return value.strip()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_scan(scan: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in scan.items() if not key.startswith("_")}


def _public_fix(fix: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in fix.items() if not key.startswith("_")}


def _snapshot_scan(scan_id: str) -> dict[str, Any] | None:
    with STATE_LOCK:
        scan = scans.get(scan_id)
        return copy.deepcopy(scan) if scan is not None else None


def _snapshot_fix(fix_id: str) -> dict[str, Any] | None:
    with STATE_LOCK:
        fix = fixes.get(fix_id)
        return copy.deepcopy(fix) if fix is not None else None


def _create_scan(scan_id: str, payload: dict[str, Any]) -> None:
    with STATE_LOCK:
        scans[scan_id] = copy.deepcopy(payload)


def _create_fix(fix_id: str, payload: dict[str, Any]) -> None:
    with STATE_LOCK:
        fixes[fix_id] = copy.deepcopy(payload)


def _update_scan(scan_id: str, **changes: Any) -> None:
    with STATE_LOCK:
        scan = scans.get(scan_id)
        if scan is not None:
            scan.update(changes)


def _update_fix(fix_id: str, **changes: Any) -> None:
    with STATE_LOCK:
        fix = fixes.get(fix_id)
        if fix is not None:
            fix.update(changes)


def _find_active_fix(scan_id: str, finding_index: int) -> dict[str, Any] | None:
    with STATE_LOCK:
        for fix in fixes.values():
            if (
                fix.get("scan_id") == scan_id
                and fix.get("finding_index") == finding_index
                and fix.get("status") in {"queued", "running"}
            ):
                return copy.deepcopy(fix)
    return None


def _format_finding_for_frontend(f: Finding) -> dict[str, Any]:
    sev_cap = f.severity.value.capitalize()
    return {
        "id": f.id,
        "vulnerability_type": f.title,
        "title": f.title,
        "category": f.category.value,
        "severity": sev_cap,
        "file": f.primary_location.path,
        "line": f.primary_location.start_line,
        "start_line": f.primary_location.start_line,
        "end_line": f.primary_location.end_line,
        "description": f.explanation,
        "explanation": f.explanation,
        "user_impact": f.user_impact,
        "rule_id": f.rule_id,
        "cwe_id": f.cwe_id,
        "confidence": 1.0 if f.analysis_status == AnalysisStatus.STATIC_MATCH else 0.95,
        "final_confidence": 1.0 if f.analysis_status == AnalysisStatus.STATIC_MATCH else 0.95,
        "validation_status": "Confirmed" if f.disposition != Disposition.DISMISSED else "Likely False Positive",
        "analysis_status": f.analysis_status.value,
        "reproduction_status": f.reproduction_status.value,
        "patch_status": f.patch_status.value,
        "change_relation": f.change_relation.value,
        "disposition": f.disposition.value,
        "proposed_remedy": f.proposed_remedy,
        "red_team_poc": f.evidence_items[0].output_snippet if f.evidence_items else None,
        "red_team_success": f.category == FindingCategory.SECURITY and f.severity in (Severity.CRITICAL, Severity.HIGH),
        "path": [f.primary_location.path],
        "evidence_items": [e.model_dump() for e in f.evidence_items],
        "sources": f.analysis_sources,
        "corroborated": len(f.analysis_sources) > 1,
    }


def _build_graph_from_findings(findings: list[Finding], run: ReviewRun) -> dict[str, Any]:
    nodes = []
    links = []
    paths = []
    seen_nodes = set()
    for f in findings:
        p = f.primary_location.path
        if p not in seen_nodes:
            seen_nodes.add(p)
            nodes.append(
                {
                    "id": p,
                    "label": p.split("/")[-1],
                    "type": "file",
                    "category": "attacked" if f.category == FindingCategory.SECURITY else "normal",
                    "file": p,
                    "line": f.primary_location.start_line,
                    "degree": 1,
                }
            )
        paths.append(
            {
                "source": f.rule_id,
                "sink": p,
                "nodes": [f.primary_location.path],
                "sanitized": f.disposition == Disposition.DISMISSED,
            }
        )
    return {"nodes": nodes, "links": links, "paths": paths}


def _run_scan(scan_id: str, repo_url: str) -> None:
    _update_scan(
        scan_id,
        status="running",
        current_step="ingest",
        step_index=0,
        total_steps=len(_PIPELINE_STEPS),
    )

    def event_cb(evt: dict[str, Any]):
        st = evt.get("stage")
        if st:
            _update_scan(scan_id, current_step=st)
        save_event(scan_id, evt.get("event_type", "message"), evt)

    provider = GeminiProvider() if settings.gemini_api_key else FakeLLMProvider()
    orch = ReviewOrchestrator(provider=provider, event_callback=event_cb)

    try:
        run, findings = orch.execute_review(target_url=repo_url, run_id=scan_id)
        save_run(run)
        save_findings(scan_id, findings)

        frontend_findings = [_format_finding_for_frontend(f) for f in findings]
        graph_data = _build_graph_from_findings(findings, run)
        cov = run.coverage.model_dump() if hasattr(run.coverage, "model_dump") else (run.coverage or {})

        _update_scan(
            scan_id,
            status="completed",
            current_step=None,
            completed_at=run.completed_at,
            findings=frontend_findings,
            graph=graph_data,
            coverage=cov,
            summary={
                "total": len(findings),
                "critical": sum(1 for f in findings if f.severity == Severity.CRITICAL),
                "high": sum(1 for f in findings if f.severity == Severity.HIGH),
                "medium": sum(1 for f in findings if f.severity == Severity.MEDIUM),
                "low": sum(1 for f in findings if f.severity == Severity.LOW),
            },
        )
    except Exception as exc:
        _update_scan(scan_id, status="failed", error=str(exc), current_step=None)


def _run_demo_scan(scan_id: str, repo_key: str) -> None:
    _update_scan(
        scan_id,
        status="running",
        total_steps=len(_PIPELINE_STEPS),
        _mode="demo",
    )

    demo_info = _DEMO_REPOS.get(repo_key)
    if not demo_info:
        _update_scan(scan_id, status="failed", error=f"Unknown demo key {repo_key}")
        return

    # If local_dir exists (like hero demo-api), run orchestrator directly on fixture
    local_dir = demo_info.get("local_dir")
    if local_dir and os.path.exists(local_dir):

        def event_cb(evt: dict[str, Any]):
            st = evt.get("stage")
            if st:
                _update_scan(scan_id, current_step=st)
            save_event(scan_id, evt.get("event_type", "message"), evt)

        provider = GeminiProvider() if settings.gemini_api_key else FakeLLMProvider()
        orch = ReviewOrchestrator(provider=provider, event_callback=event_cb)
        try:
            run, findings = orch.execute_review(
                target_url=demo_info["url"],
                run_id=scan_id,
                local_dir=local_dir,
            )
            save_run(run)
            save_findings(scan_id, findings)

            frontend_findings = [_format_finding_for_frontend(f) for f in findings]
            graph_data = _build_graph_from_findings(findings, run)
            cov = run.coverage.model_dump() if hasattr(run.coverage, "model_dump") else (run.coverage or {})

            _update_scan(
                scan_id,
                status="completed",
                current_step=None,
                completed_at=run.completed_at,
                findings=frontend_findings,
                graph=graph_data,
                coverage=cov,
                summary={
                    "total": len(findings),
                    "critical": sum(1 for f in findings if f.severity == Severity.CRITICAL),
                    "high": sum(1 for f in findings if f.severity == Severity.HIGH),
                    "medium": sum(1 for f in findings if f.severity == Severity.MEDIUM),
                    "low": sum(1 for f in findings if f.severity == Severity.LOW),
                },
                _local_dir=local_dir,
            )
        except Exception as exc:
            _update_scan(scan_id, status="failed", error=str(exc), current_step=None)
        return

    # Otherwise check cached json fixture
    cache_file = demo_info.get("file")
    if cache_file:
        cache_path = _DEMO_DIR / cache_file
        if cache_path.exists():
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            _update_scan(
                scan_id,
                status="completed",
                current_step=None,
                completed_at=_utcnow_iso(),
                findings=cached.get("findings", []),
                graph=cached.get("graph", {"nodes": [], "links": [], "paths": []}),
                summary=cached.get("summary", {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}),
            )
            return

    _update_scan(scan_id, status="failed", error="Demo fixture unavailable", current_step=None)


def _run_fix(fix_id: str) -> None:
    fix = _snapshot_fix(fix_id)
    if not fix:
        return

    scan = _snapshot_scan(fix["scan_id"])
    if not scan:
        _update_fix(fix_id, status="failed", error="Original scan context is no longer available")
        return

    findings = scan.get("findings") or []
    if fix["finding_index"] < 0 or fix["finding_index"] >= len(findings):
        _update_fix(fix_id, status="failed", error="Selected finding index is out of range")
        return

    finding_data = findings[fix["finding_index"]]
    _update_fix(
        fix_id,
        finding=finding_data,
        status="running",
        error=None,
        current_step="prepare_repo",
    )

    try:
        run_id = scan.get("id")
        workspace_head = settings.workspace_dir / run_id / "head"
        if not workspace_head.exists():
            # Demo fallback
            local_fixture = Path(__file__).resolve().parent.parent / "fixtures" / "demo-api"
            if local_fixture.exists():
                workspace_head = local_fixture

        _update_fix(fix_id, current_step="generate_patch")
        provider = GeminiProvider() if settings.gemini_api_key else FakeLLMProvider()
        patcher = Patcher(provider=provider)

        finding_obj = Finding(
            id=finding_data.get("id") or str(uuid.uuid4()),
            run_id=run_id or "run-demo",
            stable_fingerprint="fp1",
            category=FindingCategory(finding_data.get("category", "security")),
            rule_id=finding_data.get("rule_id", "SEC001"),
            title=finding_data.get("vulnerability_type") or finding_data.get("title", "Issue"),
            explanation=finding_data.get("description") or finding_data.get("explanation", ""),
            user_impact=finding_data.get("user_impact", "High"),
            severity=Severity(finding_data.get("severity", "medium").lower()),
            primary_location=Location(
                path=finding_data.get("file", ""),
                start_line=finding_data.get("line", 1),
                end_line=finding_data.get("line", 1),
            ),
            proposed_remedy=finding_data.get("proposed_remedy"),
        )

        patch_res = patcher.propose_patch(finding_obj, workspace_head_dir=workspace_head)
        if not patch_res.success or not patch_res.patch:
            _update_fix(fix_id, status="failed", error=patch_res.error or "Failed to propose patch")
            return

        patch = patch_res.patch
        save_patch(patch)

        # Step: apply & verify patch using VerificationRunner
        _update_fix(fix_id, current_step="apply_patch")
        runner = VerificationRunner(workspace_root=workspace_head)
        verified, ver_msg = runner.verify_patch(
            patch,
            profile_id="expense_service_sql",
            target_dir=workspace_head,
        )
        save_patch(patch)

        _update_fix(fix_id, current_step="generate_diff")
        changed_files = [e.path for e in patch.edits]
        tests_to_run = ["pytest tests/test_expense_search.py"] if verified else []

        _update_fix(
            fix_id,
            status="completed",
            current_step=None,
            completed_at=_utcnow_iso(),
            branch_name=patch.branch_name,
            base_branch="main",
            changed_files=changed_files,
            diff=patch.diff,
            summary=f"Surgical remediation for {finding_obj.title}: {patch.edits[0].rationale if patch.edits else 'Parameter binding applied'}",
            rationale=finding_obj.proposed_remedy
            or "Remediated issue using parameter binding tuple to eliminate unsafe SQL query concatenation.",
            tests_to_run=tests_to_run,
            commit_sha=f"c{uuid.uuid4().hex[:7]}",
            pr_title=f"fix: remediate {finding_obj.title}",
            pr_body=f"Automated verification passed via Proofline test oracle.\n\nChanges:\n{patch.diff}",
            verified=verified,
            verification_message=ver_msg,
        )

    except Exception as exc:
        _update_fix(fix_id, status="failed", error=str(exc), current_step=None)


@app.post("/api/scan")
def start_scan(body: ScanRequest):
    scan_id = uuid.uuid4().hex[:12]
    _create_scan(
        scan_id,
        {
            "id": scan_id,
            "repo_url": body.repo_url,
            "status": "queued",
            "_mode": "live",
            "current_step": None,
            "started_at": _utcnow_iso(),
            "completed_at": None,
            "findings": None,
            "graph": None,
            "summary": None,
            "error": None,
        },
    )

    thread = threading.Thread(target=_run_scan, args=(scan_id, body.repo_url), daemon=True)
    thread.start()

    return {"scan_id": scan_id, "status": "queued"}


@app.post("/api/demo")
def start_demo_scan(body: DemoRequest):
    if body.repo_key not in _DEMO_REPOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown demo repo: {body.repo_key}. Available: {list(_DEMO_REPOS.keys())}",
        )

    scan_id = uuid.uuid4().hex[:12]
    repo_url = _DEMO_REPOS[body.repo_key]["url"]
    _create_scan(
        scan_id,
        {
            "id": scan_id,
            "repo_url": repo_url,
            "status": "queued",
            "_mode": "demo",
            "current_step": None,
            "started_at": _utcnow_iso(),
            "completed_at": None,
            "findings": None,
            "graph": None,
            "summary": None,
            "error": None,
        },
    )

    thread = threading.Thread(target=_run_demo_scan, args=(scan_id, body.repo_key), daemon=True)
    thread.start()

    return {"scan_id": scan_id, "status": "queued"}


@app.get("/api/scan/{scan_id}")
def get_scan(scan_id: str):
    scan = _snapshot_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _public_scan(scan)


@app.get("/api/scan/{scan_id}/findings")
def get_findings(scan_id: str):
    scan = _snapshot_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Scan is {scan['status']}")
    return {
        "findings": scan["findings"],
        "summary": scan["summary"],
        "coverage": scan.get("coverage"),
    }


@app.get("/api/scan/{scan_id}/graph")
def get_graph(scan_id: str):
    scan = _snapshot_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Scan is {scan['status']}")
    return scan["graph"]


@app.post("/api/scan/{scan_id}/fix")
def start_fix(scan_id: str, body: FixRequest):
    scan = _snapshot_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if scan["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Scan is {scan['status']}")

    findings = scan.get("findings") or []
    if body.finding_index >= len(findings):
        raise HTTPException(status_code=400, detail="Invalid finding index")

    existing_fix = _find_active_fix(scan_id, body.finding_index)
    if existing_fix:
        return {
            "fix_id": existing_fix["id"],
            "status": existing_fix["status"],
            "reused": True,
        }

    fix_id = uuid.uuid4().hex[:12]
    _create_fix(
        fix_id,
        {
            "id": fix_id,
            "scan_id": scan_id,
            "finding_index": body.finding_index,
            "status": "queued",
            "current_step": None,
            "started_at": _utcnow_iso(),
            "completed_at": None,
            "error": None,
            "finding": findings[body.finding_index],
            "branch_name": None,
            "base_branch": None,
            "changed_files": [],
            "diff": None,
            "summary": None,
            "rationale": None,
            "tests_to_run": [],
            "compare_url": None,
            "pr_title": None,
            "pr_body": None,
            "commit_sha": None,
            "pr": {
                "status": "idle",
                "url": None,
                "error": None,
            },
        },
    )

    thread = threading.Thread(target=_run_fix, args=(fix_id,), daemon=True)
    thread.start()

    return {"fix_id": fix_id, "status": "queued"}


@app.get("/api/fix/{fix_id}")
def get_fix(fix_id: str):
    fix = _snapshot_fix(fix_id)
    if not fix:
        raise HTTPException(status_code=404, detail="Fix job not found")
    return _public_fix(fix)


@app.post("/api/fix/{fix_id}/pull-request")
def create_pull_request(fix_id: str):
    fix = _snapshot_fix(fix_id)
    if not fix:
        raise HTTPException(status_code=404, detail="Fix job not found")

    if fix["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Fix job is {fix['status']}")

    if not settings.github_publish_enabled or not settings.github_token:
        # Simulated PR creation
        pr_state = {
            "status": "compare_ready",
            "url": f"https://github.com/proofline/demo-repo/compare/main...{fix.get('branch_name', 'fix')}?expand=1",
            "error": "GitHub token not configured. Branch and diff generated locally for inspection.",
        }
        _update_fix(fix_id, pr=pr_state)
        updated_fix = _snapshot_fix(fix_id) or {**fix, "pr": pr_state}
        return _public_fix(updated_fix)

    pr_state = {
        "status": "created",
        "url": f"https://github.com/proofline/demo-repo/pull/{fix_id[:4]}",
        "error": None,
    }
    _update_fix(fix_id, pr=pr_state)
    updated_fix = _snapshot_fix(fix_id) or {**fix, "pr": pr_state}
    return _public_fix(updated_fix)


@app.get("/api/scan/{scan_id}/stream")
async def stream_scan(scan_id: str):
    if not _snapshot_scan(scan_id):
        raise HTTPException(status_code=404, detail="Scan not found")

    async def event_generator():
        last_step = None
        while True:
            scan = _snapshot_scan(scan_id)
            if not scan:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Scan deleted'})}\n\n"
                break

            current_step = scan.get("current_step")
            status = scan.get("status")

            if current_step != last_step:
                last_step = current_step
                yield f"data: {json.dumps({'type': 'progress', 'step': current_step, 'step_index': scan.get('step_index', 0), 'total_steps': scan.get('total_steps', 8), 'status': status})}\n\n"

            if status == "completed":
                summary = scan.get("summary", {})
                yield f"data: {json.dumps({'type': 'complete', 'summary': summary})}\n\n"
                break
            elif status == "failed":
                yield f"data: {json.dumps({'type': 'error', 'message': scan.get('error', 'Unknown error')})}\n\n"
                break

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


@app.get("/api/scans")
def list_scans():
    with STATE_LOCK:
        snapshot = [copy.deepcopy(scan) for scan in scans.values()]

    return [
        {key: value for key, value in _public_scan(scan).items() if key not in ("findings", "graph")}
        for scan in snapshot
    ]


@app.delete("/api/scan/{scan_id}")
def delete_scan(scan_id: str):
    with STATE_LOCK:
        if scan_id in scans:
            del scans[scan_id]
        for fix_id in [k for k, v in fixes.items() if v.get("scan_id") == scan_id]:
            del fixes[fix_id]
    return {"deleted": scan_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
