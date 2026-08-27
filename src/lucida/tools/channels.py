"""Messenger, Instagram, Facebook and YouTube — reading and publishing.

Four platforms, four jobs the owner asked for:

  * **Messenger** — read what customers send the page.
  * **Instagram** — read DMs, publish ads, reply to comments under them.
  * **Facebook** — publish ads, reply to comments under posts.
  * **YouTube** — publish videos the owner supplies.

What is honest about the state of this
--------------------------------------
Every call below is the real Graph / Data API request, with the real endpoint,
parameters and error handling. None of it is reachable without credentials
the owner has to obtain themselves, and two of them are not merely a
sign-up form:

  * Meta requires a Business account, an App in Live mode, and **App Review**
    for `pages_messaging`, `instagram_manage_messages` and
    `instagram_manage_comments`. Reading customer DMs is the most heavily
    reviewed permission Meta grants.
  * YouTube uploads need **OAuth2 with a refresh token** — an API key alone
    cannot upload, because the upload happens as a user, not as an app.

So each method reports `simulated=True` and returns representative data when
the credentials are absent. That is not the same as pretending: the flag
travels with the result, the UI shows it, and nothing is ever written to the
shop's records as though it came from a real customer.

Instagram publishing is two calls, not one, and the order matters: create a
media container from a **publicly reachable** image URL, then publish it. An
image on the owner's laptop cannot be published — Meta fetches the URL from
its own servers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.channels")

GRAPH = "https://graph.facebook.com/v21.0"
YOUTUBE_UPLOAD = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"

TIMEOUT = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ChannelResult:
    ok: bool
    platform: str
    action: str
    simulated: bool = True
    external_id: str = ""
    permalink: str = ""
    error: str = ""
    detail: str = ""

    def describe(self) -> str:
        mark = "SIMULATED " if self.simulated else ""
        if not self.ok:
            return f"{mark}{self.platform} {self.action} failed: {self.error}"
        return f"{mark}{self.platform} {self.action} ok{f' — {self.permalink}' if self.permalink else ''}"


@dataclass
class Inbox:
    messages: list[dict[str, Any]] = field(default_factory=list)
    simulated: bool = True
    error: str = ""


# ---------------------------------------------------------------------------
# What is actually configured
# ---------------------------------------------------------------------------


def _shop_db():
    """The signed-in shop's database, or None outside a request.

    Imported here rather than at module scope: memory imports tools, so a
    top-level import would be circular.
    """
    try:
        from ..memory import memory
        return memory.db
    except Exception:  # noqa: BLE001
        return None


def _creds(platform: str) -> tuple[str, str]:
    from . import connections
    return connections.credentials(_shop_db(), platform)


def _token() -> str:
    return _creds("facebook")[0]


def _page() -> str:
    return _creds("facebook")[1]


def _ig_token() -> str:
    return _creds("instagram")[0]


def _ig() -> str:
    return _creds("instagram")[1]


def _yt_app() -> tuple[str, str]:
    from . import connections
    return connections.google_app()


def _yt_refresh() -> str:
    return _creds("youtube")[0]


def meta_ready() -> bool:
    return bool(_token() and _page())


def instagram_ready() -> bool:
    return bool(_ig_token() and _ig())


def youtube_ready() -> bool:
    """Uploading needs OAuth, not the API key — which only reads."""
    from . import connections
    return bool(_yt_refresh() and connections.google_app()[0])


def telegram_ready() -> bool:
    """Telegram needs one thing: a bot token from @BotFather.

    No app review, no business verification, no domain — which is why it is
    the channel that actually works end to end for a real customer.
    """
    return bool(_telegram_token())


def _telegram_token() -> str:
    import os
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def status() -> dict[str, str]:
    return {
        "messenger": "connected" if meta_ready()
                     else "needs a Page token (App Review: pages_messaging)",
        "facebook": "connected" if meta_ready()
                    else "needs a Page token",
        "instagram": "connected" if instagram_ready()
                     else "needs a Page token + Instagram Business account id",
        "youtube": "connected" if youtube_ready()
                   else "needs OAuth2 refresh token — an API key cannot upload",
        "telegram": "connected" if telegram_ready()
                    else "needs TELEGRAM_BOT_TOKEN from @BotFather",
    }


def _get(url: str, params: dict) -> tuple[dict | None, str]:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(url, params=params)
        if r.status_code != 200:
            msg = (r.json().get("error", {}).get("message")
                   if r.headers.get("content-type", "").startswith("application/json")
                   else r.text[:200])
            return None, f"{r.status_code}: {msg}"
        return r.json(), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _post(url: str, data: dict) -> tuple[dict | None, str]:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(url, data=data)
        if r.status_code not in (200, 201):
            msg = (r.json().get("error", {}).get("message")
                   if r.headers.get("content-type", "").startswith("application/json")
                   else r.text[:200])
            return None, f"{r.status_code}: {msg}"
        return r.json(), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


# ---------------------------------------------------------------------------
# Reading customers
# ---------------------------------------------------------------------------


def read_messenger(limit: int = 25) -> Inbox:
    """Page conversations — the customer DMs the Engagement agent reads."""
    if not meta_ready():
        # Not connected: no messages. Inventing customers here would write
        # fictional people into the shop's real inbox.
        return Inbox([], simulated=True)

    data, err = _get(f"{GRAPH}/{_page()}/conversations", {
        "fields": "participants,updated_time,"
                  "messages.limit(10){message,from,created_time,id}",
        "limit": limit,
        "access_token": _token(),
    })
    if err:
        logger.warning("messenger read failed: %s", err)
        return Inbox([], simulated=False, error=err)

    out: list[dict[str, Any]] = []
    for convo in data.get("data", []):
        thread_id = convo.get("id", "")
        for m in (convo.get("messages", {}) or {}).get("data", []):
            sender = (m.get("from") or {})
            # Skip the shop's own replies; only the customer's words matter.
            if str(sender.get("id")) == str(_page()):
                continue
            out.append({
                "platform": "messenger", "kind": "dm",
                "external_id": m.get("id"), "thread_id": thread_id,
                "sender_id": sender.get("id"),
                "sender_name": sender.get("name") or "Customer",
                "message": m.get("message") or "",
                "received_at": m.get("created_time") or _now(),
            })
    logger.info("messenger: %d customer message(s)", len(out))
    return Inbox(out, simulated=False)


def read_instagram(limit: int = 25) -> Inbox:
    if not instagram_ready():
        return Inbox([], simulated=True)

    data, err = _get(f"{GRAPH}/{_ig()}/conversations", {
        "fields": "participants,messages.limit(10){message,from,created_time,id}",
        "platform": "instagram",
        "limit": limit,
        "access_token": _token(),
    })
    if err:
        logger.warning("instagram read failed: %s", err)
        return Inbox([], simulated=False, error=err)

    out: list[dict[str, Any]] = []
    for convo in data.get("data", []):
        for m in (convo.get("messages", {}) or {}).get("data", []):
            sender = (m.get("from") or {})
            if str(sender.get("id")) == str(_ig()):
                continue
            out.append({
                "platform": "instagram", "kind": "dm",
                "external_id": m.get("id"), "thread_id": convo.get("id", ""),
                "sender_id": sender.get("id"),
                "sender_name": sender.get("username") or "Customer",
                "message": m.get("message") or "",
                "received_at": m.get("created_time") or _now(),
            })
    logger.info("instagram: %d customer message(s)", len(out))
    return Inbox(out, simulated=False)


def read_comments(platform: str, post_external_id: str,
                  limit: int = 50) -> Inbox:
    """Comments under one published post, on either Meta platform."""
    ready = instagram_ready() if platform == "instagram" else meta_ready()
    if not ready or not post_external_id:
        return Inbox([], simulated=True)

    data, err = _get(f"{GRAPH}/{post_external_id}/comments", {
        "fields": "id,text,message,username,from,timestamp,created_time",
        "limit": limit,
        "access_token": _token(),
    })
    if err:
        logger.warning("%s comments failed: %s", platform, err)
        return Inbox([], simulated=False, error=err)

    out = []
    for c in data.get("data", []):
        out.append({
            "platform": platform, "kind": "comment",
            "external_id": c.get("id"), "post_id": post_external_id,
            "sender_id": (c.get("from") or {}).get("id") or c.get("username"),
            "sender_name": c.get("username")
                           or (c.get("from") or {}).get("name") or "Someone",
            # Instagram calls it `text`, Facebook calls it `message`.
            "message": c.get("text") or c.get("message") or "",
            "received_at": c.get("timestamp") or c.get("created_time") or _now(),
        })
    logger.info("%s: %d comment(s) on %s", platform, len(out), post_external_id)
    return Inbox(out, simulated=False)


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def post_facebook(message: str, link: str = "",
                  image_url: str = "") -> ChannelResult:
    if not meta_ready():
        return _simulated("facebook", "post", message)

    endpoint = "photos" if image_url else "feed"
    payload = {"access_token": _token()}
    if image_url:
        payload |= {"url": image_url, "caption": message}
    else:
        payload |= {"message": message}
        if link:
            payload["link"] = link

    data, err = _post(f"{GRAPH}/{_page()}/{endpoint}", payload)
    if err:
        return ChannelResult(False, "facebook", "post", False, error=err)
    pid = str(data.get("post_id") or data.get("id") or "")
    return ChannelResult(True, "facebook", "post", False, pid,
                         f"https://facebook.com/{pid}")


def post_instagram(caption: str, image_url: str) -> ChannelResult:
    """Two calls: build a container from a public URL, then publish it.

    The URL has to be reachable by Meta's servers — a path on the owner's
    machine cannot be published, which is why generated artwork must be
    hosted before it can go out.
    """
    if not instagram_ready():
        return _simulated("instagram", "post", caption)
    if not image_url:
        return ChannelResult(False, "instagram", "post", False,
                             error="Instagram posts need an image")
    if not image_url.startswith(("http://", "https://")):
        return ChannelResult(
            False, "instagram", "post", False,
            error="Instagram fetches the image itself, so it needs a public "
                  "URL — a local file path cannot be published")

    container, err = _post(f"{GRAPH}/{_ig()}/media", {
        "image_url": image_url, "caption": caption,
        "access_token": _token(),
    })
    if err:
        return ChannelResult(False, "instagram", "post", False, error=err)

    published, err = _post(f"{GRAPH}/{_ig()}/media_publish", {
        "creation_id": container.get("id"),
        "access_token": _token(),
    })
    if err:
        return ChannelResult(False, "instagram", "post", False, error=err)

    mid = str(published.get("id") or "")
    return ChannelResult(True, "instagram", "post", False, mid)


def reply_to_comment(platform: str, comment_id: str,
                     message: str) -> ChannelResult:
    """Reply under a comment. Same endpoint shape on both Meta platforms."""
    ready = instagram_ready() if platform == "instagram" else meta_ready()
    if not ready:
        return _simulated(platform, "reply", message)

    data, err = _post(f"{GRAPH}/{comment_id}/replies", {
        "message": message, "access_token": _token(),
    })
    if err:
        return ChannelResult(False, platform, "reply", False, error=err)
    return ChannelResult(True, platform, "reply", False,
                         str(data.get("id") or ""))


def send_dm(platform: str, recipient_id: str, message: str) -> ChannelResult:
    """Reply to a customer's DM.

    Meta's 24-hour rule applies: outside that window since the customer last
    wrote, the send is rejected. That is Meta's policy, not a bug here, and
    the error says so rather than retrying.
    """
    if platform == "telegram":
        return send_telegram(recipient_id, message)

    if not meta_ready():
        return _simulated(platform, "dm", message)

    data, err = _post(f"{GRAPH}/{_page()}/messages", {
        "recipient": f'{{"id":"{recipient_id}"}}',
        "message": f'{{"text":{message!r}}}',
        "messaging_type": "RESPONSE",
        "access_token": _token(),
    })
    if err:
        return ChannelResult(False, platform, "dm", False, error=err)
    return ChannelResult(True, platform, "dm", False,
                         str(data.get("message_id") or ""))


def upload_youtube(video_path: str, title: str, description: str = "",
                   tags: list[str] | None = None,
                   privacy: str = "public") -> ChannelResult:
    """Publish a video the owner supplied.

    Requires OAuth2 — an API key cannot upload, because the video is owned by
    a channel, not by the app. The refresh token is exchanged for an access
    token on each call rather than cached, which is slower and much harder to
    get wrong.
    """
    if not youtube_ready():
        return _simulated("youtube", "upload", title)

    from pathlib import Path
    path = Path(video_path)
    if not path.exists():
        return ChannelResult(False, "youtube", "upload", False,
                             error=f"no video at {video_path}")

    token, err = _post("https://oauth2.googleapis.com/token", {
        "client_id": _yt_app()[0],
        "client_secret": _yt_app()[1],
        "refresh_token": _yt_refresh(),
        "grant_type": "refresh_token",
    })
    if err:
        return ChannelResult(False, "youtube", "upload", False,
                             error=f"could not refresh the token: {err}")
    access = token.get("access_token")

    metadata = {
        "snippet": {"title": title, "description": description,
                    "tags": tags or []},
        "status": {"privacyStatus": privacy},
    }
    try:
        with httpx.Client(timeout=600) as c:
            r = c.post(
                YOUTUBE_UPLOAD,
                params={"part": "snippet,status", "uploadType": "multipart"},
                headers={"Authorization": f"Bearer {access}"},
                files={
                    "metadata": (None, __import__("json").dumps(metadata),
                                 "application/json"),
                    "video": (path.name, path.read_bytes(), "video/*"),
                },
            )
        if r.status_code not in (200, 201):
            return ChannelResult(False, "youtube", "upload", False,
                                 error=f"{r.status_code}: {r.text[:200]}")
        vid = r.json().get("id", "")
        return ChannelResult(True, "youtube", "upload", False, vid,
                             f"https://youtu.be/{vid}")
    except Exception as exc:  # noqa: BLE001
        return ChannelResult(False, "youtube", "upload", False, error=str(exc))


# ---------------------------------------------------------------------------
# Stand-ins used only while credentials are missing
# ---------------------------------------------------------------------------


def _simulated(platform: str, action: str, content: str) -> ChannelResult:
    logger.info("SIMULATED %s %s (%d chars)", platform, action, len(content))
    return ChannelResult(
        True, platform, action, simulated=True,
        external_id=f"sim_{platform}_{abs(hash(content)) % 10**10}",
        detail="Not sent — this platform has no credentials configured.",
    )



# ---------------------------------------------------------------------------
# Telegram
#
# The one channel a real customer can use today. Meta gates `pages_messaging`
# behind App Review and Business Verification; Telegram gates nothing, so the
# bot is publicly reachable the moment BotFather issues the token.
#
# Reading uses long-poll `getUpdates` rather than a webhook, deliberately: a
# webhook would need a public HTTPS URL, and the whole point of this channel is
# that it works from localhost.
# ---------------------------------------------------------------------------

TELEGRAM_API = "https://api.telegram.org"


def _telegram_get(method: str, params: dict) -> tuple[dict | None, str]:
    try:
        r = httpx.get(f"{TELEGRAM_API}/bot{_telegram_token()}/{method}",
                      params=params, timeout=TIMEOUT)
        body = r.json()
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if not body.get("ok"):
        return None, str(body.get("description") or f"telegram returned {r.status_code}")
    return body, ""


def _telegram_offset(db) -> int:
    """Highest Telegram update id already processed for this shop."""
    if db is None:
        return 0
    try:
        db.execute(
            """CREATE TABLE IF NOT EXISTS telegram_sync_state (
                   id INTEGER PRIMARY KEY CHECK (id=1),
                   last_update_id INTEGER NOT NULL DEFAULT 0,
                   updated_at TEXT)"""
        )
    except Exception:  # noqa: BLE001
        pass
    rows = db.query("SELECT last_update_id FROM telegram_sync_state WHERE id=1")
    if not rows:
        db.execute(
            "INSERT INTO telegram_sync_state (id, last_update_id, updated_at) VALUES (1,0,?)",
            (_now(),),
        )
        return 0
    try:
        return int((rows[0].get("last_update_id") or 0))
    except Exception:  # noqa: BLE001
        return 0


def _save_telegram_offset(db, update_id: int) -> None:
    if db is None or update_id <= 0:
        return
    try:
        db.execute(
            """INSERT INTO telegram_sync_state (id, last_update_id, updated_at)
               VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 last_update_id = excluded.last_update_id,
                 updated_at = excluded.updated_at""",
            (int(update_id), _now()),
        )
    except Exception:  # noqa: BLE001
        rows = db.query("SELECT 1 FROM telegram_sync_state WHERE id=1")
        if rows:
            db.execute(
                "UPDATE telegram_sync_state SET last_update_id=?, updated_at=? WHERE id=1",
                (int(update_id), _now()),
            )
        else:
            db.execute(
                "INSERT INTO telegram_sync_state (id, last_update_id, updated_at) VALUES (1, ?, ?)",
                (int(update_id), _now()),
            )


def read_telegram(limit: int = 25) -> Inbox:
    """Customer messages sent to the bot.

    Telegram keeps only a short retention window for old updates, so we advance
    a stored `last_update_id` after each sync. That prevents replaying the same
    message and allows the next message in the conversation to be processed.
    """
    if not telegram_ready():
        return Inbox([], simulated=True)

    db = _shop_db() if "_shop_db" in globals() else None
    last_seen = _telegram_offset(db)
    params = {"limit": max(1, min(limit, 100)), "timeout": 0}
    if last_seen > 0:
        params["offset"] = last_seen + 1

    data, err = _telegram_get("getUpdates", params)
    if err:
        logger.warning("telegram read failed: %s", err)
        return Inbox([], simulated=False, error=err)

    out: list[dict[str, Any]] = []
    max_update_id = last_seen
    for update in data.get("result", []):
        update_id = int(update.get("update_id") or 0)
        if update_id > max_update_id:
            max_update_id = update_id
        msg = update.get("message") or update.get("edited_message") or {}
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            continue  # stickers, photos without captions: nothing to read
        if text.startswith("/"):
            # /start, /help and friends are Telegram protocol, not something a
            # customer said. Storing them would skew the sentiment breakdown.
            continue
        sender = msg.get("from") or {}
        if sender.get("is_bot"):
            continue  # our own replies come back as updates too
        chat = msg.get("chat") or {}
        name = " ".join(x for x in (sender.get("first_name"),
                                    sender.get("last_name")) if x).strip()
        out.append({
            "platform": "telegram", "kind": "dm",
            # Unique per message; the chat id alone would collapse a whole
            # conversation into one row.
            "external_id": f"tg-{chat.get('id')}-{msg.get('message_id')}",
            # Replies are addressed to the chat, so that is the thread.
            "thread_id": str(chat.get("id") or ""),
            "sender_id": str(chat.get("id") or ""),
            "sender_name": name or sender.get("username") or "Customer",
            "message": text,
            "received_at": datetime.fromtimestamp(
                msg.get("date", 0), tz=timezone.utc).isoformat(timespec="seconds")
                if msg.get("date") else _now(),
        })
    if max_update_id > last_seen:
        _save_telegram_offset(db, max_update_id)
    logger.info("telegram: %d customer message(s)", len(out))
    return Inbox(out, simulated=False)


def send_telegram(chat_id: str, message: str) -> ChannelResult:
    """Reply to a customer. No 24-hour window — Telegram has no such rule."""
    if not telegram_ready():
        return _simulated("telegram", "dm", message)

    data, err = _telegram_get("sendMessage", {"chat_id": chat_id,
                                              "text": message})
    if err:
        return ChannelResult(False, "telegram", "dm", False, error=err)
    return ChannelResult(True, "telegram", "dm", False,
                         str((data.get("result") or {}).get("message_id") or ""))


