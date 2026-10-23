# snippet-share: implementation plan

This plan implements [PROJECT-IDEA.md](PROJECT-IDEA.md). Work through the phases in order; each one ends in something you can run or test. Tick the boxes as you go.

**Working rules** (from [CLAUDE.md](../CLAUDE.md)):
- **Test first.** For anything with logic, write the test, run it and watch it fail, then write the least code that makes it pass, then commit.
- **One commit per task** (each `### Task`), with a message describing it.
- **Don't build what isn't listed here.** No extra abstractions, no "might need it later" code.

**Assumptions** (the two open questions in PROJECT-IDEA.md, until you decide otherwise):
- No expiry in v1. Pastes are kept forever.
- The create rate limit is 10 per minute per IP address, with a burst of 5.

## Target layout

```
snippet-share/
├── docker-compose.yml
├── docker-compose.dev.yml      # dev only: publishes db 5432 + backend 8000
├── .env.example
├── db/init/01-test-db.sql      # creates the snippet_test database
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── alembic.ini
│   ├── alembic/                # env.py + versions/
│   ├── app/
│   │   ├── main.py             # FastAPI app, includes the router
│   │   ├── config.py           # settings from env vars
│   │   ├── db.py               # engine, session dependency
│   │   ├── models.py           # Paste table
│   │   ├── schemas.py          # request/response models
│   │   └── pastes.py           # the three routes
│   └── tests/
│       ├── conftest.py
│       └── test_pastes.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx            # router
        ├── api.js              # fetch calls + error mapping
        ├── CreatePage.jsx
        ├── ViewPage.jsx
        ├── styles.css
        └── *.test.jsx
```

---

## Phase 0: Prerequisites and repo skeleton

### Task 0.1: Install tools
- [ ] Docker Desktop, running (`docker compose version` works).
- [ ] Python 3.12 or later (`python --version`). Only needed if you want to run the backend outside Docker.
- [ ] Node.js 22 LTS (`node --version`).
- [ ] Get push access to `devinthoughtminds/snippet-share` (see the failed push earlier).

### Task 0.2: Repo skeleton
- [ ] Create a `.gitignore` covering `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `.pytest_cache/`, and `.claude/settings.local.json`.
- [ ] Create `.env.example`:
  ```
  POSTGRES_USER=snippet
  POSTGRES_PASSWORD=change-me
  POSTGRES_DB=snippet
  PUBLIC_BASE_URL=http://localhost:3000
  MAX_PASTE_BYTES=1048576
  ```
- [ ] Copy it to `.env` (not committed).
- [ ] Commit.

---

## Phase 1: Database and backend foundation

### Task 1.1: Postgres in Compose
- [ ] Create `docker-compose.yml` with only the `db` service for now:
  - `image: postgres:16-alpine`
  - `env_file: .env`
  - `volumes: [pgdata:/var/lib/postgresql/data, ./db/init:/docker-entrypoint-initdb.d:ro]`
  - `healthcheck`: `pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}`, every 5 seconds, 10 retries
  - No `ports:`. The database isn't reachable from the host.
  - A top-level `volumes: { pgdata: {} }`.
- [ ] Create `db/init/01-test-db.sql`: `CREATE DATABASE snippet_test;`
- [ ] Create `docker-compose.dev.yml`, which publishes `db` on `127.0.0.1:5432:5432`. It's for local development only.
- [ ] **Check:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db`, then wait until `docker compose ps` shows `healthy`.
- [ ] **Note:** init scripts only run when the volume is empty. If you created the volume before adding the script, run `docker compose down -v` once.
- [ ] Commit.

### Task 1.2: Backend project
- [ ] Create a virtual environment: `python -m venv backend/.venv`, then activate it.
- [ ] `backend/requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pydantic-settings`, `pytest`, `pytest-asyncio`, `httpx`. Pin the versions you install (`pip freeze`).
- [ ] `app/config.py`: a `Settings(BaseSettings)` with `database_url`, `public_base_url`, and `max_paste_bytes: int = 1_048_576`, plus a single module-level `settings = Settings()`.
- [ ] `app/db.py`: `engine = create_async_engine(settings.database_url)`, `SessionLocal = async_sessionmaker(engine, expire_on_commit=False)`, and an `async def get_session()` dependency that yields a session.
- [ ] `app/main.py`: `app = FastAPI(title="snippet-share")`.
- [ ] **Check:** `uvicorn app.main:app --reload` (from `backend/`) starts, and `http://localhost:8000/docs` loads.
- [ ] Commit.

### Task 1.3: Paste model and first migration
- [ ] `app/models.py`: a `Paste` model with `id: UUID` (primary key, `default=uuid.uuid4`), `text: Text` (not null), and `created_at: TIMESTAMP(timezone=True)` (not null, `server_default=func.now()`).
- [ ] `alembic init -t async alembic`. In `alembic/env.py`, set `target_metadata = Base.metadata` and read the URL from `settings.database_url`.
- [ ] `alembic revision --autogenerate -m "create pastes"`. **Read the generated file** and check it creates exactly the three columns.
- [ ] **Check:** `alembic upgrade head`, then `\d pastes` in `psql` shows the table.
- [ ] Commit.

### Task 1.4: Test harness
- [ ] `pytest.ini`: `asyncio_mode = auto`, plus `asyncio_default_fixture_loop_scope = session`. The engine and the tests must share one event loop; mismatched loops are the most common asyncpg test failure.
- [ ] `tests/conftest.py`:
  - Set the URL to the `snippet_test` database, from a `TEST_DATABASE_URL` env var.
  - A session-scoped fixture that creates an engine and runs `Base.metadata.create_all`. Migrations are for the real database; create_all is enough for tests.
  - A fixture that runs `TRUNCATE pastes` before each test.
  - A `client` fixture: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`, with `app.dependency_overrides[get_session]` pointing at the test engine.
- [ ] A smoke test: `GET /docs` returns 200.
- [ ] **Check:** `pytest` passes.
- [ ] Commit.

---

## Phase 2: Create a paste (`POST /api/v1/pastes`)

### Task 2.1: The happy path
- [ ] **Write the test first** (`test_pastes.py`). `test_create_returns_201_with_id_and_share_url` posts `{"text": "hello\n  world"}` and checks for status 201, a body with a valid UUID `id`, `share_url == f"{PUBLIC_BASE_URL}/view/{id}"`, and an ISO `created_at`.
- [ ] Run it and **watch it fail** (404, because there's no route yet).
- [ ] `app/schemas.py`: `PasteCreate(text: str)` and `PasteCreated(id: UUID, share_url: str, created_at: datetime)`.
- [ ] `app/pastes.py`: `router = APIRouter(prefix="/api/v1/pastes")` with a `POST ""` route (`status_code=201`) that inserts the row, commits, and returns `PasteCreated`. Include the router in `main.py`.
- [ ] Run it and watch it pass. Commit.

### Task 2.2: The text is stored exactly
- [ ] Test: create a paste containing tabs, leading spaces, `\r\n`, emoji and a trailing newline, then read the row straight from the database and check it equals the input byte for byte.
- [ ] Make it pass. It should already pass; if it doesn't, something is stripping the text.
- [ ] Commit.

### Task 2.3: Empty text is rejected
- [ ] Tests: `{"text": ""}`, `{"text": "   \n\t"}`, `{}`, and `{"text": 123}` each return 422.
- [ ] Add a `field_validator("text")` to `PasteCreate` that raises when `not v.strip()`. **Don't change `v` itself**; return it unchanged, because whitespace inside a paste is content.
- [ ] Commit.

### Task 2.4: Size limit
- [ ] Tests:
  - Text of exactly `MAX_PASTE_BYTES` bytes is accepted (201).
  - One byte more returns 413.
  - **Multi-byte case:** text that's under 1 MB *in characters* but over 1 MB *in UTF-8 bytes* (for example, 400,000 × `"é"`, which is 800,000 bytes, plus padding to go just over) returns 413. This test proves you measure bytes, not characters.
- [ ] In the route, before inserting: `if len(body.text.encode("utf-8")) > settings.max_paste_bytes: raise HTTPException(413, "Paste exceeds 1 MB")`. This goes in the route, not the validator, because a validator can only produce 422.
- [ ] Commit.

---

## Phase 3: Reading pastes

### Task 3.1: `GET /api/v1/pastes/{id}`
- [ ] Tests:
  - Create, then get by id: 200 with the same `id`, `text` and `created_at`.
  - A valid but unknown UUID returns 404.
  - **Malformed ids** (`not-a-uuid`, `123`, `c9bf9e57-1685`) return **404, not 422**.
- [ ] Route: take `paste_id: str` (deliberately not `UUID`, so FastAPI doesn't return its own 422). Parse it with `uuid.UUID(paste_id)`; on `ValueError`, return 404. Use `session.get(Paste, id)`, and return 404 if it's `None`.
- [ ] Put the parse-and-fetch steps in a small helper (`get_paste_or_404`), because Task 3.2 needs the same thing.
- [ ] Commit.

### Task 3.2: `GET /api/v1/pastes/{id}/raw`
- [ ] Tests:
  - Returns 200 with `content-type: text/plain; charset=utf-8`, and a body exactly equal to the original text (including the `\r\n` and emoji from Task 2.2).
  - An unknown id and a malformed id both return 404.
- [ ] Route: `get_paste_or_404`, then `PlainTextResponse(paste.text)`.
- [ ] **Security test:** pasting `<script>alert(1)</script>` and reading `/raw` gives back `text/plain`, never `text/html`.
- [ ] Commit.

### Task 3.3: Clean up the API docs
- [ ] Set `response_model` and `responses={404: ..., 413: ..., 422: ...}` on each route so `/docs` shows the real behaviour.
- [ ] **Check:** open `/docs` and try all three routes by hand.
- [ ] Commit.

---

## Phase 4: Backend container

### Task 4.1: Dockerfile
- [ ] `backend/Dockerfile`: start `FROM python:3.12-slim`, copy `requirements.txt` first and `pip install --no-cache-dir`, then copy the code.
- [ ] Startup command: `sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"`.
- [ ] Run as a non-root user (`useradd`, then `USER app`).
- [ ] Add a `.dockerignore` covering `.venv`, `__pycache__`, `tests/.pytest_cache`.

### Task 4.2: Add the backend service to Compose
- [ ] `backend` service: `build: ./backend`, `env_file: .env`, and an `environment:` block that builds `DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`.
- [ ] `depends_on: { db: { condition: service_healthy } }`.
- [ ] No `ports:` in the main file. In `docker-compose.dev.yml`, publish `127.0.0.1:8000:8000`.
- [ ] **Check:** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build db backend`. The logs show the migration running, then Uvicorn starting. Then `curl -X POST localhost:8000/api/v1/pastes -H "content-type: application/json" -d "{\"text\":\"hi\"}"` returns 201.
- [ ] **Check:** `docker compose run --rm -e TEST_DATABASE_URL=postgresql+asyncpg://snippet:<password>@db:5432/snippet_test backend pytest` passes.
- [ ] Commit.

---

## Phase 5: Frontend skeleton

### Task 5.1: Scaffold
- [ ] `npm create vite@latest frontend -- --template react`, then `cd frontend && npm install`.
- [ ] `npm install react-router-dom`
- [ ] `npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom`
- [ ] `vite.config.js`:
  - `test: { environment: "jsdom", setupFiles: "./src/setupTests.js" }`
  - `server: { proxy: { "/api": "http://localhost:8000" } }`, so dev builds call the backend with the same paths as production.
- [ ] Delete the Vite demo files (the logo, the counter, `App.css`).
- [ ] Add a `"test": "vitest"` script.
- [ ] Commit.

### Task 5.2: Routing
- [ ] `src/main.jsx`: `createBrowserRouter` with `/` → `CreatePage`, `/view/:id` → `ViewPage`, and `*` → a simple "Page not found" with a link home.
- [ ] Create placeholder `CreatePage` and `ViewPage` components.
- [ ] **Check:** `npm run dev`. Visiting `/`, `/view/abc` and `/nope` each shows the right placeholder.
- [ ] Commit.

### Task 5.3: API client (`src/api.js`)
- [ ] **Tests first** (`api.test.js`, mocking `fetch` with `vi.fn`):
  - `createPaste("x")` POSTs JSON to `/api/v1/pastes` and resolves with the parsed body on a 201.
  - A 413 throws an error with `kind: "too_large"`. A 429 throws `kind: "rate_limited"`, a 422 throws `kind: "invalid"`, a network failure (fetch rejects) throws `kind: "network"`, and anything else throws `kind: "server"`.
  - `getPaste(id)` resolves on a 200, and throws `kind: "not_found"` on a 404.
- [ ] Implement it. **Map errors on the status code, never on the response body.** Nginx returns 413 and 429 as HTML pages, not JSON, so calling `response.json()` on them would crash.
- [ ] Commit.

---

## Phase 6: Create view (`/`)

### Task 6.1: Text area and counters
- [ ] **Tests first** (`CreatePage.test.jsx`):
  - The text area has focus after the page renders.
  - Typing `hello world` shows "11 characters · 2 words".
  - **Save & Share** is disabled when the text is empty or only whitespace.
  - Text over 1 MB (in UTF-8 bytes) shows "Too large (max 1 MB)" and disables the button.
- [ ] Implement it:
  - A `<textarea autoFocus spellCheck={false}>` with a monospace font, filling the page.
  - Words: `text.trim().split(/\s+/).filter(Boolean).length`
  - Bytes: `new TextEncoder().encode(text).length`
  - Give the text area a label (`aria-label="Paste text"`) for screen readers.
- [ ] Commit.

### Task 6.2: Saving
- [ ] **Tests first:**
  - Clicking Save calls `createPaste` with the exact text (not trimmed).
  - While the request is pending, the button shows "Saving…" and is disabled. Double clicks must not create two pastes.
  - On success, a dialog opens showing the `share_url`.
  - For each error kind, the right inline message appears:
    - `too_large`: "Too large (max 1 MB)"
    - `rate_limited`: "Too many pastes, try again in a minute"
    - `network`: "Couldn't reach the server" with a **Retry** button
    - `server`: "Something went wrong" with a **Retry** button
  - The text is **kept** after an error. Never lose what the user pasted.
- [ ] Implement it.
- [ ] Commit.

### Task 6.3: Share dialog
- [ ] **Tests first:**
  - The dialog shows the link in a read-only input, with **Copy link** and **Open** buttons.
  - **Copy link** calls `navigator.clipboard.writeText(share_url)` and shows "Copied!".
  - When the clipboard isn't available, the dialog selects the input's text and shows "Press Ctrl+C to copy".
  - Pressing Escape or **Close** closes the dialog, and focus goes back to the text area.
- [ ] Implement it with a native `<dialog>` element and `showModal()`. That gives you focus trapping and Escape handling for free.
- [ ] **Why the fallback matters:** the clipboard API only works on `https://` or `localhost`. If someone opens the app at `http://192.168.x.x:3000`, `navigator.clipboard` is `undefined`.
- [ ] Commit.

---

## Phase 7: Reader view (`/view/:id`)

### Task 7.1: Loading and showing a paste
- [ ] **Tests first** (`ViewPage.test.jsx`, with a mocked `getPaste`):
  - Shows "Loading…" while the request is in progress.
  - On success, every line of the text appears, in order.
  - Indentation is kept exactly: a line starting with 4 spaces still starts with 4 spaces.
  - `not_found` shows "Snippet not found." and a **New paste** link.
  - A network or server error shows "Couldn't load this snippet" and a **Retry** button.
- [ ] Implement it:
  - `useParams()`, with `getPaste(id)` inside a `useEffect`.
  - The text goes in `<pre>`, one `<span class="line">` per line (`text.split("\n")`), with `white-space: pre-wrap`.
  - **Never use `dangerouslySetInnerHTML`.**
- [ ] Commit.

### Task 7.2: Line numbers
- [ ] **Test:** the line numbers are not part of the text content (the `<pre>`'s `textContent` equals the original paste).
- [ ] Use CSS counters: `.line::before { counter-increment: line; content: counter(line); user-select: none; }`. Content generated by `::before` isn't copied when someone selects the text, and isn't in `textContent`. No extra elements needed.
- [ ] **Check by hand:** select all the text in the browser, copy it, and paste it into an editor. There should be no numbers.
- [ ] Commit.

### Task 7.3: Action buttons
- [ ] **Tests first:**
  - **Copy raw text** calls `navigator.clipboard.writeText(paste.text)` and shows "Copied!". When the clipboard isn't available, it falls back to selecting the `<pre>`.
  - **Open raw** is a link to `/api/v1/pastes/{id}/raw`, opening in a new tab.
  - **New paste** links to `/`.
- [ ] Implement it.
- [ ] **Security test:** a paste of `<img src=x onerror=alert(1)>` shows as literal text, and no `<img>` element exists in the page.
- [ ] Commit.

---

## Phase 8: Nginx and the frontend container

### Task 8.1: `frontend/nginx.conf`
- [ ] Write it:
  ```nginx
  limit_req_zone $binary_remote_addr zone=create:10m rate=10r/m;

  server {
      listen 80;
      root /usr/share/nginx/html;

      # Create: rate limited, 2 MB body cap (backend enforces the 1 MB text limit)
      location = /api/v1/pastes {
          limit_req zone=create burst=5 nodelay;
          limit_req_status 429;
          client_max_body_size 2m;
          proxy_pass http://backend:8000;
      }

      # Read and raw: no rate limit
      location /api/ {
          proxy_pass http://backend:8000;
      }

      # React routes (/view/:id) fall back to index.html
      location / {
          try_files $uri /index.html;
      }
  }
  ```
- [ ] **Why it works:** `location = /api/v1/pastes` is an exact match. The only route at that exact path is `POST`, so only creates are rate limited. Reads go to `/api/v1/pastes/{id}`, which the exact match doesn't cover.
- [ ] **Behind a load balancer or Cloudflare:** add `set_real_ip_from <proxy range>;` and `real_ip_header X-Forwarded-For;`. Otherwise every user shares one IP address and one rate limit. Skip this for local use.

### Task 8.2: `frontend/Dockerfile` (multi-stage)
- [ ] Stage 1: `FROM node:22-alpine AS build`, then `npm ci`, then `npm run build`.
- [ ] Stage 2: `FROM nginx:alpine`. Copy `dist/` to `/usr/share/nginx/html`, and `nginx.conf` to `/etc/nginx/conf.d/default.conf`.
- [ ] Add a `.dockerignore` covering `node_modules`, `dist`.

### Task 8.3: Add the frontend service to Compose
- [ ] `frontend` service: `build: ./frontend`, `ports: ["3000:80"]`, `depends_on: [backend]`.
- [ ] **Check:** `docker compose up --build` (without the dev file). Open `http://localhost:3000`, create a paste, and open its link.
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
- [ ] **Tests:** backend `pytest` and frontend `npm test -- --run` both pass.

---

## Phase 10: Docs

### Task 10.1: README
- [ ] What it is, in one line (already there).
- [ ] **Run it:** copy `.env.example` to `.env`, then `docker compose up --build`, then open `http://localhost:3000`.
- [ ] **Develop:** the dev compose file, `uvicorn --reload`, `npm run dev`.
- [ ] **Test:** the backend pytest command (Phase 4.2), and `npm test` for the frontend.
- [ ] **Configuration:** the table from PROJECT-IDEA.md.
- [ ] **API:** the three routes, with status codes.

### Task 10.2: Update CLAUDE.md
- [ ] Replace its "Current state" section with the real commands (build, test, run a single test: `pytest tests/test_pastes.py::test_name` and `npx vitest run -t "name"`).
- [ ] Add a short architecture note: Nginx sits in front, the rate limit and body cap live in `nginx.conf`, and the backend enforces the 1 MB text limit.
- [ ] Commit, then push.

---

## Things that are easy to get wrong

| Area | Mistake | What to do instead |
|---|---|---|
| Malformed id | Declaring `paste_id: UUID` gives FastAPI's own 422 | Use `str`, parse it yourself, return 404 |
| Size check | `len(text)` counts characters | `len(text.encode("utf-8"))` counts bytes |
| Size check | Putting it in a Pydantic validator | Validators can only give 422. Do it in the route for 413 |
| Whitespace | `.strip()` the text before saving | Only *check* `strip()` for emptiness. Store the text as-is |
| Nginx errors | `response.json()` on 413 or 429 | Those are HTML pages. Map errors by status code |
| Clipboard | Assuming `navigator.clipboard` exists | It's `undefined` on plain HTTP away from localhost. Add a fallback |
| Line numbers | Numbers in the DOM text | CSS `::before` counters, which aren't copied |
| Rate limit | Applying `limit_req` to all of `/api/` | Exact-match `location = /api/v1/pastes`, so only creates are limited |
| Postgres init | Adding `db/init` after the volume exists | Init scripts only run on an empty volume. `down -v` once |
| Async tests | Engine and tests on different event loops | Session-scoped loop in `pytest.ini` |
