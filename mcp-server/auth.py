"""A minimal OAuth 2.1 authorization server, built into the MCP server.

The SDK serves the OAuth endpoints (/register, /authorize, /token, /revoke and the
/.well-known metadata) and checks PKCE, redirect URIs and code expiry. This class is
the storage behind them, plus the hand-off to our /login page.

shortcut: everything lives in memory, so a restart logs everyone out; move to a database before real users depend on it.
"""

import secrets
import time

import jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

CODE_TTL = 5 * 60
ACCESS_TTL = 60 * 60
REFRESH_TTL = 30 * 24 * 60 * 60


class InMemoryAuthProvider:
    def __init__(self, public_url: str, resource_url: str, jwt_secret: str):
        self.public_url = public_url
        self.resource_url = resource_url
        self.jwt_secret = jwt_secret
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.pending: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams, float]] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        self.revoked_jtis: set[str] = set()  # access tokens are JWTs, so revoking one means remembering its id

    # Step 1: dynamic client registration. Claude Code / Codex register themselves; no hand-made client IDs.
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    # Step 2: /authorize. Park the request and send the browser to our login page.
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.resource not in (None, self.resource_url):
            raise AuthorizeError("invalid_target", "This server only issues tokens for its own MCP endpoint")
        req = secrets.token_urlsafe(32)
        self.pending[req] = (client, params, time.time() + CODE_TTL)
        return f"{self.public_url}/login?req={req}"

    def is_pending(self, req: str) -> bool:
        entry = self.pending.get(req)
        return entry is not None and entry[2] > time.time()

    def approve(self, req: str) -> str | None:
        """Called after the password checks out: mint a one-time code and return the redirect back to the agent."""
        if not self.is_pending(req):
            return None
        client, params, _ = self.pending.pop(req)
        code = secrets.token_urlsafe(32)  # 256 bits; the spec asks for at least 128
        self.codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self.resource_url,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    # Step 3: /token. The SDK has already verified PKCE, expiry and redirect_uri.
    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str):
        return self.codes.get(authorization_code)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        del self.codes[authorization_code.code]  # one use only
        return self._issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str):
        return self.refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        del self.refresh_tokens[refresh_token.token]  # rotate: a refresh token is spent once used
        return self._issue(client.client_id, scopes)

    # Step 4: every /mcp request. The bearer middleware calls this to check the token.
    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            # Checks the signature, exp, iss and aud in one go; no storage lookup needed.
            claims = jwt.decode(
                token, self.jwt_secret, algorithms=["HS256"], audience=self.resource_url, issuer=self.public_url
            )
        except jwt.InvalidTokenError:
            return None
        if claims["jti"] in self.revoked_jtis:
            return None
        return AccessToken(
            token=token,
            client_id=claims["client_id"],
            scopes=claims["scope"].split(),
            expires_at=claims["exp"],
            resource=claims["aud"],
            subject=claims["sub"],
            claims={"iss": claims["iss"], "jti": claims["jti"]},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Kill the client's refresh tokens, so it can't mint new access tokens, and deny this JWT if it is one.
        if isinstance(token, AccessToken) and token.claims:
            self.revoked_jtis.add(token.claims["jti"])
        for key in [k for k, t in self.refresh_tokens.items() if t.client_id == token.client_id]:
            del self.refresh_tokens[key]

    def _issue(self, client_id: str, scopes: list[str]) -> OAuthToken:
        now = int(time.time())
        access = jwt.encode(
            {
                "iss": self.public_url,  # who signed it
                "aud": self.resource_url,  # which server may accept it
                "sub": "shared-password-user",  # who logged in; one shared password means one user
                "client_id": client_id,  # which agent install it was given to
                "scope": " ".join(scopes),
                "iat": now,
                "exp": now + ACCESS_TTL,
                "jti": secrets.token_urlsafe(16),  # unique id, so a single token can be revoked
            },
            self.jwt_secret,
            algorithm="HS256",
        )
        refresh = secrets.token_urlsafe(32)  # refresh tokens stay opaque and server-side: they must be revocable
        self.refresh_tokens[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=scopes, expires_at=now + REFRESH_TTL, resource=self.resource_url
        )
        return OAuthToken(access_token=access, expires_in=ACCESS_TTL, refresh_token=refresh, scope=" ".join(scopes) or None)
