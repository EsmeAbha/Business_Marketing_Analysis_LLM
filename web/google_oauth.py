"""Sign in with Google — the authorization-code flow, done directly.

No extra dependency: this is a redirect, a token exchange and one userinfo
call, all of which httpx already covers.

  AIW_GOOGLE_CLIENT_ID      from Google Cloud Console
  AIW_GOOGLE_CLIENT_SECRET  same place
  AIW_GOOGLE_REDIRECT_URI   defaults to http://127.0.0.1:8000/auth/google/callback

To get those:
  1. https://console.cloud.google.com/ → create (or pick) a project
  2. APIs & Services → OAuth consent screen → External → fill in the basics
  3. Credentials → Create credentials → OAuth client ID → Web application
  4. Add the redirect URI above **exactly**, character for character
  5. Copy the client ID and secret into .env

Unconfigured, `enabled()` is False and the sign-in screen simply doesn't offer
the button — rather than showing one that dead-ends.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from lucida.observability import get_logger

logger = get_logger("google-oauth")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DEFAULT_REDIRECT = "http://127.0.0.1:8000/auth/google/callback"


@dataclass
class GoogleUser:
    sub: str
    email: str
    name: str
    email_verified: bool
    picture: str = ""


class OAuthError(Exception):
    """Something the owner can see; the detail is logged, not shown."""


def client_id() -> str:
    return os.environ.get("AIW_GOOGLE_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("AIW_GOOGLE_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    return os.environ.get("AIW_GOOGLE_REDIRECT_URI", "").strip() or DEFAULT_REDIRECT


def enabled() -> bool:
    return bool(client_id() and _client_secret())


def status() -> str:
    if not enabled():
        return "not configured — the Google button is hidden"
    return f"enabled, redirecting to {redirect_uri()}"


def authorize_url(state: str) -> str:
    """Where to send the browser to ask Google for consent."""
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        # Always show the chooser, so switching accounts is possible.
        "prompt": "select_account",
    })


def new_state() -> str:
    """Anti-CSRF value; stored in the session and compared on the way back."""
    return secrets.token_urlsafe(24)


def exchange(code: str) -> GoogleUser:
    """Trade the one-time code for tokens, then read who signed in."""
    if not enabled():
        raise OAuthError("Google sign-in is not configured on this server.")
    try:
        with httpx.Client(timeout=25) as c:
            token = c.post(TOKEN_URL, data={
                "code": code,
                "client_id": client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": redirect_uri(),
                "grant_type": "authorization_code",
            })
            if token.status_code != 200:
                logger.error("token exchange failed: %s", token.text[:300])
                raise OAuthError("Google would not complete the sign-in.")
            access = token.json().get("access_token")
            if not access:
                raise OAuthError("Google did not return an access token.")

            info = c.get(USERINFO_URL,
                         headers={"Authorization": f"Bearer {access}"})
            if info.status_code != 200:
                logger.error("userinfo failed: %s", info.text[:300])
                raise OAuthError("Could not read your Google profile.")
            data = info.json()
    except httpx.HTTPError as exc:
        logger.error("network error talking to Google: %s", exc)
        raise OAuthError("Could not reach Google. Check the connection.") from exc

    if not data.get("sub"):
        raise OAuthError("Google did not identify the account.")
    return GoogleUser(
        sub=str(data["sub"]),
        email=str(data.get("email") or "").lower(),
        name=str(data.get("name") or ""),
        email_verified=bool(data.get("email_verified")),
        picture=str(data.get("picture") or ""),
    )
