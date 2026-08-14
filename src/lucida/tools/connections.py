"""Connecting a shop's own Messenger, Instagram, Facebook and YouTube.

Credentials used to live in `.env`, which meant one set of accounts for the
whole machine and a restart to change them. A shop's Page belongs to the
shop, so they belong in the shop's own database instead — per-owner, editable
while the server is running, and never visible to another shop.

Two ways in, and the difference is honest:

  * **Sign in with the platform.** Only possible when the operator has
    registered an app with Meta or Google and put its id and secret in the
    environment. Then the owner clicks a button and never sees a token.
  * **Paste a token.** Always possible. The owner obtains a Page token from
    Meta's Graph API Explorer, or a refresh token from their own OAuth client,
    and pastes it here.

Either way the credential is *verified against the live API before it is
saved* — the platform is asked who this token belongs to, and the answer is
what gets stored as the display name. A token that cannot name its own Page
is not a connection, and saving it would only mean discovering the failure
later, in front of a customer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.connections")

GRAPH = "https://graph.facebook.com/v21.0"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
TIMEOUT = 30

# Messenger and Facebook are the same Page behind the same token — Meta does
# not separate them — so connecting one connects the other. They are still
# shown apart because the owner thinks of them apart, and because the App
# Review permissions differ.
META_PLATFORMS = ("messenger", "facebook", "instagram")
PLATFORMS = META_PLATFORMS + ("youtube",)


@dataclass
class Verified:
    ok: bool
    display_name: str = ""
    external_id: str = ""
    error: str = ""
    scopes: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# What the operator has registered, if anything
# ---------------------------------------------------------------------------


def meta_app() -> tuple[str, str]:
    return (os.environ.get("META_APP_ID", "").strip(),
            os.environ.get("META_APP_SECRET", "").strip())


def google_app() -> tuple[str, str]:
    """Reuses the sign-in client if a YouTube-specific one is not set."""
    cid = (os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
           or os.environ.get("AIW_GOOGLE_CLIENT_ID", "").strip())
    sec = (os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
           or os.environ.get("AIW_GOOGLE_CLIENT_SECRET", "").strip())
    return cid, sec


def can_oauth(platform: str) -> bool:
    """Is one click possible, or does the owner have to paste a token?"""
    if platform in META_PLATFORMS:
        return all(meta_app())
    if platform == "youtube":
        return all(google_app())
    return False


# ---------------------------------------------------------------------------
# Stored connections
# ---------------------------------------------------------------------------


def saved(db, platform: str) -> dict[str, Any] | None:
    rows = db.query(
        "SELECT * FROM social_accounts WHERE platform=? AND connected=1 "
        "ORDER BY id DESC LIMIT 1", (platform,))
    return rows[0] if rows else None


def save(db, platform: str, external_id: str, display_name: str,
         token: str, expires: str = "") -> None:
    """One live connection per platform — reconnecting replaces the old one."""
    db.execute("DELETE FROM social_accounts WHERE platform=?", (platform,))
    db.execute(
        "INSERT INTO social_accounts (platform, external_id, display_name, "
        "access_token, token_expires, connected, created_at) "
        "VALUES (?,?,?,?,?,1,?)",
        (platform, external_id, display_name, token, expires, _now()))
    logger.info("connected %s as %s", platform, display_name)


def forget(db, platform: str) -> None:
    db.execute("DELETE FROM social_accounts WHERE platform=?", (platform,))
    logger.info("disconnected %s", platform)


def credentials(db, platform: str) -> tuple[str, str]:
    """(token, id) for this shop — what it saved, or the machine-wide default.

    The `.env` values stay as a fallback so an existing single-shop setup
    keeps working untouched after this change.
    """
    row = saved(db, platform) if db is not None else None
    if row and row.get("access_token"):
        return row["access_token"], (row.get("external_id") or "")
    if platform in META_PLATFORMS:
        ident = (settings.meta_ig_user_id if platform == "instagram"
                 else settings.meta_page_id)
        return settings.meta_access_token, ident
    return settings.youtube_refresh_token, ""


def connected(db, platform: str) -> bool:
    token, ident = credentials(db, platform)
    if platform == "youtube":
        cid, _ = google_app()
        return bool(token and cid)
    return bool(token and ident)


# ---------------------------------------------------------------------------
# Verification — the platform tells us who the token belongs to
# ---------------------------------------------------------------------------


def _graph(path: str, params: dict) -> tuple[dict | None, str]:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{GRAPH}/{path}", params=params)
        data = r.json() if r.headers.get("content-type", "").startswith(
            "application/json") else {}
        if r.status_code != 200:
            return None, (data.get("error", {}).get("message")
                          or f"the platform returned {r.status_code}")
        return data, ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def verify_meta(token: str, page_id: str) -> Verified:
    """Ask the Page its own name. Nothing else proves the token reaches it."""
    if not token:
        return Verified(False, error="No token given.")
    if not page_id:
        return Verified(False, error="No Page id given.")
    data, err = _graph(page_id, {"fields": "name,id", "access_token": token})
    if err:
        return Verified(False, error=err)
    return Verified(True, data.get("name") or page_id, str(data.get("id") or page_id))


def verify_instagram(token: str, ig_user_id: str) -> Verified:
    if not token:
        return Verified(False, error="No token given.")
    if not ig_user_id:
        return Verified(False, error="No Instagram account id given.")
    data, err = _graph(ig_user_id,
                       {"fields": "username,id", "access_token": token})
    if err:
        return Verified(False, error=err)
    name = data.get("username")
    return Verified(True, f"@{name}" if name else ig_user_id,
                    str(data.get("id") or ig_user_id))


def verify_youtube(refresh_token: str) -> Verified:
    """Spend the refresh token once: if it yields a channel, it works."""
    cid, secret = google_app()
    if not (cid and secret):
        return Verified(False, error=(
            "This machine has no Google OAuth client, so a refresh token "
            "cannot be exchanged. Set YOUTUBE_CLIENT_ID and "
            "YOUTUBE_CLIENT_SECRET."))
    if not refresh_token:
        return Verified(False, error="No refresh token given.")
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(GOOGLE_TOKEN, data={
                "client_id": cid, "client_secret": secret,
                "refresh_token": refresh_token, "grant_type": "refresh_token"})
            if r.status_code != 200:
                detail = ""
                try:
                    detail = r.json().get("error_description") or r.json().get("error", "")
                except Exception:  # noqa: BLE001
                    detail = r.text[:160]
                return Verified(False, error=f"Google refused the token: {detail}")
            access = r.json().get("access_token", "")

            ch = c.get(f"{YOUTUBE_API}/channels",
                       params={"part": "snippet", "mine": "true"},
                       headers={"Authorization": f"Bearer {access}"})
        if ch.status_code != 200:
            return Verified(False, error=(
                "The token works but cannot see a channel — check that the "
                "YouTube Data API v3 is enabled and youtube.upload was "
                f"granted ({ch.status_code})."))
        items = ch.json().get("items") or []
        if not items:
            return Verified(False, error="That Google account has no channel.")
        return Verified(True, items[0]["snippet"]["title"], items[0]["id"])
    except Exception as exc:  # noqa: BLE001
        return Verified(False, error=str(exc))


def verify(platform: str, token: str, ident: str = "") -> Verified:
    if platform == "instagram":
        return verify_instagram(token, ident)
    if platform == "youtube":
        return verify_youtube(token)
    return verify_meta(token, ident)


def connect(db, platform: str, token: str, ident: str = "") -> Verified:
    """Verify first, save only on success. Never store an unusable token."""
    result = verify(platform, token, ident)
    if result.ok:
        save(db, platform, result.external_id, result.display_name, token)
        # One Meta token covers the Page for both, and the owner should not
        # have to paste it twice to get what Meta treats as one connection.
        if platform in ("messenger", "facebook"):
            twin = "facebook" if platform == "messenger" else "messenger"
            save(db, twin, result.external_id, result.display_name, token)
    return result


# ---------------------------------------------------------------------------
# One-click sign-in
# ---------------------------------------------------------------------------

META_SCOPES = (
    "pages_show_list,pages_messaging,pages_manage_posts,"
    "pages_read_engagement,instagram_basic,instagram_manage_messages,"
    "instagram_manage_comments"
)
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def meta_authorize_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    cid, _ = meta_app()
    return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode({
        "client_id": cid, "redirect_uri": redirect_uri,
        "state": state, "response_type": "code", "scope": META_SCOPES,
    })


def google_authorize_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    cid, _ = google_app()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": cid, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": YOUTUBE_SCOPE, "state": state,
        # Without both of these Google returns no refresh token the second
        # time an account authorises, and the connection dies within the hour.
        "access_type": "offline", "prompt": "consent",
    })


def meta_finish(code: str, redirect_uri: str) -> tuple[list[dict], str]:
    """Code -> user token -> long-lived token -> the Pages they administer.

    Short-lived tokens expire in about an hour, which would mean a shop
    silently going offline the same afternoon, so the exchange for a
    long-lived one is not optional.
    """
    cid, secret = meta_app()
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{GRAPH}/oauth/access_token", params={
                "client_id": cid, "client_secret": secret,
                "redirect_uri": redirect_uri, "code": code})
            if r.status_code != 200:
                return [], (r.json().get("error", {}).get("message")
                            or f"Meta returned {r.status_code}")
            short = r.json().get("access_token", "")

            r = c.get(f"{GRAPH}/oauth/access_token", params={
                "grant_type": "fb_exchange_token", "client_id": cid,
                "client_secret": secret, "fb_exchange_token": short})
            long_lived = r.json().get("access_token", short) if r.status_code == 200 else short

            r = c.get(f"{GRAPH}/me/accounts", params={
                "fields": "id,name,access_token,instagram_business_account{id,username}",
                "access_token": long_lived})
        if r.status_code != 200:
            return [], (r.json().get("error", {}).get("message")
                        or f"Meta returned {r.status_code}")
        return (r.json().get("data") or []), ""
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)


def google_finish(code: str, redirect_uri: str) -> tuple[str, str]:
    """Code -> refresh token. Returns ('', reason) when Google withholds one."""
    cid, secret = google_app()
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(GOOGLE_TOKEN, data={
                "client_id": cid, "client_secret": secret, "code": code,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("error_description") or r.json().get("error", "")
            except Exception:  # noqa: BLE001
                detail = r.text[:160]
            return "", f"Google refused the code: {detail}"
        token = r.json().get("refresh_token", "")
        if not token:
            return "", ("Google returned no refresh token. Remove this app at "
                        "myaccount.google.com/permissions and try again.")
        return token, ""
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)


def status(db=None) -> dict[str, str]:
    """What the Connect screen shows against each platform."""
    out: dict[str, str] = {}
    for platform in PLATFORMS:
        row = saved(db, platform) if db is not None else None
        if row:
            out[platform] = f"connected as {row.get('display_name') or 'your account'}"
        elif connected(db, platform):
            out[platform] = "connected from this machine's .env"
        else:
            out[platform] = "not connected"
    return out
