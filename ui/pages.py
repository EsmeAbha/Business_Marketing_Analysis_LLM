"""The design's sections, rendered from what the workforce actually knows.

One function per rail entry. Each reads the shared memory the agents write to,
so a section is empty until the agent that owns it has run — that emptiness is
shown as the design's dashed placeholder rather than as invented sample data.

Where the source design showed figures this system cannot compute (sales today,
days-of-cover, cost per customer), the column is either dropped or replaced
with something real. A dashboard that quietly makes numbers up is worse than
one that admits it does not know them yet.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from lucida.config import settings
from lucida.memory import memory
from lucida.pricing import UsageLedger

from ui import theme
from ui.theme import esc, pill, tag

CUR = settings.currency


def _money(value: Any) -> str:
    try:
        return f"{CUR} {float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _tone_for(status: str) -> str:
    s = (status or "").lower()
    if s in ("published", "approved", "delivered", "live", "positive"):
        return "ok"
    if s in ("failed", "rejected", "negative"):
        return "error"
    if s in ("drafted", "new", "pending", "neutral"):
        return "warn"
    return "idle"


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


def customers() -> None:
    theme.page_header(
        "Customers",
        "Every message your shop receives, read and sorted — what they asked "
        "for, how they felt, and which ones are really orders.",
    )

    convos = memory.conversations(200)
    preorders = memory.preorders()

    if not convos and not preorders:
        theme.empty(
            "No customer messages yet. Ask the workforce to read your inbox and "
            "they'll appear here, sorted by intent."
        )
        return

    happy = sum(1 for c in convos if (c.get("sentiment") or "").lower() == "positive")
    unmet = [c for c in convos if (c.get("intent") or "") == "unmet_demand"]
    theme.kpis([
        {"label": "Messages read", "value": len(convos), "note": "across all channels"},
        {"label": "Orders found in chat", "value": len(preorders),
         "note": "pulled out of conversations"},
        {"label": "Happy customers", "value": happy,
         "note": f"of {len(convos)} messages" if convos else ""},
        {"label": "Asked for things you don't sell", "value": len(unmet),
         "note": "feeds the Grow tab", "tone": "warn" if unmet else ""},
    ])

    if convos:
        theme.section("What customers said", f"{len(convos)} messages")
        theme.table(
            ["Customer", "Channel", "Message", "Mood", "Intent"],
            "minmax(0,0.8fr) 110px minmax(0,2fr) 110px 130px",
            [
                [
                    f"<strong>{esc(c.get('customer') or 'Someone')}</strong>",
                    esc(c.get("channel") or "—"),
                    esc((c.get("message") or "")[:120]),
                    pill(c.get("sentiment") or "—", _tone_for(c.get("sentiment", ""))),
                    esc((c.get("intent") or "—").replace("_", " ")),
                ]
                for c in convos[:40]
            ],
        )

    if preorders:
        theme.section("Pre-orders waiting", "nothing is promised until you confirm")
        theme.table(
            ["Customer", "Item", "Qty", "Channel", "Status"],
            "minmax(0,1fr) minmax(0,1.4fr) 80px 120px 120px",
            [
                [
                    f"<strong>{esc(p.get('customer') or '—')}</strong>",
                    esc(p.get("product_name") or "—"),
                    esc(p.get("quantity") or 0),
                    esc(p.get("channel") or "—"),
                    pill(p.get("status") or "new", _tone_for(p.get("status", ""))),
                ]
                for p in preorders[:30]
            ],
        )


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


def stock() -> None:
    theme.page_header(
        "Stock",
        "Snap a photo when stock arrives. Your team counts it, tracks what's "
        "selling, and tells you when to reorder — before you run out.",
    )

    items = memory.inventory()
    if not items:
        theme.empty(
            "Nothing in stock yet. Upload a photo of what arrived and the "
            "Inventory agent will log it with quantities and reorder levels."
        )
        return

    low = [i for i in items if i.get("low_stock")]
    stock_value = sum(
        float(i.get("quantity") or 0) * float(i.get("unit_cost") or 0) for i in items
    )
    theme.kpis([
        {"label": "Items tracked", "value": len(items), "note": "in your catalogue"},
        {"label": "Units on hand", "value": f"{sum(int(i.get('quantity') or 0) for i in items):,}",
         "note": "across all items"},
        {"label": "Needs reordering", "value": len(low),
         "note": ", ".join(str(i["name"]) for i in low[:2]) if low else "nothing urgent",
         "tone": "warn" if low else ""},
        {"label": "Stock value", "value": _money(stock_value), "note": "at cost"},
    ])

    # "Runs out" in the source design needs a sales rate this system doesn't
    # track, so the column reports the reorder threshold instead.
    theme.table(
        ["Item", "In stock", "Reorder at", "Cost", "Selling", "What to do"],
        "minmax(0,1.4fr) 110px 110px 110px 110px minmax(0,1fr)",
        [
            [
                f"<strong>{esc(i.get('name'))}</strong>",
                esc(f"{int(i.get('quantity') or 0):,}"),
                esc(i.get("reorder_level") or 0),
                _money(i.get("unit_cost")),
                _money(i.get("sell_price")),
                (
                    pill("Reorder now", "warn")
                    if i.get("low_stock")
                    else pill("Healthy", "ok")
                ),
            ]
            for i in items
        ],
    )


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------


def marketing() -> None:
    theme.page_header(
        "Marketing",
        "Ads your team wrote for each platform. Nothing goes out until you "
        "approve it — and anything simulated is labelled as such.",
    )

    camps = memory.campaigns()
    if not camps:
        theme.empty(
            "No campaigns yet. Ask the workforce to write ads for a product and "
            "they'll queue here for your approval."
        )
        return

    published = [c for c in camps if (c.get("status") or "") == "published"]
    simulated = [c for c in camps if c.get("simulated")]
    theme.kpis([
        {"label": "Campaigns", "value": len(camps), "note": "written so far"},
        {"label": "Published", "value": len(published), "note": "live on a platform"},
        {"label": "Awaiting you", "value": len(camps) - len(published),
         "note": "not sent yet", "tone": "warn" if len(camps) > len(published) else ""},
        {"label": "Simulated", "value": len(simulated),
         "note": "add API keys to go live", "tone": "simulated" if simulated else ""},
    ])

    theme.table(
        ["Headline", "Where", "Product", "Status", "Mode"],
        "minmax(0,1.6fr) 120px minmax(0,1fr) 120px 120px",
        [
            [
                f"<strong>{esc((c.get('headline') or '—')[:70])}</strong>",
                esc(c.get("platform") or "—"),
                esc(c.get("product_name") or "—"),
                pill(c.get("status") or "—", _tone_for(c.get("status", ""))),
                pill("simulated", "simulated") if c.get("simulated") else pill("live", "live"),
            ]
            for c in camps[:30]
        ],
    )


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def money(session_id: str, ledger: UsageLedger) -> None:
    theme.page_header(
        "Money",
        "One unit, honestly costed — what you pay, what you keep, and what "
        "running this workforce costs you.",
    )

    history = memory.pricing_history()
    if history:
        latest = history[0]
        theme.section("Your latest costing", "computed in a sandbox, not guessed")
        theme.kpis([
            {"label": "Unit cost", "value": _money(latest.get("unit_cost"))},
            {"label": "Selling at", "value": _money(latest.get("sell_price"))},
            {
                "label": "You keep",
                "value": (
                    f"{float(latest['margin_pct']):.0f}%"
                    if latest.get("margin_pct") is not None else "—"
                ),
                "tone": "ok" if (latest.get("margin_pct") or 0) > 0 else "warn",
            },
            {
                "label": "Break even at",
                "value": (
                    f"{float(latest['breakeven_units']):,.0f} units"
                    if latest.get("breakeven_units") else "—"
                ),
            },
        ])
        if latest.get("rationale"):
            theme.card("How your team worked it out", str(latest["rationale"]),
                       tag_text="Pricing", tone="ok")
    else:
        theme.empty(
            "No costing yet. Tell the workforce your unit cost and it will work "
            "out margin, break-even and how you compare to nearby sellers."
        )

    theme.section("What this workforce costs", "tokens are billed per model")
    if not ledger.calls:
        theme.empty("No model calls in this conversation yet.")
        return

    theme.kpis([
        {"label": "Model calls", "value": len(ledger.calls), "note": "this conversation"},
        {"label": "Tokens", "value": f"{ledger.total_tokens:,}", "note": "in + out"},
        {"label": "Cost", "value": f"${ledger.total_cost_usd:.4f}", "note": "estimated"},
        {"label": "Per call", "value": f"${ledger.total_cost_usd / len(ledger.calls):.4f}",
         "note": "average"},
    ])

    per_agent: dict[str, dict[str, float]] = {}
    for call in ledger.calls:
        row = per_agent.setdefault(call.agent, {"calls": 0, "tokens": 0, "usd": 0.0})
        row["calls"] += 1
        row["tokens"] += call.total_tokens
        row["usd"] += call.cost_usd

    theme.table(
        ["Agent", "Calls", "Tokens", "Cost"],
        "minmax(0,1.5fr) 110px 140px 140px",
        [
            [
                f"<strong>{esc(name.replace('_', ' '))}</strong>",
                esc(int(row["calls"])),
                esc(f"{int(row['tokens']):,}"),
                esc(f"${row['usd']:.4f}"),
            ]
            for name, row in sorted(per_agent.items(), key=lambda kv: -kv[1]["usd"])
        ],
    )


# ---------------------------------------------------------------------------
# Grow
# ---------------------------------------------------------------------------


def grow() -> None:
    theme.page_header(
        "Grow",
        "What customers keep asking for that you don't sell yet — the demand "
        "your shop is turning away without noticing.",
    )

    convos = memory.conversations(500)
    unmet = [c for c in convos if (c.get("intent") or "") == "unmet_demand"]
    if not unmet:
        theme.empty(
            "Nothing detected yet. As the Engagement agent reads customer "
            "messages, anything asked for but not stocked shows up here."
        )
        return

    counts: dict[str, int] = {}
    for c in unmet:
        item = (c.get("requested_item") or "unspecified").strip().lower()
        counts[item] = counts.get(item, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])

    stocked = {str(p.get("name", "")).lower() for p in memory.products()}
    theme.kpis([
        {"label": "Requests you can't fill", "value": len(unmet), "note": "in customer chat",
         "tone": "warn"},
        {"label": "Distinct items", "value": len(ranked), "note": "asked for by name"},
        {"label": "Top request", "value": ranked[0][0][:18] if ranked else "—",
         "note": f"asked {ranked[0][1]}×" if ranked else ""},
        {"label": "Already stocked", "value": sum(1 for k, _ in ranked if k in stocked),
         "note": "of the requested items"},
    ])

    theme.section("What customers keep asking for", "ranked by how often")
    theme.table(
        ["Item", "Times asked", "Do you sell it?"],
        "minmax(0,2fr) 140px 180px",
        [
            [
                f"<strong>{esc(item)}</strong>",
                esc(n),
                pill("in stock", "ok") if item in stocked else pill("not stocked", "warn"),
            ]
            for item, n in ranked[:25]
        ],
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def history() -> None:
    theme.page_header(
        "History",
        "Every report your team has written, newest first.",
    )
    reports = memory.reports(50)
    if not reports:
        theme.empty("No reports yet. Ask for one and it will be archived here.")
        return

    for r in reports:
        with st.expander(
            f"{r.get('title') or 'Report'} — {str(r.get('created_at') or '')[:16]}",
            expanded=False,
        ):
            st.markdown(r.get("body") or "")
            st.download_button(
                "Download as Markdown",
                data=(r.get("body") or ""),
                file_name=f"lucida-report-{r.get('id')}.md",
                mime="text/markdown",
                key=f"dl_{r.get('id')}",
            )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def settings_page() -> dict:
    """Business context + integration status. Returns the owner-context dict."""
    theme.page_header(
        "Settings",
        "What your team may do on its own, and what it must ask you about "
        "first. Anything left blank, the agents estimate.",
    )

    theme.section("Connected accounts", "simulated until you add a key")
    rows = []
    for label, status in settings.integration_status().items():
        tone = (
            "live" if status.startswith("LIVE")
            else ("missing" if "MISSING" in status else "simulated")
        )
        rows.append([f"<strong>{esc(label)}</strong>", pill(status, tone)])
    theme.table(["Integration", "Status"], "minmax(0,1fr) 200px", rows)

    theme.section("Your business", "used for pricing and market research")
    c1, c2 = st.columns(2)
    with c1:
        location = st.text_input("Where you sell", value=settings.location)
        unit_cost = st.number_input("Your unit cost", min_value=0.0, value=0.0, step=1.0)
        expected_units = st.number_input(
            "Expected monthly sales", min_value=0, value=0, step=10
        )
    with c2:
        fixed_costs = st.number_input(
            "Fixed monthly costs", min_value=0.0, value=0.0, step=100.0
        )
        platforms = st.multiselect(
            "Ad platforms",
            ["facebook", "instagram", "youtube"],
            default=["facebook", "instagram"],
        )

    theme.section("Stock you've bought", "optional — feeds the Inventory agent")
    s1, s2, s3 = st.columns([2, 1, 1])
    stock_name = s1.text_input("Product")
    stock_qty = s2.number_input("Qty", min_value=0, value=0, step=1)
    stock_cost = s3.number_input("Cost each", min_value=0.0, value=0.0, step=1.0)

    theme.section("Delivery details", "used only when you approve a booking")
    d1, d2 = st.columns(2)
    with d1:
        provider = st.selectbox("Courier", ["steadfast", "pathao", "uber"])
        recipient = st.text_input("Customer name")
        phone = st.text_input("Phone")
    with d2:
        address = st.text_area("Address", height=68)
        cod = st.number_input("Cash on delivery", min_value=0.0, value=0.0, step=10.0)

    context: dict[str, Any] = {
        "location": location,
        "unit_cost": unit_cost or None,
        "fixed_costs": fixed_costs,
        "expected_monthly_units": expected_units,
        "platforms": platforms,
    }
    if stock_name and stock_qty:
        context["stock_items"] = [
            {"product_name": stock_name, "quantity": int(stock_qty),
             "unit_cost": stock_cost}
        ]
    if recipient and address:
        context["delivery"] = {
            "provider": provider, "recipient": recipient, "phone": phone,
            "address": address, "cod_amount": cod, "product_name": stock_name,
        }
    return context
