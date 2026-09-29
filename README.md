# 🎬 Movie Shadowing

An English-learning web app built around movie dialogue. Learners take a placement test, then
listen to real movie lines, look up words in context, practise speaking, talk with an AI tutor,
and track their progress. Everything is personalised from the learner's stored history.

**Journey:** sign up → placement test (CEFR level) → learner profile → movie shadowing →
AI speaking tutor → progress tracking → personalised recommendations and vocabulary review.

## Features

| Area | What it does |
|---|---|
| Accounts | Sign-up / login with bcrypt-hashed passwords and JWT sessions |
| Placement test | 24 questions (vocabulary, grammar, reading, listening) → CEFR A1-C2 + per-skill scores; can be retaken and is compared with earlier results |
| Movie shadowing | Search OpenSubtitles, split dialogue into chapters, listen with US/UK neural voices (TTS), click any word for an AI explanation *in context* (saved automatically), record yourself and get a pronunciation score |
| AI speaking tutor | Turn-based voice conversation: record → speech-to-text → LLM reply → spoken reply. Difficulty follows your CEFR level; it weaves in words you're studying; at the end it lists your mistakes with corrections and saves the session |
| Review | Fill-in-the-blank exercises from your saved words, weakest first |
| Progress | Assessment history with deltas, vocabulary stats, pronunciation trend, weak words, recent tutor mistakes, completed chapters/movies |
| Recommendations | Rule-based next steps (retake test, review due words, fix pronunciation, talk to the tutor, work on your weakest skill) |

## Architecture

```
Browser (static HTML + vanilla JS, hash routing)
   │  JSON / multipart over HTTPS
   ▼
FastAPI  ──►  PostgreSQL          (SQLite for local dev/tests)
   │
   ├─► Groq: LLM (word explanations, tutor, feedback) + Whisper (speech-to-text)
   ├─► edge-tts: text-to-speech (no key)
   └─► OpenSubtitles REST API: subtitles (parsed lines cached in the DB)
```

One service, one Docker image. FastAPI serves both the API (`/api/...`) and the web UI (`static/`).
API keys live on the server; users never enter them.

```
backend/
  main.py            app setup, error handling, static files
  routes/            auth, assessments, vocab (+review), movies (+tts, pronunciation), tutor, progress
  models.py          all tables          learning.py   progress, recommendations, review exercises
  assessment.py      scoring + questions.json (placement test)
  ai.py              every Groq call     subtitles.py, tts.py, pronunciation.py
static/              index.html, style.css, app.js (whole UI, no build step)
tests/               pytest suite (32 tests)
```

## Run locally

```bash
cp .env.example .env        # fill in GROQ_API_KEY and OPENSUBTITLES_API_KEY, set SECRET_KEY
docker compose up --build   # http://localhost:8000
```

Without Docker (uses SQLite):

```bash
pip install -r requirements-dev.txt
uvicorn backend.main:app --reload --env-file .env    # http://localhost:8000
pytest
```

Free keys: [Groq](https://console.groq.com/keys), [OpenSubtitles](https://www.opensubtitles.com/consumers).
The microphone only works on `localhost` or HTTPS.

## Tests

`pytest` runs 32 tests: auth, access control between users, placement scoring, recommendation rules,
review flow, subtitle parsing/caching, and the tutor/pronunciation/vocab endpoints with Groq, TTS and
OpenSubtitles replaced by fakes. GitHub Actions (`.github/workflows/ci.yml`) runs them and builds the Docker image on every push.

**Placement-test evaluation.** `tests/test_assessment_simulation.py` simulates learners of known level
(90% correct at or below their level, 40% one level above, 25% guessing beyond) and checks the estimate.
Result: exactly right ~54% of the time, within one CEFR level ~89%. This checks the scoring rule behaves
sensibly; it is **not** validation against real learners, and the app presents the result as an estimate.

## Deploy (Render)

1. Push the repo to GitHub (CI runs automatically).
2. In Render: **New → Blueprint**, pick the repo. `render.yaml` creates the web service and Postgres.
   Enter `GROQ_API_KEY` and `OPENSUBTITLES_API_KEY` when asked (`SECRET_KEY` is generated).
3. Deploys happen automatically after CI passes (`autoDeployTrigger: checksPass`), and the app gets HTTPS,
   which the microphone needs. Check Render's current free-tier limits (sleeping services, database
   expiry) and pick paid plans in `render.yaml` if you want a permanent demo.

## Design decisions and limitations

- **Pronunciation score is a proxy.** Whisper transcribes you; the score is how closely the transcript matches the line.
  Recognisers tend to "auto-correct" toward likely words, so it can be generous and can't judge individual sounds.
- **The tutor is turn-based**, not streaming audio. Simpler, robust, and still speech → LLM → speech.
- **Placement test** uses a small fixed question bank (4 questions per CEFR level); scoring is explained in `backend/assessment.py`.
- **Recommendations are plain rules** over stored activity (see `learning.py`), so they are easy to explain and test.
- **Schema is created on startup** (`create_all`). Add Alembic when you first need to change tables on a database that has real data.
- **No rate limiting yet.** Each user can trigger Groq calls; add limits before opening sign-up publicly. Tutor sessions are capped at 15 turns.
- Subtitles come from the official OpenSubtitles API only; movie audio/video is never used.
