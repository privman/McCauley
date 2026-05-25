# McCauley — Conversational Feedback Agent (v0.1)

A conversational AI for soliciting structured (Situation-Behavior-Impact) feedback at work
and serving it to authorized recipients through chat + reports.

See [`design.md`](design.md) for a system architecture overview, an explanation of key design decisions, and list of potential improvements.

## Layout

```
backend/    FastAPI app: orchestration, ACL, retrieval, voice relay
frontend/   Vite + React + TypeScript SPA: provider and recipient routes
skills/     Markdown coaching skills loaded into the provider system prompt
ops/        Docker Compose and seed CSVs for the demo org
```

## Quick start

You need:

- Docker Desktop (or any Docker engine with Compose).
- An [Anthropic API key](https://console.anthropic.com/).
- A [Voyage AI key](https://www.voyageai.com/) for embeddings.
- A GCP service-account JSON with the **Speech-to-Text** and **Text-to-Speech** APIs enabled.

Set up env vars and credentials. Compose reads `.env` from the directory
containing the compose file, so the env file lives in `ops/`:

```bash
cp .env.example ops/.env
# edit ops/.env:
#   ANTHROPIC_API_KEY=sk-ant-...
#   VOYAGE_API_KEY=pa-...
#   GOOGLE_APPLICATION_CREDENTIALS_SOURCE=/absolute/path/on/your/host/to/google-credentials.json
#   SESSION_SECRET=any-random-string

# One-time setup: install backend + frontend dev deps and wire up
# the pre-push hook so `git push` runs the same checks CI does.
# See "Pre-push hook" below for what it runs.
# Safe to re-run to make sure deps are up to date.
./bin/setup

docker compose -f ops/docker-compose.yml up --build
```

The backend container runs Alembic migrations on startup. Once it's up, seed the demo org:

```bash
docker compose -f ops/docker-compose.yml exec backend python -m app.seed
```

Then open [http://localhost:5173](http://localhost:5173). You'll see the user-picker login.

## Demo script (the 10-step path from v0.1-scope.md)

1. **Sign in as Sam Rivera** (Senior Engineer, Mobile).
2. **Provider mode (voice):** click *Give feedback*, hold the mic, give feedback about Priya
  Singh. The bot collects subject, headline, and two SBI examples; the right pane fills in.
3. **Pivot to text** mid-conversation: "Actually, let's talk about the Mobile team for a
  moment — they've been shipping consistently." A new draft appears in the stack with
   Priya's paused.
4. **Resume Priya's draft** by clicking it; finalize and submit.
5. **Submit the Mobile-team feedback anonymously** (toggle anonymity if you like).
6. **Sign out, sign in as Maya Patel** (Director of Engineering).
7. **Recipient mode:** click *My feedback*. Ask *"What feedback has come in about my reports
  this month?"* The sources panel shows the records the closure surfaces.
8. **Probe the ACL:** try asking about a sibling org Maya doesn't oversee. The bot reports
  zero results.
9. **Generate a report** with the button.
10. **Sign in as Priya** to confirm she sees feedback about herself but not her peers.

## Env vars

### Required

- `ANTHROPIC_API_KEY` — Claude API (Sonnet 4.6 + Haiku 4.5).
- `VOYAGE_API_KEY` — `voyage-3-large` for feedback embeddings.
- `GOOGLE_APPLICATION_CREDENTIALS_SOURCE` — absolute path **on your laptop** to a GCP
service-account JSON. Needs `roles/speech.client` and `roles/texttospeech.user`. If unset,
the compose file mounts `/dev/null` and voice STT/TTS will fail at the Google API call —
everything else still runs.

### Optional

- `GOOGLE_APPLICATION_CREDENTIALS_MOUNT_POINT` — path **inside the container** where the JSON
appears. Compose sets the standard `GOOGLE_APPLICATION_CREDENTIALS` env var (the one Google
client libraries read) from this value. Default `/run/secrets/google-credentials.json` is
usually fine.
- `SESSION_SECRET` — HMAC key for the local-auth session cookie. The default
(`change-me-if-running-remotely`) is fine for solo local dev where only seeded synthetic
users exist and the port isn't exposed beyond `localhost`; change it before exposing the
instance over the network or seeding real users.
- `POSTGRES_URL` — already wired by compose; override only if you point at an external DB.
- `LOG_LEVEL` - see next section.

## Logging

The backend uses Python's standard `logging`. App-level loggers (`app.*`)
emit:

- **INFO** when a user message arrives and when an agent response is
  complete, in both provider and recipient modes (and voice).
- **DEBUG** for fine-grained events: each text chunk received from the
  model, each tool-call round.

Adjust with `LOG_LEVEL` in `ops/.env` (default `INFO`):

```
LOG_LEVEL=DEBUG     # see every streamed chunk + tool rounds
LOG_LEVEL=INFO      # default — turn-level only
LOG_LEVEL=WARNING   # quiet — only problems
```

Uvicorn's own loggers (request lines, access logs) are independent. To
change those, pass `--log-level` in `backend/entrypoint.sh`.

## Tests

```bash
cd backend
pip install -e ".[dev]"
pytest                       # unit tests (closure, draft stack, skills, health)
pytest tests/test_acl_view.py  # integration test — needs Docker (testcontainers spins up Postgres)
```

The two load-bearing checks called out in v0.1-scope.md:

- `tests/test_closure.py` — pure-Python unit tests of the org-graph closure computation.
- `tests/test_acl_view.py` — integration test of `feedback_visible_to_me` against real Postgres.

## Pre-push hook

`.githooks/pre-push` runs the same six checks CI runs (`ruff`, `black`,
`mypy`, `pytest`, `prettier`, `eslint`, `tsc`) before any `git push`.
Wired up by `./bin/setup`. Skip a particular push with
`git push --no-verify` for a known-broken WIP branch.

## What's *not* here

See `[v0.1-scope.md](v0.1-scope.md)` **What's out** for the explicit deferral list — most of
v1's enterprise plumbing (OIDC, SCIM, multi-region, observability stack, taxonomy lifecycle,
provider-injection screening) is intentionally absent.
