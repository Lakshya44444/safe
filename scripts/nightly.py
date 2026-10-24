"""Render cron job: kicks off the nightly_report workflow task.

Render Workflows has no built-in schedule, so a small Render cron job runs this script.
Env: RENDER_API_KEY, RENDER_WORKFLOW_SLUG, API_BASE (public URL of the web service).
"""

import os

from render import Render


def main() -> None:
    slug = os.environ["RENDER_WORKFLOW_SLUG"]
    api_base = os.environ["API_BASE"]
    run = Render().workflows.start_task(f"{slug}/nightly_report", {"api_base": api_base})
    print(f"started nightly_report run {run.id}")


if __name__ == "__main__":
    main()
