"""Research across chosen sources — and asking the owner which ones first.

Searching "the web" is not one thing. What rivals charge is on Google; what
customers are actually saying is on Instagram; what the owner's own audience
responded to is on their own page. They answer different questions and they
cost different amounts of the day's tokens, so the owner picks.

Each source reports its own availability honestly. Web search works for
everyone — DuckDuckGo needs no key. The Meta sources need credentials the
owner has to obtain, and Instagram's hashtag search additionally needs App
Review, so they are listed as unavailable with the reason rather than quietly
returning nothing and looking like a shop nobody talks about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings
from ..observability import get_logger
from . import channels
from .web_search import web_search

logger = get_logger("tools.research")

GRAPH = "https://graph.facebook.com/v21.0"


@dataclass
class Source:
    key: str
    name: str
    what: str                 # what this source is actually good for
    available: bool
    reason: str = ""          # why not, when it is not
    default: bool = False     # pre-ticked in the picker


@dataclass
class Finding:
    source: str
    title: str
    snippet: str
    url: str = ""


@dataclass
class ResearchResult:
    query: str
    findings: list[Finding] = field(default_factory=list)
    per_source: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    simulated: list[str] = field(default_factory=list)

    def as_prompt_context(self, limit: int = 20) -> str:
        if not self.findings:
            return "(nothing found)"
        return "\n".join(
            f"[{f.source}] {f.title}\n{f.snippet}"
            + (f"\n{f.url}" if f.url else "")
            for f in self.findings[:limit]
        )


def sources() -> list[Source]:
    """Every place we could look, and whether we actually can."""
    meta = channels.meta_ready()
    insta = channels.instagram_ready()
    return [
        Source(
            "web", "Google & the open web",
            "what rivals charge, demand, what is already being sold",
            True, default=True,
        ),
        Source(
            "instagram_tags", "Instagram hashtags",
            "what people post about this product and how it is styled",
            insta,
            "" if insta else
            "needs META_IG_USER_ID plus App Review for hashtag search",
        ),
        Source(
            "instagram_own", "Your Instagram",
            "what your own posts and comments say about demand",
            insta,
            "" if insta else "connect your Instagram Business account",
        ),
        Source(
            "facebook_own", "Your Facebook Page",
            "how your own audience responded to what you posted",
            meta,
            "" if meta else "connect your Facebook Page",
        ),
        Source(
            "my_customers", "Your own messages",
            "what your customers have already asked you for",
            True, default=True,
        ),
    ]


def available_keys() -> list[str]:
    return [s.key for s in sources() if s.available]


# ---------------------------------------------------------------------------
# The individual searches
# ---------------------------------------------------------------------------


def _web(query: str, limit: int) -> tuple[list[Finding], str]:
    r = web_search(query, max_results=limit)
    if r.error:
        return [], r.error
    return [
        Finding("web", f.title, (f.snippet or "")[:400], f.url)
        for f in r.results
    ], ""


def _my_customers(db, query: str, limit: int) -> tuple[list[Finding], str]:
    """The cheapest source, and often the best: what people already asked."""
    like = f"%{query.split()[0].lower()}%" if query.split() else "%"
    rows = db.query(
        "SELECT sender_name, message, platform, requested_item "
        "FROM social_messages "
        "WHERE lower(message) LIKE ? OR lower(COALESCE(requested_item,'')) LIKE ? "
        "ORDER BY id DESC LIMIT ?",
        (like, like, limit),
    )
    if not rows:
        rows = db.query(
            "SELECT sender_name, message, platform, requested_item "
            "FROM social_messages ORDER BY id DESC LIMIT ?", (limit,))
    return [
        Finding("your customers",
                f"{r.get('sender_name') or 'A customer'} on "
                f"{r.get('platform') or 'message'}",
                (r.get("message") or "")[:300])
        for r in rows
    ], ""


def _instagram_tags(query: str, limit: int) -> tuple[list[Finding], str]:
    """Instagram hashtag search — two calls: resolve the tag, then read it."""
    if not channels.instagram_ready():
        return [], "Instagram is not connected"
    tag = "".join(ch for ch in query.split()[0] if ch.isalnum()) or "shop"
    try:
        with httpx.Client(timeout=25) as c:
            r = c.get(f"{GRAPH}/ig_hashtag_search", params={
                "user_id": settings.meta_ig_user_id, "q": tag,
                "access_token": settings.meta_access_token})
            if r.status_code != 200:
                return [], f"hashtag lookup failed ({r.status_code})"
            data = (r.json().get("data") or [])
            if not data:
                return [], f"no hashtag matching #{tag}"
            hid = data[0]["id"]

            r = c.get(f"{GRAPH}/{hid}/recent_media", params={
                "user_id": settings.meta_ig_user_id,
                "fields": "caption,permalink,like_count",
                "limit": limit,
                "access_token": settings.meta_access_token})
            if r.status_code != 200:
                return [], f"hashtag media failed ({r.status_code})"
            posts = r.json().get("data") or []
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)

    return [
        Finding("instagram", f"#{tag} · {p.get('like_count', 0)} likes",
                (p.get("caption") or "")[:300], p.get("permalink", ""))
        for p in posts
    ], ""


def _own_media(platform: str, node: str, limit: int) -> tuple[list[Finding], str]:
    """The owner's own posts, and how they landed."""
    edge = "media" if platform == "instagram" else "posts"
    fields = ("caption,permalink,like_count,comments_count"
              if platform == "instagram" else "message,permalink_url,shares")
    try:
        with httpx.Client(timeout=25) as c:
            r = c.get(f"{GRAPH}/{node}/{edge}", params={
                "fields": fields, "limit": limit,
                "access_token": settings.meta_access_token})
        if r.status_code != 200:
            return [], f"{platform} returned {r.status_code}"
        items = r.json().get("data") or []
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)

    out = []
    for p in items:
        text = p.get("caption") or p.get("message") or ""
        reach = p.get("like_count")
        out.append(Finding(
            f"your {platform}",
            f"Your post" + (f" · {reach} likes" if reach is not None else ""),
            text[:300], p.get("permalink") or p.get("permalink_url") or ""))
    return out, ""


# ---------------------------------------------------------------------------
# Running the chosen ones
# ---------------------------------------------------------------------------


# A price in a search result reads like "৳450", "BDT 450", "Tk 450/pc" or
# "450 taka". One expression for all of them; anything it cannot read stays
# unpriced rather than being guessed at.
_PRICE = re.compile(
    r"(?:৳|bdt|tk\.?|taka)\s*([0-9][0-9,]{1,7})|([0-9][0-9,]{1,7})\s*(?:৳|bdt|tk\b|taka)",
    re.I)


def _price_in(text: str) -> float | None:
    m = _PRICE.search(text or "")
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    # A four-figure "price" is usually a follower count or a year.
    return value if 1 <= value <= 100000 else None


def record_competitors(db, query: str, findings: list[Finding]) -> int:
    """Keep the priced results as rows, so a comparison can be shown later.

    Only findings that actually name a price are kept. A competitor without
    one adds nothing to the Money page except the impression of research.
    """
    kept = 0
    for f in findings:
        price = _price_in(f"{f.title} {f.snippet}")
        if price is None:
            continue
        name = " ".join((f.title or "").split())[:70] or "A seller"
        db.execute(
            "INSERT OR REPLACE INTO competitors "
            "(name, product, price, currency, note, source, found_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (name, query[:60], price, settings.currency,
             " ".join((f.snippet or "").split())[:160], f.url))
        kept += 1
    if kept:
        logger.info("recorded %d competitor price(s) for '%s'", kept, query[:40])
    return kept


def run(db, query: str, chosen: list[str],
        limit: int = 6) -> ResearchResult:
    """Search only where the owner said to look."""
    result = ResearchResult(query=query)
    picked = [k for k in chosen if k in available_keys()] or ["web"]

    for key in picked:
        if key == "web":
            found, err = _web(query, limit)
        elif key == "my_customers":
            found, err = _my_customers(db, query, limit)
        elif key == "instagram_tags":
            found, err = _instagram_tags(query, limit)
        elif key == "instagram_own":
            found, err = _own_media("instagram", settings.meta_ig_user_id, limit)
        elif key == "facebook_own":
            found, err = _own_media("facebook", settings.meta_page_id, limit)
        else:
            continue

        if err:
            result.errors.append(f"{key}: {err}")
        result.findings.extend(found)
        result.per_source[key] = len(found)

    # Anything with a price in it is worth keeping as a row.
    try:
        record_competitors(db, query, result.findings)
    except Exception as exc:  # noqa: BLE001 — research is not worth an outage
        logger.warning("could not record competitor prices: %s", exc)

    logger.info("research '%s' across %s -> %d finding(s)",
                query[:40], ",".join(picked), len(result.findings))
    return result
