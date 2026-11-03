from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config import settings
from schemas.contracts import Disposition, Finding, Patch, ReviewRun

_LOCAL_LOCK = threading.RLock()


def _get_db_path() -> Path:
    if settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.replace("sqlite:///", "")
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "proofline.db"


def init_database() -> None:
    """Initialize SQLite database with WAL mode and tables."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _LOCAL_LOCK, sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_runs (
                id TEXT PRIMARY KEY,
                canonical_repo TEXT NOT NULL,
                input_mode TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                data JSON NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                stable_fingerprint TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                disposition TEXT NOT NULL,
                data JSON NOT NULL,
                FOREIGN KEY (run_id) REFERENCES review_runs(id)
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patches (
                id TEXT PRIMARY KEY,
                finding_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                status TEXT NOT NULL,
                data JSON NOT NULL
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload JSON NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, event_id);")
        conn.commit()


init_database()


def save_run(run: ReviewRun, *, preserve_cancelled: bool = False) -> None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        if preserve_cancelled:
            previous = conn.execute("SELECT status, completed_at FROM review_runs WHERE id=?", (run.id,)).fetchone()
            if previous and previous[0] == "cancelled":
                from schemas.contracts import RunStatus

                run.status = RunStatus.CANCELLED
                run.completed_at = previous[1] or run.completed_at
        conn.execute(
            """
            INSERT OR REPLACE INTO review_runs (id, canonical_repo, input_mode, status, started_at, completed_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run.id,
                run.canonical_repo,
                run.input_mode.value,
                run.status.value,
                run.started_at,
                run.completed_at,
                run.model_dump_json(),
            ),
        )
        conn.commit()


def get_run(run_id: str) -> ReviewRun | None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT data FROM review_runs WHERE id = ?;", (run_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return ReviewRun.model_validate_json(row[0])


def save_findings(run_id: str, findings: list[Finding]) -> None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        for f in findings:
            conn.execute(
                """
                INSERT OR REPLACE INTO findings (id, run_id, stable_fingerprint, category, severity, disposition, data)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    f.id,
                    run_id,
                    f.stable_fingerprint,
                    f.category.value,
                    f.severity.value,
                    f.disposition.value,
                    f.model_dump_json(),
                ),
            )
        conn.commit()


def get_findings(run_id: str) -> list[Finding]:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT data FROM findings WHERE run_id = ?;", (run_id,))
        rows = cursor.fetchall()
        return [Finding.model_validate_json(row[0]) for row in rows]


def get_finding(finding_id: str) -> Finding | None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT data FROM findings WHERE id = ?;", (finding_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Finding.model_validate_json(row[0])


def update_finding_disposition(finding_id: str, disposition: str, reason: str | None = None) -> bool:
    finding = get_finding(finding_id)
    if not finding:
        return False
    finding.disposition = Disposition(disposition)
    finding.disposition_reason = reason
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        conn.execute(
            "UPDATE findings SET disposition = ?, data = ? WHERE id = ?;",
            (finding.disposition.value, finding.model_dump_json(), finding_id),
        )
        conn.commit()
    return True


def save_patch(patch: Patch) -> None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO patches (id, finding_id, run_id, status, data)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                patch.id,
                patch.finding_id,
                patch.run_id,
                patch.status.value,
                patch.model_dump_json(),
            ),
        )
        conn.commit()


def get_patch(patch_id: str) -> Patch | None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute("SELECT data FROM patches WHERE id = ?;", (patch_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Patch.model_validate_json(row[0])


def save_event(run_id: str, event_type: str, payload: dict[str, Any]) -> int:
    import datetime

    ts = datetime.datetime.now(datetime.UTC).isoformat()
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO events (run_id, event_type, timestamp, payload)
            VALUES (?, ?, ?, ?);
            """,
            (run_id, event_type, ts, json.dumps(payload)),
        )
        conn.commit()
        return cursor.lastrowid or 0


def get_events(run_id: str, after_event_id: int = 0) -> list[dict[str, Any]]:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        cursor = conn.execute(
            """
            SELECT event_id, event_type, timestamp, payload
            FROM events
            WHERE run_id = ? AND event_id > ?
            ORDER BY event_id ASC;
            """,
            (run_id, after_event_id),
        )
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "event_id": row[0],
                    "event_type": row[1],
                    "timestamp": row[2],
                    **json.loads(row[3]),
                }
            )
        return results


def interrupt_orphaned_runs() -> None:
    """Single-worker deployment restart recovery: never leave stale jobs polling forever."""
    from datetime import UTC, datetime

    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        rows = conn.execute("SELECT id, data FROM review_runs WHERE status IN ('queued','running')").fetchall()
        for run_id, raw in rows:
            run = ReviewRun.model_validate_json(raw)
            from schemas.contracts import RunStatus

            run.status = RunStatus.INTERRUPTED
            run.completed_at = datetime.now(UTC).isoformat()
            run.errors.append("Server restarted before this review finished; resume from sealed source when available")
            conn.execute(
                "UPDATE review_runs SET status=?, completed_at=?, data=? WHERE id=?",
                (run.status.value, run.completed_at, run.model_dump_json(), run_id),
            )
            conn.execute(
                "INSERT INTO events (run_id, event_type, timestamp, payload) VALUES (?, ?, ?, ?)",
                (
                    run_id,
                    "run_interrupted",
                    run.completed_at,
                    json.dumps({"status": "interrupted", "reason": "server_restart"}),
                ),
            )
        conn.commit()


def previous_review(run: ReviewRun) -> ReviewRun | None:
    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        rows = conn.execute(
            "SELECT data FROM review_runs WHERE canonical_repo=? AND id!=? AND status IN ('completed','partial') ORDER BY started_at DESC LIMIT 30",
            (run.canonical_repo, run.id),
        ).fetchall()
    for (raw,) in rows:
        candidate = ReviewRun.model_validate_json(raw)
        if (
            candidate.review_mode == run.review_mode
            and candidate.started_at < run.started_at
            and candidate.coverage.get("identity_version", 1) == run.coverage.get("identity_version", 1)
        ):
            return candidate
    return None


def cancel_review_run(run_id: str) -> ReviewRun | None:
    """Atomically stop an active record without overwriting a concurrent completed result."""
    from datetime import UTC, datetime

    from schemas.contracts import RunStatus

    with _LOCAL_LOCK, sqlite3.connect(_get_db_path()) as conn:
        row = conn.execute("SELECT data FROM review_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        run = ReviewRun.model_validate_json(row[0])
        if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
            return run
        run.status = RunStatus.CANCELLED
        run.completed_at = datetime.now(UTC).isoformat()
        conn.execute(
            "UPDATE review_runs SET status=?, completed_at=?, data=? WHERE id=?",
            (run.status.value, run.completed_at, run.model_dump_json(), run.id),
        )
        conn.execute(
            "INSERT INTO events (run_id, event_type, timestamp, payload) VALUES (?, ?, ?, ?)",
            (run.id, "run_cancelled", run.completed_at, json.dumps({"status": "cancelled"})),
        )
        return run
