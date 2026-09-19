# %%
# Imports #

import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

# %%
# Variables #

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_HTTP_TIMEOUT = 30

# Google access tokens last an hour; refresh a minute early so a call that
# starts just under the wire does not land with an expired token.
EXPIRY_MARGIN_SECONDS = 60

# access_token cache keyed by refresh token: {key: (token, expires_at)}. A
# long-lived process (the MCP server) otherwise burns a token round-trip on
# every single tool call.
_TOKEN_CACHE: dict = {}


# %%
# Token refresh #


def refresh_access_token(client_id, client_secret, refresh_token, context=""):
    """
    Trade a refresh token for an access token. ``context`` names the caller
    (source/mailbox) in the error, since a revoked consent is the usual cause
    and the fix is re-running that thing's ``--auth``.
    """
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=DEFAULT_HTTP_TIMEOUT,
    )
    if response.status_code != 200:
        raise ValueError(
            f"Google token refresh returned {response.status_code}: {response.text[:200]}"
            + (f" (revoked consent? re-run --auth {context})" if context else "")
        )
    return response.json()


def cached_access_token(client_id, client_secret, refresh_token, context=""):
    """
    ``refresh_access_token`` with the access token memoized until it expires.
    Same arguments, returns just the access-token string.
    """
    cached = _TOKEN_CACHE.get(refresh_token)
    if cached and cached[1] > time.time():
        return cached[0]
    payload = refresh_access_token(client_id, client_secret, refresh_token, context=context)
    token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _TOKEN_CACHE[refresh_token] = (token, time.time() + expires_in - EXPIRY_MARGIN_SECONDS)
    return token


def clear_token_cache():
    """Drop every memoized access token (tests, and after a re-auth)."""
    _TOKEN_CACHE.clear()


# %%
# Interactive consent (one-time refresh-token minting) #


def consent_url(client_id, redirect_uri, scope):
    """The Google consent URL for ``scope``; offline + consent force a refresh token on every run."""
    return (
        GOOGLE_AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
                "access_type": "offline",
                "prompt": "consent",
            }
        )
    )


def run_loopback_consent(client_id, client_secret, scope, label):
    """
    One-time interactive OAuth: prints the consent URL, catches the redirect on
    a localhost loopback server, and exchanges the code. Returns the token
    endpoint's payload (carrying ``refresh_token``), or None after printing why
    it failed. Google's device flow does not allow the Calendar or Drive
    scopes, so the browser must run on THIS machine (or with the shown port
    forwarded to it). ``label`` names the caller on the browser's landing page.
    """
    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            if "code" in query or "error" in query:
                captured.update({key: value[0] for key, value in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"{label}: authorization received - return to the terminal".encode("utf-8"))

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect_uri = f"http://localhost:{server.server_port}"
    url = consent_url(client_id, redirect_uri, scope)
    print(f"Open this URL in a browser on THIS machine (redirect lands on {redirect_uri}):\n\n  {url}\n")
    while "code" not in captured and "error" not in captured:
        server.handle_request()
    server.server_close()
    if "error" in captured:
        print(f"authorization failed: {captured['error']}")
        return None
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": captured["code"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=DEFAULT_HTTP_TIMEOUT,
    )
    payload = response.json()
    if "refresh_token" not in payload:
        print(f"token exchange failed ({response.status_code}): {response.text[:300]}")
        return None
    return payload


# %%
