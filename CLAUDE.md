# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

snippet-share is a lightweight pastebin-style service: users save text snippets, get a shareable link, and read the snippet back as plain text.

The design is in [.claude/PROJECT-IDEA.md](.claude/PROJECT-IDEA.md) and was built by following [.claude/IMPLEMENTATION-PLAN.md](.claude/IMPLEMENTATION-PLAN.md). The UI follows [DESIGN.md](DESIGN.md). Start `brainstorming` for any new feature.

## Workflow

This repo uses the Superpowers plugin, which is enabled in `.claude/settings.json`. Use its workflow for every change: `brainstorming` → `using-git-worktrees` → `writing-plans` → `subagent-driven-development` / `executing-plans` with `test-driven-development` → `requesting-code-review` → `finishing-a-development-branch`. Don't write implementation code before the design is approved and a failing test exists.

The Ponytail plugin is also enabled. Superpowers decides the process; Ponytail decides how little code each task needs. Where they disagree on testing, Superpowers' test-first rule wins.

Developer setup steps are in [.claude/CLAUDE-INITIAL-SETUP.md](.claude/CLAUDE-INITIAL-SETUP.md).

## Commands

Tests run on the host and need the dev database: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db`.

| | Backend (`backend/`, uv) | Frontend (`frontend/`, Bun) |
|---|---|---|
| Install | `uv sync` | `bun install` |
| Run | `uv run alembic upgrade head`, then `uv run uvicorn app.main:app --reload` | `bun run dev` (proxies `/api` to :8000) |
| Test | `uv run pytest` | `bun run test --run` (Vitest), `bun run test:e2e` (Playwright) |
| One test | `uv run pytest tests/test_pastes.py::test_name` | `bunx vitest run -t "name"`, `bunx playwright test -g "name"` |
| Lint / build | — | `bun run lint`, `bun run build` (type-checks `src/`, `test/`, `e2e/`) |
| Migration | `uv run alembic revision --autogenerate -m "..."` (read the file), `uv run alembic upgrade head` | — |

Full stack: `docker compose up --build`, then http://localhost:3000.

## Architecture

- **Gateway:** `nginx` ([nginx/nginx.conf](nginx/nginx.conf)) is the only service published to the host (:3000). It sends `/api/*` to the backend and everything else to the frontend container (static files). The create rate limit (10/min, burst 5) and the 2 MB body cap live there, on `location = /api/v1/pastes`. `db` and `backend` are published on 127.0.0.1 only by `docker-compose.dev.yml`.
- **Backend** (`backend/app/`): `routes/paste.py` (HTTP + status codes) → `services/paste.py` (database access) → `model/` (SQLAlchemy). `schemas/` holds the Pydantic models, `core/` holds settings, the engine and the `get_db` dependency. New models must be imported in `model/__init__.py` for Alembic autogenerate.
- **Storage and ids:** one Postgres table, `pastes(id UUID v4 primary key, text TEXT, created_at TIMESTAMPTZ default now())`. The id is created by the backend and is the whole link: `share_url = PUBLIC_BASE_URL + "/view/" + id`. The container runs `alembic upgrade head` on start.
- **Routes** (under `/api/v1`):
  - `POST /pastes` returns 201. 413 if the text is over `MAX_PASTE_BYTES` in **UTF-8 bytes**, checked in the route because a validator can only give 422. 422 for empty, whitespace-only, NUL or lone-surrogate text.
  - `GET /pastes/{id}` returns 200. `GET /pastes/{id}/raw` returns `text/plain` with `nosniff`. Both return 404 for unknown *and* malformed ids: `paste_id` is a `str` on purpose, parsed in `get_paste_or_404`.
- **Text is stored exactly:** never strip or normalise it, anywhere.
- **Frontend** (`frontend/src/`): `routes/` (`/`, `/view/:id`, `*`) → `pages/`. `service/api.ts` maps errors to kinds by **HTTP status only**, because nginx's 413 and 429 are HTML pages. Text is rendered as text nodes, never `dangerouslySetInnerHTML`. Line numbers are CSS `::before` counters, so they're not part of the copied text. Unit tests are in `test/` (mirroring `src/`), Playwright specs in `e2e/`.
- **Tests:** `backend/tests/conftest.py` refuses any database not ending in `_test`, and rebuilds the schema with `create_all` on each run.
