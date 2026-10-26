# secret-scanner MCP server

A **stateless** MCP server with two tools that keep secrets out of shared snippets:

| Tool | Input | Returns |
|---|---|---|
| `scan_secrets(text)` | any text | `{found, findings: [{type, line, preview}]}`. The preview is masked (`AKIA... (20 chars)`) and never contains the secret |
| `redact_secrets(text)` | any text | the same text with each secret replaced by `[REDACTED:<type>]`, everything else unchanged |

It detects private keys, JWTs, AWS keys, GitHub tokens, Google API keys, Slack tokens, `sk-...` API keys, passwords in URLs, quoted `password = "..."` assignments, and `.env`-style `*_PASSWORD=` / `*_TOKEN=` lines. Obvious placeholders (`change-me`, `${VAR}`, `<your-token>`) are skipped.

The test agent calls `scan_secrets` before `share_snippet`, and offers the redacted version when something is found.

## Files

- [scanner.py](scanner.py): the detection rules and `scan` / `redact`, as plain Python with no MCP code. You can test it with no server.
- [server.py](server.py): wraps them as MCP tools and serves them statelessly.

## Stateless vs stateful

This repo has one of each, so you can compare them:

| | `mcp-server` (snippet-share) | `mcp-secret-scanner` |
|---|---|---|
| Transport setting | `stateless_http=False` (default) | `stateless_http=True, json_response=True` |
| `initialize` | starts a session; the reply carries `Mcp-Session-Id` | answered, then forgotten; no session id |
| Later requests | must send `Mcp-Session-Id`; the server looks the session up | stand alone; a `tools/call` works with no `initialize` first |
| Response format | event stream (`text/event-stream`) | one plain JSON body |
| Server memory | one session per connected agent | nothing |
| Restart | sessions lost, agents reconnect | nothing to lose |
| Several copies behind nginx | need sticky routing | any copy answers any request |
| Server → agent messages (progress, sampling, elicitation) | possible | not possible |
| Login | OAuth 2.1 + JWT | none: the tools only process the text sent to them |

In the SDK, the whole difference is the arguments in `streamable_app()` in [server.py](server.py). The stateless manager builds a fresh transport for each request, marks it already initialized, and throws it away when the response is sent.

## Try it by hand

```powershell
# One request, no handshake, no session: plain JSON back.
$h = @{ Accept = "application/json, text/event-stream"; "MCP-Protocol-Version" = "2025-06-18" }
$body = '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"scan_secrets","arguments":{"text":"key = \"AKIAIOSFODNN7EXAMPLE\""}}}'
$r = Invoke-WebRequest -UseBasicParsing -Method Post http://localhost:8003/mcp -ContentType application/json -Headers $h -Body $body
$r.Headers["mcp-session-id"]   # empty: stateless
$r.Content
```

Compare with the stateful server: `initialize` on `localhost:8002/mcp` (once logged in) returns an `mcp-session-id` header, which every later request must send back.

## Run and test

```sh
uv sync
uv run pytest      # test_scanner.py: detection rules; test_stateless.py: no session id, no handshake, JSON replies
MCP_PORT=8003 uv run python server.py
```

In Docker it runs as `mcp-secret-scanner`, and nginx publishes it on `MCP_SCANNER_HOST_PORT` (default 8003).

## Limits

- Pattern matching only. A secret with no recognisable shape (say, a random password in a plain variable) is missed, and look-alikes can be flagged. Treat it as a safety net, not a guarantee.
- Text is processed in memory and never logged or stored.
