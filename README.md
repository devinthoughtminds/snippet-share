# snippet-share
A lightweight pastebin-style service to save snippets, generate shareable links, and read plain text instantly.

**Stack:** FastAPI + PostgreSQL (backend), React + Vite + TypeScript with React Query and axios (frontend), nginx gateway, Docker Compose.

> Work in progress. The API routes, migrations and tests are still being built, so follow [.claude/IMPLEMENTATION-PLAN.md](.claude/IMPLEMENTATION-PLAN.md) for what exists today.

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
uv run uvicorn app.main:app --reload        # http://localhost:8000/api/docs
```

Or run the backend in Docker with hot reload (your `backend/` folder is mounted into the container):

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build db backend
```

- Add a dependency: `uv add <pkg>` (or `uv add --dev <pkg>`). Never edit `uv.lock` by hand.
- Tests (once they exist) run on your machine, not in the container: `uv run pytest` from `backend/`, against the dev database (`snippet_test`).
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

API calls go through the axios instance in [frontend/src/api.ts](frontend/src/api.ts) (`baseURL: /api/v1`), and pages read and write data with React Query (`useQuery` / `useMutation`).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `required variable ... copy .env.example to .env` | You skipped the configuration step. |
| `snippet_test` database missing | The init script only runs on an empty volume. Run `docker compose down -v` once (this deletes data). |
| Port 3000, 5432 or 8000 already in use | Stop whatever uses it, or change the port mapping in the compose file. |
| `502 Bad Gateway` right after start | The backend is still starting. Wait a few seconds. |
