"""Live exchange rates, from a free source that needs no account.

open.er-api.com publishes daily rates with no key and no sign-up, which is
what makes it usable here: every other integration in this project degrades
to a labelled simulation when a credential is missing, and a rate nobody can
fetch would be one more of those.

Used for the one thing an owner actually needs it for — seeing what a price
in their own currency is worth in another, when a supplier quotes in USD or a
customer asks. Rates are cached for six hours; they only move daily, and a
dashboard should not make a network call per render.

If the fetch fails the answer is `None`, never a stale guess dressed up as
today's rate.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.fx")

ENDPOINT = "https://open.er-api.com/v6/latest/{base}"
CACHE_SECONDS = 6 * 3600

_lock = threading.RLock()
_cache: dict[str, tuple[float, dict[str, float]]] = {}


def _fetch(base: str) -> dict[str, float] | None:
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get(ENDPOINT.format(base=base.upper()))
        if r.status_code != 200:
            logger.warning("fx: provider returned %s", r.status_code)
            return None
        data: dict[str, Any] = r.json()
        if data.get("result") != "success" or not data.get("rates"):
            logger.warning("fx: unusable response")
            return None
        return {k: float(v) for k, v in data["rates"].items()}
    except Exception as exc:  # noqa: BLE001 — a rate is never worth an outage
        logger.warning("fx: %s", exc)
        return None


def rates(base: str | None = None) -> dict[str, float] | None:
    """Every rate against `base`, cached. None when the lookup failed."""
    base = (base or settings.currency or "USD").upper()
    now = time.time()
    with _lock:
        hit = _cache.get(base)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    fresh = _fetch(base)
    if fresh is None:
        return None
    with _lock:
        _cache[base] = (now, fresh)
    logger.info("fx: refreshed %d rates against %s", len(fresh), base)
    return fresh


def convert(amount: float, to: str, base: str | None = None) -> float | None:
    table = rates(base)
    if not table:
        return None
    rate = table.get(to.upper())
    return None if rate is None else amount * rate


def snapshot(base: str | None = None,
             against: tuple[str, ...] = ("USD", "EUR", "INR")) -> dict[str, Any]:
    """A small set of headline rates, for display.

    `available` is False when the provider could not be reached, so a caller
    can say so plainly instead of showing nothing and implying parity.
    """
    base = (base or settings.currency or "USD").upper()
    table = rates(base)
    if not table:
        return {"base": base, "available": False, "rates": {}}
    return {
        "base": base,
        "available": True,
        "rates": {c: table[c] for c in against if c in table and c != base},
    }
