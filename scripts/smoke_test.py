"""Smoke-test a running deployment: is every backend piece actually working?

    python scripts/smoke_test.py https://kachra-report-card.onrender.com
    python scripts/smoke_test.py https://... --photo my_bin.jpg   # grade a real bin photo too

Uses only the public API. Each check prints PASS / FAIL / SKIP with the reason.
Note: it adds one test report and one complaint (marked fixed straight away).
"""

from __future__ import annotations

import argparse
import sys
import time

import requests

RESULTS: list[tuple[str, str, str]] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    status = "SKIP" if ok is None else "PASS" if ok else "FAIL"
    RESULTS.append((status, name, detail))
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="deployment URL, e.g. https://kachra-report-card.onrender.com")
    ap.add_argument("--photo", help="a real bin photo to grade with the live model")
    args = ap.parse_args()
    b = args.base.rstrip("/")
    s = requests.Session()
    s.headers["User-Agent"] = "kachra-smoke-test"

    t0 = time.time()
    try:
        r = s.get(f"{b}/api/health", timeout=90)  # free Render instances take ~50 s to wake
        check("server is up", r.ok, f"{r.status_code} in {time.time() - t0:.1f}s")
    except requests.RequestException as e:
        check("server is up", False, str(e))
        return 1

    meta = s.get(f"{b}/api/meta", timeout=30).json()
    chain = meta.get("llm_chain", [])
    check("LLM provider is a real model", bool(chain) and not chain[0].startswith("mock"), f"chain={chain}")
    check("ElevenLabs text-to-speech configured", meta.get("tts"), "needs ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID")
    check("ElevenLabs speech-to-text configured", meta.get("stt"))
    check("ElevenLabs agent widget", True if meta.get("agent_id") else None, "set ELEVENLABS_AGENT_ID to enable")
    check("Render Workflows hand-off", True if meta.get("workflows") else None, "set RENDER_WORKFLOW_SLUG to enable")

    for path in ("/", "/api/leaderboard", "/api/summary", "/api/issues", "/api/reports?limit=5",
                 "/api/bhawans/Govind", "/qr.html", "/manifest.webmanifest", "/sw.js",
                 "/api/collection-plan", "/api/forecast", "/api/compliance", "/report.html"):
        r = s.get(b + path, timeout=30)
        check(f"GET {path}", r.ok, str(r.status_code))

    t = time.time()
    r = s.post(f"{b}/api/reports?wait=1", timeout=90, data={
        "bhawan": "Govind", "bin_stream": "wet", "reporter": "smoke-test",
        "note": "a plastic bag and a bottle on top of food scraps"})
    rep = r.json()
    check("grade a note with the LLM", r.status_code == 201 and rep.get("status") == "graded",
          f"grade={rep.get('grade')} items={rep.get('found_items')} by={rep.get('provider')} "
          f"in {time.time() - t:.1f}s {rep.get('error') or ''}")

    if rep.get("id"):
        v = s.post(f"{b}/api/reports/{rep['id']}/verdict", json={"agree": True}, timeout=30)
        check("worker check of an AI grade", v.ok and v.json().get("verdict") == "agree")

    if args.photo:
        t = time.time()
        with open(args.photo, "rb") as f:
            r = s.post(f"{b}/api/reports?wait=1", timeout=120, files={"photo": f},
                       data={"bhawan": "Govind", "bin_stream": "wet", "reporter": "smoke-test"})
        rep = r.json()
        check("grade a photo with the vision model", rep.get("status") == "graded",
              f"grade={rep.get('grade')} {rep.get('contamination')}% items={rep.get('found_items')} "
              f"by={rep.get('provider')} in {time.time() - t:.1f}s {rep.get('error') or ''}")
    else:
        check("grade a photo with the vision model", None, "pass --photo bin.jpg")

    br = s.get(f"{b}/api/briefing/Govind", timeout=120).json()
    if br.get("audio_url"):
        a = s.get(b + br["audio_url"], timeout=60)
        check("warden briefing audio (ElevenLabs TTS)", a.ok and len(a.content) > 2000,
              f"{len(a.content) // 1024} KB mp3")
    else:
        check("warden briefing audio (ElevenLabs TTS)", None if not meta.get("tts") else False,
              br.get("tts_error", "TTS not configured"))

    r = s.post(f"{b}/api/issues", json={"bhawan": "Govind", "kind": "overflow", "note": "smoke test"}, timeout=30)
    ok = r.status_code == 201
    if ok:
        ok = s.post(f"{b}/api/issues/{r.json()['id']}/resolve", timeout=30).json().get("status") == "resolved"
    check("complaint create + resolve", ok)

    r = s.post(f"{b}/api/agent/score", json={"bhawan": "Govind"}, timeout=30)
    check("voice agent tool get_score", r.ok and "Govind" in r.json().get("say", ""), r.json().get("say", ""))

    stats = s.get(f"{b}/api/llm/stats", timeout=30).json()
    calls = sum(t.get("calls", 0) for t in stats.get("tasks", {}).values())
    fails = sum(t.get("failures", 0) for t in stats.get("tasks", {}).values())
    check("LLM gateway stats", calls > 0 and fails == 0, f"calls={calls} failures={fails} chain={stats.get('chain')}")

    failed = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(failed)} ok, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
