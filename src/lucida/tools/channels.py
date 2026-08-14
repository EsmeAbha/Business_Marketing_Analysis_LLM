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


def meta_ready() -> bool:
    return bool(settings.meta_access_token and settings.meta_page_id)


def instagram_ready() -> bool:
    return bool(settings.meta_access_token and settings.meta_ig_user_id)


def youtube_ready() -> bool:
    """Uploading needs OAuth, not the API key — which only reads."""
    return bool(getattr(settings, "youtube_refresh_token", "")
                and getattr(settings, "youtube_client_id", ""))


def status() -> dict[str, str]:
    return {
        "messenger": "connected" if meta_ready()
                     else "needs META_ACCESS_TOKEN + META_PAGE_ID (App Review: pages_messaging)",
        "facebook": "connected" if meta_ready()
                    else "needs META_ACCESS_TOKEN + META_PAGE_ID",
        "instagram": "connected" if instagram_ready()
                     else "needs META_ACCESS_TOKEN + META_IG_USER_ID (Business account)",
        "youtube": "connected" if youtube_ready()
                   else "needs OAuth2 refresh token — an API key cannot upload",
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
        return Inbox(_sample_dms("messenger", limit), simulated=True)

    data, err = _get(f"{GRAPH}/{settings.meta_page_id}/conversations", {
        "fields": "participants,updated_time,"
                  "messages.limit(10){message,from,created_time,id}",
        "limit": limit,
        "access_token": settings.meta_access_token,
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
            if str(sender.get("id")) == str(settings.meta_page_id):
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
        return Inbox(_sample_dms("instagram", limit), simulated=True)

    data, err = _get(f"{GRAPH}/{settings.meta_ig_user_id}/conversations", {
        "fields": "participants,messages.limit(10){message,from,created_time,id}",
        "platform": "instagram",
        "limit": limit,
        "access_token": settings.meta_access_token,
    })
    if err:
        logger.warning("instagram read failed: %s", err)
        return Inbox([], simulated=False, error=err)

    out: list[dict[str, Any]] = []
    for convo in data.get("data", []):
        for m in (convo.get("messages", {}) or {}).get("data", []):
            sender = (m.get("from") or {})
            if str(sender.get("id")) == str(settings.meta_ig_user_id):
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
        return Inbox(_sample_comments(platform, post_external_id, limit),
                     simulated=True)

    data, err = _get(f"{GRAPH}/{post_external_id}/comments", {
        "fields": "id,text,message,username,from,timestamp,created_time",
        "limit": limit,
        "access_token": settings.meta_access_token,
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
    payload = {"access_token": settings.meta_access_token}
    if image_url:
        payload |= {"url": image_url, "caption": message}
    else:
        payload |= {"message": message}
        if link:
            payload["link"] = link

    data, err = _post(f"{GRAPH}/{settings.meta_page_id}/{endpoint}", payload)
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

    container, err = _post(f"{GRAPH}/{settings.meta_ig_user_id}/media", {
        "image_url": image_url, "caption": caption,
        "access_token": settings.meta_access_token,
    })
    if err:
        return ChannelResult(False, "instagram", "post", False, error=err)

    published, err = _post(f"{GRAPH}/{settings.meta_ig_user_id}/media_publish", {
        "creation_id": container.get("id"),
        "access_token": settings.meta_access_token,
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
        "message": message, "access_token": settings.meta_access_token,
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
    if not meta_ready():
        return _simulated(platform, "dm", message)

    data, err = _post(f"{GRAPH}/{settings.meta_page_id}/messages", {
        "recipient": f'{{"id":"{recipient_id}"}}',
        "message": f'{{"text":{message!r}}}',
        "messaging_type": "RESPONSE",
        "access_token": settings.meta_access_token,
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
        "client_id": settings.youtube_client_id,
        "client_secret": settings.youtube_client_secret,
        "refresh_token": settings.youtube_refresh_token,
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


def _sample_dms(platform: str, limit: int) -> list[dict[str, Any]]:
    seed = [
        ("Nusrat", "Apu 24 pcs lagbe Friday er jonno. Chicken er ta ki ache?"),
        ("Shahana", "Kal delivery ashe nai, 3 din hoye gelo."),
        ("Rakib", "Uttara te deliver koren? Koto lagbe?"),
        ("Mim", "Price ta ki kome hobe jodi beshi ni?"),
    ]
    return [
        {
            "platform": platform, "kind": "dm",
            "external_id": f"sim_{platform}_dm_{i}",
            "thread_id": f"sim_thread_{i}", "sender_id": f"sim_user_{i}",
            "sender_name": name, "message": text, "received_at": _now(),
        }
        for i, (name, text) in enumerate(seed[:limit])
    ]


def _sample_comments(platform: str, post_id: str,
                     limit: int) -> list[dict[str, Any]]:
    seed = [
        ("shopper_bd", "Price koto?"),
        ("mim.crafts", "Chittagong e deliver hoy?"),
        ("rifat", "Nice! Ekta order dilam."),
    ]
    return [
        {
            "platform": platform, "kind": "comment",
            "external_id": f"sim_{platform}_c_{i}", "post_id": post_id,
            "sender_id": f"sim_user_{i}", "sender_name": name,
            "message": text, "received_at": _now(),
        }
        for i, (name, text) in enumerate(seed[:limit])
    ]
