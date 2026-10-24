"""Bhawan Segregation Score and the leaderboard.

Score = average grade points (A=100, B=60, C=20) over the window.
Trend compares the latest day with the days before it.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import config, db


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def bhawan_scores(days: int = 7) -> list[dict]:
    reports = db.graded_since(_since(days))
    by_bhawan: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        by_bhawan[r["bhawan"]].append(r)

    today = datetime.now(timezone.utc).date().isoformat()
    rows = []
    for bhawan, rs in by_bhawan.items():
        pts = [config.GRADE_POINTS[r["grade"]] for r in rs]
        today_pts = [config.GRADE_POINTS[r["grade"]] for r in rs if r["created_at"][:10] == today]
        before_pts = [config.GRADE_POINTS[r["grade"]] for r in rs if r["created_at"][:10] != today]
        item_counts: dict[str, int] = defaultdict(int)
        for r in rs:
            for it in r["found_items"]:
                item_counts[it] += 1
        top_items = sorted(item_counts, key=item_counts.get, reverse=True)[:3]
        trend = None
        if today_pts and before_pts:
            trend = round(sum(today_pts) / len(today_pts) - sum(before_pts) / len(before_pts))
        rows.append({
            "bhawan": bhawan,
            "score": round(sum(pts) / len(pts)),
            "reports": len(rs),
            "grades": {g: sum(1 for r in rs if r["grade"] == g) for g in ("A", "B", "C")},
            "avg_contamination": round(sum(r["contamination"] for r in rs) / len(rs)),
            "top_wrong_items": top_items,
            "trend": trend,
        })
    rows.sort(key=lambda x: (-x["score"], -x["reports"], x["bhawan"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def campus_summary(days: int = 7) -> dict:
    reports = db.graded_since(_since(days))
    n = len(reports)
    clean = sum(1 for r in reports if r["grade"] == "A")
    wet_clean = sum(1 for r in reports if r["bin_stream"] == "wet" and r["grade"] == "A")
    by_day: dict[str, list[int]] = defaultdict(list)
    for r in reports:
        by_day[r["created_at"][:10]].append(config.GRADE_POINTS[r["grade"]])
    daily = [{"date": d, "score": round(sum(v) / len(v)), "reports": len(v)}
             for d, v in sorted(by_day.items())]
    return {
        "days": days,
        "reports": n,
        "segregation_rate": round(100 * clean / n) if n else 0,
        "wet_bins_compost_ready": wet_clean,
        "daily": daily,
    }
