# snippet-share MCP server

A remote MCP server. It gives Claude Code and Codex one tool, `share_snippet(text)`, which saves the text to snippet-share and returns the share link. Agents connect over HTTP at `/mcp` and must first log in through OAuth 2.1.

## Run

```sh
cd mcp-server
uv sync
MCP_PASSWORD=choose-one uv run python server.py     # PowerShell: $env:MCP_PASSWORD="choose-one"; uv run python server.py
```

The snippet-share app must be running too (`docker compose -f docker-compose.dev.yml up`).

| Variable | Default | What it is |
|---|---|---|
| `MCP_PASSWORD` | (required) | the password people type on the login page |
| `MCP_JWT_SECRET` | (required, 32+ chars) | the key that signs access tokens; changing it logs everyone out |
| `MCP_PUBLIC_URL` | `http://localhost:8001` | the address agents use to reach this server |
| `MCP_PORT` / `MCP_HOST` | `8001` / `127.0.0.1` | where it listens |
| `SNIPPET_API_URL` | `http://localhost:8000` | the snippet-share API (`http://localhost:3000` with the full compose stack) |

Tests: `uv run pytest`. To run one: `uv run pytest tests/test_auth.py::test_full_login_flow_gives_working_token`.

## Connect an agent

**Claude Code:**

```sh
claude mcp add --transport http -s user snippet-share http://localhost:8001/mcp
```

Then run `/mcp` in a session, pick `snippet-share` and choose Authenticate. A browser opens; type the password.

**Codex:** add this to `~/.codex/config.toml`, then run `codex mcp login snippet-share`:

```toml
[mcp_servers.snippet-share]
url = "http://localhost:8001/mcp"
```

## How the auth works

The SDK serves the OAuth endpoints. [auth.py](auth.py) stores clients, codes and tokens, and [server.py](server.py) adds the login page.

1. **Discovery.** The agent calls `/mcp` with no token and gets `401`. The `WWW-Authenticate` header points to `/.well-known/oauth-protected-resource/mcp`, which names the login server. Here that's this same app, and its `/.well-known/oauth-authorization-server` lists the endpoints.
2. **Registration.** The agent `POST`s to `/register` and receives a `client_id`. No one creates client IDs by hand.
3. **Authorization.** The agent opens the browser at `/authorize` with a PKCE `code_challenge`, which is a hash of a secret only the agent knows. `InMemoryAuthProvider.authorize` parks the request and sends you to `/login`. When the password is right, `approve()` creates a one-time code and redirects back to the agent.
4. **Token.** The agent sends the code plus the PKCE secret (`code_verifier`) to `/token`. The SDK checks that the secret hashes to the challenge, so a stolen code is useless on its own. The agent then gets an access token and a refresh token. The access token is a JWT signed with HS256, valid 1 hour, carrying `iss`, `aud` (this `/mcp` endpoint), `sub`, `client_id`, `exp` and `jti`. The refresh token is a random string stored on the server, valid 30 days and replaced each time it's used.
5. **Use.** Every `/mcp` request carries `Authorization: Bearer <jwt>`. The SDK's middleware calls `load_access_token`, which checks the signature, expiry, issuer and audience without any lookup. A token that is forged, expired, issued for another server, or revoked (its `jti` is on the denylist) is refused.

## Known limits

- Tokens live in memory, so restarting the server logs everyone out.
- There's one shared password and no limit on wrong guesses. Add a rate limit before exposing this publicly.
- The snippet-share API itself is still open. Anyone who can reach it can create pastes without this server.
- Links use the app's `PUBLIC_BASE_URL`, so they are `localhost` links until you deploy.
