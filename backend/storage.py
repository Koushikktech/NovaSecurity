from __future__ import annotations

import os
from supabase import create_client, Client


def is_storage_configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)


def save_scan(
    scan_id: str,
    repo_url: str,
    status: str,
    started_at: str | None,
    completed_at: str | None,
    total_files: int,
    python_files: int,
    graph_nodes: int,
    graph_edges: int,
    vulnerable_paths: int,
    summary: dict | None,
    findings: list[dict],
    error: str | None = None,
) -> None:
    if not is_storage_configured():
        return

    client = _get_client()

    scan_row = {
        "id": scan_id,
        "repo_url": repo_url,
        "status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "total_files": total_files,
        "python_files": python_files,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "vulnerable_paths": vulnerable_paths,
        "findings_count": summary.get("total", 0) if summary else 0,
        "critical": summary.get("critical", 0) if summary else 0,
        "high": summary.get("high", 0) if summary else 0,
        "medium": summary.get("medium", 0) if summary else 0,
        "low": summary.get("low", 0) if summary else 0,
        "error": error,
    }
    client.table("scans").upsert(scan_row).execute()

    if findings:
        finding_rows = []
        for f in findings:
            finding_rows.append(
                {
                    "scan_id": scan_id,
                    "vulnerability_type": f.get("vulnerability_type"),
                    "severity": f.get("severity"),
                    "file": f.get("file"),
                    "line": f.get("line"),
                    "description": f.get("description"),
                    "evidence": f.get("evidence"),
                    "confidence": f.get("confidence"),
                    "final_confidence": f.get("final_confidence"),
                    "validation_status": f.get("validation_status"),
                    "sources": f.get("sources"),
                    "corroborated": f.get("corroborated"),
                    "red_team_success": f.get("red_team_success"),
                    "blue_team_disputed": f.get("blue_team_disputed"),
                    "cwe_id": f.get("cwe_id"),
                }
            )
        client.table("findings").insert(finding_rows).execute()

    print(f"  Saved scan {scan_id} to Supabase ({len(findings)} findings)")
