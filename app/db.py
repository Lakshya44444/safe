"""Tiny SQLite layer. One table of reports; scores are computed from it."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    bhawan        TEXT NOT NULL,
    bin_stream    TEXT NOT NULL,          -- which bin the photo is of: wet/dry/sanitary/special_care
    reporter      TEXT,                   -- e.g. "Ramesh bhaiya"
    note          TEXT,                   -- what the worker said (voice transcript)
    photo_path    TEXT,
    status        TEXT NOT NULL,          -- pending | graded | failed
    grade         TEXT,                   -- A | B | C
    contamination INTEGER,                -- estimated % of wrong-stream items
    found_items   TEXT,                   -- JSON list of wrong items spotted
    tag_hi        TEXT,                   -- Shabash / Oops message in Hinglish
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_reports_bhawan ON reports(bhawan);
CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);

-- Collection problems: bin overflowing, pickup missed, bin broken.
CREATE TABLE IF NOT EXISTS issues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    bhawan       TEXT NOT NULL,
    kind         TEXT NOT NULL,           -- overflow | missed_pickup | broken_bin | other
    note         TEXT,
    reporter     TEXT,
    status       TEXT NOT NULL DEFAULT 'open',   -- open | resolved
    resolved_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_status ON issues(status);
"""

ISSUE_KINDS = ["overflow", "missed_pickup", "broken_bin", "other"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def create_report(bhawan: str, bin_stream: str, reporter: str | None,
                  note: str | None, photo_path: str | None,
                  created_at: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO reports (created_at, bhawan, bin_stream, reporter, note, photo_path, status)"
            " VALUES (?, ?, ?, ?, ?, ?, 'pending')",
            (created_at or now_iso(), bhawan, bin_stream, reporter, note, photo_path),
        )
        return int(cur.lastrowid)


def save_grade(report_id: int, grade: str, contamination: int,
               found_items: list[str], tag_hi: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE reports SET status='graded', grade=?, contamination=?, found_items=?, tag_hi=?, error=NULL"
            " WHERE id=?",
            (grade, contamination, json.dumps(found_items, ensure_ascii=False), tag_hi, report_id),
        )


def mark_failed(report_id: int, error: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE reports SET status='failed', error=? WHERE id=?", (error[:500], report_id))


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["found_items"] = json.loads(d["found_items"]) if d.get("found_items") else []
    return d


def get_report(report_id: int) -> dict | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return _row(r) if r else None


def list_reports(limit: int = 50, bhawan: str | None = None) -> list[dict]:
    q = "SELECT * FROM reports"
    args: list = []
    if bhawan:
        q += " WHERE bhawan=?"
        args.append(bhawan)
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [_row(r) for r in conn.execute(q, args).fetchall()]


def graded_since(since_iso: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE status='graded' AND created_at>=? ORDER BY created_at",
            (since_iso,),
        ).fetchall()
        return [_row(r) for r in rows]


# ---- issues ----

def create_issue(bhawan: str, kind: str, note: str | None, reporter: str | None,
                 created_at: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO issues (created_at, bhawan, kind, note, reporter) VALUES (?, ?, ?, ?, ?)",
            (created_at or now_iso(), bhawan, kind, note, reporter),
        )
        return int(cur.lastrowid)


def list_issues(status: str | None = "open", limit: int = 50) -> list[dict]:
    q, args = "SELECT * FROM issues", []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def resolve_issue(issue_id: int) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE issues SET status='resolved', resolved_at=? WHERE id=? AND status='open'",
                     (now_iso(), issue_id))
        r = conn.execute("SELECT * FROM issues WHERE id=?", (issue_id,)).fetchone()
        return dict(r) if r else None


def issue_stats(since_iso: str) -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM issues WHERE created_at>=?", (since_iso,)).fetchall()
    rows = [dict(r) for r in rows]
    fixed = [r for r in rows if r["status"] == "resolved" and r["resolved_at"]]
    hours = []
    for r in fixed:
        a = datetime.fromisoformat(r["created_at"])
        b = datetime.fromisoformat(r["resolved_at"])
        hours.append((b - a).total_seconds() / 3600)
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r["status"] == "open"),
        "avg_hours_to_fix": round(sum(hours) / len(hours), 1) if hours else None,
    }
