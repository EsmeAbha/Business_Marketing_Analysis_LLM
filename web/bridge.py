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

import re
from typing import Any

from lucida.agents.base import ledger_for
from lucida.config import settings
from lucida.graph import agent_roster
from lucida.memory import memory
from lucida.observability import bus
from lucida.tools import fx

# The design's palette, referenced by the shapes below.
INK = "#17120F"
BODY_FG = "#4A3728"
MUTED = "#8A7563"
FAINT = "#A89680"
ACCENT = "#7B1E22"
ACCENT_TINT = "#F3E2E1"
AMBER = "#B4741B"
AMBER_TINT = "#FBF1E1"
RED = "#A63A2E"
RED_TINT = "#F8E9E6"
NEUTRAL_TINT = "#EFE2CE"

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

    Run-rate and cover are computed from logged sales. Until any exist they
    are dashed with a note saying why — the design's version showed a
    confident "4 days" that came from its fixture.
    """
    rows = []
    for item in memory.inventory():
        low = bool(item.get("low_stock"))
        qty = int(item.get("quantity") or 0)
        name = str(item.get("name") or "")
        rate = memory.run_rate(name)
        cover = memory.days_of_cover(name, qty)
        price = item.get("sell_price")
        sub_bits = []
        if price:
            sub_bits.append(f"{_cur(price)} each")
        if item.get("category"):
            sub_bits.append(str(item["category"]))
        rows.append({
            "initial": _initial(str(item.get("name", "?"))),
            "thumbBg": AMBER_TINT if low else ACCENT_TINT,
            "thumbFg": AMBER if low else ACCENT,
            "name": item.get("name") or "Unnamed item",
            "sub": " · ".join(sub_bits) or "No price set yet",
            "qty": f"{qty:,} pcs",
            "qtyColor": RED if low else INK,
            "rate": f"{rate:.0f}/day" if rate else DASH,
            "cover": f"in {cover:.0f} days" if cover is not None else DASH,
            "coverColor": (
                RED if (cover is not None and cover <= 3)
                else (AMBER if (cover is not None and cover <= 7) else BODY_FG)
            ) if cover is not None else FAINT,
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
    "positive": ("Happy", ACCENT, ACCENT_TINT),
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
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:12]
    top = ranked[0][1] if ranked else 1
    # Shape: {name, note, n, pct} — pct is a bar width against the top item.
    return [
        {
            "name": item,
            "note": "already in your catalogue" if item in stocked
                    else "nobody asked before this week",
            "n": n,
            "pct": round((n / top) * 100),
        }
        for item, n in ranked
    ]


# ---------------------------------------------------------------------------
# Marketing
# ---------------------------------------------------------------------------


_CAMPAIGN_TONE = {
    "published": (ACCENT, ACCENT_TINT),
    "approved": (ACCENT, ACCENT_TINT),
    "drafted": (AMBER, AMBER_TINT),
    "failed": (RED, RED_TINT),
}


def campaigns() -> list[dict]:
    """Shape: {name, sub, where, spent, orders, state, stateFg}.

    `spent` and `orders` are dashed: there is no ad-spend or attribution feed,
    and a fabricated number here would be read as a real result.
    """
    rows = []
    for c in memory.campaigns():
        status = (c.get("status") or "drafted").lower()
        fg, _ = _CAMPAIGN_TONE.get(status, (BODY_FG, NEUTRAL_TINT))
        sub_bits = [b for b in (c.get("product_name"),
                                str(c.get("created_at") or "")[:10]) if b]
        rows.append({
            "name": c.get("headline") or "Untitled ad",
            "sub": " · ".join(sub_bits) or "no product attached",
            "where": (c.get("platform") or DASH).title(),
            "spent": DASH,
            "orders": DASH,
            "state": "Simulated" if c.get("simulated") else status.title(),
            "stateFg": AMBER if c.get("simulated") else fg,
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


def _pnl_row(k, v, note="", strong=False, good=False):
    """One PNL line in the design's shape: {k, v, note, weight, keyColor, vColor}."""
    return {
        "k": k, "v": v, "note": note,
        "weight": "700" if strong else "400",
        "keyColor": INK if strong else BODY_FG,
        "vColor": ACCENT if good else (INK if strong else BODY_FG),
    }


def pnl() -> list[dict]:
    """Unit economics — only ever what the Pricing agent actually computed."""
    history = memory.pricing_history()
    if not history:
        return []
    latest = history[0]
    product = latest.get("product_name") or "your product"
    rows = [
        _pnl_row("You sell at", _cur(latest.get("sell_price")),
                 f"per unit of {product}", strong=True),
        _pnl_row("Costs you", "-" + _cur(latest.get("unit_cost")),
                 "materials and making"),
    ]
    if latest.get("margin_pct") is not None:
        pct = float(latest["margin_pct"])
        rows.append(_pnl_row(
            "What you keep", f"{pct:.1f}%",
            "of every sale", strong=True, good=pct > 0,
        ))
    if latest.get("breakeven_units"):
        rows.append(_pnl_row(
            "Break even at",
            f"{float(latest['breakeven_units']):,.0f} units",
            "before you are in profit",
        ))
    return rows


_USAGE_RE = re.compile(r"(\d[\d,]*)\s*in\s*/\s*(\d[\d,]*)\s*out")


def cost_bars(session_id: str) -> list[dict]:
    """Where the tokens went, per agent.

    Shape must match the design's COST_BARS: {name, tok, cost, pct, color}.
    `pct` is a bar width scaled against the heaviest agent.

    Read from the durable `llm_usage` trace rather than the in-process
    ledger: `ledger_for()` lives in a module-level dict, so a restart — or
    simply the other front-end — sees nothing. The trace survives both.

    (The design's separate COST_ROWS is an *ingredient* cost breakdown —
    filling, dough, oil, packaging. Lucida records no per-ingredient costing,
    so that constant is deliberately left un-overridden.)
    """
    per: dict[str, dict[str, float]] = {}

    for e in bus.load(session_id, 600):
        if e["kind"] != "llm_usage":
            continue
        row = per.setdefault(str(e["actor"]), {"tokens": 0.0, "usd": 0.0})
        row["usd"] += float((e.get("payload") or {}).get("cost_usd") or 0.0)
        m = _USAGE_RE.search(e.get("summary") or "")
        if m:
            row["tokens"] += int(m.group(1).replace(",", ""))
            row["tokens"] += int(m.group(2).replace(",", ""))

    # Fall back to the live ledger for the session running in this process,
    # which has data the trace has not been asked for yet.
    if not per:
        for call in ledger_for(session_id).calls:
            row = per.setdefault(call.agent, {"tokens": 0.0, "usd": 0.0})
            row["tokens"] += call.total_tokens
            row["usd"] += call.cost_usd

    if not per:
        return []

    top = max(r["usd"] for r in per.values()) or 1.0
    return [
        {
            "name": name.replace("_", " ").title(),
            "tok": f"{int(r['tokens']):,}",
            "cost": f"${r['usd']:.4f}",
            "pct": max(2, round((r["usd"] / top) * 100)),
            "color": AMBER if r["usd"] >= top else ACCENT,
        }
        for name, r in sorted(per.items(), key=lambda kv: -kv[1]["usd"])
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

    events = bus.load(session_id, 500)
    seen = {e["actor"] for e in events}
    degraded = {e["actor"] for e in events if e.get("level") == "error"}

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
        "bad": "supervisor" in degraded,
    }]

    for key, meta in agent_roster().items():
        gated = meta.get("requires_approval") == "True"
        broke = key in degraded
        rows.append({
            "id": NODE_ID.get(key, key),
            "name": meta.get("title") or key.replace("_", " ").title(),
            "kind": "router" if key == "supervisor" else "specialist",
            "owns": meta.get("description") or "",
            "tools": meta.get("tools") or "",
            "calls": calls.get(key, 0),
            "state": ("degraded" if broke
                      else "used this run" if key in seen else "idle"),
            "busy": False,
            "wait": gated,
            "bad": broke,
        })
    return rows


def overnight(session_id: str) -> list[dict]:
    """The design's 'done while you slept' list — what the team did unasked.

    Reads the durable trace, not the in-process buffer: the buffer is empty
    in a freshly started process, which made this panel silently fall back to
    the design's fixture on every restart.
    """
    rows = []
    for e in reversed(bus.load(session_id, 400)):
        if e["kind"] not in ("agent_end", "tool_call"):
            continue
        rows.append({
            "text": e.get("summary") or "",
            "by": str(e["actor"]).replace("_", " ").title(),
            "t": str(e.get("ts") or "")[11:16],
        })
        if len(rows) >= 8:
            break
    return rows


def failures(session_id: str) -> list[dict]:
    """Shape: {level, what, t, tagBg, tagFg, fix}."""
    rows = []
    for e in bus.load(session_id, 400):
        if e.get("level") != "error":
            continue
        rows.append({
            "level": "Failure",
            "what": e.get("summary") or "unknown error",
            "t": str(e.get("ts") or "")[11:16],
            "tagBg": RED_TINT,
            "tagFg": RED,
            "fix": f"Raised by {str(e.get('actor', '')).replace('_', ' ')}. "
                   "The graph retries once, then drops the agent and carries "
                   "on rather than failing the whole run.",
        })
    return rows[:10]


# The design's step kinds, mapped from the trace's own event kinds. Anything
# unrecognised falls back to 'think', which renders as a neutral step.
_STEP_KIND = {
    "agent_start": "think",
    "agent_end": "act",
    "tool_call": "tool",
    "handoff": "handoff",
    "approval": "gate",
    "error": "error",
    "llm_usage": "think",
    "llm_call": "think",
    "memory": "memory",
    "plan": "plan",
    "session_start": "plan",
}


def _step(ev: dict) -> dict:
    """One trace event in the shape the design's run player expects."""
    kind = _STEP_KIND.get(ev["kind"], "think")
    payload = ev.get("payload") or {}
    actor = str(ev.get("actor") or "").replace("_", " ").title()

    # `detail` is the expandable body; show whatever the event carried.
    detail_bits = []
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        text = value if isinstance(value, str) else str(value)
        detail_bits.append(f"{key}: {text[:400]}")
    detail = "\n".join(detail_bits)

    step = {
        "t": str(ev.get("ts") or "")[11:16],
        "a": actor or "Supervisor",
        "k": kind,
        "title": ev.get("summary") or ev["kind"],
        "meta": "",
        "detail": detail,
    }
    if ev.get("level") == "error":
        step["k"] = "error"
        step["level"] = "ERROR"
    if kind == "gate":
        step["gate"] = True
    if kind == "handoff":
        step["h"] = {
            "from": actor,
            "to": str(payload.get("to") or payload.get("next_agent") or "")
                  .replace("_", " ").title(),
            "t": step["t"],
            "payload": detail or str(payload)[:400],
        }
    tokens = payload.get("total_tokens") or payload.get("tokens")
    if tokens:
        step["meta"] = f"{tokens} tok"
    return step


def runs(current_session: str) -> list[dict]:
    """Real runs for the design's Runs player, newest first.

    Replaces the bundle's scripted demo run. Steps come from the durable
    trace, so a run recorded before this process started still plays back.
    """
    out = []
    for s in bus.sessions(30):
        # Only real owner sessions. WorkforceRuntime mints "sess-…" ids; the
        # component test suite writes traces under its own short ids, and
        # those would otherwise show up as runs the owner never made.
        if not str(s["session_id"]).startswith("sess-"):
            continue
        events = bus.load(s["session_id"], 400)
        if not events:
            continue
        # `llm_usage` is per-call token accounting — real, but it belongs on
        # the cost page, not as a step in the story of what the team did.
        steps = [_step(e) for e in events if e["kind"] != "llm_usage"]
        if not steps:
            continue
        gate = next((st for st in steps if st.get("gate")), None)
        label = next(
            (e["summary"] for e in events if e["kind"] == "session_start"),
            f"Run {s['session_id'][-6:]}",
        )
        cost = ledger_for(s["session_id"]).total_cost_usd
        meta_bits = [f"{len(steps)} steps"]
        if s["errors"]:
            meta_bits.append(f"{s['errors']} error(s)")
        if cost:
            meta_bits.append(f"${cost:.4f}")
        if s["session_id"] == current_session:
            meta_bits.append("this session")
        out.append({
            "id": s["session_id"],
            "label": str(label)[:80],
            "meta": " · ".join(meta_bits),
            "gate": {
                "title": gate["title"] if gate else "Waiting on you",
                "body": (gate.get("detail") if gate else "")
                        or "Nothing is spent or sent until you approve.",
            },
            "steps": steps,
        })
        if len(out) >= 12:
            break
    return out


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


# Which agent's work belongs under which heading in the History log.
_HISTORY_CAT = {
    "inventory": ("Stock", AMBER),
    "engagement": ("Customers", ACCENT),
    "pricing": ("Money", ACCENT),
    "ad_creative": ("Marketing", ACCENT),
    "delivery": ("Delivery", ACCENT),
    "market_research": ("Research", ACCENT),
    "product_vision": ("Products", ACCENT),
    "reporting": ("Reports", ACCENT),
    "supervisor": ("Planning", MUTED),
}


def history() -> list[dict]:
    """What the team has actually done, newest first.

    Shape: {id, cat, text, by, t, dot, why}. Built from the durable trace so
    it survives a restart, with each agent's own summary as the `why`.
    """
    rows = []
    for s in bus.sessions(10):
        if not str(s["session_id"]).startswith("sess-"):
            continue
        for e in reversed(bus.load(s["session_id"], 300)):
            if e["kind"] not in ("agent_end", "approval", "error"):
                continue
            actor = str(e.get("actor") or "")
            cat, dot = _HISTORY_CAT.get(actor, ("Activity", MUTED))
            if e.get("level") == "error":
                cat, dot = "Problem", RED
            payload = e.get("payload") or {}
            why = " · ".join(
                f"{k}: {v}" for k, v in payload.items()
                if v not in (None, "", [], {})
            )[:400]
            rows.append({
                "id": e["id"],
                "cat": cat,
                "text": e.get("summary") or e["kind"],
                "by": actor.replace("_", " ").title() or "Supervisor",
                "t": str(e.get("ts") or "")[11:16],
                "dot": dot,
                "why": why or "No extra detail was recorded for this step.",
            })
            if len(rows) >= 40:
                return rows
    return rows


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


def kpis() -> dict[str, str]:
    """The four headline tiles, from what the shop actually recorded.

    Every one of these was a literal in the design. They are real now, and
    where the shop has no basis for a figure it shows an em dash and says what
    is missing — an invented number on the first screen is the one thing that
    would make the whole dashboard untrustworthy.
    """
    today = memory.sales_since(1)
    week = memory.sales_since(7)
    preorders = memory.preorders()
    units = sum(int(p.get("quantity") or 0) for p in preorders)
    customers = len({p.get("customer") for p in preorders if p.get("customer")})

    # Sales today, and how it compares with the daily average of the week.
    if today["known"]:
        sales = _cur(today["revenue"])
        n = today["orders"]
        note = f"{n} order{'s' if n != 1 else ''} today"
        if week["orders"] > today["orders"]:
            avg = week["revenue"] / 7.0
            if avg:
                delta = ((today["revenue"] - avg) / avg) * 100
                note += f" · {delta:+.0f}% vs the week's average"
    else:
        sales, note = DASH, "no sales logged yet"

    # Days of cover for whichever item runs out first.
    cover, cover_note = DASH, "needs sales history"
    soonest = None
    for item in memory.inventory():
        days = memory.days_of_cover(str(item.get("name")),
                                    int(item.get("quantity") or 0))
        if days is not None and (soonest is None or days < soonest[0]):
            soonest = (days, item.get("name"))
    if soonest:
        cover = f"{soonest[0]:.0f} days"
        cover_note = f"{soonest[1]} runs out first"
    elif memory.inventory():
        cover_note = "log some sales to see this"

    return {
        "salesToday": sales,
        "salesTodayNote": note,
        "preorderUnits": f"{units:,} pcs" if units else DASH,
        "preorderNote": (
            f"{len(preorders)} promise{'s' if len(preorders) != 1 else ''}"
            + (f" · {customers} customer{'s' if customers != 1 else ''}"
               if customers else "")
            if preorders else "none yet"
        ),
        "coverDays": cover,
        "coverNote": cover_note,
    }


def reorder() -> dict[str, str]:
    """What the Stock page's reorder panel can honestly say.

    The design's version names a supplier, a delivery date and a payback
    period. None of that exists here, so this reports the one thing the shop
    does know: which items have fallen to their reorder level.
    """
    low = memory.low_stock()
    if not low:
        stocked = len(memory.inventory())
        return {
            "basis": f"{stocked} item(s) tracked" if stocked
                     else "no stock recorded yet",
            "title": "Nothing needs reordering",
            "sent": "Recorded. Your stock page updates when it arrives.",
            "body": ("Every item is above the reorder level you set."
                     if stocked else
                     "No stock has been recorded yet. Add a photo of what "
                     "arrived on this page and your team will log it."),
        }
    names = ", ".join(str(i.get("name")) for i in low[:3])
    worth = sum(
        float(i.get("unit_cost") or 0) * max(0, int(i.get("reorder_level") or 0))
        for i in low
    )
    covers = [
        (str(i.get("name")), memory.days_of_cover(str(i.get("name")),
                                                  int(i.get("quantity") or 0)))
        for i in low
    ]
    soon = [f"{n} runs out in about {d:.0f} days"
            for n, d in covers if d is not None]
    return {
        "basis": f"{len(low)} item(s) at or below the level you set",
        "title": (f"Reorder {names}"
                  + (f" — about {_cur(worth)} at cost" if worth else "")),
        "sent": "Recorded. Your stock page updates when it arrives.",
        "body": (
            ("; ".join(soon) + ". " if soon else "")
            + "Based on the reorder levels you set"
            + (" and the sales you have logged." if soon
               else ". Log some sales and this will predict when you run out.")
        ),
    }


def is_first_run() -> bool:
    """True while this shop's memory is still empty.

    Matters because the design falls back to its own demo figures when a key
    is empty — good for keeping the layout intact, bad for a new owner who
    would otherwise read someone else's sales as their own. The front-end uses
    this to say plainly that the numbers are samples.
    """
    s = memory.stats()
    return not any((s["products"], s["conversations"], s["campaigns"],
                    s["preorders"], s["reports"], memory.orders(1)))


def snapshot(session_id: str, pending: dict[str, Any] | None = None) -> dict:
    """Everything the design needs, keyed to the constants it declares."""
    return {
        "firstRun": is_first_run(),
        "kpi": kpis(),
        "reorder": reorder(),
        "fx": fx.snapshot(settings.currency),
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
        "channels": channels(),
        "pnl": pnl(),
        "demands": demands(),
        "history": history(),
        "roster": roster(session_id),
        "runs": runs(session_id),
        "memRecords": mem_records(),
        "costBars": cost_bars(session_id),
        "failures": failures(session_id),
        "stats": memory.stats(),
    }
