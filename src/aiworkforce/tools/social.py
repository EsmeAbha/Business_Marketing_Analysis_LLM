"""Social publishing adapters: Meta Graph API (Facebook + Instagram) and YouTube.

Real API calls run when credentials are present. Meta requires a verified
business app and IG Business account, which cannot be provisioned inside this
project's timeline — so without credentials the adapter returns realistic,
explicitly-labelled simulated responses in the *same shape*. Agent logic never
branches on which mode is active; only `simulated` in the response differs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.social")

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
_TIMEOUT = 20


@dataclass
class PublishResult:
    platform: str
    ok: bool
    simulated: bool
    external_id: str = ""
    permalink: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        tag = "SIMULATED" if self.simulated else "LIVE"
        if not self.ok:
            return f"[{tag}] {self.platform}: FAILED — {self.error}"
        return f"[{tag}] {self.platform}: published as {self.external_id} {self.permalink}".strip()


def _sim_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class SocialAdapter:
    """One interface over Facebook, Instagram and YouTube publishing."""

    # --- Facebook ---

    def publish_facebook(self, message: str, link: str = "") -> PublishResult:
        if not settings.has_meta:
            return self._simulate("facebook", message)
        try:
            payload = {"message": message, "access_token": settings.meta_access_token}
            if link:
                payload["link"] = link
            resp = requests.post(
                f"{GRAPH_BASE}/{settings.meta_page_id}/feed",
                data=payload,
                timeout=_TIMEOUT,
            )
            data = resp.json()
            if resp.status_code >= 400 or "error" in data:
                err = data.get("error", {}).get("message", resp.text[:300])
                return PublishResult("facebook", False, False, error=err, raw=data)
            post_id = data.get("id", "")
            return PublishResult(
                "facebook",
                True,
                False,
                external_id=post_id,
                permalink=f"https://facebook.com/{post_id}",
                raw=data,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("facebook publish failed: %s", exc)
            return PublishResult("facebook", False, False, error=str(exc))

    # --- Instagram ---

    def publish_instagram(self, caption: str, image_url: str = "") -> PublishResult:
        """IG requires a publicly reachable image URL — it cannot accept raw bytes."""
        if not settings.has_meta or not settings.meta_ig_user_id:
            return self._simulate("instagram", caption)
        if not image_url:
            return PublishResult(
                "instagram",
                False,
                False,
                error="Instagram publishing requires a public image URL",
            )
        try:
            create = requests.post(
                f"{GRAPH_BASE}/{settings.meta_ig_user_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": settings.meta_access_token,
                },
                timeout=_TIMEOUT,
            ).json()
            container_id = create.get("id")
            if not container_id:
                return PublishResult(
                    "instagram",
                    False,
                    False,
                    error=create.get("error", {}).get("message", "container failed"),
                    raw=create,
                )
            publish = requests.post(
                f"{GRAPH_BASE}/{settings.meta_ig_user_id}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": settings.meta_access_token,
                },
                timeout=_TIMEOUT,
            ).json()
            media_id = publish.get("id", "")
            if not media_id:
                return PublishResult(
                    "instagram",
                    False,
                    False,
                    error=publish.get("error", {}).get("message", "publish failed"),
                    raw=publish,
                )
            return PublishResult(
                "instagram", True, False, external_id=media_id, raw=publish
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("instagram publish failed: %s", exc)
            return PublishResult("instagram", False, False, error=str(exc))

    # --- YouTube ---

    def publish_youtube(self, title: str, description: str) -> PublishResult:
        """YouTube uploads need OAuth user consent, not just an API key.

        With only an API key we can read but not write, so publishing is always
        simulated here; the seam is left in place for a real OAuth flow.
        """
        return self._simulate("youtube", f"{title}\n{description}")

    # --- Inbound message reading (Customer Engagement agent) ---

    def fetch_messages(self, limit: int = 12) -> tuple[list[dict[str, Any]], bool]:
        """Return (messages, simulated). Real Messenger/IG DMs need pages_messaging."""
        if settings.has_meta:
            try:
                resp = requests.get(
                    f"{GRAPH_BASE}/{settings.meta_page_id}/conversations",
                    params={
                        "fields": "participants,messages{message,from,created_time}",
                        "limit": limit,
                        "access_token": settings.meta_access_token,
                    },
                    timeout=_TIMEOUT,
                )
                data = resp.json()
                if "data" in data:
                    out = []
                    for convo in data["data"]:
                        for m in (convo.get("messages", {}) or {}).get("data", []):
                            out.append(
                                {
                                    "channel": "messenger",
                                    "customer": (m.get("from") or {}).get("name", "customer"),
                                    "message": m.get("message", ""),
                                    "created_time": m.get("created_time", ""),
                                }
                            )
                    if out:
                        return out[:limit], False
            except Exception as exc:  # noqa: BLE001
                logger.warning("messenger fetch failed, using simulated inbox: %s", exc)

        return self._simulated_inbox(limit), True

    # --- simulation helpers ---

    def _simulate(self, platform: str, content: str) -> PublishResult:
        ident = _sim_id(platform[:2])
        logger.info("SIMULATED publish to %s (%d chars)", platform, len(content))
        return PublishResult(
            platform=platform,
            ok=True,
            simulated=True,
            external_id=ident,
            permalink=f"https://example.invalid/{platform}/{ident}",
            raw={
                "note": (
                    f"SIMULATED {platform} publish. No credentials configured, so no "
                    "network call was made. Supplying the relevant API keys in .env "
                    "switches this to a live call with no change to agent logic."
                ),
                "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "content_preview": content[:280],
            },
        )

    def _simulated_inbox(self, limit: int) -> list[dict[str, Any]]:
        """Realistic sample inbox covering every intent the engagement agent handles."""
        samples = [
            ("messenger", "Rifat Hasan", "Vai, ei product ta ki stock e ache? Ami 2 ta nibo."),
            ("messenger", "Nusrat Jahan", "Price ta ki kombe? 500 taka onek beshi mone hocche."),
            ("instagram", "shopno_kitchen", "Do you deliver to Chattogram? And do you have a smaller size?"),
            ("comment", "Tanvir Ahmed", "Amar order ta 5 din hoye gelo, ekhono pai nai. Khub disappointed."),
            ("instagram", "farhana.b", "Sugar-free version ache? Amar diabetes, tai kinte parchi na."),
            ("messenger", "Sabbir Khan", "Bulk order korle discount ache? 20 pcs lagbe office er jonno."),
            ("comment", "Mim Akter", "Quality just amazing! Abar order dibo definitely."),
            ("instagram", "rakib_ff", "Vegan option ta kobe ashbe? Onek din dhore wait korchi."),
            ("messenger", "Ayesha Siddiqua", "COD ache to? Advance payment korte chai na."),
            ("comment", "Jubayer H", "Packaging ta aro valo hole valo hoto, ektu damaged chilo."),
        ]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return [
            {
                "channel": ch,
                "customer": who,
                "message": msg,
                "created_time": now,
                "simulated": True,
            }
            for ch, who, msg in samples[:limit]
        ]


social = SocialAdapter()
