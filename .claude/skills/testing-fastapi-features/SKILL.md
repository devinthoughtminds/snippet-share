---
name: testing-fastapi-features
description: Use when adding or changing any module, route, service, schema or feature in the FastAPI backend (backend/), before writing its tests or its code.
---

# Testing FastAPI features

## Overview

Every backend module or feature gets **two test files**: unit tests and integration tests. Integration tests prove the feature works end to end against Postgres. Unit tests prove the logic inside it (validation, parsing, branching, error mapping) in milliseconds, with no database.

**Both files, every feature. "Only integration tests" is not done.**

**REQUIRED SUB-SKILL:** superpowers:test-driven-development. Write the failing tests first, in both files.

## The two sets

| | Unit | Integration |
|---|---|---|
| File | `backend/tests/unit/test_<feature>.py` | `backend/tests/integration/test_<feature>.py` |
| Calls | functions, schemas, services, helpers directly | the API over HTTP (`client` fixture) |
| Database | **none**: no `client`, `engine` or `session_maker` fixture | real `snippet_test` Postgres |
| Fakes | a fake session or stub for anything that would touch I/O | none: real app, real DB |
| Covers | each validation rule, each branch, each error the code raises | status codes, response bodies, data stored, 404s, the feature working end to end |
| Run | `uv run pytest tests/unit` (no Docker) | `uv run pytest tests/integration` |

## Layout (one-time setup)

The DB fixtures in `tests/conftest.py` refuse to run without a `_test` database and truncate tables for every test. Unit tests must not inherit them. If `tests/unit/` doesn't exist yet, do this once, before your feature:

1. Move `tests/conftest.py` to `tests/integration/conftest.py`, unchanged.
2. Move the existing `tests/test_*.py` into `tests/integration/`.
3. Create `tests/unit/` with an empty `conftest.py`.
4. Run `uv run pytest`. The same tests must pass as before the move.
5. Update the test table in `backend/README.md`.

## Example: unit tests for the paste feature

```python
# backend/tests/unit/test_pastes.py: no database, no HTTP
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.paste import get_paste_or_404
from app.schemas.paste import PasteCreate


@pytest.mark.parametrize("text", ["", "   \n\t", "a\x00b"])
def test_paste_create_rejects_blank_or_nul_text(text):
    with pytest.raises(ValidationError):
        PasteCreate(text=text)


def test_paste_create_keeps_whitespace_unchanged():
    assert PasteCreate(text="  a\n").text == "  a\n"


async def test_malformed_id_is_404_before_any_db_call():
    with pytest.raises(HTTPException) as exc:
        await get_paste_or_404("not-a-uuid", session=None)  # never reaches the session
    assert exc.value.status_code == 404
```

The integration file then checks the same rules through `client.post` and `client.get`, plus what only a real database can show, such as stored bytes, timestamps and missing rows.

## What to unit-test when the route is thin

A feature always has logic somewhere. Unit-test, in this order:
1. the Pydantic schema's validators and defaults;
2. route helpers (id parsing, error mapping, size checks), called directly;
3. service functions, with a fake session that records what was added or deleted.

If the logic only exists inline in the route, move it into a helper or a validator so it can be tested. That move is part of the feature.

## Rationalizations

| Excuse | Reality |
|---|---|
| "It's needed today, integration tests are enough" | Unit tests for a feature take minutes, and they catch the edge cases integration tests skip. Both files ship together. |
| "conftest needs Postgres, so nothing can run without it" | Do the one-time layout above. Then unit tests don't load DB fixtures. |
| "Every test touches the DB" | Schemas, helpers and branches don't. Test them directly. |
| "A DB-free test means faking the whole session" | Test the pure parts first. Fake only the one method a service calls. |
| "The integration tests already cover this validation" | Only for the inputs they send. The unit tests list every rule. |

## Red flags: stop and add the missing file

- A feature PR with only `tests/integration/test_<feature>.py`, or only the unit file
- A unit test that takes `client`, `engine` or `session_maker`
- A unit test that needs Docker running
- "I'll add unit tests later"
