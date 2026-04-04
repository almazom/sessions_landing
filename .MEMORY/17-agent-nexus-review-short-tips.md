# Memory Card: Agent Nexus Review Short Tips

Use this card when:

- you need a fast mental model of this repo before changing code
- you want to know what this project is really for beyond "dashboard"
- you need the shortest safe path to review or extend the system

Core idea:

- Agent Nexus is a private operational cockpit for one user managing many AI agent sessions
- the raw session JSON or JSONL artifact is the primary source of truth
- the product goal is not only listing sessions, but making them identifiable, inspectable, queryable, and handoff-ready

Product shape:

- landing page = map of the day
- session detail page = dossier for one artifact
- derived layers must support the source artifact, not replace it

Read order:

1. `PROFILE.md` — why the project exists
2. `docs/product/HIGH_LEVEL_EXPECTATIONS.md` — what a good product result looks like
3. `AURA.md` — how the repo should be built
4. `PROTOCOL.json` — current tool and contract registry
5. `.MEMORY/00-index.md` — short operational cards

Key architecture split:

- web app: FastAPI backend + Next.js frontend
- isolated CLIs: contract-first tools in `tools/`
- parser layer: normalizes provider-specific session files into one session model

Most important backend files:

- `backend/api/main.py` — app bootstrap, health, middleware, routers
- `backend/api/scanner.py` — warm scan of provider session roots into the in-memory store
- `backend/api/session_artifacts.py` — stable route resolution and detail payload shaping
- `backend/api/routes/sessions.py` — session detail, ask-only query, resume, interactive orchestration
- `backend/parsers/*.py` — provider-specific normalization logic

Most important frontend files:

- `frontend/app/page.tsx` — dashboard loading, auth state, latest session, filters
- `frontend/app/sessions/[harness]/[id]/page.tsx` — detail route entrypoint
- `frontend/lib/api.ts` — shared API types and client contracts

Operational truths:

- source artifact > timeline from artifact > local repo evidence > derived layers
- `tools/` should stay isolated from `backend/` and `frontend/`
- stdout for tool JSON, stderr for diagnostics
- route identity matters: harness + artifact route id must stay stable

Current strengths:

- very clear why/what/how split across `PROFILE.md`, product docs, `AURA.md`, and `PROTOCOL.json`
- strong contract-first discipline
- good evidence model for session detail pages
- real tests and operational smoke artifacts already exist

Current risks:

- `backend/api/routes/sessions.py` is a heavy orchestration hotspot
- there are two mental models for session freshness: scanner path and watcher path
- test invocation currently works best with `PYTHONPATH=.`

Useful commands:

```bash
cd /home/pets/zoo/agents_sessions_dashboard
PYTHONPATH=. pytest -q tests/test_sessions_routes.py backend/test_parsers.py tests/test_websocket_routes.py
python3 -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend && npm run dev
```

Short reviewer verdict:

- this is not just a dashboard
- it is a personal observability and handoff system for multi-provider AI work
- preserve the source-of-truth model and contract-first CLI spine when extending it
