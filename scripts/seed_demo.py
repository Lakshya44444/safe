"""Fills the database with a week of believable demo reports so the dashboard isn't empty.

Run:  python -m scripts.seed_demo
All seeded reports are marked reporter='demo-seed' so they are easy to tell apart.
"""

import random
from datetime import datetime, timedelta, timezone

from app import config, db, grader

NOTES = {
    "good": ["dabba saaf hai", "sab sahi hai", "theek hai aaj"],
    "mid": ["thoda plastic hai", "ek do packet pade hain", "kaagaz mila"],
    "bad": ["polythene aur bottle bahut hai", "khaana aur plastic mixed hai", "pad aur packet mixed"],
}

# Some Bhawans start better than others, and most improve over the week.
BASE_QUALITY = {b: random.Random(b).uniform(0.25, 0.75) for b in config.BHAWANS}


def main(days: int = 7, per_day: int = 6, seed: int = 7) -> None:
    rnd = random.Random(seed)
    db.init_db()
    now = datetime.now(timezone.utc)
    n = 0
    for d in range(days - 1, -1, -1):
        day = now - timedelta(days=d)
        for b in config.BHAWANS:
            q = min(0.95, BASE_QUALITY[b] + (days - 1 - d) * 0.04)
            for _ in range(rnd.randint(per_day // 2, per_day)):
                x = rnd.random()
                kind = "good" if x < q else ("mid" if x < q + (1 - q) / 2 else "bad")
                note = rnd.choice(NOTES[kind])
                stream = rnd.choices(config.STREAMS, weights=[5, 4, 1, 1])[0]
                t = day.replace(hour=rnd.randint(1, 4), minute=rnd.randint(0, 59))
                ts = min(t, now - timedelta(minutes=rnd.randint(1, 60))).isoformat(timespec="seconds")
                rid = db.create_report(b, stream, "demo-seed", note, None, created_at=ts)
                g = grader.grade_bin(None, stream, note)
                db.save_grade(rid, g.grade, g.contamination, g.found_items, g.tag_hi)
                n += 1
    # A few collection issues, most already fixed, so the issue panel and fix-time stat have data.
    issue_notes = {"overflow": "dabba bhar gaya hai", "missed_pickup": "subah gaadi nahi aayi",
                   "broken_bin": "dabbe ka dhakkan toota hai"}
    k = 0
    for d in range(days - 1, -1, -1):
        for _ in range(rnd.randint(1, 3)):
            kind = rnd.choice(list(issue_notes))
            t = now - timedelta(days=d, hours=rnd.randint(1, 10))
            iid = db.create_issue(rnd.choice(config.BHAWANS), kind, issue_notes[kind], "demo-seed",
                                  created_at=t.isoformat(timespec="seconds"))
            if d > 0 or rnd.random() < 0.3:
                fixed_at = min(now, t + timedelta(hours=rnd.uniform(1, 9)))
                with db.connect() as conn:
                    conn.execute("UPDATE issues SET status='resolved', resolved_at=? WHERE id=?",
                                 (fixed_at.isoformat(timespec="seconds"), iid))
            k += 1
    print(f"seeded {n} demo reports and {k} issues")


if __name__ == "__main__":
    main()
