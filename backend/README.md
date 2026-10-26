# backend

FastAPI + PostgreSQL. See the [root README](../README.md#run-the-backend-for-development) for how to run it.

## Running the tests

The tests call the API in-process (no server needed) and use a real Postgres database, `snippet_test`. They **drop, recreate and empty** its tables, so `conftest.py` refuses to run unless `TEST_DATABASE_URL` points at a database whose name ends in `_test`.

**1. Start Postgres on `localhost:5432`.** From the repo root:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

`snippet_test` is created automatically by [db/init/01-test-db.sql](../db/init/01-test-db.sql) the first time the database volume is created. If your volume is older than that file, create it once yourself:

```sh
docker compose exec db psql -U snippet -c "CREATE DATABASE snippet_test"
```

**2. Configure.** Copy `.env.example` to `backend/.env`. The password in `TEST_DATABASE_URL` must match `POSTGRES_PASSWORD` in the root `.env`.

**3. Install and run.** Run from `backend/`, on your machine, not inside the container:

```sh
uv sync
uv run pytest                                   # all tests
uv run pytest tests/test_pastes.py              # one file
uv run pytest tests/test_pastes.py::test_get_unknown_id_returns_404   # one test
uv run pytest -k "raw"                          # tests whose name matches
uv run pytest -x -v                             # stop at first failure, list each test
```

| File | Covers |
|---|---|
| `tests/test_smoke.py` | the app starts and serves `/api/docs` |
| `tests/test_foundation.py` | settings, database session, the `Paste` model |
| `tests/test_pastes.py` | create, read and raw routes: validation, 1 MB limit, 404s, plain-text safety |

**Common errors**

- `TEST_DATABASE_URL must point at a *_test database`: `backend/.env` is missing, or the URL doesn't end in `_test`.
- `connection refused`: Postgres isn't running, or isn't published on port 5432 (step 1).
- `database "snippet_test" does not exist`: see the `CREATE DATABASE` command in step 1.
- `password authentication failed`: the passwords in `backend/.env` and the root `.env` don't match.
