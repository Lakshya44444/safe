"""Bhawan segregation scores, the leaderboard and campus summary.

Score = average grade points (A=100, B=60, C=20) over the window.
Days are counted in campus time (config.TIMEZONE), so "today" matches what people on campus see.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, db

TZ = ZoneInfo(config.TIMEZONE)


def local_day(iso: str) -> str:
    """Campus-time date of a stored UTC timestamp."""
    return datetime.fromisoformat(iso).astimezone(TZ).date().isoformat()


def window_start(days: int, now: datetime | None = None) -> str:
    """UTC ISO timestamp of local midnight `days - 1` days ago: days=1 means 'today'."""
    now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    start = datetime.combine(now.date() - timedelta(days=days - 1), time.min, tzinfo=TZ)
    return start.astimezone(timezone.utc).isoformat(timespec="seconds")


def _avg_points(rs: list[dict]) -> float:
    return sum(config.GRADE_POINTS[r["grade"]] for r in rs) / len(rs)


def bhawan_scores(days: int = 7) -> list[dict]:
    reports = db.graded_since(window_start(days))
    today = datetime.now(TZ).date().isoformat()
    by_bhawan: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        by_bhawan[r["bhawan"]].append(r)

    rows = []
    for bhawan, rs in by_bhawan.items():
        todays = [r for r in rs if local_day(r["created_at"]) == today]
        earlier = [r for r in rs if local_day(r["created_at"]) != today]
        items = Counter(item for r in rs for item in r["found_items"])
        rows.append({
            "bhawan": bhawan,
            "score": round(_avg_points(rs)),
            "reports": len(rs),
            "grades": {g: sum(r["grade"] == g for r in rs) for g in ("A", "B", "C")},
            "avg_contamination": round(sum(r["contamination"] for r in rs) / len(rs)),
            "top_wrong_items": [name for name, _ in items.most_common(3)],
            # Today's average minus the rest of the window; None when either side is empty.
            "trend": round(_avg_points(todays) - _avg_points(earlier)) if todays and earlier else None,
        })
    rows.sort(key=lambda x: (-x["score"], -x["reports"], x["bhawan"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def campus_summary(days: int = 7) -> dict:
    since = window_start(days)
    reports = db.graded_since(since)
    n = len(reports)
    clean = sum(r["grade"] == "A" for r in reports)
    wet_clean = sum(r["bin_stream"] == "wet" and r["grade"] == "A" for r in reports)

    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        by_day[local_day(r["created_at"])].append(r)
    daily = [{"date": d, "score": round(_avg_points(rs)), "reports": len(rs)} for d, rs in sorted(by_day.items())]

    by_stream = {}
    for s in config.STREAMS:
        rs = [r for r in reports if r["bin_stream"] == s]
        by_stream[s] = {"reports": len(rs),
                        "clean_rate": round(100 * sum(r["grade"] == "A" for r in rs) / len(rs)) if rs else None}

    return {
        "days": days,
        "reports": n,
        "segregation_rate": round(100 * clean / n) if n else 0,
        "wet_bins_compost_ready": wet_clean,
        # Estimate only: clean wet bins x assumed weight per bin (KG_PER_WET_BIN).
        "compost_kg_estimate": round(wet_clean * config.KG_PER_WET_BIN),
        "kg_per_wet_bin": config.KG_PER_WET_BIN,
        "by_stream": by_stream,
        "issues": db.issue_stats(since),
        "daily": daily,
    }


def bhawan_detail(bhawan: str, days: int = 7) -> dict:
    """One Bhawan's report card: rank, per-bin clean rates, daily trend and recent checks."""
    rows = bhawan_scores(days)
    row = next((r for r in rows if r["bhawan"] == bhawan), None)
    reports = [r for r in db.graded_since(window_start(days)) if r["bhawan"] == bhawan]

    by_day: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        by_day[local_day(r["created_at"])].append(r)
    by_stream = {}
    for s in config.STREAMS:
        rs = [r for r in reports if r["bin_stream"] == s]
        by_stream[s] = {
            "reports": len(rs),
            "clean_rate": round(100 * sum(r["grade"] == "A" for r in rs) / len(rs)) if rs else None,
            "top_wrong_items": [n for n, _ in Counter(i for r in rs for i in r["found_items"]).most_common(3)],
        }
    worst = min((s for s in by_stream if by_stream[s]["reports"]),
                key=lambda s: by_stream[s]["clean_rate"], default=None)
    return {
        "bhawan": bhawan,
        "days": days,
        "rank": row["rank"] if row else None,
        "of": len(rows),
        "score": row["score"] if row else None,
        "grades": row["grades"] if row else {"A": 0, "B": 0, "C": 0},
        "reports": len(reports),
        "trend": row["trend"] if row else None,
        "by_stream": by_stream,
        "worst_stream": worst,
        "daily": [{"date": d, "score": round(_avg_points(rs)), "reports": len(rs)} for d, rs in sorted(by_day.items())],
    }
