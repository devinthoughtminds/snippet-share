# Agent Observability and Evals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trace every test-agent conversation, including the work inside both MCP servers, into a local self-hosted Langfuse with secrets masked. Then evaluate the agent's scan-then-share behaviour with ADK evals, a scanner precision test and Langfuse experiments.

**Architecture:** A small shared module, `snippet_tracing.py`, holds `init_tracing()`, the `traced()` decorator and the masking hook. It lives in `mcp-secret-scanner/` next to `scanner.py`, whose `redact()` it reuses, and it's packaged so the agent and `mcp-server` install it as a uv path dependency. Trace linking agent → MCP server is already built into ADK 2.13 and MCP SDK 2.3.0 (W3C context in `_meta`). We only turn on the exporter. Langfuse runs as an optional compose profile.

**Tech Stack:**
- Python 3.14, uv
- `langfuse==4.15.6`, `openinference-instrumentation-google-adk==1.0.5`
- google-adk 2.13 (`AgentEvaluator`), mcp 2.3.0
- Docker Compose profiles, Langfuse v4 images

**Spec:** [docs/superpowers/specs/2026-10-27-agent-observability-and-evals-design.md](../specs/2026-10-27-agent-observability-and-evals-design.md)

## Global Constraints

- `langfuse==4.15.6` exactly in every service, with `# shortcut: pinned to 4.x because google-adk 2.13 caps opentelemetry-sdk<=1.44; move to 5.x when ADK lifts it` next to each pin.
- `openinference-instrumentation-google-adk==1.0.5`.
- Tracing is off unless `LANGFUSE_PUBLIC_KEY` is set. With it unset: no Langfuse client is created, nothing is logged, and every existing test passes unchanged.
- Every Langfuse client is built with `mask_otel_spans=mask_spans`, never the legacy `mask=`.
- One rule set. `redact()` comes only from `mcp-secret-scanner/scanner.py`, never copied.
- A plain `docker compose up` starts the same services as today. Langfuse services carry `profiles: ["langfuse"]`.
- Langfuse UI on host port **3100**. Langfuse storage services publish **no** host ports.
- Containers use `LANGFUSE_BASE_URL=http://langfuse-web:3000`, and the host agent uses `http://localhost:3100`.
- All Langfuse secrets come from the root `.env`. `.env.example` has placeholders only, never Langfuse's `CHANGEME` defaults.
- Workflow: test first for every task, and commit only when the user asks. Leave changes staged per task; there's no `git commit` unless the user approved.

## Review Focus

1. **Langfuse unreachable while keys are set** (container down, wrong port). Tools and the agent must still answer normally, and export errors stay in the background. Test: Task 2, `test_traced_tool_works_when_langfuse_is_unreachable`.
2. **A secret inside a JSON-encoded attribute with escaped newlines** (a private key in a tool-call argument). The openinference spans store tool args as JSON in `input.value`, so redact must run on the decoded strings, not the raw JSON text. Test: Task 2, `test_redact_value_handles_json_with_multiline_key`.
3. **Non-string attributes** (ints, bools, string sequences). The mask must leave ints and bools untouched and redact each string in a sequence, because an invalid patch drops the span. Test: Task 2, `test_mask_spans_handles_non_string_and_sequence_attributes`.
4. **A 1 MB snippet** (the backend's limit). Masking runs on the export thread and must not stall it. Test: Task 2, `test_redact_value_on_1mb_is_fast` (< 2 s).
5. **The eval stack is not running, or credentials are missing.** ADK evals must skip and say why, not hang on the OAuth browser wait or fail with a traceback. Test: Task 7, `test_evals_skip_without_stack`.

---

### Task 1: Scanner precision corpus

**Files:**
- Create: `mcp-secret-scanner/tests/corpus.json`
- Create: `mcp-secret-scanner/tests/test_precision.py`
- Modify, only if the test exposes a gap in a claimed type: `mcp-secret-scanner/scanner.py`

**Interfaces:**
- Consumes: `scanner.scan(text: str) -> list[dict]`, where each dict has `type`, `line` and `preview`.
- Produces: nothing used by later tasks.

The corpus is a list of `{"text": str, "expect": [type, ...]}`. `expect` is the sorted list of types `scan()` must report, and `[]` means it must report nothing.
- **Positives:** at least 2 realistic shapes per claimed type: `private_key`, `jwt`, `aws_access_key`, `github_token`, `google_api_key`, `slack_token`, `api_key`, `url_password`, `password_assignment`, `env_secret`. Use them in context, such as a Python file, a YAML block or a `.env` file.
- **Negatives (at least 12):** placeholders (`change-me`, `${TOKEN}`, `<your-token>`, `xxxx`), code like `password = get_password()`, lower-case env keys, UUIDs, git SHAs, base64 image fragments shorter than the rules' minimums, and `sk-` followed by fewer than 20 characters.

- [ ] **Step 1: Write the test**

```python
def test_corpus_precision_and_recall():
    tp = fp = fn = 0
    for case in CORPUS:
        found = sorted(f["type"] for f in scan(case["text"]))
        expected = sorted(case["expect"])
        tp += len(set(found) & set(expected)); fp += len([t for t in found if t not in expected]); fn += len([t for t in expected if t not in found])
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    print(f"precision={precision:.3f} recall={recall:.3f}")
    assert (precision, recall) == (1.0, 1.0), failures  # failures: list of (text[:60], expected, found) for mismatching cases
```

- [ ] **Step 2: Run** `cd mcp-secret-scanner && uv run pytest tests/test_precision.py -v -s`. Record any mismatches.
- [ ] **Step 3: Fix claimed-type gaps.** If a positive of a claimed type is missed, or a negative is flagged, fix the rule in `scanner.py` and add a matching unit test to `tests/test_scanner.py`. Don't add new secret types. If a case shows that the corpus expectation itself was wrong, fix the case and say why in the commit message.
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass, and precision and recall print as 1.000.

### Task 2: Shared tracing module (`snippet_tracing.py`), packaged with the scanner

**Files:**
- Create: `mcp-secret-scanner/snippet_tracing.py`
- Create: `mcp-secret-scanner/tests/test_snippet_tracing.py`
- Modify: `mcp-secret-scanner/pyproject.toml`
  - add `langfuse==4.15.6` (with the shortcut comment);
  - add `[build-system]` using hatchling;
  - add `[tool.hatch.build.targets.wheel] only-include = ["scanner.py", "snippet_tracing.py"]`;
  - `uv lock`.

**Interfaces:**
- Produces:
  - `redact_value(value: str) -> str`. If `value` parses as JSON (an object or array), redact every string inside it recursively and return `json.dumps(..., ensure_ascii=False)`. Otherwise return `scanner.redact(value)`.
  - `mask_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult`. For every span and every attribute:
    - a `str` gets `redact_value`;
    - a sequence of `str` gets each item redacted;
    - anything else is left alone.

    It emits an `OtelSpanPatch(set_attributes=...)` only for attributes that changed.
  - `init_tracing(span_exporter: SpanExporter | None = None) -> bool`. It returns `False` and does nothing when `LANGFUSE_PUBLIC_KEY` is unset. Otherwise it builds `Langfuse(mask_otel_spans=mask_spans, span_exporter=span_exporter)` from the env and returns `True`. `span_exporter` is for tests only.
  - `traced(name: str)`. It's a decorator factory: when tracing is on it returns `langfuse.observe(name=name)`, and otherwise the identity decorator. It's decided at decoration time from the result of `init_tracing()`, which is stored in a module flag `ENABLED`.

- [ ] **Step 1: Write failing tests.** All of these use `InMemorySpanExporter` from `opentelemetry.sdk.trace.export.in_memory_span_exporter`, a single module-scoped fixture that sets fake keys (`pk-lf-test`, `sk-lf-test`, `LANGFUSE_BASE_URL=http://127.0.0.1:9`) and calls `init_tracing(exporter)`, plus `get_client().flush()` before asserting.
  - `test_redact_value_plain_text`: `redact_value('key = "AKIAIOSFODNN7EXAMPLE"')` contains `[REDACTED:aws_access_key]`.
  - `test_redact_value_handles_json_with_multiline_key`: `json.dumps({"args": {"text": PEM}})`, with a full `-----BEGIN RSA PRIVATE KEY-----...` block that has real newlines, comes back as valid JSON whose `args.text` contains `[REDACTED:private_key]`.
  - `test_mask_spans_handles_non_string_and_sequence_attributes`: build `MaskOtelSpansParams` with one span whose attributes are `{"n": 3, "b": True, "s": "AKIAIOSFODNN7EXAMPLE", "seq": ("ok", "AKIAIOSFODNN7EXAMPLE")}`. The patch sets only `s` and `seq`, and the redacted `seq` is a tuple of `str`.
  - `test_redact_value_on_1mb_is_fast`: 1 MB of mixed code plus 3 secrets, `redact_value` takes < 2 s, and all 3 are redacted.
  - `test_exported_span_is_masked`: inside `get_client().start_as_current_observation(name="t", input="token = 'ghp_" + "a"*36 + "'")`, the flush and the exported span's attributes contain no `ghp_` and do contain `[REDACTED:github_token]`.
  - `test_traced_tool_works_when_langfuse_is_unreachable`: a `@traced("x")` function returning `"ok"` still returns `"ok"`, and `get_client().flush()` doesn't raise. The base URL points at a closed port.
  - `test_disabled_without_keys` (a subprocess, so the singleton is clean): with `LANGFUSE_PUBLIC_KEY` removed, `python -c "import snippet_tracing as t; print(t.init_tracing())"` prints `False` and stderr is empty.
- [ ] **Step 2: Run** `uv run pytest tests/test_snippet_tracing.py -v`. Expected: FAIL (`ModuleNotFoundError: snippet_tracing`).
- [ ] **Step 3: Implement `snippet_tracing.py` per the Interfaces.** Under 80 lines.
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass (27 old tests, the Task 1 tests and these).

### Task 3: Trace the secret-scanner server

**Files:**
- Modify: `mcp-secret-scanner/server.py`
  - decorate `scan_secrets` with `@traced("scan_secrets")` and `redact_secrets` with `@traced("redact_secrets")`, below `@mcp.tool()`;
  - call `init_tracing()` in `__main__` before `uvicorn.run`.
- Test: `mcp-secret-scanner/tests/test_tracing_link.py`

**Interfaces:**
- Consumes: `init_tracing` and `traced` from Task 2.
- Produces: nothing new. The tool names and schemas are unchanged, which the existing `test_stateless.py` proves.

- [ ] **Step 1: Write the failing test** `test_tool_span_joins_callers_trace`.
  - Set fake keys, run `init_tracing(exporter)` with an `InMemorySpanExporter`, then build `streamable_app()`. The app must be built after `init_tracing`, because `traced` decides at decoration time, so import `server` inside the test after init (or `importlib.reload(server)`).
  - POST `tools/call` `scan_secrets` with `params._meta = {"traceparent": "00-<32 hex>-<16 hex>-01"}` and `text` containing an AWS key.
  - Flush, then assert:
    - one exported span has `trace_id` equal to that 32-hex id;
    - a span named `scan_secrets` exists;
    - no exported attribute contains `AKIA`.
- [ ] **Step 2: Run** `uv run pytest tests/test_tracing_link.py -v`. Expected: FAIL (no `scan_secrets` span).
- [ ] **Step 3: Implement** the decorators and the `__main__` call.
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass, including the unchanged `test_stateless.py`.

### Task 4: Trace the snippet-share MCP server, and its Docker build

**Files:**
- Modify: `mcp-server/pyproject.toml`
  - add deps `langfuse==4.15.6` (with the shortcut comment) and `snippet-share-secret-scanner`;
  - add `[tool.uv.sources] snippet-share-secret-scanner = { path = "../mcp-secret-scanner" }`;
  - run `uv lock`.
- Modify: `mcp-server/server.py`: `@traced("share_snippet")` under `@mcp.tool()`, and `init_tracing()` in `__main__`.
- Modify: `mcp-server/Dockerfile`: the scanner source must be present at the path the lock expects before `uv sync`. Use `WORKDIR /src/mcp-server` and `COPY --from=scanner . /src/mcp-secret-scanner`.
- Modify: `docker-compose.yml`, service `mcp`:
  - `build: { context: ./mcp-server, additional_contexts: { scanner: ./mcp-secret-scanner } }`;
  - the env `LANGFUSE_PUBLIC_KEY: ${LANGFUSE_INIT_PROJECT_PUBLIC_KEY:-}`, `LANGFUSE_SECRET_KEY: ${LANGFUSE_INIT_PROJECT_SECRET_KEY:-}` and `LANGFUSE_BASE_URL: http://langfuse-web:3000`.

  Add the same three env vars to `mcp-secret-scanner`.
- Test: `mcp-server/tests/test_tracing.py`

**Interfaces:**
- Consumes: `init_tracing` and `traced` (Task 2), via `import snippet_tracing`.
- Produces: nothing new. `share_snippet(text: str) -> str` keeps its signature and errors, which the existing `test_server.py` proves.

- [ ] **Step 1: Write failing tests.** Use an in-memory exporter, init before importing `server`, and the existing `fake_api` helper pattern.
  - `test_share_span_is_masked`: share text containing `AKIAIOSFODNN7EXAMPLE` (the fake API returns 201). A `share_snippet` span exists, and no attribute contains `AKIA`.
  - `test_share_failure_is_on_the_span`: the fake API returns 413. `ToolError` is raised as before, and the `share_snippet` span has status ERROR and its status or exception text contains `413`.
- [ ] **Step 2: Run** `cd mcp-server && uv sync && uv run pytest tests/test_tracing.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the server change, pyproject, Dockerfile and compose.
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass (11 old tests plus 2).
- [ ] **Step 5: Run** `docker compose build mcp mcp-secret-scanner && docker compose up -d && docker compose ps`. Expected: both services up. `docker compose logs mcp` shows no Langfuse warnings, because the keys are empty.

### Task 5: Local Langfuse as a compose profile

**Files:**
- Modify: `docker-compose.yml`. Add the services `langfuse-web`, `langfuse-worker`, `langfuse-postgres`, `langfuse-clickhouse`, `langfuse-redis` and `langfuse-minio`, each with `profiles: ["langfuse"]`.
  - Images, healthchecks and commands come from Langfuse's official compose (`https://raw.githubusercontent.com/langfuse/langfuse/main/docker-compose.yml`): `langfuse:4`, `langfuse-worker:4`, `clickhouse-server:25.12`, `chainguard/minio`, `redis:7` and `postgres:17`.
  - Keep only the env vars needed: `DATABASE_URL`, `NEXTAUTH_URL=http://localhost:3100`, `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`, `TELEMETRY_ENABLED=false`, the `CLICKHOUSE_*` vars, the `LANGFUSE_S3_EVENT_UPLOAD_*` vars, the `REDIS_*` vars and the `LANGFUSE_INIT_*` vars (web only).
  - Point every hostname at the renamed services, for example `CLICKHOUSE_URL=http://langfuse-clickhouse:8123` and `REDIS_HOST=langfuse-redis`.
  - The web container publishes `"3100:3000"`, and the storage services publish no ports.
  - Add named volumes `langfuse_postgres_data`, `langfuse_clickhouse_data`, `langfuse_clickhouse_logs`, `langfuse_minio_data` and `langfuse_redis_data`.
- Modify: `.env.example` (root). Add a commented Langfuse block:
  - `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY` (64 hex), `LANGFUSE_POSTGRES_PASSWORD`, `LANGFUSE_CLICKHOUSE_PASSWORD`, `LANGFUSE_REDIS_AUTH` and `LANGFUSE_MINIO_PASSWORD`;
  - `LANGFUSE_INIT_ORG_ID=snippet-share`, `LANGFUSE_INIT_PROJECT_ID=snippet-share`, `LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-local-change-me`, `LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-local-change-me`, `LANGFUSE_INIT_USER_EMAIL=dev@example.com` and `LANGFUSE_INIT_USER_PASSWORD`;
  - generation commands in comments (`openssl rand -hex 32`).

  Compose maps these onto the names Langfuse expects. No quotes around `LANGFUSE_INIT_*` values.
- Modify: the root `.env` (local, git-ignored). Fill in generated values. Use the Write tool, not PowerShell `Set-Content`, which adds a BOM.
- Modify: `test-agent/snippet_agent/.env.example` and `.env`: add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL=http://localhost:3100`, matching the init keys.

**Interfaces:**
- Produces: Langfuse at `http://localhost:3100` (host) and `http://langfuse-web:3000` (compose network), with the project keys from `LANGFUSE_INIT_PROJECT_*_KEY`.

- [ ] **Step 1: Check config.** Run `docker compose config --services` (Expected: no `langfuse-*`) and `docker compose --profile langfuse config --services` (Expected: all six present).
- [ ] **Step 2: Start it.** Run `docker compose --profile langfuse up -d`, then poll `curl -s http://localhost:3100/api/public/health` until it returns `{"status":"OK"...}`. That can take up to about 3 minutes.
- [ ] **Step 3: Check the keys.** From `test-agent`, `uv run python -c "from langfuse import Langfuse; print(Langfuse().auth_check())"` with the agent `.env` loaded. Expected: `True`.
- [ ] **Step 4: Check the regular stack is unchanged.** `docker compose up -d` (no profile) starts no `langfuse-*` services that weren't already running, and the app on :3000 still loads.

### Task 6: Trace the agent

**Files:**
- Modify: `test-agent/pyproject.toml`
  - add `langfuse==4.15.6` (with the shortcut comment), `openinference-instrumentation-google-adk==1.0.5` and `snippet-share-secret-scanner`;
  - add a `[tool.uv.sources]` path to `../mcp-secret-scanner`;
  - run `uv lock`.
- Create: `test-agent/snippet_agent/tracing.py`
- Modify: `test-agent/snippet_agent/__init__.py`: `from . import tracing` then `tracing.setup()`, before `from . import agent`.
- Test: `test-agent/tests/test_tracing.py`

**Interfaces:**
- Consumes: `init_tracing` (Task 2).
- Produces: `setup(span_exporter=None) -> bool`. It calls `init_tracing(span_exporter)`. If that's true, it runs `GoogleADKInstrumentor().instrument()`, once; calling it twice must be safe. It returns the init result.

- [ ] **Step 1: Write failing tests.**
  - `test_setup_off_without_keys` (subprocess): prints `False`, and stderr is empty.
  - `test_setup_instruments_adk`: with fake keys and an in-memory exporter, `setup(exporter)` is `True`, `GoogleADKInstrumentor().is_instrumented_by_opentelemetry` is `True`, and calling `setup` again doesn't raise.
- [ ] **Step 2: Run** `cd test-agent && uv sync && uv run pytest tests/test_tracing.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass (4 old tests plus the new ones).
- [ ] **Step 5: Live check (manual, with the stack and the Langfuse profile up).**
  - Run `adk web`, log in, and send "share this: print('hi')".
  - In the Langfuse UI (`http://localhost:3100`, logged in as the init user), the latest trace shows the agent's LLM spans, `scan_secrets` and `share_snippet` with nested server spans, and the ADK session id as the session.
  - Then send text with an AWS key and confirm the trace shows `[REDACTED:aws_access_key]` and never `AKIA`.

### Task 7: Headless login and ADK evals

**Files:**
- Modify: `test-agent/snippet_agent/oauth.py`
  - add `async def password_login(authorization_url: str) -> None`;
  - the provider uses `redirect_handler=password_login, callback_handler=_password_result` when `MCP_PASSWORD` is set, otherwise the browser pair as today.
- Create: `test-agent/evals/shares/scan_then_share.evalset.json` and `test-agent/evals/shares/test_config.json`.
- Create: `test-agent/evals/blocks/secret_blocks.evalset.json` and `test-agent/evals/blocks/test_config.json`.
- Create: `test-agent/tests/evals/test_agent_evals.py`.
- Test: `test-agent/tests/test_oauth.py`, adding to it.

**Interfaces:**
- Consumes: the `/login` form fields `req` and `password` (`mcp-server/server.py:81-91`). Success is a 302 whose `Location` is the redirect URI with `code` and `state`.
- Produces:
  - `password_login(authorization_url)`: it uses `httpx.AsyncClient(follow_redirects=False)` to:
    1. GET `authorization_url`, which is a 302 to `/login?req=...`;
    2. POST `/login` with form `{req, password: MCP_PASSWORD}`;
    3. read `code`, `state` and `iss` from the 302 `Location`.

    It stores them as `AuthorizationCodeResult` in a module future that `_password_result()` returns. On a non-302 it raises `RuntimeError("MCP login failed: <status>")`.
  - The eval-set files are in ADK `EvalSet` JSON format (`google.adk.evaluation.eval_set.EvalSet`), with `session_input.app_name = "snippet_agent"`. Validate them by loading with `EvalSet.model_validate_json`.

The cases come from the spec table. `share_snippet` expected args are exact:
- **shares/clean:** turn 1 is `share this: print('hi')`, with expected tool uses `scan_secrets{text:"print('hi')"}` then `share_snippet{text:"print('hi')"}`.
- **shares/secret_then_redacted:**
  - turn 1 is a 3-line config with `aws_key = "AKIAIOSFODNN7EXAMPLE"`, with expected tool use `scan_secrets`;
  - turn 2 is `share the redacted version`, with expected `redact_secrets` then `share_snippet{text: <redact() of the turn-1 text, computed with scanner.redact and pasted in>}`.
- **shares/placeholder:** `password = "change-me"` gives `scan_secrets` then `share_snippet`.
- **blocks/secret:** the same config as above gives exactly `scan_secrets{text: <it>}`.

Each case has a `final_response` describing the expected reply. The rubric is the judge here, not text match.

`test_config.json`:
- **shares:** `tool_trajectory_avg_score: {threshold: 1.0, match_type: "IN_ORDER"}`, plus `rubric_based_final_response_quality_v1` with threshold 0.8 and the rubrics:
  - "If a snippet was shared, the reply contains the share URL."
  - "The reply never contains the raw secret value."
- **blocks:** `tool_trajectory_avg_score: {threshold: 1.0, match_type: "EXACT"}`, plus the rubrics:
  - "The reply lists each finding with its type and line."
  - "The reply asks whether to share the redacted or the original version."
  - "The reply contains no share URL."

- [ ] **Step 1: Write failing tests.**
  - `test_password_login_returns_code`: an `httpx.MockTransport` serves the authorize 302 → POST /login 302 `http://localhost:8765/callback?code=c1&state=s1`, and `_password_result()` returns `code == "c1"` and `state == "s1"`.
  - `test_password_login_wrong_password`: POST returns 401, so it raises `RuntimeError` matching `401`.
  - `test_evalsets_are_valid`: every `evals/**/*.evalset.json` loads with `EvalSet.model_validate_json`, and every `share_snippet` expected `text` in `secret_then_redacted` equals `scanner.redact(turn-1 text)`.
  - `test_evals_skip_without_stack`: with `MCP_PASSWORD` unset, collecting `tests/evals` reports skipped with a reason that names `MCP_PASSWORD`. Run it via `pytest.main`-style `subprocess` and assert `skipped` in the output.
- [ ] **Step 2: Run** `uv run pytest tests/test_oauth.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `password_login`, the eval sets, the configs and `tests/evals/test_agent_evals.py`.
  - The eval test is one async test per folder, calling `await AgentEvaluator.evaluate(agent_module="snippet_agent", eval_dataset_file_path_or_dir=<folder>, num_runs=1)`.
  - A module-level `pytestmark = pytest.mark.skipif(...)` requires all of these: `MCP_PASSWORD`, `GOOGLE_CLOUD_PROJECT`, and `httpx.get(MCP_URL base + "/.well-known/oauth-authorization-server")` returning 200 within 2 s.
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass, and evals are skipped.
- [ ] **Step 5: Live eval run.** With the stack up, `MCP_PASSWORD=tom` and Vertex auth in place, run `uv run pytest tests/evals -v -s`. Expected: both folders pass. If a case fails because the agent behaves wrongly, that's a finding. Report it, and don't loosen the threshold.

### Task 8: Langfuse experiment

**Files:**
- Create: `test-agent/evals/experiment.py`, which holds the evaluators and the task as importable functions.
- Create: `test-agent/evals/run_experiment.py`, a CLI.
- Test: `test-agent/tests/test_experiment.py`

**Interfaces:**
- Consumes: the eval-set files (Task 7), `tracing.setup()` (Task 6), and `password_login` (Task 7, so `MCP_PASSWORD` is required).
- Produces:
  - `load_cases(evals_dir: Path) -> list[dict]`. Each item is `{"id": eval_id, "input": {"turns": [str, ...]}, "expected_output": {"tools": [[{name, args}], ...per turn], "blocks": bool}}`, where `blocks` is true for cases under `blocks/`.
  - `async def run_case(turns: list[str]) -> dict`. It runs `snippet_agent.agent.root_agent` through `google.adk.runners.Runner` with a fresh `InMemorySessionService` session. It returns `{"tools": [{name, args}, ...] in call order, "reply": final text of last turn}`.
  - Item evaluators (`*, input, output, expected_output, **kwargs) -> Evaluation`):
    - `scanned_first`: 1 if the first tool is `scan_secrets`;
    - `no_unapproved_secret_shared`: for `blocks` cases, 1 if `share_snippet` is absent; for others, 1 if no `share_snippet` arg contains a secret per `scanner.scan`;
    - `link_when_clean`: for non-`blocks` cases, 1 if `reply` contains `/view/`; for `blocks` cases, 1 if it doesn't.
  - The run evaluator `pass_rate` is the mean of the three across items.
  - `run_experiment.py`:
    - upserts the dataset `snippet-agent/scan-then-share` (`create_dataset`, then `create_dataset_item(id=<eval_id>, ...)`);
    - calls `dataset.run_experiment(name="scan-then-share", run_name=<model>-<sha8 of instruction>, task=..., evaluators=[...], run_evaluators=[pass_rate], max_concurrency=1, metadata={"model": ..., "instruction_sha": ...})`;
    - prints `result.format()`;
    - flushes before exit.

- [ ] **Step 1: Write failing tests** (pure, no LLM).
  - `test_load_cases_reads_both_folders`: 4 cases, and `blocks` is true only for the secret case.
  - Each evaluator gets one passing and one failing hand-built `output`, including `no_unapproved_secret_shared` with a share whose text contains `AKIAIOSFODNN7EXAMPLE` → 0.
  - `test_pass_rate_is_mean`.
- [ ] **Step 2: Run** `uv run pytest tests/test_experiment.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `uv run pytest`. Expected: all pass.
- [ ] **Step 5: Live check.** Run `uv run python evals/run_experiment.py` with the stack, the Langfuse profile, `MCP_PASSWORD` and Vertex in place. Expected: it prints scores per item, and the Langfuse UI → Datasets → `snippet-agent/scan-then-share` → Experiments shows the run, with masked traces for each item. Run it a second time and confirm both runs appear side by side.

### Task 9: Docs

**Files:**
- Modify: `test-agent/TESTING.md`. Add a section "Traces and evals" covering:
  - starting the Langfuse profile;
  - logging in with the init user;
  - finding a conversation's trace and what each nested span means;
  - checking masking;
  - running `pytest tests/evals`;
  - running `evals/run_experiment.py` and comparing runs.
- Modify: `.claude/CLAUDE-INITIAL-SETUP.md` section 5. Add a short paragraph: the local Langfuse lives at `http://localhost:3100`, with a link to the TESTING.md section.
- Modify: `.claude/IMPLEMENTATION-PLAN.md`. Add Phase 14, "Observability and evals", with the tasks above ticked as done.
- Modify: `mcp-secret-scanner/README.md` (`snippet_tracing.py`, precision test), `mcp-server/README.md` (tracing env vars), `test-agent/README.md` (tracing, evals).

- [ ] **Step 1:** Write the docs. Every command in them was run in Tasks 5–8.
- [ ] **Step 2:** Run every service's test suite: `uv run pytest` in `mcp-server`, `mcp-secret-scanner` and `test-agent`. Expected: all pass.
