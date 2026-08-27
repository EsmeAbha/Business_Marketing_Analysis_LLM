"""The customer-facing shop bot.

A customer messages the Telegram bot and gets an answer without the owner
having to be awake: what is in stock, what it costs, what has run out, and a
place to leave a review.

The split that matters
----------------------
**Facts come from the database. The model only chooses words.**

Stock levels and prices are read straight from `products` and `inventory` and
pasted into the reply verbatim. The model is given that data and asked to
phrase a response; it is never asked what the shop sells or what anything
costs. A bot that invents a price, or promises stock the shop does not have,
is worse than no bot at all — the customer turns up expecting something real.

If the model is unavailable the bot still answers, from a plain template. The
shop does not go silent because a free tier ran out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.shopbot")

# What the customer is trying to do. Deliberately a small, closed set: every
# one of these can be answered from the shop's own records.
INTENTS = ("catalogue", "price", "availability", "review", "order", "greeting", "other")

_GREETING = re.compile(r"^\s*(/start|hi+|hey+|hello|salam|assalamu|আসসালাম|হ্যালো)\b", re.I)
_CATALOGUE = re.compile(
    r"\b(what.*(sell|have|available)|product|menu|list|catalog|ki ki|ache|আছে|কি কি)\b", re.I)
_PRICE = re.compile(r"\b(price|cost|koto|kto|dam|taka|৳|dhaka|how much|দাম|কত)\b", re.I)
_REVIEW = re.compile(r"\b(/review|review|feedback|rating|rate|stars?|★|মতামত|রিভিউ)\b", re.I)
_ORDER = re.compile(r"\b(/order|order|buy|nibo|nebo|chai|want|লাগবে|নিবো)\b", re.I)
_STARS = re.compile(r"([1-5])\s*(?:/\s*5|star|stars|★)?", re.I)


@dataclass
class BotReply:
    text: str
    intent: str
    handled: bool = True
    used_model: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Reading the shop
# ---------------------------------------------------------------------------


def catalogue(db) -> tuple[list[dict], list[dict]]:
    """(in stock, out of stock). Only priced products are offered for sale."""
    rows = db.inventory_view()
    live = [r for r in rows if (r.get("sell_price") or 0) > 0]
    in_stock = [r for r in live if (r.get("quantity") or 0) > 0]
    out = [r for r in live if (r.get("quantity") or 0) <= 0]
    return in_stock, out


def _money(value: Any) -> str:
    try:
        return f"{float(value):,.0f} {settings.currency}"
    except (TypeError, ValueError):
        return f"? {settings.currency}"


def find_product(db, text: str) -> dict | None:
    """Best product match for whatever the customer typed.

    Substring first, then a word-overlap score, so "do you have paratha" finds
    "Frozen Paratha Pack" without needing the exact name.
    """
    # Only priced products are sellable, so only they are matchable. An
    # unpriced row would answer "? BDT", which is worse than saying nothing.
    rows = [r for r in db.inventory_view() if (r.get("sell_price") or 0) > 0]
    if not rows:
        return None
    low = text.lower()

    def in_stock(r: dict) -> int:
        return 1 if (r.get("quantity") or 0) > 0 else 0

    exact = [r for r in rows if str(r["name"]).lower() in low]
    if exact:
        # Two products can both match; the one the customer can actually buy wins.
        return sorted(exact, key=lambda r: (in_stock(r), len(str(r["name"]))))[-1]

    scored = []
    for r in rows:
        words = {w for w in re.findall(r"[a-z0-9]+", str(r["name"]).lower()) if len(w) > 2}
        if not words:
            continue
        score = sum(1 for w in words if w in low)
        if score:
            scored.append((score, in_stock(r), r))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]))
    return scored[-1][2]


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


def classify(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "other"
    if _GREETING.search(t):
        return "greeting"
    if _REVIEW.search(t):
        return "review"
    if _CATALOGUE.search(t):
        return "catalogue"
    if _PRICE.search(t):
        return "price"
    if _ORDER.search(t):
        return "order"
    return "other"


# ---------------------------------------------------------------------------
# The answers — every number below comes from the database
# ---------------------------------------------------------------------------


def _catalogue_text(db) -> str:
    in_stock, out = catalogue(db)
    if not in_stock and not out:
        return ("We are still setting up our product list. "
                "Please check back shortly.")

    lines = []
    if in_stock:
        lines.append("Available now:")
        for r in in_stock:
            qty = int(r.get("quantity") or 0)
            low = "  (only a few left)" if qty <= int(r.get("reorder_level") or 0) else ""
            lines.append(f"• {r['name']} — {_money(r.get('sell_price'))}{low}")
    if out:
        lines.append("")
        lines.append("Out of stock right now:")
        for r in out:
            lines.append(f"• {r['name']} — back soon")
    lines.append("")
    lines.append("Reply with a product name for details, or /review to leave feedback.")
    return "\n".join(lines)


def _product_text(row: dict) -> str:
    qty = int(row.get("quantity") or 0)
    price = _money(row.get("sell_price"))
    if qty <= 0:
        return (f"{row['name']} is **out of stock** at the moment.\n"
                f"The price when it returns is {price}. "
                f"Tell us if you would like to be told when it is back.")
    scarce = qty <= int(row.get("reorder_level") or 0)
    tail = "  Only a few left." if scarce else ""
    return (f"{row['name']} — {price}\n"
            f"In stock: yes ({qty} available).{tail}\n"
            f"Reply with how many you would like and we will hold them for you.")


def record_review(db, customer: str, text: str, product: str = "") -> int:
    """Store a review. Rating is parsed if the customer gave one."""
    m = _STARS.search(text or "")
    rating = int(m.group(1)) if m else 0
    db.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               customer TEXT, product_name TEXT, rating INTEGER,
               comment TEXT, channel TEXT, created_at TEXT)"""
    )
    return db.execute(
        "INSERT INTO reviews (customer, product_name, rating, comment, channel, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (customer, product, rating, (text or "").strip(), "telegram", _now()),
    )


def reviews(db, limit: int = 50) -> list[dict]:
    try:
        return db.query("SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,))
    except Exception:  # noqa: BLE001 — table only exists once one is left
        return []


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def answer(db, message: str, customer: str = "there") -> BotReply:
    """Compose a reply to one customer message.

    Deterministic first. The model is consulted only to phrase an answer whose
    facts have already been established, and only when the question does not
    map cleanly onto the shop's own data.
    """
    text = (message or "").strip()
    intent = classify(text)
    shop = (db.get_profile() or {}).get("business_name") or "our shop"

    if intent == "greeting":
        in_stock, _ = catalogue(db)
        return BotReply(
            f"Hello! Welcome to {shop}.\n\n"
            f"We have {len(in_stock)} item(s) available today. "
            f"Ask me what we sell, ask the price of anything, "
            f"or send /review to leave feedback.",
            intent)

    if intent == "review":
        rid = record_review(db, customer, text)
        m = _STARS.search(text)
        if m or len(text) > 25:
            return BotReply(
                "Thank you — your review has been saved and the owner will see it. "
                "We read every one.", intent)
        return BotReply(
            "We would love your feedback. Reply with a rating out of 5 and a "
            "sentence about what you thought.", intent)

    row = find_product(db, text)

    if intent in ("price", "availability", "order") or row is not None:
        if row is not None:
            resolved = intent if intent in ("price", "availability", "order") else "price"
            return BotReply(_product_text(row), resolved)
        in_stock, _ = catalogue(db)
        if not in_stock:
            return BotReply(
                "We have nothing in stock at the moment — please check back soon.",
                "availability")
        return BotReply(
            "I could not find that one. Here is what we have today:\n\n"
            + _catalogue_text(db), "catalogue")

    if intent == "catalogue":
        return BotReply(_catalogue_text(db), intent)

    # Anything else: let the model phrase it, but hand it the facts and forbid
    # inventing any. If it is unavailable, fall back to the catalogue.
    drafted = _model_reply(db, text, shop)
    if drafted:
        return BotReply(drafted, "other", used_model=True)
    return BotReply(
        "Thanks for your message. Here is what we have today:\n\n"
        + _catalogue_text(db), "catalogue")


def _model_reply(db, question: str, shop: str) -> str:
    """Phrase an answer from supplied facts. Returns '' if unavailable."""
    if not settings.has_llm:
        return ""
    try:
        from ..llm import get_llm
        from langchain_core.messages import HumanMessage, SystemMessage

        in_stock, out = catalogue(db)
        facts = "\n".join(
            [f"IN STOCK: {r['name']} — {_money(r.get('sell_price'))} "
             f"({int(r.get('quantity') or 0)} available)" for r in in_stock]
            + [f"OUT OF STOCK: {r['name']}" for r in out]
        ) or "(the shop has no products listed yet)"

        system = (
            f"You are the assistant for {shop}, replying to a customer on Telegram.\n\n"
            "Rules:\n"
            "- Use ONLY the stock and price facts given below. Never invent a product, "
            "a price, a delivery time or a discount. If the facts do not answer the "
            "question, say you will pass it to the owner.\n"
            "- Two or three sentences. Warm, plain, no marketing voice.\n"
            "- Reply in the same language the customer used (Bangla, Banglish or "
            "English).\n\n"
            f"SHOP FACTS\n{facts}"
        )
        out_msg = get_llm(max_tokens=400).invoke(
            [SystemMessage(content=system), HumanMessage(content=question)])
        content = out_msg.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text")
        return str(content).strip()[:900]
    except Exception as exc:  # noqa: BLE001 — the shop must not go silent
        logger.warning("shopbot model reply failed, using template: %s", exc)
        return ""
