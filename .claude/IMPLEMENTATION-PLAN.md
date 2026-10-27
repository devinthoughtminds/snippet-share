# snippet-share: implementation plan

This plan implements [PROJECT-IDEA.md](PROJECT-IDEA.md). Work through the phases in order; each one ends in something you can run or test. Tick the boxes as you go.

**Working rules** (from [CLAUDE.md](../CLAUDE.md)):
- **Test first.** For anything with logic, write the test, run it and watch it fail, then write the least code that makes it pass, then commit.
- **One commit per task** (each `### Task`), with a message describing it.
- **Don't build what isn't listed here.** No extra abstractions, no "might need it later" code.

**Status (26 Oct 2026):**
- **Built:** Phases 1–8 (the pastebin works through the nginx gateway on `:3000`) and Phases 11–12 (a remote MCP server with OAuth 2.1 login, and a Google ADK test agent).
- **Still open:**
  - run migrations when the backend container starts (Task 4.1);
  - add error responses to the API docs (Task 3.3);
  - a default for `max_paste_bytes` (Task 1.2);
  - the end-to-end checks in Phase 9;
  - updating CLAUDE.md (Task 10.2);
  - the follow-ups in Phases 11 and 12.

**Assumptions** (the two open questions in PROJECT-IDEA.md, until you decide otherwise):
- No expiry in v1. Pastes are kept forever.
- The create rate limit is 10 per minute per IP address, with a burst of 5.

## Target layout

```
snippet-share/
├── docker-compose.yml          # production: db, backend, frontend, mcp, nginx (only nginx publishes :3000 and :8001)
├── docker-compose.dev.yml      # override: db + backend on 127.0.0.1, backend hot reload
├── .env.example                # Compose: Postgres credentials, PUBLIC_BASE_URL, MCP_PASSWORD, MCP_JWT_SECRET, MCP_HOST_PORT
├── db/init/01-test-db.sql      # creates the snippet_test database
├── nginx/
│   └── nginx.conf              # gateway: :80 /api → backend, / → frontend; :8001 → mcp
├── mcp-server/                 # remote MCP server (Phase 11)
│   ├── server.py               # share_snippet tool, /login page, OAuth settings
│   ├── auth.py                 # OAuth 2.1 provider: clients, codes, JWT access tokens, refresh tokens
│   ├── Dockerfile
│   └── tests/                  # test_server.py (tool), test_auth.py (login flow, JWT)
├── test-agent/                 # Google ADK agent on Vertex AI for testing the MCP server (Phase 12)
│   ├── snippet_agent/
│   │   ├── agent.py            # Gemini agent + McpToolset
│   │   ├── oauth.py            # mcp SDK OAuth client, browser opener, :8765 callback listener
│   │   └── .env.example        # Vertex project/location, model, MCP_URL
│   ├── tests/test_oauth.py
│   └── TESTING.md              # manual test plan and flow diagrams
├── backend/
│   ├── .env.example            # backend outside Docker: DB URLs, size limit
│   ├── Dockerfile              # uv sync --frozen, non-root
│   ├── pyproject.toml + uv.lock
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── alembic/                # env.py + versions/
│   ├── app/
│   │   ├── main.py             # FastAPI app, includes the router
│   │   ├── core/
│   │   │   ├── config.py       # settings from env vars
│   │   │   ├── database.py     # engine, async_session_maker
│   │   │   └── dependencies.py # get_db session dependency
│   │   ├── model/
│   │   │   ├── __init__.py     # imports every model, so Base.metadata sees all tables
│   │   │   ├── base.py         # DeclarativeBase
│   │   │   └── paste.py        # Paste table
│   │   ├── schemas/
│   │   │   └── paste.py        # request/response models
│   │   ├── services/
│   │   │   └── paste.py        # database access for pastes
│   │   └── routes/
│   │       └── paste.py        # the three routes
│   └── tests/
│       ├── conftest.py
│       ├── test_smoke.py       # /api/docs
│       ├── test_foundation.py  # settings, get_db, Paste model
│       └── test_pastes.py
└── frontend/
    ├── .env.example            # Vite: size limit, dev proxy target
    ├── Dockerfile
    ├── nginx.conf              # static files + SPA fallback only
    ├── package.json + bun.lock
    ├── vite.config.ts
    ├── index.html
    ├── playwright.config.ts    # end-to-end: starts backend :8000 and Vite :5173
    ├── e2e/paste.spec.ts
    ├── test/                   # Vitest: components/, pages/, service/, setupTests.ts, test-utils.tsx
    └── src/
        ├── main.tsx
        ├── routes/index.tsx    # router: /, /view/:id, *
        ├── service/api.ts      # axios instance, QueryClient, calls + error mapping
        ├── service/clipboard.ts
        ├── hooks/useCopy.ts    # clipboard with select-text fallback
        ├── pages/              # CreatePage, ViewPage, NotFound
        ├── components/         # Layout, ShareDialog
        └── index.css           # tokens from .claude/DESIGN.md
```

---

## Phase 0: Prerequisites and repo skeleton

### Task 0.1: Install tools
- [ ] Docker Desktop, running (`docker compose version` works).
- [x] uv (`uv --version`). It installs Python 3.14 for the backend itself. If `uv` prints a pyenv message, a pyenv-win shim is shadowing it: put the real uv first on `PATH` or remove the shim.
- [x] Bun 1.3 (`bun --version`) and Node.js 24 (`node --version`).
- [ ] Get push access to `devinthoughtminds/snippet-share` (see the failed push earlier).

### Task 0.2: Repo skeleton
- [x] Create a `.gitignore` covering `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.pytest_cache/`, and `.claude/settings.local.json`.
- [x] Create the env files. Each `.env.example` is committed, and its `.env` copy is ignored:

  | File | Read by | Holds |
  |---|---|---|
  | `.env` | Docker Compose | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `PUBLIC_BASE_URL` (`:3000`) |
  | `backend/.env` | the backend outside Docker (uvicorn, pytest, alembic, run from `backend/`) | `DATABASE_URL`, `TEST_DATABASE_URL` (both `localhost:5432`), `PUBLIC_BASE_URL` (`:5173`), `MAX_PASTE_BYTES` |
  | `frontend/.env` | Vite (dev and build) | `VITE_MAX_PASTE_BYTES`, `API_PROXY_TARGET` |

- [x] Copy each to `.env`. The local `.env` and `backend/.env` share one generated database password.
- [ ] **New developers:** copy all three `.env.example` files to `.env`, and put the same password in `.env` and both URLs in `backend/.env`.
- [ ] Commit.

---

## Phase 1: Database and backend foundation

### Task 1.1: Postgres in Compose
- [x] `docker-compose.yml` has all four services: `db` (`postgres:17-alpine`, `pgdata` volume, `db/init` mounted, `pg_isready` healthcheck, no published port), `backend`, `frontend`, and the `nginx` gateway.
- [x] `db/init/01-test-db.sql`: `CREATE DATABASE snippet_test;`
- [x] `docker-compose.dev.yml` is an *override*. It only adds what dev needs: `db` on `127.0.0.1:5432`, `backend` on `127.0.0.1:8000`, a bind mount, and `--reload`.
- [ ] **Check:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db`, then wait until `docker compose ps` shows `healthy`.
- [ ] **Note:** init scripts only run when the volume is empty. If you created the volume before adding the script, run `docker compose down -v` once.
- [ ] Commit.

### Task 1.2: Backend project
- [x] Dependencies are in `pyproject.toml`, and `uv.lock` pins them. Runtime: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`. Dev group: `pytest`, `pytest-asyncio`, `httpx`. Add more with `uv add <pkg>` (or `uv add --dev <pkg>`); never edit `uv.lock` by hand. Run commands with `uv run ...` from `backend/`.
- [x] `app/core/config.py`: a `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", extra="ignore")`, fields `database_url`, `public_base_url`, `debug`, and `max_paste_bytes`, plus a single module-level `settings = Settings()`. Real environment variables take priority over `.env`, which is how Compose overrides the values in Docker. A missing `.env` is ignored. `extra="ignore"` is needed because `backend/.env` also holds `TEST_DATABASE_URL`.
  - [ ] Give `max_paste_bytes` its default, `= 1_048_576`.
- [x] `app/core/database.py`: `engine = create_async_engine(settings.database_url, echo=settings.debug)` and `async_session_maker = async_sessionmaker(engine, expire_on_commit=False)`. SQL logging stays off outside debug, because it would write paste text to the logs.
- [x] `app/core/dependencies.py`: an `async def get_db()` dependency that yields a session.
- [x] `app/main.py`: `app = FastAPI(title="snippet-share", docs_url="/api/docs", openapi_url="/api/openapi.json")`. The docs live under `/api` so the gateway routes them to the backend.
- [ ] **Check:** `uv run uvicorn app.main:app --reload` (from `backend/`) starts, and `http://localhost:8000/api/docs` loads.
- [ ] Commit.

### Task 1.3: Paste model and first migration
- [x] `app/model/base.py`: `Base(DeclarativeBase)`. `app/model/paste.py`: a `Paste` model with `id: UUID` (primary key, `default=uuid.uuid4`), `text: Text` (not null), and `created_at: TIMESTAMP(timezone=True)` (not null, `server_default=func.now()`).
- [x] `app/model/__init__.py` imports `Base` and every model. **When you add a model, import it here**, or autogenerate won't see its table and will write a migration that drops it.
- [x] `alembic init -t async alembic`. In `alembic/env.py`, `from app.model import Base`, set `target_metadata = Base.metadata`, and read the URL from `settings.database_url`.
- [x] `alembic revision --autogenerate -m "create pastes"`. **Read the generated file** and check it creates exactly the three columns.
- [ ] **Check:** `alembic upgrade head`, then `\d pastes` in `psql` shows the table.
- [ ] Commit.

### Task 1.4: Test harness
- [x] `pytest.ini`: `pythonpath = .`, `asyncio_mode = auto`, plus `asyncio_default_fixture_loop_scope = session` and `asyncio_default_test_loop_scope = session`. The engine and the tests must share one event loop; mismatched loops are the most common asyncpg test failure.
- [x] `tests/conftest.py`:
  - Load `backend/.env` with `load_dotenv()` and take the URL from `TEST_DATABASE_URL`. Refuse to run unless its database name ends in `_test`, because the fixtures drop and truncate tables.
  - A session-scoped fixture that creates an engine and runs `Base.metadata.drop_all` then `create_all`, so the test schema always matches the models. Migrations are for the real database; create_all is enough for tests.
  - A fixture that runs `TRUNCATE pastes` before each test.
  - A `client` fixture: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`, with `app.dependency_overrides[get_db]` pointing at the test engine.
- [x] A smoke test (`test_smoke.py`): `GET /api/docs` returns 200. `test_foundation.py` covers settings, `get_db`, and the `Paste` model.
- [x] **Check:** with the dev `db` running, `uv run pytest` (from `backend/`) passes. It reads `TEST_DATABASE_URL` from `backend/.env`.
- [x] Commit.

---

## Phase 2: Create a paste (`POST /api/v1/pastes`)

### Task 2.1: The happy path
- [x] **Write the test first** (`test_pastes.py`). `test_create_returns_201_with_id_and_share_url` posts `{"text": "hello\n  world"}` and checks for status 201, a body with a valid UUID `id`, `share_url == f"{PUBLIC_BASE_URL}/view/{id}"`, and an ISO `created_at`.
- [x] Run it and **watch it fail** (404, because there's no route yet).
- [x] `app/schemas/paste.py`: `PasteCreate(text: str)` and `PasteCreated(id: UUID, share_url: str, created_at: datetime)`.
- [x] `app/services/paste.py`: `create_paste(session, text)` inserts the row, commits, and refreshes it (to load `created_at`); `get_paste(session, id)` wraps `session.get`.
- [x] `app/routes/paste.py`: `router = APIRouter(prefix="/api/v1/pastes")` with a `POST ""` route (`status_code=201`) that takes a session from `Depends(get_db)`, calls the service, commits, and returns `PasteCreated`. Include the router in `main.py`.
- [x] Run it and watch it pass. Commit.

### Task 2.2: The text is stored exactly
- [x] Test: create a paste containing tabs, leading spaces, `\r\n`, emoji and a trailing newline, then read the row straight from the database and check it equals the input byte for byte.
- [x] Make it pass. It should already pass; if it doesn't, something is stripping the text.
- [x] Commit.

### Task 2.3: Empty text is rejected
- [x] Tests: `{"text": ""}`, `{"text": "   \n\t"}`, `{}`, and `{"text": 123}` each return 422.
- [x] Add a `field_validator("text")` to `PasteCreate` that raises when `not v.strip()`. **Don't change `v` itself**; return it unchanged, because whitespace inside a paste is content.
- [x] Commit.

### Task 2.4: Size limit
- [x] Tests:
  - Text of exactly `MAX_PASTE_BYTES` bytes is accepted (201).
  - One byte more returns 413.
  - **Multi-byte case:** text that's under 1 MB *in characters* but over 1 MB *in UTF-8 bytes* (for example, 400,000 × `"é"`, which is 800,000 bytes, plus padding to go just over) returns 413. This test proves you measure bytes, not characters.
- [x] In the route, before inserting: `if len(body.text.encode("utf-8")) > settings.max_paste_bytes: raise HTTPException(413, "Paste exceeds 1 MB")`. This goes in the route, not the validator, because a validator can only produce 422.
- [x] Commit.

---

## Phase 3: Reading pastes

### Task 3.1: `GET /api/v1/pastes/{id}`
- [x] Tests:
  - Create, then get by id: 200 with the same `id`, `text` and `created_at`.
  - A valid but unknown UUID returns 404.
  - **Malformed ids** (`not-a-uuid`, `123`, `c9bf9e57-1685`) return **404, not 422**.
- [x] Route: take `paste_id: str` (deliberately not `UUID`, so FastAPI doesn't return its own 422). Parse it with `uuid.UUID(paste_id)`; on `ValueError`, return 404. Use `session.get(Paste, id)`, and return 404 if it's `None`.
- [x] Put the parse-and-fetch steps in a small helper (`get_paste_or_404`), because Task 3.2 needs the same thing.
- [x] Commit.

### Task 3.2: `GET /api/v1/pastes/{id}/raw`
- [x] Tests:
  - Returns 200 with `content-type: text/plain; charset=utf-8`, and a body exactly equal to the original text (including the `\r\n` and emoji from Task 2.2).
  - An unknown id and a malformed id both return 404.
- [x] Route: `get_paste_or_404`, then `PlainTextResponse(paste.text)`.
- [x] **Security test:** pasting `<script>alert(1)</script>` and reading `/raw` gives back `text/plain`, never `text/html`.
- [x] Commit.

### Task 3.3: Clean up the API docs
- [ ] Set `response_model` and `responses={404: ..., 413: ..., 422: ...}` on each route so `/docs` shows the real behaviour.
- [ ] **Check:** open `/api/docs` and try all three routes by hand.
- [ ] Commit.

---

## Phase 4: Backend container

### Task 4.1: Dockerfile
- [x] `backend/Dockerfile`: `python:3.14-slim` plus the uv binary. `uv sync --frozen --no-dev` installs from `uv.lock` into `/opt/venv`, which sits outside `/app` so the dev bind mount doesn't hide it. Runs as the non-root `app` user.
- [x] `.dockerignore` covers `.env`, `.venv`, `__pycache__`, `.pytest_cache`. Secrets are never baked into the image.
- [ ] Alembic exists now (Task 1.3) but the image still starts only uvicorn, so a fresh database has no `pastes` table. Change the startup command to `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"`.

### Task 4.2: The backend service in Compose
- [x] `backend` gets its settings only from `environment:` in `docker-compose.yml`. Compose fills the `${...}` values from the root `.env`. `MAX_PASTE_BYTES` defaults to 1 MB unless the root `.env` sets it:
  ```yaml
    backend:
      build: ./backend
      environment:
        DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
        PUBLIC_BASE_URL: ${PUBLIC_BASE_URL}
        MAX_PASTE_BYTES: ${MAX_PASTE_BYTES:-1048576}
      depends_on:
        db:
          condition: service_healthy
  ```
- [x] No `ports:` in the main file. The dev override publishes `127.0.0.1:8000:8000`.
- [ ] **Check:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build db backend`. The logs show the migration running, then Uvicorn starting. Then `curl -X POST localhost:8000/api/v1/pastes -H "content-type: application/json" -d "{\"text\":\"hi\"}"` returns 201.
- [ ] **Tests** run on the host (`uv run pytest`) against the dev `db`. The image has no dev dependencies.
- [ ] Commit.

---

## Phase 5: Frontend skeleton

### Task 5.1: Scaffold
- [x] Vite + React + TypeScript scaffold, with Bun (`bun.lock`).
- [x] `bun add react-router-dom`
- [x] `bun add @tanstack/react-query axios`. `src/service/api.ts` holds the axios instance (`baseURL: "/api/v1"`) and the `QueryClient` (`staleTime: Infinity`, because pastes never change; `retry: false`, because errors show a **Retry** button). `main.tsx` wraps the app in `QueryClientProvider`.
- [x] `bun add -d vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom`
- [x] `vite.config.ts` proxies `/api` to `API_PROXY_TARGET` (from `frontend/.env`) in dev, so dev uses the same paths as production.
- [x] Add `test: { environment: "jsdom", setupFiles: "./test/setupTests.ts", exclude: ["e2e/**", "node_modules/**"] }` to `vite.config.ts`.
- [x] Deleted the Vite demo files (`App.css`, assets, `icons.svg`). There is no `App.tsx`: `main.tsx` mounts the router from `src/routes/index.tsx`.
- [x] Add a `"test": "vitest"` script.
- [x] Commit.

### Task 5.2: Routing
- [x] `src/main.tsx`: `createBrowserRouter` with `/` → `CreatePage`, `/view/:id` → `ViewPage`, and `*` → a simple "Page not found" with a link home.
- [x] Create placeholder `CreatePage` and `ViewPage` components.
- [ ] **Check:** `bun run dev`. Visiting `/`, `/view/abc` and `/nope` each shows the right placeholder.
- [x] Commit.

### Task 5.3: API client (`src/service/api.ts`)
- [x] **Tests first** (`test/service/`, mocking the instance with `vi.spyOn(api, "post")` / `vi.spyOn(api, "get")`):
  - `createPaste("x")` POSTs `{ text: "x" }` to `/pastes` and resolves with `response.data` on a 201.
  - A 413 throws an error with `kind: "too_large"`. A 429 throws `kind: "rate_limited"`, a 422 throws `kind: "invalid"`, an axios error with no `response` (network failure) throws `kind: "network"`, and anything else throws `kind: "server"`.
  - `getPaste(id)` resolves on a 200, and throws `kind: "not_found"` on a 404.
- [x] Implement `createPaste` and `getPaste` next to the instance in `api.ts`, catching with `axios.isAxiosError(err)`. **Map errors on `err.response?.status`, never on the body.** Nginx returns 413 and 429 as HTML pages, not JSON.
- [x] Commit.

---

## Phase 6: Create view (`/`)

### Task 6.1: Text area and counters
- [x] **Tests first** (`CreatePage.test.tsx`):
  - The text area has focus after the page renders.
  - Typing `hello world` shows "11 characters · 2 words".
  - **Save & Share** is disabled when the text is empty or only whitespace.
  - Text over 1 MB (in UTF-8 bytes) shows "Too large (max 1 MB)" and disables the button.
- [x] Implement it:
  - A `<textarea autoFocus spellCheck={false}>` with a monospace font, filling the page.
  - Words: `text.trim().split(/\s+/).filter(Boolean).length`
  - Bytes: `new TextEncoder().encode(text).length`
  - Limit: `Number(import.meta.env.VITE_MAX_PASTE_BYTES ?? 1048576)`. The fallback matters: the Docker build has no `.env` (it's in `.dockerignore`).
  - Give the text area a label (`aria-label="Paste text"`) for screen readers.
- [x] Commit.

### Task 6.2: Saving
- [x] **Tests first:**
  - Clicking Save calls `createPaste` with the exact text (not trimmed).
  - While the request is pending, the button shows "Saving…" and is disabled. Double clicks must not create two pastes.
  - On success, a dialog opens showing the `share_url`.
  - For each error kind, the right inline message appears:
    - `too_large`: "Too large (max 1 MB)"
    - `rate_limited`: "Too many pastes, try again in a minute"
    - `network`: "Couldn't reach the server" with a **Retry** button
    - `server`: "Something went wrong" with a **Retry** button
  - The text is **kept** after an error. Never lose what the user pasted.
- [x] Implement it with `useMutation({ mutationFn: createPaste })`. Disable the button while `isPending`, read the error kind from `error`, and make **Retry** call `mutate(text)` again. Tests wrap the page in a fresh `QueryClientProvider` each time.
- [x] Commit.

### Task 6.3: Share dialog
- [x] **Tests first:**
  - The dialog shows the link in a read-only input, with **Copy link** and **Open** buttons.
  - **Copy link** calls `navigator.clipboard.writeText(share_url)` and shows "Copied!".
  - When the clipboard isn't available, the dialog selects the input's text and shows "Press Ctrl+C to copy".
  - Pressing Escape or **Close** closes the dialog, and focus goes back to the text area.
- [x] Implement it with a native `<dialog>` element and `showModal()`. That gives you focus trapping and Escape handling for free.
- [x] **Why the fallback matters:** the clipboard API only works on `https://` or `localhost`. If someone opens the app at `http://192.168.x.x:3000`, `navigator.clipboard` is `undefined`.
- [x] Commit.

---

## Phase 7: Reader view (`/view/:id`)

### Task 7.1: Loading and showing a paste
- [x] **Tests first** (`ViewPage.test.tsx`, with a mocked `getPaste`):
  - Shows "Loading…" while the request is in progress.
  - On success, every line of the text appears, in order.
  - Indentation is kept exactly: a line starting with 4 spaces still starts with 4 spaces.
  - `not_found` shows "Snippet not found." and a **New paste** link.
  - A network or server error shows "Couldn't load this snippet" and a **Retry** button.
- [x] Implement it:
  - `useParams()`, then `useQuery({ queryKey: ["paste", id], queryFn: () => getPaste(id) })`. `isPending` shows "Loading…", and **Retry** calls `refetch()`.
  - The text goes in `<pre>`, one `<span class="line">` per line (`text.split("\n")`), with `white-space: pre-wrap`.
  - **Never use `dangerouslySetInnerHTML`.**
- [x] Commit.

### Task 7.2: Line numbers
- [x] **Test:** the line numbers are not part of the text content (the `<pre>`'s `textContent` equals the original paste).
- [x] Use CSS counters: `.line::before { counter-increment: line; content: counter(line); user-select: none; }`. Content generated by `::before` isn't copied when someone selects the text, and isn't in `textContent`. No extra elements needed.
- [ ] **Check by hand:** select all the text in the browser, copy it, and paste it into an editor. There should be no numbers.
- [x] Commit.

### Task 7.3: Action buttons
- [x] **Tests first:**
  - **Copy raw text** calls `navigator.clipboard.writeText(paste.text)` and shows "Copied!". When the clipboard isn't available, it falls back to selecting the `<pre>`.
  - **Open raw** is a link to `/api/v1/pastes/{id}/raw`, opening in a new tab.
  - **New paste** links to `/`.
- [x] Implement it.
- [x] **Security test:** a paste of `<img src=x onerror=alert(1)>` shows as literal text, and no `<img>` element exists in the page.
- [x] Commit.

---

## Phase 8: Frontend container and Nginx gateway

```
Browser ──► nginx (gateway, :3000 on host)
              ├─ = /api/v1/pastes  → rate limit + 2 MB cap → backend:8000
              ├─ /api/*            → backend:8000
              └─ /*                → frontend:80 (static files, SPA fallback)
```

The gateway is the only container with a port open on the host. `frontend` and `backend` are reachable only inside the Compose network.

### Task 8.1: `frontend/nginx.conf` (static files only)
- [x] Write it:
  ```nginx
  server {
      listen 80;
      root /usr/share/nginx/html;

      # React routes (/view/:id) fall back to index.html
      location / {
          try_files $uri /index.html;
      }
  }
  ```
- [x] It has no `/api` handling and no rate limiting. The gateway does both.

### Task 8.2: `frontend/Dockerfile` (multi-stage)
- [x] Stage 1: `FROM node:24-alpine AS build`, install Bun, `bun install --frozen-lockfile`, `bun run build`. Stage 2: `nginx:1.27-alpine` with `frontend/nginx.conf` and the built `dist/`.
- [x] Add a `.dockerignore` covering `node_modules`, `dist`, `.env`.

### Task 8.3: The gateway, `nginx/nginx.conf` (already written)
- [x] **Changed since this was written:** the `upstream` blocks are gone. nginx now uses `resolver 127.0.0.11 valid=10s` and `proxy_pass $variable`, so it looks up containers through Docker's DNS on each request. Fixed addresses from startup went stale when a container was recreated: nginx crashed with "host not found", or sent `/mcp` to the backend (502). There is also a second `server` on `:8001` for the MCP server (Task 11.4).
- [x] Read [nginx/nginx.conf](../nginx/nginx.conf). It's already in the repo. Make sure you understand each block:
  - `limit_req_zone`: tracks how often each client IP creates pastes (10 per minute).
  - `location = /api/v1/pastes`: an exact match. The only route at that exact path is `POST`, so only creates are rate limited, with a burst of 5 and a 429 response when exceeded. Reads go to `/api/v1/pastes/{id}`, which the exact match doesn't cover. `client_max_body_size 2m` caps the request body here.
  - `location /api/`: reads, raw, and `/api/docs` go to the backend without a rate limit.
  - `location /`: everything else goes to the frontend container.
  - `proxy_set_header`: passes the client's real IP and the original host to the backend.
- [ ] **Behind a load balancer or Cloudflare:** add `set_real_ip_from <proxy range>;` and `real_ip_header X-Forwarded-For;` to the gateway. Otherwise every user shares one IP address and one rate limit. Skip this for local use.

### Task 8.4: Add `frontend` and `nginx` to Compose
- [x] Add to `docker-compose.yml` (it now also has `mcp`, and nginx publishes `${MCP_HOST_PORT:-8001}:8001`):
  ```yaml
    frontend:
      build: ./frontend
      # no ports: reached only through the gateway

    nginx:
      image: nginx:1.27-alpine
      ports:
        - "3000:80"
      volumes:
        - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
      depends_on:
        - backend
        - frontend
  ```
- [x] **Check the config:** `docker compose run --rm nginx nginx -t` prints `syntax is ok`.
- [x] **Check:** `docker compose up --build` (without the dev file). Open `http://localhost:3000`, create a paste, and open its link. Also check that `http://localhost:3000/api/docs` loads the API docs.
- [ ] **Check isolation:** `curl localhost:8000` fails (connection refused). The backend isn't reachable from the host without the dev file.
- [ ] Commit.

---

## Phase 9: End-to-end checks ("Done when")

Do each check against `docker compose up --build`, with no dev file. Each one is from PROJECT-IDEA.md.

- [ ] **Clean start:** `docker compose down -v`, then `docker compose up --build`. The app works at `http://localhost:3000`.
- [ ] **Round trip:** paste text with tabs, indentation, emoji and Windows line endings. Open the link in a private window, copy the raw text, and compare it with the original in a diff tool. They should be identical.
- [ ] **Size:** a file of exactly 1 MB saves and displays with line numbers. One byte more shows "Too large".
  - PowerShell: `"a" * 1048576 | Set-Clipboard`
- [ ] **Errors:** an unknown UUID and `/view/not-a-uuid` both show "Snippet not found." Also check that `curl -i localhost:3000/api/v1/pastes/not-a-uuid` returns 404.
- [ ] **Rate limit:** send 20 creates in a row. The first 6 or so succeed, the rest return 429, and the UI shows the rate-limit message.
  ```sh
  for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:3000/api/v1/pastes -H "content-type: application/json" -d '{"text":"x"}'; done
  ```
- [ ] **Persistence:** `docker compose down`, then `docker compose up` (without `-v`). Old links still work.
- [ ] **Raw:** `curl -i localhost:3000/api/v1/pastes/<id>/raw` returns `text/plain; charset=utf-8` and the exact text.
- [ ] **XSS:** pastes of `<script>alert(1)</script>` and `<img src=x onerror=alert(1)>` show as literal text, and no alert pops up.
- [ ] **Clipboard over plain HTTP:** open the app at `http://<your-LAN-IP>:3000`. Copy falls back to selecting the text instead of failing silently.
- [ ] **Tests:** backend `uv run pytest`, frontend `bun run test --run` and `bun run test:e2e`, `mcp-server` `uv run pytest`, and `test-agent` `uv run pytest` all pass.
- [ ] **Agent round trip:** follow the main scenario in [test-agent/TESTING.md](../test-agent/TESTING.md). The agent logs in, gets a JWT, calls `share_snippet`, and the link opens in a private window.
- [ ] **Agent edge cases:** cases N1–N9 in TESTING.md (no token, forged token, wrong password, login rate limit, app down, MCP restart, key change, agent restart).

---

## Phase 10: Docs

### Task 10.1: README
- [x] What it is, in one line (already there).
- [x] **Run it:** copy the three `.env.example` files (root, `backend/`, `frontend/`) to `.env` and set the password, then `docker compose up --build`, then open `http://localhost:3000`.
- [x] **Develop:** the dev compose file, `uvicorn --reload`, `bun run dev`.
- [x] **Test:** in [backend/README.md](../backend/README.md) ("Running the tests") and [frontend/README.md](../frontend/README.md) ("Writing a Playwright test").
- [x] **Configuration:** the table from PROJECT-IDEA.md.
- [ ] **API:** the three routes, with status codes.
- [ ] **MCP:** a short section in the root README pointing to [mcp-server/README.md](../mcp-server/README.md) and [test-agent/README.md](../test-agent/README.md), and listing the new root `.env` keys (`MCP_PASSWORD`, `MCP_JWT_SECRET`, `MCP_HOST_PORT`). Compose now refuses to start without the first two.

### Task 10.2: Update CLAUDE.md
- [ ] Replace its "Current state" section (it still says the repo has only `README.md`) with the real commands: build, test, and how to run a single test (`uv run pytest tests/test_pastes.py::test_name`, `bunx vitest run -t "name"`, `bunx playwright test -g "name"`).
- [ ] Add a short architecture note:
  - the `nginx` gateway is the only service open to the host (`:3000` for the app, `:8001` for MCP);
  - the rate limits and body cap live in `nginx/nginx.conf`;
  - the backend enforces the 1 MB text limit;
  - the MCP server calls the backend inside Docker at `http://backend:8000`.
- [ ] Commit, then push.

---

## Phase 11: Remote MCP server (`mcp-server/`)

Lets coding agents (Claude Code, Codex, the ADK test agent) turn text into a share link. Built with the official `mcp` Python SDK 2.x, where `FastMCP` was renamed `MCPServer`.

### Task 11.1: The `share_snippet` tool
- [x] `@mcp.tool() async def share_snippet(text: str) -> str` posts to `POST /api/v1/pastes` and returns `share_url`. The docstring is what the agent reads to decide when to call it.
- [x] Failures raise `ToolError`, because the SDK hides the message of any other exception from the agent. Tests cover the app being down and the API rejecting text.
- [x] `SNIPPET_API_URL` sets where the API is (`http://backend:8000` in Docker).

### Task 11.2: OAuth 2.1 login (the server is its own login server)
- [x] The SDK serves `/.well-known/oauth-protected-resource/mcp`, `/.well-known/oauth-authorization-server`, `/register`, `/authorize`, `/token` and `/revoke`, and checks PKCE, redirect URIs and code expiry.
- [x] `auth.py` `InMemoryAuthProvider` holds:
  - registered clients (dynamic registration, so agents register themselves);
  - pending logins;
  - one-time codes (5 minutes);
  - refresh tokens (30 days, replaced on each use).
- [x] `/login` (GET form, POST check) compares `MCP_PASSWORD` in constant time, then `approve()` mints the code and redirects back to the agent.
- [x] Tests ([tests/test_auth.py](../mcp-server/tests/test_auth.py)):
  - `401` with a pointer to the discovery document;
  - the full login with PKCE;
  - a replayed code is refused;
  - a wrong password gives no code;
  - a made-up token is refused;
  - refreshing replaces the old token.

### Task 11.3: JWT access tokens
- [x] Access tokens are HS256 JWTs signed with `MCP_JWT_SECRET` (32+ characters), valid 1 hour. They carry `iss`, `aud` (the `/mcp` URL), `sub`, `client_id`, `scope`, `iat`, `exp` and `jti`.
- [x] Every `/mcp` request checks the signature, expiry, issuer and audience without a storage lookup. `validate_token_resource=True` refuses tokens issued for another server.
- [x] Revoking an access token adds its `jti` to a denylist. Revoking a token also deletes the client's refresh tokens.
- [x] Tests: the token decodes with the right claims, and a JWT signed with another key is refused.

### Task 11.4: Docker and gateway
- [x] `mcp-server/Dockerfile` is built the same way as the backend's (uv, non-root). It isn't published to the host directly.
- [x] nginx `server { listen 8001; }` → `mcp:8001`. It's a separate port because `/login`, `/token` and `/.well-known` would clash with the frontend's paths. Responses are streamed without buffering, with a 1-hour read timeout.
- [x] `/login` is rate limited to 5 per minute with a burst of 3 (`429`), to slow down password guessing.
- [x] `MCP_HOST_PORT` (default 8001) changes the port on your machine. Locally it's 8002, because another project uses 8001. `MCP_PUBLIC_URL` follows it.
- [x] Checked: `POST /mcp` with no token returns `401` through nginx, and the discovery documents load.

### Task 11.5: Follow-ups
- [ ] Store clients and refresh tokens in Postgres. Right now an MCP restart forgets every agent's registration and refresh token, so agents must log in again once their JWT expires.
- [ ] Replace the shared password with per-user logins, or a hosted login provider (Auth0, Keycloak, Entra ID) when this goes public.
- [ ] Require auth on the snippet-share API itself. Anyone who can reach `/api/v1/pastes` can still create pastes without going through MCP.
- [ ] When deploying: set `MCP_PUBLIC_URL` to the public `https://` address, configure the SDK's transport security (DNS rebinding protection) for the real host, and pick a strong `MCP_PASSWORD` (the local one is `tom`).

---

## Phase 12: ADK test agent (`test-agent/`)

A separate project that tests the MCP server the way a real agent uses it.

### Task 12.1: The agent
- [x] Google ADK 2.13 with the `mcp` extra (`google-adk[mcp]`). It runs Gemini on Vertex AI (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`): project `nft-ai-product-dev-prj`, location `global`, model `gemini-3.1-flash-lite` (set by `AGENT_MODEL`).
- [x] `McpToolset(StreamableHTTPConnectionParams(url=MCP_URL, timeout=120, httpx_client_factory=...))`. The long timeout covers waiting for you to log in in the browser.
- [x] Settings live in `snippet_agent/.env`, which git ignores. Vertex AI needs `gcloud auth application-default login`.

### Task 12.2: The agent's side of the login
- [x] `oauth.py` gives ADK the `mcp` SDK's `OAuthClientProvider` through `httpx_client_factory`. The SDK does discovery, registration, PKCE, the token exchange and refreshing.
- [x] Our code adds only:
  - `open_browser`, which prints the URL and opens it;
  - `CallbackListener`, a one-shot server on `127.0.0.1:8765` that catches `/callback?code&state`.
- [x] Tests: the listener returns the code and state, reports a denied login, and ignores other paths; the factory attaches the provider.
- [x] Checked end to end with a script playing the human: `/authorize`, then `/login`, then the callback, then the JWT, then `share_snippet` called with the bearer token.

### Task 12.3: Follow-ups
- [ ] Run the manual scenario in TESTING.md with the real browser and Gemini (Phase 9).
- [ ] Keep tokens across `adk web` restarts by saving them to a file or the OS keyring instead of memory.
- [ ] Remove `test-agent/snippet_agent/.adk/session.db` from git (it was committed in `da0fabc` and holds local chat history), and add `.adk/` to `.gitignore`.

---

## Phase 13: Stateless secret-scanner MCP server (`mcp-secret-scanner/`)

A second, separate MCP server, built to learn the stateless transport. It also stops the agent from sharing snippets that contain secrets.

### Task 13.1: Detection logic
- [x] `scanner.py`: regex rules for private keys, JWTs, AWS, GitHub, Google and Slack tokens, `sk-` keys, URL passwords, quoted password assignments and `.env` secrets. Placeholders are skipped, and overlapping matches are reported once.
- [x] `scan(text)` returns type, line and a masked preview (never the secret). `redact(text)` replaces only the secret part.
- [x] 22 tests ([tests/test_scanner.py](../mcp-secret-scanner/tests/test_scanner.py)): every rule, normal code and placeholders not flagged, redaction keeps all other bytes.

### Task 13.2: Stateless MCP server
- [x] `server.py`: `scan_secrets` (structured output `{found, findings}`) and `redact_secrets`, served with `streamable_http_app(stateless_http=True, json_response=True)`. No login.
- [x] 5 tests ([tests/test_stateless.py](../mcp-secret-scanner/tests/test_stateless.py)):
  - `initialize` returns no `mcp-session-id`;
  - `tools/call` works with no `initialize` first;
  - replies are `application/json`;
  - separate requests are answered independently.

### Task 13.3: Wiring
- [x] Compose service `mcp-secret-scanner`. nginx `listen 8003` publishes it on `${MCP_SCANNER_HOST_PORT:-8003}`, with a 2 MB body cap.
- [x] The test agent has a second `McpToolset` (`SCANNER_URL`, no auth factory). Its instruction is to scan first, ask before sharing anything with findings, and offer the redacted text.
- [x] Checked live through nginx: 200, `application/json`, no session id, both secrets found. ADK's `McpToolset` lists and calls both tools.
- [ ] Run the "Second scenario" in [test-agent/TESTING.md](../test-agent/TESTING.md) with Gemini.

---

## Phase 14: Observability and evals

Traces for the test agent and both MCP servers in a self-hosted Langfuse, with secrets masked, plus evals for the scan-then-share rule. Design: [docs/superpowers/specs/2026-10-27-agent-observability-and-evals-design.md](../docs/superpowers/specs/2026-10-27-agent-observability-and-evals-design.md). Plan: [docs/superpowers/plans/2026-10-27-agent-observability-and-evals.md](../docs/superpowers/plans/2026-10-27-agent-observability-and-evals.md).

- [x] Scanner precision corpus (`tests/corpus.json`): precision and recall 1.000. It caught prefixed names like `db_password = "..."`, which the `password_assignment` rule now finds.
- [x] `snippet_tracing.py` (packaged with the scanner, shared by all three): Langfuse client with `mask_otel_spans` using `redact()`, including JSON-encoded tool arguments; `@traced` tools; off without `LANGFUSE_PUBLIC_KEY`.
- [x] Both MCP servers traced. The scanner reaches `mcp-server`'s Docker build as a second build context (`additional_contexts`).
- [x] Local Langfuse v4 as compose profile `langfuse` (UI on :3100, no storage ports, headless init from `.env`).
- [x] Agent traced with `openinference-instrumentation-google-adk`; server spans nest under the agent's tool spans (the MCP client's `tools/call` span is exported to link them).
- [x] Headless MCP login (`MCP_PASSWORD`) and ADK evals in `evals/shares` (IN_ORDER) and `evals/blocks` (EXACT), with rubric checks. Both pass live.
- [x] Langfuse experiment `evals/run_experiment.py` on dataset `snippet-agent/scan-then-share`; runs compare side by side.
- [ ] Score live traces automatically (deferred).

---

## Things that are easy to get wrong

| Area | Mistake | What to do instead |
|---|---|---|
| Malformed id | Declaring `paste_id: UUID` gives FastAPI's own 422 | Use `str`, parse it yourself, return 404 |
| Size check | `len(text)` counts characters | `len(text.encode("utf-8"))` counts bytes |
| Size check | Putting it in a Pydantic validator | Validators can only give 422. Do it in the route for 413 |
| Whitespace | `.strip()` the text before saving | Only *check* `strip()` for emptiness. Store the text as-is |
| Nginx errors | Reading `err.response.data` on 413 or 429 | Those are HTML pages. Map errors by `err.response?.status` |
| React Query | Default `retry: 3` on a 404 | Keeps "Loading…" up for seconds. `retry: false` is set on the `QueryClient` in `api.ts` |
| Clipboard | Assuming `navigator.clipboard` exists | It's `undefined` on plain HTTP away from localhost. Add a fallback |
| Line numbers | Numbers in the DOM text | CSS `::before` counters, which aren't copied |
| Rate limit | Applying `limit_req` to all of `/api/` | Exact-match `location = /api/v1/pastes`, so only creates are limited |
| Gateway | `upstream` blocks look up container IPs once at startup. A recreated container gets a new IP, so nginx crashes ("host not found") or sends traffic to the wrong container (502) | `resolver 127.0.0.11` plus `proxy_pass $variable`, so nginx looks up names on each request |
| Ports | Publishing a fixed host port that another project already uses | Make it a setting (`MCP_HOST_PORT`) and update `MCP_URL` in the agent's `.env` to match |
| MCP errors | Raising `RuntimeError` in a tool: the agent only sees "Error executing tool" | Raise `ToolError`; its message reaches the agent |
| MCP SDK 2.x | Following tutorials that import `FastMCP` | `from mcp.server.mcpserver import MCPServer`; client models use snake_case (`input_schema`, `is_error`) |
| MCP auth | Expecting stdio servers to use OAuth | OAuth applies only to remote HTTP servers. A stdio server gets its secrets from environment variables |
| JWT | Checking the signature but not `aud` | Decode with `audience=` and `issuer=`, so a token minted for another server is refused |
| Windows `.env` | PowerShell 5 `Set-Content -Encoding utf8` adds a byte-order mark that breaks the first key | Write `.env` files with an editor, or `[IO.File]::WriteAllText` |
| API docs | Leaving FastAPI's docs at `/docs`, where the gateway sends them to the frontend | `docs_url="/api/docs"`, `openapi_url="/api/openapi.json"` |
| Postgres init | Adding `db/init` after the volume exists | Init scripts only run on an empty volume. `down -v` once |
| Async tests | Engine and tests on different event loops | Session-scoped loop in `pytest.ini` |
| Compose profiles | `${VAR:?message}` in a profile-only service fails `docker compose up` for everyone, even with the profile off | Use `${VAR:-}` there and let the service itself refuse to start without it |
| Langfuse + MCP | The server's spans show up loose in the trace, not under the tool call | Langfuse's default filter drops the MCP client's `MCP send tools/call` span (no `gen_ai.*` attributes), which is their parent. Export it with `should_export_span` |
| Tracing decorators | Calling `init_tracing()` in `__main__`, after module-level `@traced` already ran | Initialise at import, before the decorated functions |
