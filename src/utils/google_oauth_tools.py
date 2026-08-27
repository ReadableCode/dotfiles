# %%
# Imports #

import time

import requests

# %%
# Variables #

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
