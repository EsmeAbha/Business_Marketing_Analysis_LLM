"""Map Lucida's shared memory onto the shapes the design's view model expects.

The design was drawn against a demo fixture — a shingara kitchen in Mirpur 11
with sales, run-rates and days-of-cover. Lucida records what its agents
actually observe, which is a smaller set: stock counts, conversations,
campaigns, pricing runs, token cost.

So every builder here follows one rule: **emit only fields backed by a real
value**. Where the design shows a figure this system cannot compute — daily
sales, days-of-cover, cost-per-order — the field is filled with an em dash
rather than an invented number, and the layout carries it unchanged.

A builder that finds no rows returns `[]`. The patched design treats an empty
list as "no override" and falls back to its own literal, so a fresh install
still renders exactly as drawn.
"""

from __future__ import annotations

from typing import Any

from lucida.agents.base import ledger_for
from lucida.config import settings
from lucida.graph import agent_roster
from lucida.memory import memory
from lucida.observability import bus

# The design's palette, referenced by the shapes below.
INK = "#18211D"
BODY_FG = "#4A554E"
MUTED = "#7C877F"
FAINT = "#A19B8E"
GREEN = "#14603F"
GREEN_TINT = "#EAF1EC"
AMBER = "#B4741B"
AMBER_TINT = "#FBF1E1"
RED = "#A63A2E"
RED_TINT = "#F8E9E6"
NEUTRAL_TINT = "#F1EEE6"

DASH = "—"

# Lucida's agent keys -> the short node ids the design's NODE_POS / GRAPH_EDGES
# are drawn against. The supervisor keeps its name in both.
NODE_ID = {
    "supervisor": "supervisor",
    "market_research": "market",
    "product_vision": "vision",
    "pricing": "pricing",
    "inventory": "inventory",
    "ad_creative": "ads",
    "engagement": "engage",
    "delivery": "delivery",
    "reporting": "report",
}


def _cur(value: Any, prefix: str | None = None) -> str:
    sym = prefix if prefix is not None else f"{settings.currency} "
    try:
        return f"{sym}{float(value):,.0f}"
    except (TypeError, ValueError):
        return DASH


def _initial(name: str) -> str:
    name = (name or "?").strip()
    return name[0].upper() if name else "?"


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


def stock() -> list[dict]:
    """Design columns: qty, run-rate, days-of-cover, what-to-do.

    Run-rate and cover need a sales feed Lucida has no source for, so both are
    dashed. Quantity, price and the low-stock flag are real.
    """
    rows = []
    for item in memory.inventory():
        low = bool(item.get("low_stock"))
        qty = int(item.get("quantity") or 0)
        price = item.get("sell_price")
        sub_bits = []
        if price:
            sub_bits.append(f"{_cur(price)} each")
        if item.get("category"):
            sub_bits.append(str(item["category"]))
        rows.append({
            "initial": _initial(str(item.get("name", "?"))),
            "thumbBg": AMBER_TINT if low else GREEN_TINT,
            "thumbFg": AMBER if low else GREEN,
            "name": item.get("name") or "Unnamed item",
            "sub": " · ".join(sub_bits) or "No price set yet",
            "qty": f"{qty:,} pcs",
            "qtyColor": RED if low else INK,
            "rate": DASH,          # no sales feed
            "cover": DASH,         # cannot be derived without a run rate
            "coverColor": FAINT,
            "todo": (
                f"Reorder — at or below {item.get('reorder_level', 0)}"
                if low else "Nothing to do"
            ),
        })
    return rows


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


_SENTIMENT = {
    "positive": ("Happy", GREEN, GREEN_TINT),
    "negative": ("Upset", RED, RED_TINT),
    "neutral": ("Neutral", BODY_FG, NEUTRAL_TINT),
}


def threads() -> list[dict]:
    rows = []
    for c in memory.conversations(60):
        name = c.get("customer") or "Someone"
        sentiment = (c.get("sentiment") or "neutral").lower()
        label, fg, bg = _SENTIMENT.get(sentiment, _SENTIMENT["neutral"])
        intent = (c.get("intent") or "other").replace("_", " ")
        message = c.get("message") or ""
        tags = [[label, bg, fg]]
        if c.get("requested_item"):
            tags.append([f"Wants {c['requested_item']}", AMBER_TINT, AMBER])
        rows.append({
            "id": f"c{c.get('id')}",
            "name": name,
            "initials": _initials(name),
            "channel": (c.get("channel") or "message").title(),
            "t": str(c.get("created_at") or "")[11:16] or DASH,
            "history": intent,
            "preview": message[:110],
            "message": message,
            "state": f"Read as: {intent}",
            "stateFg": fg,
            "mark": fg,
            "read": f"Sorted as {intent} by the Engagement agent.",
            "tags": tags,
            # Lucida stores no drafted reply, so the design's draft pane
            # states that plainly rather than inventing the shop's words.
            "draft": "",
            "action": "",
        })
    return rows


def demands() -> list[dict]:
    """The design's unmet-demand list, ranked by how often it was asked for."""
    counts: dict[str, int] = {}
    for c in memory.conversations(500):
        if (c.get("intent") or "") != "unmet_demand":
            continue
        item = (c.get("requested_item") or "unspecified").strip().lower()
        counts[item] = counts.get(item, 0) + 1
    stocked = {str(p.get("name", "")).lower() for p in memory.products()}
    return [
        {
            "name": item,
            "count": f"{n}",
            "note": "already in your catalogue" if item in stocked
                    else "not stocked yet",
            "fg": GREEN if item in stocked else AMBER,
            "bg": GREEN_TINT if item in stocked else AMBER_TINT,
        }
        for item, n in sorted(counts.items(), key=lambda kv: -kv[1])[:12]
    ]


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------


_CAMPAIGN_TONE = {
    "published": (GREEN, GREEN_TINT),
    "approved": (GREEN, GREEN_TINT),
    "drafted": (AMBER, AMBER_TINT),
    "failed": (RED, RED_TINT),
}


def campaigns() -> list[dict]:
    rows = []
    for c in memory.campaigns():
        status = (c.get("status") or "drafted").lower()
        fg, bg = _CAMPAIGN_TONE.get(status, (BODY_FG, NEUTRAL_TINT))
        rows.append({
            "name": c.get("headline") or "Untitled ad",
            "where": (c.get("platform") or DASH).title(),
            "spent": DASH,      # no ad-spend feed
            "orders": DASH,     # no attribution feed
            "status": "simulated" if c.get("simulated") else status,
            "statusFg": AMBER if c.get("simulated") else fg,
            "statusBg": AMBER_TINT if c.get("simulated") else bg,
        })
    return rows


def creatives() -> list[dict]:
    rows = []
    for c in memory.campaigns():
        if (c.get("status") or "") == "published":
            continue
        rows.append({
            "platform": (c.get("platform") or DASH).title(),
            "headline": c.get("headline") or "Untitled ad",
            "body": (c.get("body") or "")[:240],
            "cta": c.get("call_to_action") or "",
            "product": c.get("product_name") or DASH,
        })
    return rows


def channels() -> list[dict]:
    """Shape must match the design's CHANNELS: {name, state, ok}."""
    rows = []
    for label, status in settings.integration_status().items():
        rows.append({
            "name": label,
            "state": "Connected" if status.startswith("LIVE") else status.title(),
            "ok": status.startswith("LIVE"),
        })
    return rows


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def pnl() -> list[dict]:
    """Unit economics — only ever what the Pricing agent actually computed."""
    history = memory.pricing_history()
    if not history:
        return []
    latest = history[0]
    rows = [
        {"k": "Costs you", "v": _cur(latest.get("unit_cost")), "fg": INK},
        {"k": "You sell at", "v": _cur(latest.get("sell_price")), "fg": INK},
    ]
    if latest.get("margin_pct") is not None:
        pct = float(latest["margin_pct"])
        rows.append({
            "k": "You keep", "v": f"{pct:.1f}%",
            "fg": GREEN if pct > 0 else RED,
        })
    if latest.get("breakeven_units"):
        rows.append({
            "k": "Break even at",
            "v": f"{float(latest['breakeven_units']):,.0f} units",
            "fg": INK,
        })
    return rows


def cost_rows(session_id: str) -> list[dict]:
    ledger = ledger_for(session_id)
    per: dict[str, dict[str, float]] = {}
    for call in ledger.calls:
        row = per.setdefault(call.agent, {"calls": 0, "tokens": 0, "usd": 0.0})
        row["calls"] += 1
        row["tokens"] += call.total_tokens
        row["usd"] += call.cost_usd
    return [
        {
            "agent": name.replace("_", " ").title(),
            "calls": f"{int(r['calls'])}",
            "tokens": f"{int(r['tokens']):,}",
            "cost": f"${r['usd']:.4f}",
        }
        for name, r in sorted(per.items(), key=lambda kv: -kv[1]["usd"])
    ]


def cost_bars(session_id: str) -> list[dict]:
    ledger = ledger_for(session_id)
    if not ledger.calls:
        return []
    per: dict[str, float] = {}
    for call in ledger.calls:
        per[call.agent] = per.get(call.agent, 0.0) + call.cost_usd
    top = max(per.values()) or 1.0
    return [
        {
            "label": name.replace("_", " ").title(),
            "value": f"${usd:.4f}",
            "pct": f"{(usd / top) * 100:.0f}%",
            "fill": GREEN,
        }
        for name, usd in sorted(per.items(), key=lambda kv: -kv[1])
    ]


# ---------------------------------------------------------------------------
# The workforce
# ---------------------------------------------------------------------------


def roster(session_id: str) -> list[dict]:
    """The agent roster, keyed to the design's own node ids.

    The design's execution graph hard-codes node coordinates in `NODE_POS`
    under short ids ('market', 'vision', 'ads' …). Emitting Lucida's internal
    keys instead makes that lookup miss and the graph crash, so the ids are
    translated here and the real title travels in `name`.
    """
    ledger = ledger_for(session_id)
    calls: dict[str, int] = {}
    for call in ledger.calls:
        calls[call.agent] = calls.get(call.agent, 0) + 1

    events = bus.recent(session_id)
    seen = {e.actor for e in events}

    # agent_roster() lists the eight specialists; the supervisor routes them
    # and the design draws it as the hub, so it is added explicitly.
    rows = [{
        "id": "supervisor",
        "name": "Supervisor",
        "kind": "router",
        "owns": "Reads the request, picks the stage, plans the order of work, "
                "and holds the approval gates.",
        "tools": "planner · state graph · checkpoints",
        "calls": calls.get("supervisor", 0),
        "state": "used this run" if "supervisor" in seen else "idle",
        "busy": False,
        "wait": False,
    }]

    for key, meta in agent_roster().items():
        gated = meta.get("requires_approval") == "True"
        rows.append({
            "id": NODE_ID.get(key, key),
            "name": meta.get("title") or key.replace("_", " ").title(),
            "kind": "router" if key == "supervisor" else "specialist",
            "owns": meta.get("description") or "",
            "tools": meta.get("tools") or "",
            "calls": calls.get(key, 0),
            "state": "used this run" if key in seen else "idle",
            "busy": False,
            "wait": gated,
        })
    return rows


def overnight(session_id: str) -> list[dict]:
    """The design's 'done while you slept' list, from the real event bus."""
    rows = []
    for e in reversed(bus.recent(session_id)):
        if e.kind not in ("agent_end", "tool_call", "handoff"):
            continue
        rows.append({
            "text": e.summary,
            "by": e.actor.replace("_", " ").title(),
            "t": str(e.ts)[11:19],
        })
        if len(rows) >= 8:
            break
    return rows


def failures(session_id: str) -> list[dict]:
    return [
        {
            "what": e.summary,
            "who": e.actor.replace("_", " ").title(),
            "then": "retried once, then dropped",
            "fg": RED,
            "bg": RED_TINT,
        }
        for e in bus.recent(session_id)
        if e.level == "error"
    ][:10]


def mem_records() -> list[dict]:
    """Everything the workforce has written down, in the design's table shape."""
    rows: list[dict] = []
    for p in memory.products():
        rows.append({
            "store": "catalog", "key": f"prod_{p.get('id')}",
            "value": " · ".join(
                x for x in (
                    p.get("name"),
                    _cur(p.get("sell_price")) if p.get("sell_price") else None,
                    p.get("category"),
                ) if x
            ),
            "by": p.get("source_agent") or "Inventory",
            "when": str(p.get("created_at") or "")[:10], "cat": "Business",
        })
    for i in memory.inventory():
        rows.append({
            "store": "inventory", "key": str(i.get("name", "")),
            "value": f"{int(i.get('quantity') or 0):,} pcs on hand · "
                     f"reorder at {i.get('reorder_level')}",
            "by": "Inventory", "when": DASH, "cat": "Stock",
        })
    for ph in memory.pricing_history()[:10]:
        rows.append({
            "store": "pricing_history", "key": str(ph.get("product_name") or "pricing"),
            "value": f"{_cur(ph.get('sell_price'))} · keeps "
                     f"{float(ph['margin_pct']):.1f}%"
                     if ph.get("margin_pct") is not None
                     else _cur(ph.get("sell_price")),
            "by": "Pricing & Cost", "when": str(ph.get("created_at") or "")[:10],
            "cat": "Money",
        })
    for c in memory.campaigns()[:10]:
        rows.append({
            "store": "campaigns", "key": f"cmp_{c.get('id')}",
            "value": f"{c.get('headline') or ''} · {c.get('status') or ''}",
            "by": "Ad Creation", "when": str(c.get("created_at") or "")[:10],
            "cat": "Marketing",
        })
    for r in memory.reports(10):
        rows.append({
            "store": "reports", "key": f"report_{r.get('id')}",
            "value": r.get("title") or "Report",
            "by": "Reporting", "when": str(r.get("created_at") or "")[:10],
            "cat": "Money",
        })
    return rows


def history() -> list[dict]:
    return [
        {
            "title": r.get("title") or "Report",
            "when": str(r.get("created_at") or "")[:16],
            "body": (r.get("body") or "")[:400],
            "id": str(r.get("id")),
        }
        for r in memory.reports(30)
    ]


# ---------------------------------------------------------------------------
# Decisions (human-in-the-loop gates)
# ---------------------------------------------------------------------------


def decisions(pending: dict[str, Any] | None) -> list[dict]:
    """The one gate the graph is actually suspended on, if any."""
    if not pending:
        return []
    agent = str(pending.get("agent", ""))
    kind = "Delivery" if "deliver" in agent.lower() else "Marketing"
    return [{
        "id": "gate",
        "tag": kind,
        "by": f"From your {agent.replace('_', ' ')} assistant" if agent else "",
        "when": "",
        "title": pending.get("title") or "I need your go-ahead",
        "body": pending.get("detail") or "",
        "facts": [],
        "yes": "Go ahead",
        "edit": "Change it",
        "hint": "Nothing happens until you tap.",
        "doneText": "Approved — the workforce is carrying on.",
        "denyText": "Held back. Nothing was sent.",
    }]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def snapshot(session_id: str, pending: dict[str, Any] | None = None) -> dict:
    """Everything the design needs, keyed to the constants it declares."""
    return {
        "businessName": (memory.profile() or {}).get("business_name") or "Lucida",
        "ownerName": (memory.profile() or {}).get("owner_name") or "",
        "location": settings.location,
        "currency": settings.currency,
        "hasLlm": bool(settings.has_llm),
        "decisions": decisions(pending),
        "overnight": overnight(session_id),
        "threads": threads(),
        "stock": stock(),
        "campaigns": campaigns(),
        "creatives": creatives(),
        "channels": channels(),
        "pnl": pnl(),
        "demands": demands(),
        "history": history(),
        "roster": roster(session_id),
        "memRecords": mem_records(),
        "costRows": cost_rows(session_id),
        "costBars": cost_bars(session_id),
        "failures": failures(session_id),
        "stats": memory.stats(),
    }
