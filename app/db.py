"""SQLite storage: bin reports and collection issues. Scores are computed from reports."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config
from .models import GradeResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    bhawan        TEXT NOT NULL,
    bin_stream    TEXT NOT NULL,          -- wet | dry | sanitary | special_care
    reporter      TEXT,
    note          TEXT,                   -- what the worker said (typed or transcribed)
    photo_path    TEXT,
    status        TEXT NOT NULL,          -- pending | graded | failed
    grade         TEXT,                   -- A | B | C
    contamination INTEGER,                -- estimated % of items from other streams
    found_items   TEXT,                   -- JSON list of wrong items
    tag           TEXT,                   -- feedback shown to the worker
    confidence    REAL,
    source        TEXT,                   -- photo | note
    provider      TEXT,                   -- which LLM graded it
    model         TEXT,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_bhawan ON reports(bhawan);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);

CREATE TABLE IF NOT EXISTS issues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    bhawan       TEXT NOT NULL,
    kind         TEXT NOT NULL,           -- overflow | missed_pickup | broken_bin | other
    note         TEXT,
    reporter     TEXT,
    status       TEXT NOT NULL DEFAULT 'open',
    resolved_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
"""

ISSUE_KINDS = ["overflow", "missed_pickup", "broken_bin", "other"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # readers don't block the grading thread's writes
        conn.executescript(SCHEMA)


def _report(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["found_items"] = json.loads(d["found_items"]) if d.get("found_items") else []
    return d


# ---- reports ----

def create_report(bhawan: str, bin_stream: str, reporter: str | None, note: str | None,
                  photo_path: str | None, created_at: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO reports (created_at, bhawan, bin_stream, reporter, note, photo_path, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (created_at or now_iso(), bhawan, bin_stream, reporter, note, photo_path),
        )
        return int(cur.lastrowid)


def save_grade(report_id: int, g: GradeResult) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE reports SET status='graded', grade=?, contamination=?, found_items=?, tag=?,"
            " confidence=?, source=?, provider=?, model=?, error=NULL WHERE id=?",
            (g.grade, g.contamination, json.dumps(g.found_items), g.tag, g.confidence,
             g.source, g.provider, g.model, report_id),
        )


def mark_failed(report_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE reports SET status='failed', error=? WHERE id=?", (error[:500], report_id))


def get_report(report_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    return _report(row) if row else None


def list_reports(limit: int = 50, bhawan: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM reports", []
    if bhawan:
        sql += " WHERE bhawan=?"
        args.append(bhawan)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [_report(r) for r in conn.execute(sql, args).fetchall()]


def graded_since(since_iso: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE status='graded' AND created_at>=? ORDER BY created_at",
            (since_iso,),
        ).fetchall()
    return [_report(r) for r in rows]


def has_reports() -> bool:
    with connect() as conn:
        return conn.execute("SELECT 1 FROM reports LIMIT 1").fetchone() is not None


# ---- issues ----

def create_issue(bhawan: str, kind: str, note: str | None, reporter: str | None,
                 created_at: str | None = None) -> int:
    if kind not in ISSUE_KINDS:
        kind = "other"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO issues (created_at, bhawan, kind, note, reporter) VALUES (?, ?, ?, ?, ?)",
            (created_at or now_iso(), bhawan, kind, note, reporter),
        )
        return int(cur.lastrowid)


def list_issues(status: str | None = "open", limit: int = 50) -> list[dict]:
    sql, args = "SELECT * FROM issues", []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def resolve_issue(issue_id: int, resolved_at: str | None = None) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE issues SET status='resolved', resolved_at=? WHERE id=? AND status='open'",
                     (resolved_at or now_iso(), issue_id))
        row = conn.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
    return dict(row) if row else None


def issue_stats(since_iso: str) -> dict:
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM issues WHERE created_at>=?", (since_iso,))]
    hours = [
        (datetime.fromisoformat(r["resolved_at"]) - datetime.fromisoformat(r["created_at"])).total_seconds() / 3600
        for r in rows if r["status"] == "resolved" and r["resolved_at"]
    ]
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "avg_hours_to_fix": round(sum(hours) / len(hours), 1) if hours else None,
    }
