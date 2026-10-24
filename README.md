# Kachra Report Card

Every day, the person who empties a hostel bin takes one photo and says one line.
AI grades the bin against India's four-stream rule, and every Bhawan at IIT Roorkee
gets a daily segregation report card, a place on the leaderboard and a Hindi voice
note for its warden.

Built for SOCIOTHON 2026 (IIT Roorkee).

## Why this works

- **Feedback beats awareness.** An RCT on the IIT Delhi campus (303 households) found
  personalised feedback with peer comparison (scorecards, leaderboards) improved
  segregation more than awareness campaigns.
- **"Oops" tags cut contamination.** San José's cart-tagging RCT cut recycling
  contamination 19% within 1-2 weeks of a single tag. We make the tag digital and AI-graded.
- **The collector decides.** A Delhi field experiment (15 localities) found the garbage
  collector can undo households' effort, so we make the collector the reporter.
- **The law changed.** The Solid Waste Management Rules 2026 (in force 1 April 2026)
  require four streams at source: wet, dry, sanitary, special care. Institutions are covered.

## How it works

```
worker photo + voice note ─▶ API ─▶ grade (vision model, or Render Workflows task)
                                  └▶ A / B / C  +  Shabash / Oops tag (Hinglish)
reports ─▶ Bhawan score (A=100, B=60, C=20) ─▶ leaderboard + trend
nightly Render cron ─▶ Workflows fan-out per Bhawan ─▶ ElevenLabs voice note for warden
```

Grade rule: share of visible items that belong in a different stream.
A = up to 10%, B = up to 35%, C = more.

## Where ElevenLabs is used

| Feature | ElevenLabs product |
| --- | --- |
| Worker speaks a note instead of typing | Speech-to-text (Scribe), `/api/transcribe` |
| Warden's daily Hinglish voice report ("Suno" button) | Text-to-speech, `/api/briefing/{bhawan}` |
| Hands-free reporting by talking to an agent | Agents Platform widget + two server tools |

## Where Render is used

| Piece | Render service |
| --- | --- |
| API + front end | Web service (`render.yaml`) |
| Photo grading with retries, nightly fan-out over Bhawans | **Workflows** service (`workflows/main.py`) |
| 10 PM IST trigger for the nightly report | Cron job (`scripts/nightly.py`) |

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env            # fill keys, or keep GRADER_PROVIDER=mock
python -m scripts.seed_demo     # optional: a week of demo data
uvicorn app.server:app --reload
# open http://127.0.0.1:8000
python -m unittest discover -s tests
```

## Deploy on Render

1. **Web service:** New > Blueprint > this repo. Fill `GEMINI_API_KEY`,
   `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (and `ELEVENLABS_AGENT_ID` once the agent exists).
2. **Workflow service:** New > Workflow > this repo.
   Build `pip install -r requirements-workflows.txt`, start `python workflows/main.py`.
   Give it `GRADER_PROVIDER` and `GEMINI_API_KEY`. Note its slug.
3. On the web service and the cron job set `RENDER_API_KEY`, `RENDER_WORKFLOW_SLUG`;
   on the cron job set `API_BASE` to the web service URL.

## ElevenLabs agent setup

Create an agent (language Hindi, Hinglish mode on). System prompt:

> You help IIT Roorkee safai karamcharis report hostel dustbins. Speak short, simple
> Hinglish. Ask which Bhawan and which bin (geela, sookha, sanitary, special care) and
> what they see inside. Then call `file_report` and read back the `say` field.
> If asked for a Bhawan's score, call `get_score`.

Server tools (POST, JSON body):

| Tool | URL | Parameters |
| --- | --- | --- |
| `file_report` | `https://<web-service>/api/agent/report` | `bhawan`, `bin_stream`, `note`, `reporter` (strings) |
| `get_score` | `https://<web-service>/api/agent/score` | `bhawan` (string) |

## API

| Method | Path | What |
| --- | --- | --- |
| GET | `/api/meta` | Bhawans, streams, which features are on |
| POST | `/api/reports?wait=1` | multipart: `bhawan`, `bin_stream`, `photo`, `note`, `reporter` |
| GET | `/api/reports` | latest reports |
| GET | `/api/leaderboard?days=7` | ranked Bhawans |
| GET | `/api/summary?days=7` | campus stats + daily trend |
| GET | `/api/briefing/{bhawan}` | warden script + ElevenLabs audio URL |
| POST | `/api/transcribe` | multipart `audio` → text |

## Sources

- IIT Delhi RCT summary: https://www.policyedge.in/p/waste-segregation-nudges-why-feedback
- San José CART tags: https://citiesideaexchange.bloomberg.org/recycling-contamination/
- Delhi field experiment (Wadehra & Mishra 2018): https://www.efdinitiative.org/publications/encouraging-urban-households-segregate-waste-they-generate-insights-field-experiment
- SWM Rules 2026: https://visionias.in/current-affairs/news-today/2026-03-31/environment/solid-waste-management-swm-rules-2026-to-come-into-effect-from-1st-april-2026
- IITR waste (Watchout, 2020): https://watchout.iitr.ac.in/2020/12/managing-waste-at-IIT-Roorkee

## Limits

- SQLite on the web service; on Render's free plan the disk resets on redeploy
  (demo data is re-seeded automatically). Use a Render Postgres or disk for real use.
- The vision model estimates contamination from one photo; it can miss items under the top layer.
