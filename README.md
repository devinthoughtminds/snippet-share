# snippet-share
A lightweight pastebin-style service to save snippets, generate shareable links, and read plain text instantly.

**Stack:** FastAPI + PostgreSQL (backend), React + Vite + TypeScript with React Query and axios (frontend), nginx gateway, Docker Compose. The UI follows the design system in [DESIGN.md](DESIGN.md).

Quick start, after the [configuration](#configuration-do-this-once) step: `docker compose up --build`, then open http://localhost:3000.

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Docker Desktop | with `docker compose` | full system, database |
| [uv](https://docs.astral.sh/uv/) | latest | backend (installs Python 3.14 itself) |
| [Bun](https://bun.sh) | 1.3 | frontend |

## Configuration (do this once)

Copy each example file and set **one** database password in all of them:

```sh
cp .env.example .env                  # Compose: Postgres user/password/db, PUBLIC_BASE_URL
cp backend/.env.example backend/.env  # backend outside Docker: DB URLs, size limit
cp frontend/.env.example frontend/.env  # Vite: size limit, dev proxy target
```

- Put the same password in `POSTGRES_PASSWORD` (`.env`) and in both URLs in `backend/.env`.
- Use letters and digits only (for example `openssl rand -hex 24`). The password goes into a URL, so `/`, `@` or `#` break the connection.
- Never commit a `.env` file. They are git-ignored.

---

## Run the full system (Docker)

Everything runs in containers. Only the nginx gateway is published, on port 3000.

```sh
docker compose up --build -d
```

| URL | What |
|---|---|
| http://localhost:3000 | the app |
| http://localhost:3000/api/docs | API docs (Swagger) |

The backend container runs `alembic upgrade head` before it starts, so a fresh database gets its tables automatically.

```sh
docker compose ps              # status; db should be "healthy"
docker compose logs -f backend # follow logs of one service
docker compose down            # stop (data is kept)
docker compose down -v         # stop AND delete all pastes (wipes the database volume)
```

How requests flow:

```
Browser ──► nginx :3000
              ├─ POST /api/v1/pastes → rate limit (10/min per IP) + 2 MB cap → backend:8000
              ├─ /api/*              → backend:8000
              └─ /*                  → frontend:80 (built static files)
```

---

## Run the backend (for development)

The backend needs Postgres. Start the database (and optionally the backend) with the dev override, which publishes them on `127.0.0.1` only:

```sh
# Database only, then run the backend on your machine:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db

cd backend
uv sync                                     # install dependencies from uv.lock
uv run alembic upgrade head                 # create/upgrade the tables in the dev database
uv run uvicorn app.main:app --reload        # http://localhost:8000/api/docs
```

Or run the backend in Docker with hot reload (your `backend/` folder is mounted into the container):

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build db backend
```

- Add a dependency: `uv add <pkg>` (or `uv add --dev <pkg>`). Never edit `uv.lock` by hand.
- Changed a model? `uv run alembic revision --autogenerate -m "<what>"`, **read the generated file**, then `uv run alembic upgrade head`. New models must be imported in `app/model/__init__.py`, or autogenerate won't see them.
- **Windows:** if `uv` prints a pyenv message, a pyenv-win shim is shadowing it. Put the real uv first on `PATH`.

---

## Run the frontend (for development)

Start the backend first (see above). The Vite dev server proxies `/api` to `API_PROXY_TARGET` (default `http://localhost:8000`), so the browser uses the same `/api/v1/...` paths as in Docker and needs no CORS.

```sh
cd frontend
bun install       # install dependencies from bun.lock
bun run dev       # http://localhost:5173
```

| Command | What |
|---|---|
| `bun run build` | type-check and build to `dist/` |
| `bun run lint` | ESLint |
| `bun run preview` | serve the built `dist/` locally |

API calls go through the axios instance in [frontend/src/service/api.ts](frontend/src/service/api.ts) (`baseURL: /api/v1`), and pages read and write data with React Query (`useQuery` / `useMutation`). Code lives in `src/` (`pages/`, `components/`, `hooks/`, `routes/`, `service/`).

---

## Test

All tests run on your machine. Start the dev database first: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db`.

| What | Command | Notes |
|---|---|---|
| Backend | `uv run pytest` (from `backend/`) | Uses the `snippet_test` database (`TEST_DATABASE_URL`); refuses to run against any database not ending in `_test`. |
| Backend, one test | `uv run pytest tests/test_pastes.py::test_get_unknown_id_returns_404` | |
| Frontend unit | `bun run test` (from `frontend/`) | Vitest + Testing Library, in `frontend/test/`. `bun run test --run` runs once without watching. |
| Frontend, one test | `bunx vitest run -t "counts characters and words"` | |
| End-to-end | `bun run test:e2e` (from `frontend/`) | Playwright in `frontend/e2e/`. Starts (or reuses) the backend on :8000 and Vite on :5173. Creates real pastes in the dev database. First time: `bunx playwright install chromium`. |

---

## Configuration

| Variable | Where | Default | What |
|---|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `.env` | `snippet` / — / `snippet` | Postgres credentials for Compose. |
| `PUBLIC_BASE_URL` | `.env`, `backend/.env` | `http://localhost:3000` (Docker), `http://localhost:5173` (dev) | Share links are built from it. |
| `DATABASE_URL` | `backend/.env` (Compose sets it in Docker) | — | Backend database. |
| `TEST_DATABASE_URL` | `backend/.env` | — | Test database; must end in `_test`. |
| `MAX_PASTE_BYTES` | `backend/.env` / Compose | `1048576` (1 MB) | Largest paste, in UTF-8 bytes. |
| `VITE_MAX_PASTE_BYTES` | `frontend/.env` | `1048576` | Same limit for the UI. Must match `MAX_PASTE_BYTES`. |
| `API_PROXY_TARGET` | `frontend/.env` | `http://localhost:8000` | Where the Vite dev server proxies `/api`. |
| `client_max_body_size` | `nginx/nginx.conf` | `2m` | Whole JSON body on create. Bigger than the text limit because escaping adds bytes. Raise it with `MAX_PASTE_BYTES`. |
| `limit_req` | `nginx/nginx.conf` | `10r/m`, burst `5` | Create rate limit per client IP. |

---

## API

All routes are under `/api/v1`. Interactive docs: `/api/docs`.

| Route | Success | Errors |
|---|---|---|
| `POST /pastes` with `{"text": "..."}` | `201` `{id, share_url, created_at}` | `413` over `MAX_PASTE_BYTES`; `422` missing, empty, whitespace-only, NUL or invalid Unicode text; `429` from the gateway when rate limited |
| `GET /pastes/{id}` | `200` `{id, text, created_at}` | `404` unknown or malformed id |
| `GET /pastes/{id}/raw` | `200` the exact text, `text/plain; charset=utf-8` | `404` unknown or malformed id |

Text is stored and returned exactly as sent: whitespace, tabs, `\r\n` and emoji are kept.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `required variable ... copy .env.example to .env` | You skipped the configuration step. |
| `snippet_test` database missing | The init script only runs on an empty volume. Run `docker compose down -v` once (this deletes data). |
| Port 3000, 5432 or 8000 already in use | Stop whatever uses it, or change the port mapping in the compose file. |
| `502 Bad Gateway` right after start | The backend is still starting. Wait a few seconds. |
