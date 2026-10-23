# Project idea: snippet-share

> **Status: idea, not an approved design.** This is the starting point for the Superpowers `brainstorming` step. The main decisions are made (see [Decisions](#decisions)), but [Open questions](#open-questions) still need answers before any plan or code.

## What it is

snippet-share is a public, self-hosted pastebin. Anyone can paste text, get a link to share, and anyone with the link can read the text. There are no accounts. A paste's address is a random UUID, so it can't be guessed, but anyone who has the link can read it.

## Stack

| Layer | Choice |
|---|---|
| Frontend | React single-page app built with Vite, served by Nginx |
| Backend | FastAPI on Uvicorn, Pydantic validation, SQLAlchemy 2 (async) with asyncpg |
| Database | PostgreSQL 16 |
| Migrations | Alembic |
| Runtime | Docker Compose: `db`, `backend`, `frontend` |
| Tests | pytest with httpx (backend); Vitest with React Testing Library (frontend) |

```
Browser ──► frontend (Nginx :3000)
              ├─ /           → React app
              └─ /api/*      → rate limit, size limit → backend:8000
                                                          │
                                                          ▼
                                             db (Postgres :5432, internal only)
```

Nginx serves the app and passes `/api` requests to the backend, so the browser only ever talks to one address. That means no CORS setup is needed. Only port 3000 is open on the host machine. Nginx also enforces the rate limit and size limit, so abusive requests never reach the backend.

## Data model

One table, `pastes`:

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | Primary key, v4, created by the backend |
| `text` | `TEXT` | Not null |
| `created_at` | `TIMESTAMPTZ` | Not null, default `now()` |

There's no `updated_at` column, because v1 has no way to edit a paste. Add it when editing is added.

## API

All routes live under `/api/v1`.

### `POST /api/v1/pastes`: create a paste

Request:

```json
{ "text": "multi-line text or logs..." }
```

| Result | Status | When |
|---|---|---|
| Created | `201` | Returns `id`, `share_url`, and `created_at` |
| Invalid | `422` | `text` is missing, empty, or only whitespace |
| Too large | `413` | The request body is larger than 1 MB |
| Rate limited | `429` | This IP address has sent too many paste requests recently |

```json
{
  "id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "share_url": "http://localhost:3000/view/c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "created_at": "2026-10-23T07:30:00Z"
}
```

`share_url` is `PUBLIC_BASE_URL` + `/view/{id}`. Writing `localhost` into the code would give wrong links once the app is deployed anywhere else.

### `GET /api/v1/pastes/{id}`: read a paste

| Result | Status | When |
|---|---|---|
| Found | `200` | Returns `id`, `text`, and `created_at` |
| Not found | `404` | No paste has this id, **or the id isn't a valid UUID** |

A malformed id returns `404`, not FastAPI's default `422`, so the reader view has only one error case to handle.

### `GET /api/v1/pastes/{id}/raw`: plain text

This returns the text alone as `text/plain; charset=utf-8`, with the same `404` rules as above. It fulfils the README's "read plain text instantly", and it works with `curl`.

## Size limit (1 MB)

- **Nginx:** `client_max_body_size 2m` stops very large requests before they reach the backend. It's above 1 MB because JSON escaping makes the request bigger than the text.
- **Backend:** enforces the real limit: the text's UTF-8 size must be at most `MAX_PASTE_BYTES` (1 MB), otherwise it returns `413`.
- **Create view:** checks the size before uploading, so the user sees the error without waiting for the upload.

1 MB is small enough to display in full, with line numbers, without slowing the browser down. So every paste is shown inline, and there's no separate view for large pastes.

## Abuse protection

The app is open to everyone, so v1 includes:

- **Rate limiting in Nginx** (`limit_req`, per client IP), applied only to `POST /api/v1/pastes`. Proposed limit: 10 per minute with a burst of 5. Reading isn't rate limited. Over the limit, Nginx returns `429`.
- **The real client IP.** If something else sits in front of Nginx (a load balancer, Cloudflare), Nginx has to be configured to trust its `X-Forwarded-For` header. Otherwise every user shares one IP address and one rate limit.
- **The 1 MB size limit** (above).

## Frontend

### Create view (`/`)

- A full-screen text area in a monospace font, focused when the page loads.
- An action bar showing the character count, word count and size, with a **Save & Share** button. The button is disabled when the text is empty, over 1 MB, or saving.
- After saving, a dialog shows the link, a **Copy link** button, and an **Open** link.
- Errors appear inline: too large (shows the limit), rate limited ("Too many pastes, try again in a minute"), and network failure (with a retry option).

### Reader view (`/view/:id`)

- Fetches the paste using the `id` from the URL.
- Shows the text read-only, with indentation kept and line numbers in a left-hand column that copying doesn't pick up.
- Has **Copy raw text**, **Open raw** (`/raw`), and **New paste** buttons.
- If the paste doesn't exist, it says "Snippet not found."
- The paste is always rendered as text, never as HTML (no `dangerouslySetInnerHTML`), so pasted content can't run scripts in a reader's browser.

## Configuration

| Variable | Used by | Default (dev) |
|---|---|---|
| `DATABASE_URL` | backend | `postgresql+asyncpg://snippet:snippet@db:5432/snippet` |
| `PUBLIC_BASE_URL` | backend | `http://localhost:3000` |
| `MAX_PASTE_BYTES` | backend | `1048576` (1 MB) |
| `client_max_body_size` | Nginx | `2m`. This is the whole JSON body, which is bigger than the text because escaping (`\n`, `\"`) adds bytes. The backend enforces the real 1 MB limit on the text. |
| `limit_req` rate | Nginx | `10r/m`, burst `5` |

The Postgres username and password come from a `.env` file, which isn't committed. A `.env.example` file is committed instead, showing which values are needed.

## Docker Compose

`docker compose up --build` starts everything.

- **`db`**: `postgres:16-alpine`, with a named volume `pgdata:/var/lib/postgresql/data` and a `pg_isready` healthcheck. Its port isn't published to the host.
- **`backend`**: built from `backend/Dockerfile`. It waits until `db` is healthy (`depends_on: condition: service_healthy`), runs `alembic upgrade head`, then starts Uvicorn.
- **`frontend`**: a multi-stage build. Vite builds the app, then Nginx serves it, proxies `/api` with the size and rate limits, and publishes `3000:80`.

## Out of scope for v1

These are possible later additions, not part of v1:

- **Expiry:** an `expires_at` column, with expired pastes treated as not found. (See open question 1.)
- **Burn after reading:** a paste is deleted the first time someone reads it. This needs a delete-and-return in one database statement so two readers can't both see it.
- **Syntax highlighting.**
- **Short ids** (7 characters instead of a 36-character UUID). Short ids are easier to guess, so they would need stricter rate limiting on reads.
- **Editing pastes** (this is when `updated_at` comes back).
- **Accounts and deleting pastes.**

## Decisions

| Question | Decision |
|---|---|
| Name | **snippet-share** |
| Size limit | **1 MB** per paste. (50 MB was considered and dropped: it would let one IP address add about 720 GB a day, and would need a separate view for pastes too large to display.) |
| Who can use it | **Everyone.** Public, with no login, so rate limiting is part of v1 |
| Raw endpoint | **Yes**, `/raw` is in v1 |

## Open questions

These came out of the decisions above, and need answers before planning:

1. **Disk usage.** Pastes never expire, so storage only grows. At the proposed rate limit, one IP address could add about 14 GB a day at most. Is that acceptable for v1, or should expiry (for example, a default of 30 days) move into v1?
2. **Rate limit values.** Is 10 pastes per minute per IP address with a burst of 5 right?

## Done when

- `docker compose up --build` from a clean checkout serves the app at `http://localhost:3000`.
- You can create a paste, open its link in a new browser, copy the raw text, and get back exactly what you pasted.
- A 1 MB paste saves and displays with line numbers. A paste just over 1 MB is rejected with `413`.
- Empty text, an unknown id, and a malformed id each give the response listed above.
- Going over the create rate limit returns `429`, and the create view shows the rate-limit message.
- Pastes are still there after `docker compose down && docker compose up` (without `-v`).
- The backend and frontend tests pass.
