"""Fill the database with a believable demo week so the dashboard isn't empty.

Run:  python -m scripts.seed_demo
Seeded rows have reporter='demo-seed'. Grading uses the offline mock provider, never a paid API.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app import config, db, grader
from app.llm_gateway import LLMGateway, get_gateway, reset_gateway
from app.llm_gateway.providers import MockProvider

NOTES = {
    "good": ["bin is clean", "all fine today", "looks clean"],
    "mid": ["some plastic in it", "a couple of wrappers", "some paper mixed in"],
    "bad": ["plastic bag and bottle", "food and plastic mixed", "pad and chips packet mixed"],
}
ISSUE_NOTES = {"overflow": "bin is full", "missed_pickup": "morning pickup did not come",
               "broken_bin": "bin lid is broken"}


def main(days: int = 7, per_day: int = 6, seed: int = 7) -> None:
    rnd = random.Random(seed)
    base_quality = {b: random.Random(b).uniform(0.25, 0.75) for b in config.BHAWANS}
    db.init_db()
    now = datetime.now(timezone.utc)

    previous = get_gateway()
    reset_gateway(LLMGateway([MockProvider()]))
    try:
        n = 0
        for d in range(days - 1, -1, -1):
            day = now - timedelta(days=d)
            for b in config.BHAWANS:
                quality = min(0.95, base_quality[b] + (days - 1 - d) * 0.04)  # most Bhawans improve
                for _ in range(rnd.randint(per_day // 2, per_day)):
                    x = rnd.random()
                    kind = "good" if x < quality else ("mid" if x < quality + (1 - quality) / 2 else "bad")
                    note = rnd.choice(NOTES[kind])
                    stream = rnd.choices(config.STREAMS, weights=[5, 4, 1, 1])[0]
                    t = day.replace(hour=rnd.randint(1, 4), minute=rnd.randint(0, 59))
                    ts = min(t, now - timedelta(minutes=rnd.randint(1, 60))).isoformat(timespec="seconds")
                    rid = db.create_report(b, stream, "demo-seed", note, None, created_at=ts)
                    db.save_grade(rid, grader.grade_bin(None, stream, note))
                    n += 1
    finally:
        reset_gateway(previous)

    k = 0
    for d in range(days - 1, -1, -1):
        for _ in range(rnd.randint(1, 3)):
            kind = rnd.choice(list(ISSUE_NOTES))
            t = now - timedelta(days=d, hours=rnd.randint(1, 10))
            iid = db.create_issue(rnd.choice(config.BHAWANS), kind, ISSUE_NOTES[kind], "demo-seed",
                                  created_at=t.isoformat(timespec="seconds"))
            if d > 0 or rnd.random() < 0.3:  # most older complaints are already fixed
                fixed = min(now, t + timedelta(hours=rnd.uniform(1, 9)))
                db.resolve_issue(iid, resolved_at=fixed.isoformat(timespec="seconds"))
            k += 1
    print(f"seeded {n} demo reports and {k} issues")


if __name__ == "__main__":
    main()
