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
            "hazard_bins": hazard_stats(rs)["bins"],
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
        # Estimate only: compost estimate x EPA WARM landfill-vs-compost factor (see config).
        "co2e_kg_avoided_estimate": round(wet_clean * config.KG_PER_WET_BIN * config.CO2E_KG_PER_KG_COMPOSTED),
        "by_stream": by_stream,
        "issues": db.issue_stats(since),
        "worker_checks": db.verdict_stats(since),
        "hazards": hazard_stats(reports),
        "daily": daily,
    }


def hazard_stats(reports: list[dict]) -> dict:
    """Bins where a dangerous item was found in the wrong bin (sharps, batteries, medicines, sanitary waste)."""
    from .identify import identify  # local import: identify -> chat -> scoring
    items: Counter = Counter()
    bins = 0
    for r in reports:
        found = [x["item"] for x in identify(r["found_items"], r["bin_stream"]) if x["hazard"]]
        if found:
            bins += 1
            items.update(found)
    return {"bins": bins, "top_items": [n for n, _ in items.most_common(3)]}


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


# ---------- collection priority (problem area 2) ----------

ISSUE_WEIGHT = {"overflow": 3, "missed_pickup": 3, "broken_bin": 1, "other": 1}


def collection_plan() -> list[dict]:
    """Which Bhawans the collection team should visit first today, and why.

    Priority = open complaints (overflowing / missed pickup weigh most, older ones more)
             + mixed (C) bins found today, which need re-sorting before collection.
    No GPS here: it is an ordered list, not a route.
    """
    now = datetime.now(timezone.utc)
    stops: dict[str, dict] = {}

    def stop(b: str) -> dict:
        return stops.setdefault(b, {"bhawan": b, "priority": 0.0, "reasons": [], "open_issues": 0, "mixed_bins_today": 0,
                                    "hazards_today": 0})

    for i in db.list_issues("open", limit=500):
        hours = (now - datetime.fromisoformat(i["created_at"])).total_seconds() / 3600
        s = stop(i["bhawan"])
        s["priority"] += ISSUE_WEIGHT.get(i["kind"], 1) * (1 + min(hours, 48) / 12)
        s["open_issues"] += 1
        s["reasons"].append({"kind": i["kind"], "hours_open": round(hours, 1), "issue_id": i["id"]})
    from .identify import identify
    for r in db.graded_since(window_start(1)):
        danger = [x["item"] for x in identify(r["found_items"], r["bin_stream"]) if x["hazard"]]
        if danger:  # worker safety first: pull dangerous items out before anyone hand-sorts the bin
            s = stop(r["bhawan"])
            s["priority"] += 4
            s["hazards_today"] = s.get("hazards_today", 0) + 1
            s["reasons"].insert(0, {"kind": "hazard", "items": danger, "bin_stream": r["bin_stream"]})
        if r["grade"] == "C":
            s = stop(r["bhawan"])
            s["priority"] += 1
            s["mixed_bins_today"] += 1
    plan = sorted(stops.values(), key=lambda x: -x["priority"])
    for n, s in enumerate(plan, 1):
        s["order"] = n
        s["priority"] = round(s["priority"], 1)
    return plan


# ---------- forecast: who needs a nudge (problem area 4) ----------

def _slope(ys: list[float]) -> float:
    n = len(ys)
    mx, my = (n - 1) / 2, sum(ys) / n
    den = sum((x - mx) ** 2 for x in range(n))
    return sum((x - mx) * (y - my) for x, y in enumerate(ys)) / den if den else 0.0


def forecast(days: int = 7, min_days: int = 3) -> list[dict]:
    """Tomorrow's score per Bhawan from a straight-line fit over its recent daily scores.

    Deliberately simple and explainable: with a week of data per Bhawan, a trend line is
    about as much as the data supports. Flags Bhawans heading below a B (60) or falling fast.
    """
    by: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in db.graded_since(window_start(days)):
        by[r["bhawan"]][local_day(r["created_at"])].append(r)
    out = []
    for bhawan, days_map in by.items():
        if len(days_map) < min_days:
            continue
        series = [_avg_points(rs) for _, rs in sorted(days_map.items())]
        slope = _slope(series)
        nxt = max(0.0, min(100.0, series[-1] + slope))
        out.append({
            "bhawan": bhawan,
            "last": round(series[-1]),
            "slope_per_day": round(slope, 1),
            "tomorrow": round(nxt),
            "days_used": len(series),
            "needs_nudge": nxt < 60 or slope <= -5,
        })
    out.sort(key=lambda x: (not x["needs_nudge"], x["tomorrow"]))
    return out
