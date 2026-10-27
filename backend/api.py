from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _parse_allowed_origins(raw_value: str | None) -> list[str]:
    if not raw_value:
        return [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
        ]
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return max(1, int(raw_value))
    except ValueError:
        return default


app = FastAPI(title="Nova Security Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(os.getenv("NOVA_ALLOWED_ORIGINS")),
    allow_methods=["*"],
    allow_headers=["*"],
)


scans: dict[str, dict] = {}
fixes: dict[str, dict] = {}
STATE_LOCK = threading.RLock()
MAX_DIFF_PREVIEW_CHARS = _env_int("NOVA_MAX_DIFF_PREVIEW_CHARS", 60000)
_REPO_URL_RE = re.compile(r"^(?:https?://|ssh://|git@).+", re.IGNORECASE)


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

# Available demo repos with their cached results
_DEMO_DIR = Path(__file__).parent / "demo_results"
_DEMO_REPOS = {
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


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_scan(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in scan.items()
        if not key.startswith("_")
    }


def _public_fix(fix: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in fix.items()
        if not key.startswith("_")
    }


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


def _delete_scan_state(scan_id: str) -> list[str]:
    with STATE_LOCK:
        if scan_id not in scans:
            raise KeyError(scan_id)

        workspace_paths = [
            str(fix.get("_workspace_path"))
            for fix in fixes.values()
            if fix.get("scan_id") == scan_id and fix.get("_workspace_path")
        ]

        del scans[scan_id]
        for fix_id in [
            key for key, value in fixes.items() if value.get("scan_id") == scan_id
        ]:
            del fixes[fix_id]

    return workspace_paths


def _normalize_optional_text(value: Any, *, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def _normalize_string_list(
    value: Any,
    *,
    max_items: int = 12,
    max_item_len: int = 240,
) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        cleaned = cleaned[:max_item_len]
        if cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
        if len(items) >= max_items:
            break
    return items


def _truncate_diff(diff: str) -> str:
    if len(diff) <= MAX_DIFF_PREVIEW_CHARS:
        return diff
    return (
        f"{diff[:MAX_DIFF_PREVIEW_CHARS]}\n\n"
        f"[NOVA truncated this diff preview after {MAX_DIFF_PREVIEW_CHARS} characters.]"
    )


def _resolve_demo_repo_path(repo_key: str) -> str:
    from ingestor import CodeIngestor

    demo_info = _DEMO_REPOS[repo_key]
    local_dir = demo_info.get("local_dir")
    if local_dir:
        candidate = Path(__file__).parent / "temp" / str(local_dir)
        if candidate.exists():
            return str(candidate)

    ingestor = CodeIngestor(temp_dir=str(Path(__file__).parent / "temp"))
    try:
        return ingestor.from_git(demo_info["url"])
    except Exception as exc:
        print(f"  Note: Demo clone skipped or unavailable ({exc}). Using cached demo context.")
        return str(Path(__file__).parent / "temp" / (local_dir or repo_key))


def _build_demo_context(repo_key: str) -> tuple[str, list[dict[str, Any]], str]:
    from indexer import build_codebase_index, format_index_for_llm
    from ingestor import CodeIngestor

    repo_path = _resolve_demo_repo_path(repo_key)
    files = []
    if os.path.exists(repo_path):
        try:
            ingestor = CodeIngestor(temp_dir=str(Path(__file__).parent / "temp"))
            files = ingestor.get_files(repo_path)
        except Exception:
            files = []

    codebase_summary = ""
    if files:
        repo_name = Path(repo_path).name
        index, _ = build_codebase_index(files, repo_name=repo_name)
        codebase_summary = format_index_for_llm(index)

    return repo_path, files, codebase_summary


def _build_graph_data(graph, vulnerable_paths: list[dict]) -> dict:

    detected_nodes: set[str] = set()
    detected_edges: set[tuple[str, str]] = set()
    paths = []

    for finding in vulnerable_paths:
        path = finding["path"]
        paths.append(
            {
                "source": finding["source"],
                "sink": finding["sink"],
                "nodes": path,
                "sanitized": finding["sanitized"],
            }
        )
        for i, node in enumerate(path):
            detected_nodes.add(node)
            if i < len(path) - 1:
                detected_edges.add((path[i], path[i + 1]))

    nodes = []
    for node_id, data in graph.nodes(data=True):
        node_type = data.get("type", "unknown")
        category = "normal"
        if node_id in detected_nodes:
            category = "attacked"
        elif node_type == "source":
            category = "source"
        elif node_type == "sink":
            category = "sink"

        nodes.append(
            {
                "id": node_id,
                "label": data.get(
                    "label", node_id.split("::")[-1] if "::" in node_id else node_id
                ),
                "type": node_type,
                "category": category,
                "file": data.get("file", ""),
                "line": data.get("line", 0),
                "degree": graph.degree(node_id),
            }
        )

    links = []
    for u, v, data in graph.edges(data=True):
        links.append(
            {
                "source": u,
                "target": v,
                "type": data.get("type", "unknown"),
                "detected": (u, v) in detected_edges,
                "line": data.get("line", 0),
            }
        )

    return {"nodes": nodes, "links": links, "paths": paths}


# Pipeline steps in execution order (matched to ScanningSequence phases)
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


def _run_scan(scan_id: str, repo_url: str) -> None:

    from agent import app as agent_app, AgentState

    _update_scan(
        scan_id,
        status="running",
        current_step="ingest",
        step_index=0,
        total_steps=len(_PIPELINE_STEPS),
    )
    started_at = (_snapshot_scan(scan_id) or {}).get("started_at")

    try:
        initial_state: AgentState = {
            "repo_url": repo_url,
            "files": [],
            "python_files": [],
            "repo_path": "",
            "codebase_index": None,
            "codebase_summary": "",
            "code_fetcher": None,
            "graph": None,
            "vulnerable_paths": [],
            "findings": [],
            "findings_full": [],
            "all_findings": [],
            "after_validation": [],
        }

        # Stream pipeline execution to track real-time progress
        accumulated_state = dict(initial_state)
        for event in agent_app.stream(initial_state, stream_mode="updates"):
            # event is dict: {node_name: partial_state_update}
            for node_name, partial_update in event.items():
                if node_name in _PIPELINE_STEPS:
                    step_idx = _PIPELINE_STEPS.index(node_name)
                    # Merge partial update into accumulated state
                    if isinstance(partial_update, dict):
                        accumulated_state.update(partial_update)
                    # Mark current step as the NEXT one (this one just finished)
                    if step_idx + 1 < len(_PIPELINE_STEPS):
                        _update_scan(
                            scan_id,
                            current_step=_PIPELINE_STEPS[step_idx + 1],
                            step_index=step_idx + 1,
                        )
                    else:
                        _update_scan(
                            scan_id,
                            current_step="finalizing",
                            step_index=len(_PIPELINE_STEPS),
                        )

        result = accumulated_state

        findings = result.get("after_validation") or result.get("all_findings", [])

        graph_data = None
        graph_nodes = 0
        graph_edges = 0
        if result.get("graph") is not None:
            graph_data = _build_graph_data(
                result["graph"],
                result.get("vulnerable_paths", []),
            )
            graph_nodes = result["graph"].number_of_nodes()
            graph_edges = result["graph"].number_of_edges()

        clean_findings = []
        for f in findings:
            clean = {k: v for k, v in f.items() if _is_json_safe(v)}
            clean_findings.append(clean)

        summary = {
            "total": len(clean_findings),
            "critical": sum(
                1 for f in clean_findings if f.get("severity") == "Critical"
            ),
            "high": sum(1 for f in clean_findings if f.get("severity") == "High"),
            "medium": sum(1 for f in clean_findings if f.get("severity") == "Medium"),
            "low": sum(1 for f in clean_findings if f.get("severity") == "Low"),
        }

        completed_at = _utcnow_iso()
        _update_scan(
            scan_id,
            status="completed",
            current_step=None,
            completed_at=completed_at,
            findings=clean_findings,
            graph=graph_data,
            summary=summary,
            _repo_path=result.get("repo_path", ""),
            _files=result.get("files", []),
            _codebase_summary=result.get("codebase_summary", ""),
        )

        try:
            from storage import save_scan

            save_scan(
                scan_id=scan_id,
                repo_url=repo_url,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                total_files=len(result.get("files", [])),
                python_files=len(result.get("python_files", [])),
                graph_nodes=graph_nodes,
                graph_edges=graph_edges,
                vulnerable_paths=len(result.get("vulnerable_paths", [])),
                summary=summary,
                findings=clean_findings,
            )
        except Exception as db_err:
            print(f"  Warning: Supabase save failed: {db_err}")
            _update_scan(scan_id, db_error=str(db_err))

    except Exception as exc:
        completed_at = _utcnow_iso()
        _update_scan(
            scan_id,
            status="failed",
            error=str(exc),
            current_step=None,
            completed_at=completed_at,
        )

        try:
            from storage import save_scan

            save_scan(
                scan_id=scan_id,
                repo_url=repo_url,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                total_files=0,
                python_files=0,
                graph_nodes=0,
                graph_edges=0,
                vulnerable_paths=0,
                summary=None,
                findings=[],
                error=str(exc),
            )
        except Exception:
            pass


def _is_json_safe(value: object) -> bool:

    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


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

    thread = threading.Thread(
        target=_run_scan, args=(scan_id, body.repo_url), daemon=True
    )
    thread.start()

    return {"scan_id": scan_id, "status": "queued"}


# ── Demo endpoints ──────────────────────────────────────────────


def _run_demo_scan(scan_id: str, repo_key: str) -> None:
    """Simulate a scan using cached demo results."""
    import time

    _update_scan(
        scan_id,
        status="running",
        total_steps=len(_PIPELINE_STEPS),
        _mode="demo",
    )

    try:
        # Load cached results
        demo_info = _DEMO_REPOS[repo_key]
        cache_path = _DEMO_DIR / demo_info["file"]
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        repo_path, files, codebase_summary = _build_demo_context(repo_key)

        # Simulate progress through each pipeline step
        for i, step in enumerate(_PIPELINE_STEPS):
            _update_scan(scan_id, current_step=step, step_index=i)
            time.sleep(0.75)

        # Apply cached results
        _update_scan(
            scan_id,
            status="completed",
            current_step=None,
            completed_at=_utcnow_iso(),
            findings=cached["findings"],
            graph=cached["graph"],
            summary=cached["summary"],
            _repo_path=repo_path,
            _files=files,
            _codebase_summary=codebase_summary,
        )

    except Exception as exc:
        _update_scan(scan_id, status="failed", error=str(exc), current_step=None)


def _run_fix(fix_id: str) -> None:
    import git
    from graph import extract_code_for_finding
    from remediation import (
        apply_fix_response,
        build_compare_url,
        build_fix_prompt,
        cleanup_fix_workspace,
        checkout_fix_branch,
        commit_fix,
        create_pr_metadata,
        detect_base_branch,
        generate_diff,
        prepare_fix_workspace,
        request_fix_plan,
        select_fix_context_files,
    )

    fix = _snapshot_fix(fix_id)
    if not fix:
        return

    scan = _snapshot_scan(fix["scan_id"])
    if not scan:
        _update_fix(
            fix_id,
            status="failed",
            error="Original scan context is no longer available",
            current_step=None,
        )
        return

    repo_path = scan.get("_repo_path") or ""
    files = scan.get("_files") or []
    codebase_summary = scan.get("_codebase_summary") or ""
    findings = scan.get("findings") or []

    if not repo_path or not files:
        _update_fix(
            fix_id,
            status="failed",
            error="The selected scan does not have enough retained context to generate a fix",
            current_step=None,
        )
        return

    if fix["finding_index"] < 0 or fix["finding_index"] >= len(findings):
        _update_fix(
            fix_id,
            status="failed",
            error="Selected finding index is out of range",
            current_step=None,
        )
        return

    finding = findings[fix["finding_index"]]
    _update_fix(
        fix_id,
        finding=finding,
        status="running",
        error=None,
        current_step="prepare_repo",
    )

    workspace_path: str | None = None
    try:
        workspace_path = prepare_fix_workspace(repo_path, fix["scan_id"], fix_id)
        _update_fix(fix_id, _workspace_path=workspace_path)
        repo = git.Repo(workspace_path)
        base_branch = detect_base_branch(repo)

        slug = re.sub(
            r"[^a-zA-Z0-9]+",
            "-",
            str(finding.get("vulnerability_type", "security-fix")).strip().lower(),
        ).strip("-") or "security-fix"
        branch_name = f"nova/{slug}-{fix_id}"
        checkout_fix_branch(repo, base_branch, branch_name)

        _update_fix(fix_id, current_step="assemble_context")
        context_files = select_fix_context_files(finding, files)
        if not context_files:
            raise ValueError(
                "Could not gather any full-file context for this vulnerability"
            )

        relevant_code = extract_code_for_finding(finding, files)
        prompt = build_fix_prompt(
            repo_url=scan["repo_url"],
            finding=finding,
            codebase_summary=codebase_summary,
            context_files=context_files,
            relevant_code=relevant_code,
        )

        _update_fix(fix_id, current_step="generate_patch")
        response = request_fix_plan(prompt)

        _update_fix(fix_id, current_step="apply_patch")
        allowed_paths = {
            os.path.normpath(str(file_info["relative_path"]))
            for file_info in context_files
            if file_info.get("relative_path")
        }
        changed_files = apply_fix_response(workspace_path, allowed_paths, response or {})

        pr_title, pr_body = create_pr_metadata(response or {}, finding, branch_name)
        safe_pr_title = (
            _normalize_optional_text(pr_title, max_len=240)
            or "fix: remediate security issue"
        )
        safe_pr_body = (
            _normalize_optional_text(pr_body, max_len=20000)
            or "Automated remediation generated by NOVA."
        )
        commit_sha = commit_fix(repo, safe_pr_title)

        _update_fix(fix_id, current_step="generate_diff")
        diff = _truncate_diff(generate_diff(repo))
        compare_url = build_compare_url(
            repo_url=scan["repo_url"],
            base_branch=base_branch,
            branch_name=branch_name,
            title=safe_pr_title,
            body=safe_pr_body,
        )

        tests_to_run = _normalize_string_list(
            response.get("tests_to_run") if isinstance(response, dict) else []
        )

        _update_fix(
            fix_id,
            status="completed",
            current_step=None,
            completed_at=_utcnow_iso(),
            branch_name=branch_name,
            base_branch=base_branch,
            changed_files=changed_files,
            diff=diff,
            summary=_normalize_optional_text(
                response.get("summary") if isinstance(response, dict) else None,
                max_len=4000,
            ),
            rationale=_normalize_optional_text(
                response.get("rationale") if isinstance(response, dict) else None,
                max_len=12000,
            ),
            tests_to_run=tests_to_run,
            compare_url=compare_url,
            pr_title=safe_pr_title,
            pr_body=safe_pr_body,
            commit_sha=commit_sha,
            pr={
            "status": "idle",
            "url": None,
            "error": None,
            },
            _workspace_path=workspace_path,
        )

    except Exception as exc:
        cleanup_fix_workspace(workspace_path)
        _update_fix(
            fix_id,
            status="failed",
            error=str(exc),
            current_step=None,
            _workspace_path=None,
        )


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

    thread = threading.Thread(
        target=_run_demo_scan, args=(scan_id, body.repo_key), daemon=True
    )
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
    return {"findings": scan["findings"], "summary": scan["summary"]}


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
        "_workspace_path": None,
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
    from remediation import attempt_create_github_pr

    fix = _snapshot_fix(fix_id)
    if not fix:
        raise HTTPException(status_code=404, detail="Fix job not found")

    scan = _snapshot_scan(fix.get("scan_id", ""))
    if fix["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"Fix job is {fix['status']}")

    current_pr = fix.get("pr") or {"status": "idle", "url": None, "error": None}
    if current_pr.get("status") == "creating":
        raise HTTPException(
            status_code=409,
            detail="Pull request creation is already in progress",
        )

    if current_pr.get("status") == "created" and current_pr.get("url"):
        return _public_fix(fix)

    if scan and scan.get("_mode") == "demo":
        _update_fix(
            fix_id,
            pr={
                "status": "failed",
                "url": None,
                "error": "Pull request creation is unavailable for this scan.",
            },
        )
        updated_fix = _snapshot_fix(fix_id) or fix
        return _public_fix(updated_fix)

    workspace_path = fix.get("_workspace_path")
    if not workspace_path:
        raise HTTPException(status_code=409, detail="No remediation workspace is available")
    if not fix.get("branch_name") or not fix.get("base_branch"):
        raise HTTPException(
            status_code=409,
            detail="The remediation branch metadata is incomplete",
        )

    _update_fix(
        fix_id,
        pr={
        "status": "creating",
        "url": None,
        "error": None,
        },
    )

    try:
        pr_state = attempt_create_github_pr(
            workspace_path=workspace_path,
            branch_name=fix["branch_name"],
            base_branch=fix["base_branch"],
            title=fix["pr_title"] or "fix: remediate security issue",
            body=fix["pr_body"] or "Automated remediation generated by NOVA.",
            compare_url=fix.get("compare_url"),
        )
    except Exception as exc:
        pr_state = {
            "status": "failed",
            "url": None,
            "error": str(exc),
        }

    _update_fix(fix_id, pr=pr_state)
    updated_fix = _snapshot_fix(fix_id) or {**fix, "pr": pr_state}
    return _public_fix(updated_fix)


@app.get("/api/scan/{scan_id}/stream")
async def stream_scan(scan_id: str):
    """SSE endpoint for real-time scan progress."""
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
    from remediation import cleanup_fix_workspace

    try:
        workspace_paths = _delete_scan_state(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Scan not found")

    for workspace_path in workspace_paths:
        cleanup_fix_workspace(workspace_path)

    return {"deleted": scan_id}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
