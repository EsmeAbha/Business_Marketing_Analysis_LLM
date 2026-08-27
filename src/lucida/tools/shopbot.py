"""The customer-facing shop bot.

A customer messages the Telegram bot and gets an answer without the owner
having to be awake: what is in stock, what it costs, what delivery comes to,
and a place to leave a review.

Two ideas hold this file together
---------------------------------
**Facts come from the database. The model only chooses words.** Stock and
prices are read from `products` and `inventory` and pasted in verbatim. The
model is handed those facts and asked to phrase a reply; it is never asked
what the shop sells or what anything costs. A bot that invents a price is
worse than no bot, because the customer turns up expecting something real.

**A conversation is not a pile of unrelated questions.** "How much for 2?"
and "ok I want it" only mean something if you remember what was being
discussed. Each chat therefore carries a little state - the product last
talked about, how many, and what the shop is waiting for - so the thread
reads as one conversation instead of a stranger answering each line cold.
That memory is why the bot no longer answers "when will it arrive" with the
price list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.shopbot")

INTENTS = ("catalogue", "price", "availability", "delivery", "review",
           "order", "greeting", "smalltalk", "other")

# --- what the customer is doing -------------------------------------------
#
# Every pattern below is a raw string. `\b` in a normal Python string is a
# backspace character, not a word boundary, and the resulting regex matches
# nothing at all - silently.

_GREETING = re.compile(
    r"^\s*(/start|hi+|hey+|hello|salam|assalamu|আসসালাম|হ্যালো)\b", re.I)
_CATALOGUE = re.compile(
    r"\b(what.*(sell|have|available|got)|show.*(product|item)|menu|catalog|"
    r"price list|ki ki|কি কি)\b", re.I)
_PRICE = re.compile(r"\b(price|cost|koto|kto|dam|taka|৳|how much|দাম|কত)\b", re.I)
_REVIEW = re.compile(r"\b(/review|review|feedback|rating|rate|stars?|★|রিভিউ)\b", re.I)
_ORDER = re.compile(
    r"\b(/order|order|buy|nibo|nebo|chai|want|take it|লাগবে|নিবো)\b", re.I)
_DELIVERY = re.compile(
    r"\b(deliver|delivery|shipping|courier|pathao|pouchabe|dibe|"
    r"charge koto|kivabe pabo|home delivery)\b", re.I)
_THANKS = re.compile(
    r"\b(thanks|thank you|thx|dhonnobad|ধন্যবাদ|bye|ok|okay|acha|আচ্ছা)\b", re.I)
#: "thik ache" is an acceptance, not thanks - a customer who says it has
#: agreed, and answering "you are welcome" drops the order on the floor.
#: Bare "acha" is left out on purpose: on its own it is usually just "I see".
_YES = re.compile(
    r"^\s*(yes|yeah|yep|ok|okay|sure|hae|ha|জি|হ্যাঁ|i want it|want it|"
    r"take it|confirm|deal)\b|\b(thik ache|thik ase|thik achhe|ঠিক আছে)\b",
    re.I)
_WHEN = re.compile(
    r"\b(when|kobe|koto din|how long|arrive|how many days|pouchabe kobe)\b", re.I)
#: "it", "that one", "this" - only meaningful with something remembered.
_PRONOUN = re.compile(r"\b(it|that|this|those|ta|ti|oita|eita)\b", re.I)

_STARS = re.compile(r"\b([1-5])\b\s*(?:/\s*5|star|stars|★)?", re.I)
#: What a tapped star button sends back.
_RATE_TAP = re.compile(r"^\s*/rate\s+([1-5])\b", re.I)

#: The keyboard itself. One row, so it fits a phone without wrapping.
STAR_BUTTONS = [[(f"{n} {'★' * n}", f"/rate {n}") for n in range(1, 6)]]

# --- addresses -------------------------------------------------------------
#
# A usable address needs a place AND a street or house line. A city on its own
# is not somewhere a rider can go, so it is answered by asking for the rest.

_AREA_WORDS = re.compile(
    r"\b(dhanmondi|gulshan|banani|uttara|mirpur|mohakhali|bashundhara|badda|"
    r"motijheel|tejgaon|rampura|khilgaon|shyamoli|farmgate|azimpur|lalmatia|"
    r"jatrabari|savar|narayanganj|gazipur|chattogram|chittagong|sylhet|"
    r"khulna|rajshahi|barisal|rangpur|mymensingh|dhaka|comilla|bogura)\b", re.I)
_STREET = re.compile(
    r"\b(road|rd|house|flat|block|sector|lane|street|avenue|apt|floor|"
    r"building|bari|holding)\b|\d{1,4}", re.I)

# A count only counts when the customer led with it, or attached it to a
# counting word. A bare number mid-line is a house number far more often.
_QTY_LEAD = re.compile(r"^\s*(\d{1,3})\b")
_QTY_WORD = re.compile(
    r"(\d{1,3})\s*(?:x|pcs|pc|pieces?|ta|ti|khana|lagbe|chai|nibo|nebo)\b", re.I)
_QTY_X = re.compile(r"x\s*(\d{1,3})", re.I)
#: "how much for 2" - "for" is what makes the number a count and not a house.
_QTY_FOR = re.compile(r"\bfor\s+(\d{1,3})\b", re.I)
#: "i want 5", "amake 5 dao", "give me 3". The verb is what marks the number
#: as a count: without one, a bare digit mid-sentence is usually a house
#: number, which is why this is a listed verb and not "any number anywhere".
_QTY_VERB = re.compile(
    r"\b(?:want|need|order|take|buy|get|give\s+me|send\s+me|send|dao|den|"
    r"nibo|nebo|chai|lagbe|dorkar)\s+(?:me\s+)?(\d{1,3})\b", re.I)


@dataclass
class BotReply:
    text: str
    intent: str
    handled: bool = True
    used_model: bool = False
    #: Rows of (label, payload) offered as tappable buttons. A rating is a
    #: thing to pick, not to spell: asking someone to type "4" invites "four",
    #: "4/5", "four stars" and a silence when they cannot be bothered.
    buttons: list[list[tuple[str, str]]] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Per-chat memory
# ---------------------------------------------------------------------------
#
# Small on purpose: the product under discussion, how many of it, and what the
# shop is waiting for. That is enough to make the thread cohere, and little
# enough that a stale row can never produce a wrong price - prices are always
# re-read from the database.

_STATE_TABLE = """CREATE TABLE IF NOT EXISTS bot_state (
    chat_id        TEXT PRIMARY KEY,
    last_product   TEXT,
    last_qty       INTEGER DEFAULT 1,
    awaiting       TEXT,
    pending_area   TEXT,
    pending_review INTEGER DEFAULT 0,
    updated_at     TEXT)"""

#: Columns added after the table first shipped, in the order they arrived.
_STATE_COLUMNS = (("pending_area", "TEXT"), ("pending_review", "INTEGER DEFAULT 0"))


#: Done once per database, not once per message: the ALTER below raises on
#: every run after the first, and a customer sending five lines should not pay
#: for five failed statements. Keyed by file, because the schema belongs to
#: the database rather than to this process - two of them in one run (a test
#: suite, say) each need their own table.
_STATE_READY: set[str] = set()


def _ensure_state(db) -> None:
    """The table, and the column added to it after the table first shipped."""
    key = str(getattr(db, "_path", "") or id(db))
    if key in _STATE_READY:
        return
    db.execute(_STATE_TABLE)
    for column, spec in _STATE_COLUMNS:
        try:
            db.execute(f"ALTER TABLE bot_state ADD COLUMN {column} {spec}")
        except Exception:  # noqa: BLE001 - already there, the normal case
            pass
    _STATE_READY.add(key)


def get_state(db, chat_id: str) -> dict[str, Any]:
    """What this chat was last talking about."""
    if not chat_id:
        return {}
    try:
        _ensure_state(db)
        rows = db.query("SELECT * FROM bot_state WHERE chat_id=?", (str(chat_id),))
        return dict(rows[0]) if rows else {}
    except Exception as exc:  # noqa: BLE001 - a lost thread is not a crash
        logger.warning("bot state read failed: %s", exc)
        return {}


def set_state(db, chat_id: str, **fields: Any) -> None:
    """Remember, merging with whatever is already there."""
    if not chat_id:
        return
    try:
        _ensure_state(db)
        current = get_state(db, chat_id)
        product = fields.get("last_product", current.get("last_product") or "")
        qty = int(fields.get("last_qty", current.get("last_qty") or 1) or 1)
        awaiting = fields.get("awaiting", current.get("awaiting") or "")
        area = fields.get("pending_area", current.get("pending_area") or "")
        pending = int(fields.get("pending_review",
                                 current.get("pending_review") or 0) or 0)
        db.execute(
            "INSERT INTO bot_state (chat_id, last_product, last_qty, awaiting,"
            " pending_area, pending_review, updated_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(chat_id) DO UPDATE SET last_product=excluded.last_product,"
            " last_qty=excluded.last_qty, awaiting=excluded.awaiting,"
            " pending_area=excluded.pending_area,"
            " pending_review=excluded.pending_review,"
            " updated_at=excluded.updated_at",
            (str(chat_id), product, qty, awaiting, area, pending, _now()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("bot state write failed: %s", exc)


# ---------------------------------------------------------------------------
# Reading the shop
# ---------------------------------------------------------------------------


def catalogue(db) -> tuple[list[dict], list[dict]]:
    """(in stock, out of stock). Only priced products are offered for sale."""
    rows = db.inventory_view()
    live = [r for r in rows if (r.get("sell_price") or 0) > 0]
    return ([r for r in live if (r.get("quantity") or 0) > 0],
            [r for r in live if (r.get("quantity") or 0) <= 0])


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
    rows = [r for r in db.inventory_view() if (r.get("sell_price") or 0) > 0]
    if not rows:
        return None
    low = (text or "").lower()

    def in_stock(r: dict) -> int:
        return 1 if (r.get("quantity") or 0) > 0 else 0

    exact = [r for r in rows if str(r["name"]).lower() in low]
    if exact:
        # Two products can both match; the one they can actually buy wins.
        return sorted(exact, key=lambda r: (in_stock(r), len(str(r["name"]))))[-1]

    scored = []
    for r in rows:
        words = {w for w in re.findall(r"[a-z0-9]+", str(r["name"]).lower())
                 if len(w) > 2}
        hits = sum(1 for w in words if w in low)
        if hits:
            scored.append((hits, in_stock(r), r))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]))
    return scored[-1][2]


def short_of_stock(product: dict, qty: int) -> str:
    """What to say when the shop cannot fill the order, or '' when it can.

    A promise the shelf cannot keep is the one mistake a customer travels
    for, so this is checked before an order is confirmed rather than when
    the owner comes to pack it.
    """
    stock = int(product.get("quantity") or 0)
    name = product["name"]
    if stock <= 0:
        return f"Sorry, {name} is sold out right now."
    if qty > stock:
        each = _money(product.get("sell_price"))
        return (f"We only have {stock} {name} in stock right now, {each} "
                f"each. Would you like {stock}?")
    return ""


def by_name(db, name: str) -> dict | None:
    """Re-read a remembered product, so its price and stock are current."""
    if not name:
        return None
    for r in db.inventory_view():
        if str(r["name"]).lower() == str(name).lower():
            return r
    return None


def _qty_in(text: str) -> int:
    """How many, but only when it is unambiguous.

    A house number is a digit too. Reading "House 7" as seven candles would
    quote the customer the wrong total, so a bare number mid-line is ignored.
    """
    for pattern in (_QTY_LEAD, _QTY_WORD, _QTY_X, _QTY_FOR, _QTY_VERB):
        m = pattern.search(text or "")
        if m:
            n = int(m.group(1))
            if 1 <= n <= 200:
                return n
    return 1


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


# ---------------------------------------------------------------------------
# The answers - every number below comes from the database
# ---------------------------------------------------------------------------


def _catalogue_text(db) -> str:
    """Just the names and the prices."""
    in_stock, out = catalogue(db)
    if not in_stock and not out:
        return "We are still setting up our list - check back shortly."
    lines = [f"{r['name']} - {_money(r.get('sell_price'))}" for r in in_stock]
    lines += [f"{r['name']} - sold out" for r in out]
    return chr(10).join(lines)


def _product_text(row: dict, qty: int = 1) -> str:
    """One line, the way a shopkeeper answers.

    How many are on the shelf is the shop's business, not the customer's. They
    asked whether they can buy it and what it costs, so that is what comes
    back. A count appears only as "the last few", and only because it changes
    whether someone should hurry.
    """
    stock = int(row.get("quantity") or 0)
    price = float(row.get("sell_price") or 0)
    if stock <= 0:
        return f"Sorry, {row['name']} is sold out right now."
    if qty > 1:
        if qty > stock:
            return (f"We only have {stock} {row['name']} left, "
                    f"{_money(price)} each.")
        return (f"{qty} x {row['name']} is {_money(price * qty)} "
                f"({_money(price)} each).")
    if stock <= int(row.get("reorder_level") or 0):
        return f"Yes, we have it. {row['name']} is {_money(price)} - last few left."
    return f"Yes, we have it. {row['name']} is {_money(price)}."


def record_review(db, customer: str, text: str, product: str = "",
                  rating: int | None = None) -> int:
    """Store a review. The rating is parsed from the words unless given."""
    if rating is None:
        m = _STARS.search(text or "")
        rating = int(m.group(1)) if m else 0
    db.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               customer TEXT, product_name TEXT, rating INTEGER,
               comment TEXT, channel TEXT, created_at TEXT)""")
    return db.execute(
        "INSERT INTO reviews (customer, product_name, rating, comment, channel,"
        " created_at) VALUES (?,?,?,?,?,?)",
        (customer, product, rating, (text or "").strip(), "telegram", _now()))


def _has_words(text: str) -> bool:
    """Is there an opinion here, or only a number?"""
    return len(re.sub(r"[^a-z\u0980-\u09FF]+", "", (text or "").lower())) > 3


def add_review_words(db, review_id: int, text: str) -> None:
    """Attach the "why" to a rating already stored."""
    if not review_id:
        return
    try:
        db.execute("UPDATE reviews SET comment=? WHERE id=?",
                   ((text or "").strip(), int(review_id)))
    except Exception as exc:  # noqa: BLE001 - the rating is already safe
        logger.warning("review comment update failed: %s", exc)


def reviews(db, limit: int = 50) -> list[dict]:
    try:
        return db.query("SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,))
    except Exception:  # noqa: BLE001 - the table appears with the first review
        return []


def delivery_text(db, product: dict | None, address: str, qty: int = 1) -> str:
    """What delivery costs to that address, priced from the courier's rates."""
    from . import delivery_pricing

    profile = db.get_profile() or {}
    shop_place = str(profile.get("location") or "")
    kind = delivery_pricing.classify_address(
        area=address, city=address, shop_city=shop_place, shop_area=shop_place)

    items = ([{"product_name": product["name"], "quantity": max(1, qty)}]
             if product else [])
    try:
        q = delivery_pricing.quote(db, items, kind=kind, is_cod=True)
    except Exception as exc:  # noqa: BLE001 - never show a customer a traceback
        logger.warning("delivery quote failed: %s", exc)
        return "The owner will confirm the delivery charge shortly."

    cur = settings.currency
    charge = q.delivery_charge if q.known else 0

    if product is None:
        if charge:
            return (f"Delivery there is {charge:,.0f} {cur}. "
                    f"Which one would you like?")
        return "Got it. Which one would you like?"

    goods = float(product.get("sell_price") or 0) * max(1, qty)
    head = f"{qty} x {product['name']}" if qty > 1 else str(product["name"])
    if not charge:
        return (f"{head} is {goods:,.0f} {cur}. The owner will confirm the "
                f"delivery charge shortly.")
    total = goods + charge + (q.cod_fee or 0)
    return (f"{head} is {goods:,.0f} {cur}, delivery {charge:,.0f} {cur}. "
            f"Total {total:,.0f} {cur} cash on delivery. "
            f"The owner will confirm and send it out.")


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
    if _DELIVERY.search(t):
        return "delivery"
    if _PRICE.search(t):
        return "price"
    if _ORDER.search(t):
        return "order"
    if _THANKS.search(t):
        return "smalltalk"
    return "other"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def answer(db, message: str, customer: str = "there", chat_id: str = "") -> BotReply:
    """Compose a reply to one customer message, in the context of the chat.

    Deterministic first. The model is consulted only when the shop's own data
    cannot answer, and even then it is handed the facts and told not to add to
    them.
    """
    text = (message or "").strip()
    intent = classify(text)
    state = get_state(db, chat_id)
    shop = (db.get_profile() or {}).get("business_name") or "our shop"
    remembered = by_name(db, str(state.get("last_product") or ""))

    # --- the answer to "how did we do?" -----------------------------------
    # This runs before anything tries to read the line as a product, because
    # "lovely candle, smells great" is an opinion, and answering it with a
    # price is how a review gets lost.
    tap = _RATE_TAP.match(text)
    if tap:
        score = int(tap.group(1))
        rid = record_review(db, customer, "", str(state.get("last_product") or ""),
                            rating=score)
        set_state(db, chat_id, awaiting="review_why", pending_review=rid)
        return BotReply(
            f"Thank you - {score} out of 5. What made it that score? Send a "
            f"line and the owner will read it.", "review")

    if str(state.get("awaiting") or "").startswith("review"):
        # We asked "what made it that score?", so whatever comes back is the
        # answer. Reading it for intent first meant a review that happened to
        # mention delivery — "lovely smell, delivery was quick" — was taken
        # for a delivery question and the customer's words were thrown away.
        # Only a fresh command is a change of subject.
        answering_us = (state.get("awaiting") == "review_why"
                        and not text.startswith("/"))
        if answering_us or intent in ("review", "other", "smalltalk"):
            if state.get("awaiting") == "review_why":
                add_review_words(db, int(state.get("pending_review") or 0), text)
                set_state(db, chat_id, awaiting="", pending_review=0)
                return BotReply("Thank you, that means a lot. The owner will "
                                "see it.", "review")
            rid = record_review(db, customer, text,
                                str(state.get("last_product") or ""))
            # They sent the number but not the reason we asked for. Ask for
            # it, and keep the row so the answer lands on the same review.
            if not _has_words(text):
                set_state(db, chat_id, awaiting="review_why", pending_review=rid)
                return BotReply("Thanks! And what made it that score?", "review")
            set_state(db, chat_id, awaiting="", pending_review=0)
            return BotReply("Thank you, that means a lot. The owner will see it.",
                            "review")
        # They asked a real question instead. Answer it, and stop waiting.
        set_state(db, chat_id, awaiting="", pending_review=0)
        state = get_state(db, chat_id)

    # --- who are we talking about? ---------------------------------------
    # A named product always wins. Otherwise the remembered one stands in,
    # but only when the message is plainly about something already discussed.
    named = find_product(db, text)
    address = address_in(text)
    # The shop asked for "the house or road number with the area", so the
    # customer sends the half it does not have yet. Rejecting that for not
    # being a whole address on its own asks the same question forever, so
    # the two halves are joined instead.
    if not address and state.get("awaiting") == "address" and state.get("pending_area"):
        joined = f"{text.strip()}, {state['pending_area']}"
        address = address_in(joined)
    # An address is the answer to a question the shop asked, so whatever was
    # being discussed is still the subject even though the line names no
    # product. Without this the bot asks "which one would you like?" of a
    # customer who has already said, which reads as having stopped listening.
    refers_back = bool(
        _PRONOUN.search(text) or _YES.search(text) or _WHEN.search(text)
        or address or intent in ("price", "order", "delivery"))
    product = named or (remembered if refers_back else None)

    # An address is full of digits and none of them are counts: "7 Road 3" is
    # a house, not seven candles. On an address, carry the count over instead
    # of reading one out of the street.
    qty = 1 if address else _qty_in(text)
    if qty == 1 and (address or not _QTY_LEAD.search(text)) and state.get("last_qty"):
        qty = int(state["last_qty"] or 1)
    if product is not None:
        set_state(db, chat_id, last_product=str(product["name"]), last_qty=qty)

    # --- greeting ---------------------------------------------------------
    if intent == "greeting":
        set_state(db, chat_id, awaiting="")
        return BotReply(
            f"Hello! Welcome to {shop}. Ask me about anything you are after "
            f"and I will tell you the price.", intent)

    # --- review -----------------------------------------------------------
    # "/review" on its own is a request to leave one, not the review itself.
    # Filing the command as the customer's opinion stored a rating of 0 and a
    # comment of "/review", and left the rating they sent next with nothing to
    # attach itself to.
    if intent == "review":
        said = _REVIEW.sub(" ", text).strip(" ,.-\u2014")
        if _STARS.search(said) or len(said) > 10:
            record_review(db, customer, said, str(state.get("last_product") or ""))
            set_state(db, chat_id, awaiting="")
            return BotReply("Thank you, that means a lot. The owner will see it.",
                            intent)
        set_state(db, chat_id, awaiting="review")
        return BotReply("How did we do? Tap a star, then tell me why.",
                        intent, buttons=STAR_BUTTONS)

    # --- a full address, which is what an order actually needs ------------
    if address:
        set_state(db, chat_id, awaiting="", pending_area="")
        short = short_of_stock(product, qty) if product is not None else ""
        if short:
            return BotReply(short, "availability")
        return BotReply(delivery_text(db, product, address, qty), "delivery")

    # --- half an address --------------------------------------------------
    if _AREA_WORDS.search(text) and len(text) < 60 and not _CATALOGUE.search(text):
        set_state(db, chat_id, awaiting="address", pending_area=text.strip())
        return BotReply(
            "Almost there - send the house or road number with the area and I "
            "will work out the delivery charge.", "delivery")

    # --- we asked for an address and got something else -------------------
    if state.get("awaiting") == "address" and intent in ("other", "smalltalk"):
        return BotReply(
            "Send your full address - house or road, and the area - and I will "
            "give you the total.", "delivery")

    # --- yes / I will take it --------------------------------------------
    if (_YES.search(text) or intent == "order") and product is not None:
        # Check the shelf before taking the order. Asking for an address
        # first and finding out afterwards that only three are left is how a
        # shop loses a customer it had already won.
        short = short_of_stock(product, qty)
        if short:
            stock = int(product.get("quantity") or 0)
            if stock > 0:
                set_state(db, chat_id, last_qty=stock, awaiting="")
            return BotReply(short, "availability")
        set_state(db, chat_id, awaiting="address")
        head = f"{qty} x {product['name']}" if qty > 1 else str(product["name"])
        return BotReply(
            f"Lovely - {head}. Send your full address and I will tell you the "
            f"delivery charge and the total.", "order")

    # --- when will it come ------------------------------------------------
    if _WHEN.search(text):
        return BotReply(
            "Usually one to three days once the order is confirmed. Send your "
            "address and the owner will confirm the day.", "delivery")

    # --- delivery, before we know the address -----------------------------
    if intent == "delivery":
        set_state(db, chat_id, awaiting="address")
        if product is not None:
            return BotReply(
                f"Yes, we deliver. {product['name']} is "
                f"{_money(product.get('sell_price'))}. Send your full address "
                f"and I will tell you the delivery charge.", "delivery")
        return BotReply(
            "Yes, we deliver anywhere in the country. Send your full address "
            "and I will tell you the charge.", "delivery")

    # --- a product, named or remembered -----------------------------------
    if product is not None and intent in ("price", "availability", "order", "other"):
        return BotReply(_product_text(product, qty), "price")

    # --- they asked for something we do not stock -------------------------
    if intent in ("price", "availability") and named is None:
        in_stock, _ = catalogue(db)
        if not in_stock:
            return BotReply(
                "We are out of everything at the moment - please check back soon.",
                "availability")
        return BotReply(
            "We do not have that one. We do have:" + chr(10) + chr(10)
            + _catalogue_text(db), "catalogue")

    # --- the list, when it was actually asked for -------------------------
    if intent == "catalogue":
        return BotReply(_catalogue_text(db), intent)

    # --- thanks -----------------------------------------------------------
    if intent == "smalltalk":
        return BotReply("You are welcome. Just ask if you need anything else.",
                        intent)

    # --- anything else ----------------------------------------------------
    # Deliberately NOT the product list. Repeating the catalogue at someone who
    # asked something else is exactly what made the bot feel like it had
    # stopped listening.
    drafted = _model_reply(db, text, shop, state)
    if drafted:
        return BotReply(drafted, "other", used_model=True)
    return BotReply(
        "I am not sure about that one - the owner will reply shortly. In the "
        "meantime I can tell you prices and delivery charges.", "other")


def _model_reply(db, question: str, shop: str, state: dict) -> str:
    """Phrase an answer from supplied facts. Returns '' if unavailable."""
    if not settings.has_llm:
        return ""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from ..llm import get_llm

        in_stock, out = catalogue(db)
        nl = chr(10)
        facts = nl.join(
            [f"IN STOCK: {r['name']} - {_money(r.get('sell_price'))}"
             for r in in_stock]
            + [f"SOLD OUT: {r['name']}" for r in out]
        ) or "(no products listed yet)"
        context = ""
        if state.get("last_product"):
            context = f"{nl}They were just asking about: {state['last_product']}."

        system = (
            f"You are the assistant for {shop}, replying to a customer on "
            f"Telegram.{nl}{nl}"
            f"Rules:{nl}"
            f"- ONE short sentence. A shopkeeper answering, not a brochure.{nl}"
            f"- Use ONLY the facts below. Never invent a product, price, "
            f"discount or delivery time. If they are not enough, say the owner "
            f"will reply shortly.{nl}"
            f"- Never list stock quantities. Never say 'reply with how many'.{nl}"
            f"- Reply in the language the customer used (Bangla, Banglish or "
            f"English).{nl}{nl}"
            f"SHOP FACTS{nl}{facts}{context}"
        )
        out_msg = get_llm(max_tokens=200).invoke(
            [SystemMessage(content=system), HumanMessage(content=question)])
        content = out_msg.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text")
        return str(content).strip()[:600]
    except Exception as exc:  # noqa: BLE001 - the shop must not go silent
        logger.warning("shopbot model reply failed, using template: %s", exc)
        return ""
