"""What a delivery costs, and what the customer pays in total.

A courier quote is a function of three things: how heavy the parcel is, where
it is going, and which courier. This works all three out from rows in
`delivery_zones`, so an owner whose courier charges differently edits numbers
rather than waiting on a code change.

Three rules that are easy to get wrong and expensive to get wrong:

  * **Weight is grams, everywhere.** Kilograms as a float invites an argument
    at exactly the boundary where the price steps up — 1000 g must be one
    unit, not two because 1.0000001 rounded up.
  * **Part of a kilo is a whole kilo.** Every courier bills that way, so the
    extra weight is ceil()'d, not rounded.
  * **Nothing is guessed.** A product with no weight recorded does not get an
    assumed one; the quote says the weight is missing and which products need
    it. A confident wrong delivery charge comes out of the owner's margin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..observability import get_logger

logger = get_logger("tools.delivery")

# What an address looks like when the owner has not said. Deliberately the
# dearer of the two: quoting "inside city" for somewhere that turns out to be
# outside loses money on every order until someone notices.
DEFAULT_KIND = "outside_city"


@dataclass
class Quote:
    """A delivery quote, with its own arithmetic shown."""

    weight_g: int = 0
    billable_kg: int = 0
    zone_name: str = ""
    zone_kind: str = ""
    provider: str = ""
    base_charge: float = 0.0
    extra_charge: float = 0.0
    delivery_charge: float = 0.0
    cod_fee: float = 0.0
    goods_total: float = 0.0
    total_charge: float = 0.0
    is_cod: bool = True
    known: bool = True
    problems: list[str] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)

    def explain(self, currency: str = "BDT") -> str:
        """The quote as the owner would say it out loud."""
        if not self.known:
            return "Delivery cannot be quoted yet: " + "; ".join(self.problems)
        bits = [
            f"{self.weight_g:,} g billed as {self.billable_kg} kg",
            f"{self.zone_name} — {currency} {self.base_charge:,.0f} base",
        ]
        if self.extra_charge:
            bits.append(f"{currency} {self.extra_charge:,.0f} for the extra weight")
        if self.cod_fee:
            bits.append(f"{currency} {self.cod_fee:,.0f} cash-on-delivery fee")
        return (
            " · ".join(bits)
            + f" → delivery {currency} {self.delivery_charge:,.0f}"
            + f", customer pays {currency} {self.total_charge:,.0f}"
        )


def classify_address(
    area: str = "",
    city: str = "",
    shop_city: str = "",
    shop_area: str = "",
) -> str:
    """Same area, inside the city, or outside it.

    Deliberately a plain string comparison and nothing cleverer: a wrong guess
    here silently changes what every customer is charged, so it only claims
    the cheaper zone when the text actually matches.
    """
    area_l, city_l = area.strip().lower(), city.strip().lower()
    shop_city_l, shop_area_l = shop_city.strip().lower(), shop_area.strip().lower()

    if not city_l and not area_l:
        return DEFAULT_KIND
    if shop_area_l and area_l and shop_area_l == area_l:
        return "same_area"
    if shop_city_l and city_l and shop_city_l == city_l:
        return "inside_city"
    # The shop's own city named inside a free-text area line.
    if shop_city_l and shop_city_l in f"{area_l} {city_l}":
        return "inside_city"
    return DEFAULT_KIND


def billable_kilos(weight_g: int, base_weight_g: int) -> int:
    """Whole kilos charged *beyond* the base. Part of a kilo bills as one."""
    over = max(0, int(weight_g) - int(base_weight_g))
    return math.ceil(over / 1000) if over else 0


def quote(
    db,
    items: list[dict[str, Any]],
    kind: str = DEFAULT_KIND,
    provider: str = "",
    is_cod: bool = True,
    goods_total: float | None = None,
) -> Quote:
    """Price a delivery.

    `items` are ``{"product_name", "quantity"}`` — weight and price are read
    from the catalogue so the quote cannot disagree with what is on sale.
    """
    q = Quote(is_cod=is_cod, zone_kind=kind, provider=provider)

    # --- weigh the parcel ---------------------------------------------
    total_g = 0
    total_goods = 0.0
    for item in items or []:
        name = str(item.get("product_name") or "").strip()
        qty = max(0, int(item.get("quantity") or 0))
        if not name or not qty:
            continue
        rows = db.query(
            "SELECT name, weight_g, sell_price FROM products WHERE name=?",
            (name,),
        )
        if not rows:
            q.problems.append(f"{name} is not in your catalogue")
            continue
        row = rows[0]
        grams = int(row.get("weight_g") or 0)
        if grams <= 0:
            q.problems.append(f"{name} has no weight recorded")
        total_g += grams * qty
        total_goods += float(row.get("sell_price") or 0) * qty
        q.lines.append({
            "product": name, "quantity": qty,
            "unit_weight_g": grams, "weight_g": grams * qty,
        })

    q.weight_g = total_g
    q.goods_total = goods_total if goods_total is not None else total_goods

    if not q.lines:
        q.problems.append("nothing to deliver")
    if q.problems:
        q.known = False
        logger.info("delivery quote incomplete: %s", "; ".join(q.problems))
        return q

    # --- find the zone -------------------------------------------------
    rows = db.query(
        "SELECT * FROM delivery_zones WHERE kind=? AND active=1 "
        "AND (provider=? OR provider='' OR provider IS NULL) "
        "ORDER BY CASE WHEN provider=? THEN 0 ELSE 1 END LIMIT 1",
        (kind, provider, provider),
    )
    if not rows:
        q.known = False
        q.problems.append(f"no delivery rate set up for '{kind}'")
        return q

    zone = rows[0]
    q.zone_name = str(zone["name"])
    q.provider = str(zone.get("provider") or provider or "")
    q.billable_kg = billable_kilos(total_g, int(zone["base_weight_g"]))
    q.base_charge = float(zone["base_charge"])
    q.extra_charge = q.billable_kg * float(zone["per_kg_extra"])
    q.delivery_charge = q.base_charge + q.extra_charge

    if is_cod:
        pct = float(zone.get("cod_percent") or 0) / 100.0
        q.cod_fee = max(float(zone.get("min_cod_fee") or 0), q.goods_total * pct)

    q.total_charge = q.goods_total + q.delivery_charge + q.cod_fee
    return q


def zones(db) -> list[dict[str, Any]]:
    return db.query(
        "SELECT * FROM delivery_zones WHERE active=1 ORDER BY base_charge"
    )
