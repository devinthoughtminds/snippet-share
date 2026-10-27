# Agent observability and evals: design

Date: 2026-10-27. Status: draft, awaiting approval. The builder check is done, and its questions are answered below.

## Intent

The test agent (`test-agent/`, Google ADK on Vertex AI) calls two MCP servers: `mcp-server` (snippet-share, `share_snippet`, OAuth) and `mcp-secret-scanner` (`scan_secrets`, `redact_secrets`, stateless). Today, when the agent misbehaves, there is no record of what it saw or did. Examples: it shares without scanning first, a tool call fails, or a secret slips through. The only clues are `adk web`'s local trace panel and container logs.

This adds two things:

1. **Observability:** every conversation becomes one trace in a self-hosted Langfuse running in Docker on this machine. The trace shows the prompt, each Gemini call (tokens and cost), each tool call, and what happened *inside* each MCP server, all nested under the agent's trace.
2. **Evaluation:** repeatable checks that the agent follows its core rule, which is to scan before sharing and never share a secret without asking. A precision check covers the scanner itself. Langfuse experiments compare runs across prompt and model changes.

The user chose this combination from the options offered. Scoring live traces automatically was explicitly deferred.

## Goals

- One Langfuse trace per agent turn, grouped by ADK session, with the MCP server work nested inside the matching tool call.
- Tool-level detail inside the servers: the scanner's scan or redact step (finding count and types), and the snippet API call (status code, share URL, or error).
- ADK evals for the scan-then-share rule, run with pytest.
- A scanner precision/recall test on a labelled corpus, run with pytest and no LLM.
- Langfuse experiments that run the same eval cases through the agent, score each run, and appear side by side under Experiments.

## Non-goals

- Scoring live traces automatically, with LLM-as-judge or rules on production traffic. This comes later.
- Langfuse Cloud, dashboards, alerts, Langfuse prompt management, Enterprise (licence-key) features.
- Production-grade Langfuse hosting: high availability, backups, Kubernetes. This instance is for local development.
- Tracing the FastAPI backend, frontend or nginx. The `share_snippet` span records the backend's response, and that is enough.
- CI gates. Evals run on demand for now.

## Anti-goals (a failure even if everything "works")

- **A secret lands in the trace store.** Snippet text is the whole point of the scanner, so every trace payload is masked before it leaves the process. The masking reuses the scanner's own `redact()`. This holds even though Langfuse is local, so pointing at Langfuse Cloud later is only a URL change.
- **Langfuse makes the normal stack heavier.** A plain `docker compose up` starts exactly what it starts today.
- **Tracing becomes required.** With no `LANGFUSE_*` keys, all three services and every existing test behave exactly as today, with no errors and no warnings that need action.
- **Evals need a human.** The OAuth login opens a browser today, and an eval run must complete it on its own.

## Design

### Tracing

- **Langfuse server (self-hosted, v4, open source):** its six services come from Langfuse's official `docker-compose.yml`, added to ours under the compose **profile `langfuse`**:
  - `langfuse-web` (`docker.langfuse.com/langfuse/langfuse:4`) and `langfuse-worker` (`langfuse/langfuse-worker:4`);
  - its own `langfuse-postgres`, `clickhouse`, `redis` and `minio`.

  Start it with `docker compose --profile langfuse up -d`; a plain `up` doesn't start it.
  - **Ports:** the UI is at **`http://localhost:3100`**, because nginx already holds 3000. Langfuse's storage services publish no host ports, because the app database already holds 5432. MinIO's S3 port stays internal unless media upload needs it.
  - **Headless initialization** (`LANGFUSE_INIT_*`) creates the org, the project `snippet-share`, a user and an API key pair from the root `.env` on first start, so there's no manual sign-up.
  - All secrets (`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` and storage passwords) come from `.env` with placeholders in `.env.example`, never the defaults from Langfuse's file.
  - Data persists in named volumes.
  - Every feature used here is in the MIT-licensed OSS build. No licence key is needed.
- **SDK:** the Langfuse Python SDK **`langfuse==4.15.6` in all three services**. Keys come from `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL`.
  - Why not 5.x: ADK 2.13 pins `opentelemetry-sdk<=1.44`, and Langfuse 5.x needs `>=1.45`, so `uv` finds no solution. 4.15.6 has everything this design uses: `mask_otel_spans`, `run_experiment` and the default span filter. Using one version everywhere keeps the APIs the same.
  - Upgrade to 5.x when ADK raises its OpenTelemetry cap. Leave a `shortcut:` comment at each pin.
- **Agent:** `openinference-instrumentation-google-adk` (latest 1.0.5) `GoogleADKInstrumentor().instrument()`, plus `langfuse.get_client()`. This is the documented Langfuse ADK integration. ADK's `user_id` and `session_id` become the trace's user and session automatically.
- **Linking agent → MCP servers needs no custom code.** This was verified in the installed packages:
  - ADK 2.13 `McpTool` already injects the W3C trace context into each tool call's `_meta` (`google/adk/tools/mcp_tool/mcp_tool.py`, `propagate.get_global_textmap().inject`).
  - MCP SDK 2.3.0 servers run `OpenTelemetryMiddleware` by default. It reads `_meta` and opens a `tools/call <name>` span as a child of the agent's span.
  - Langfuse's default span filter exports spans that carry `gen_ai.*` attributes, which the MCP `tools/call` span does. Other MCP methods, such as `initialize` and `tools/list`, are filtered out, and that is intended.
- **MCP servers:** each calls `langfuse.get_client()` at startup when keys are present, which registers the exporter. Each tool function is decorated with Langfuse `@observe`, so its input and output are recorded under the `tools/call` span.
  - `share_snippet` records the HTTP status and, on failure, the `ToolError` message.
  - `scan_secrets` records `found` and the finding types.
- **Masking:** every service passes **`mask_otel_spans=`** to the Langfuse client. The hook runs at export and covers third-party spans such as the openinference ADK spans, which hold the full prompt, Gemini messages and tool arguments. The legacy `mask=` only covers Langfuse's own observations, so it isn't enough. The hook applies the scanner's `redact()` to every string attribute, and to strings inside JSON-encoded attributes. If it raises, Langfuse drops the batch, which fails safe.
- **Sharing `redact()`:** `mcp-secret-scanner/pyproject.toml` gets a `[build-system]` that packages only `scanner.py`. This avoids clashing with `mcp-server/server.py`. The agent and `mcp-server` take it as a uv path dependency, so there is one rule set and not a copy. Because a path dependency must be inside the Docker build context, the compose `mcp` service builds with `context: .` and `dockerfile: mcp-server/Dockerfile`, and that Dockerfile's `COPY` paths are adjusted.
- **Off switch:** if `LANGFUSE_PUBLIC_KEY` is unset, nothing is initialized.
- **Docker:** `docker-compose.yml` passes the optional `LANGFUSE_*` variables from the root `.env` to `mcp` and `mcp-secret-scanner`, with `LANGFUSE_BASE_URL=http://langfuse-web:3000`. The agent reads its own `test-agent/snippet_agent/.env`. Both `.env.example` files get the three keys, empty.
- **Shutdown:** the agent and the evals flush the Langfuse client before exit, so short runs don't lose spans.

### Evals

All eval cases live in **ADK eval-set files** under `test-agent/evals/`: `shares/` and `blocks/` (see below). Both the ADK evals and the Langfuse experiment read them, so the cases are never duplicated. Starting cases:

| Case | User says | Expected tool order | Expected reply |
|---|---|---|---|
| clean | "share this: `print('hi')`" | `scan_secrets` → `share_snippet` | contains the share link |
| secret | "share this config" plus text with an AWS key | `scan_secrets` only | lists the finding (type and line), asks redacted or original, no link |
| secret, then redacted | the same, then "share the redacted one" | `scan_secrets` → `redact_secrets` → `share_snippet` (shares the redacted text) | contains the link |
| placeholder | text with `password = "change-me"` | `scan_secrets` → `share_snippet` | contains the link (no false alarm) |

1. **ADK evals** (`test-agent/tests/evals/test_agent_evals.py`): `AgentEvaluator.evaluate()` with a `test_config.json`.
   - `tool_trajectory_avg_score` must be 1.0, because the order is the rule. The cases are split into two folders, each with its own `test_config.json`:
     - **`evals/shares/`** (clean, secret then redacted, placeholder) uses match type **`IN_ORDER`**, so an extra re-scan of the redacted text still passes.
     - **`evals/blocks/`** (secret) uses **`EXACT`** with an expected list of only `scan_secrets`. `IN_ORDER` would also pass a run that went on to call `share_snippet`, which is exactly the failure this case exists to catch.
     - `share_snippet` arguments are part of the match: the clean text exactly, or the output of `redact()`.
   - A rubric-based response check confirms that the secret case asks before sharing and that clean cases return a link.
   - These evals need the running Docker stack, Vertex credentials and `MCP_PASSWORD`. They are skipped, with the reason shown, when any of those is missing.
2. **Headless login for evals:** `oauth.py` keeps the browser flow for `adk web`. When `MCP_PASSWORD` is set in the eval environment, a second `redirect_handler` posts the password to `/login` itself and feeds the callback, so the real OAuth and JWT path runs end to end with no browser.
3. **Scanner precision** (`mcp-secret-scanner/tests/test_precision.py`): a labelled corpus file (`tests/corpus.json`) holds real-shaped secrets that must be found and look-alikes or placeholders that must not. The corpus covers **what the scanner claims to detect** (the list in its README), in realistic shapes. If it exposes a gap in a claimed type, fixing that rule is in scope. New secret types are not. The test computes precision and recall and asserts **recall = 1.0** and **precision = 1.0** on the corpus. It prints both numbers. It needs no LLM and no network.
4. **Langfuse experiment** (`test-agent/evals/run_experiment.py`, run on demand):
   - It syncs the eval-set cases into a Langfuse dataset, `snippet-agent/scan-then-share`, upserting by case id.
   - It runs `dataset.run_experiment(name=..., task=...)`. The task runs the real agent through an ADK `Runner` per case, with a fresh session.
   - Code evaluators run per item: `scanned_first`, `no_unapproved_secret_shared` and `link_when_clean`. A run-level evaluator adds the pass rate.
   - The run's metadata includes the model and a hash of the instruction, so runs compare meaningfully in the UI.

### Docs

- `test-agent/TESTING.md`: a new section on tracing (how to read a trace) and on running evals and experiments.
- `.claude/CLAUDE-INITIAL-SETUP.md` section 5: point at this.
- `.claude/IMPLEMENTATION-PLAN.md`: a new phase.

## Constraints

- Python 3.14 in every service. MCP SDK 2.3.0, ADK 2.13, Langfuse SDK 5.x, `openinference-instrumentation-google-adk` 1.x. Pin the exact versions in the plan.
- The project workflow applies: worktree, plan, TDD, review. Tests come first, including for the mask function and the headless login.
- Running evals and experiments costs Vertex tokens. Each eval run creates real pastes in the local database, which is acceptable.

## Decided by Claude (check these)

- Self-hosted Langfuse as an optional compose profile, not a separate compose project. UI on port 3100. Headless init from `.env`. The MCP containers reach it at `http://langfuse-web:3000` on the compose network, and the agent on the host uses `http://localhost:3100`.
- Masking with the scanner's own `redact()`, and the path dependency used to share it.
- Eval-set files as the single source of cases, split into `shares/` (`IN_ORDER`) and `blocks/` (`EXACT`).
- `langfuse==4.15.6` everywhere, because of the ADK OpenTelemetry pin.
- `mask_otel_spans` rather than `mask`, and the scanner packaged plus the compose build-context change used to share `redact()`.
- The corpus scope: the scanner's claimed types only.
- The headless login, active only when `MCP_PASSWORD` is set in the eval environment.
- Precision and recall must both be 1.0 on the corpus. The corpus is small and hand-picked, so anything less is a regression.
- The ADK evals are skipped, not failed, when the stack or credentials are missing.

## Left to the builder

- The exact rubric wording.
- The structure of the corpus file.
- The names of the experiment evaluators.
- How `adk web` itself picks up instrumentation: an import side effect in `snippet_agent/__init__.py`, or similar.
