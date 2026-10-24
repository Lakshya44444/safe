"""On a fresh deploy (empty database) load the demo week, so the live URL never shows an empty board.

Set SEED_DEMO=0 to switch this off once real reports are coming in.
"""

import os

from app import db
from scripts import seed_demo

if __name__ == "__main__":
    db.init_db()
    if os.getenv("SEED_DEMO", "1") != "0" and not db.list_reports(limit=1):
        seed_demo.main()
    else:
        print("database already has reports, not seeding")
