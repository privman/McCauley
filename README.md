# McCauley — Conversational Feedback Agent (v0.1)

A conversational AI for soliciting structured (Situation-Behavior-Impact) feedback at work and
serving it to authorized recipients through chat + reports.

See [`spec.md`](spec.md), [`design.md`](design.md), [`v0.1-scope.md`](v0.1-scope.md), and
[`cloud-choice.md`](cloud-choice.md) for the full design context.

## Layout

```
backend/    FastAPI app: orchestration, ACL, retrieval, voice relay
frontend/   Vite + React + TypeScript SPA: provider and recipient routes
skills/     Markdown coaching skills loaded into the provider system prompt
ops/        Docker Compose and seed CSVs for the demo org
```

## Quick start

```bash
cp .env.example .env       # fill in ANTHROPIC_API_KEY, VOYAGE_API_KEY, GOOGLE_APPLICATION_CREDENTIALS
docker compose -f ops/docker-compose.yml up --build
# in another terminal:
docker compose -f ops/docker-compose.yml exec backend python -m app.seed
open http://localhost:5173
```

The seed loads ~50 users, ~10 org units, and ~30 pre-existing feedback records — enough to
exercise the closure-based ACL, run the recipient retrieval, and walk through the demo script
in [`v0.1-scope.md`](v0.1-scope.md).

## Required env vars

- `ANTHROPIC_API_KEY` — Claude API (Sonnet 4.6 + Haiku 4.5).
- `VOYAGE_API_KEY` — `voyage-3-large` for feedback embeddings.
- `GOOGLE_APPLICATION_CREDENTIALS` — path to a GCP service-account JSON with STT + TTS scopes.
- `POSTGRES_URL` — defaults to the docker-compose Postgres instance.
- `SESSION_SECRET` — random string for signing the local-auth session cookie.
