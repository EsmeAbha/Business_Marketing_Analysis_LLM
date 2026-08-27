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
INTENTS = ("catalogue", "price", "availability", "delivery", "review", "order",
           "greeting", "other")

_GREETING = re.compile(r"^\s*(/start|hi+|hey+|hello|salam|assalamu|আসসালাম|হ্যালো)\b", re.I)
_CATALOGUE = re.compile(
    r"\b(what.*(sell|have|available)|product|menu|list|catalog|ki ki|ache|আছে|কি কি)\b", re.I)
_PRICE = re.compile(r"\b(price|cost|koto|kto|dam|taka|৳|dhaka|how much|দাম|কত)\b", re.I)
_REVIEW = re.compile(r"\b(/review|review|feedback|rating|rate|stars?|★|মতামত|রিভিউ)\b", re.I)
_DELIVERY = re.compile(
    "(deliver|delivery|shipping|courier|pathao|pouchabe|dibe|"
    "charge koto|kivabe pabo|home delivery)", re.I)
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
    """Just the names and the prices."""
    in_stock, out = catalogue(db)
    if not in_stock and not out:
        return "We are still setting up our list - check back shortly."
    lines = [f"{r['name']} - {_money(r.get('sell_price'))}" for r in in_stock]
    lines += [f"{r['name']} - sold out" for r in out]
    return chr(10).join(lines)


def _product_text(row: dict) -> str:
    """One line, the way a shopkeeper answers.

    How many are on the shelf is the shop's business, not the customer's.
    They asked whether they can buy it and what it costs, so that is what
    comes back. A count only appears as "the last few", and only because it
    changes whether someone should hurry.
    """
    qty = int(row.get("quantity") or 0)
    price = _money(row.get("sell_price"))
    if qty <= 0:
        return f"Sorry, {row['name']} is sold out right now."
    if qty <= int(row.get("reorder_level") or 0):
        return f"Yes, we have it. {row['name']} is {price} - only the last few left."
    return f"Yes, we have it. {row['name']} is {price}."


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
# Delivery
# ---------------------------------------------------------------------------

# A usable address needs a street or house line AND an area. "Dhaka" alone is
# a city, not somewhere a rider can go, so it is deliberately not enough.
_AREA_WORDS = re.compile(
    "(dhanmondi|gulshan|banani|uttara|mirpur|mohakhali|bashundhara|badda|"
    "motijheel|tejgaon|rampura|khilgaon|shyamoli|farmgate|azimpur|lalmatia|"
    "jatrabari|savar|narayanganj|gazipur|chattogram|chittagong|sylhet|"
    r"khulna|rajshahi|barisal|rangpur|mymensingh|dhaka|comilla|bogura)", re.I)
# A count only counts when the customer led with it ("2 coconut candles")
# or attached it to a counting word ("3 pcs", "x2"). A bare number in the
# middle of a line is a house number far more often than a quantity.
_QTY_LEAD = re.compile(r"^\s*(\d{1,3})\b", re.I)
_QTY_WORD = re.compile(r"(\d{1,3})\s*(?:x|pcs|pc|pieces?|ta|ti)\b", re.I)
_QTY_X = re.compile(r"x\s*(\d{1,3})", re.I)

_STREET = re.compile(
    r"(road|rd|house|flat|block|sector|lane|street|avenue|apt|floor|"
    r"building|bari|holding|\d{1,4})", re.I)


def address_in(text: str) -> str:
    """The address the customer gave, or '' if it is not one yet."""
    t = (text or "").strip()
    if len(t) < 12:
        return ""
    if _AREA_WORDS.search(t) and _STREET.search(t):
        return t
    # A long line with a comma and an area name reads like an address too.
    if _AREA_WORDS.search(t) and "," in t and len(t) > 20:
        return t
    return ""


def delivery_text(db, product: dict | None, address: str, qty: int = 1) -> str:
    """What delivery costs to that address, priced from the courier's rates."""
    from . import delivery_pricing

    profile = db.get_profile() or {}
    kind = delivery_pricing.classify_address(
        area=address, city=address,
        shop_city=str(profile.get("location") or ""),
        shop_area=str(profile.get("location") or ""))

    items = ([{"product_name": product["name"], "quantity": max(1, qty)}]
             if product else [])
    try:
        q = delivery_pricing.quote(db, items, kind=kind, is_cod=True)
    except Exception as exc:  # noqa: BLE001 — never leave a customer with a traceback
        logger.warning("delivery quote failed: %s", exc)
        return ("I could not work out the delivery charge just now - "
                "the owner will confirm it shortly.")

    if not q.known or not q.delivery_charge:
        return ("We deliver there. The owner will confirm the exact charge "
                "shortly.")

    cur = settings.currency
    if product:
        goods = (product.get("sell_price") or 0) * max(1, qty)
        total = goods + q.delivery_charge + (q.cod_fee or 0)
        return (f"{product['name']} is {_money(product.get('sell_price'))}"
                f"{f' x {qty}' if qty > 1 else ''}. "
                f"Delivery to that address is {q.delivery_charge:,.0f} {cur}. "
                f"Total {total:,.0f} {cur} cash on delivery.")
    return f"Delivery to that address is {q.delivery_charge:,.0f} {cur}."


def _qty_in(text: str) -> int:
    """How many, but only when it is unambiguous.

    A house number is a digit too. Reading "House 7" as seven candles
    would quote the customer the wrong total, so a bare number in the
    middle of a line is ignored.
    """
    t = text or ""
    for pattern in (_QTY_LEAD, _QTY_WORD, _QTY_X):
        m = pattern.search(t)
        if m:
            n = int(m.group(1))
            return n if 1 <= n <= 200 else 1
    return 1


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
        return BotReply(
            f"Hello! Welcome to {shop}. Ask me about anything you are after "
            f"and I will tell you the price.", intent)

    if intent == "review":
        record_review(db, customer, text)
        if _STARS.search(text) or len(text) > 25:
            return BotReply("Thank you, that means a lot. The owner will see it.",
                            intent)
        return BotReply("How did we do? Send a rating out of 5 and a line about why.",
                        intent)

    row = find_product(db, text)

    # --- delivery ---------------------------------------------------------
    # An address is only worth pricing when it is one. "Dhaka" is a city, not
    # somewhere a rider can go, so anything short of a street plus an area is
    # answered by asking for the rest rather than by guessing a charge.
    address = address_in(text)
    if address:
        return BotReply(delivery_text(db, row, address, _qty_in(text)), "delivery")

    # An area with no street is half an address. Ask for the rest rather than
    # dropping the customer back into the product list, which is what made it
    # look like the bot had stopped listening.
    if _AREA_WORDS.search(text) and len(text) < 60 and not _CATALOGUE.search(text):
        return BotReply(
            "Almost there - send the house or road number with the area and I "
            "will work out the delivery charge.", "delivery")

    if _DELIVERY.search(text):
        if row is not None:
            return BotReply(
                f"Yes, we deliver. {row['name']} is {_money(row.get('sell_price'))}. "
                f"Send your full address - house or road, and the area - and I "
                f"will tell you the delivery charge.", "delivery")
        return BotReply(
            "Yes, we deliver. Send your full address - house or road, and the "
            "area - and I will tell you the charge.", "delivery")

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
            "We do not have that one. We do have:\n\n"
            + _catalogue_text(db), "catalogue")

    if intent == "catalogue":
        return BotReply(_catalogue_text(db), intent)

    # Anything else: let the model phrase it, but hand it the facts and forbid
    # inventing any. If it is unavailable, fall back to the catalogue.
    drafted = _model_reply(db, text, shop)
    if drafted:
        return BotReply(drafted, "other", used_model=True)
    return BotReply(
        "We sell:\n\n"
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
            "- ONE short sentence. A shopkeeper answering, not a brochure. Never list stock quantities and never say 'reply with how many'.\n"
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
