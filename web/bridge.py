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
from datetime import datetime
from pathlib import Path
from typing import Any

from lucida.agents.base import ledger_for
from lucida.config import settings
from lucida.graph import agent_roster
from lucida.memory import memory
from lucida.observability import bus
from lucida.tools import fx, inbox

# The design's palette, referenced by the shapes below.
INK = "#000000"
BODY_FG = "#3F3F46"
MUTED = "#71717A"
FAINT = "#A1A1AA"
ACCENT = "#7B1E22"
ACCENT_TINT = "#FBEBEB"
AMBER = "#A16207"
AMBER_TINT = "#FEF9C3"
RED = "#B91C1C"
RED_TINT = "#FEE2E2"
NEUTRAL_TINT = "#F4F4F5"

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


def _transcript(latest: dict) -> str:
    """One thread rendered as it was actually said.

    `inbox.conversation` already returns every turn oldest-first; until now the
    Customers screen only ever showed the most recent customer line, so a
    conversation the bot had answered looked one-sided.
    """
    platform = str(latest.get("platform") or "")
    thread_id = str(latest.get("thread_id") or "")
    if not thread_id:
        return str(latest.get("message") or "")

    turns = inbox.conversation(memory.db, platform, thread_id)
    if not turns:
        return str(latest.get("message") or "")

    who = str(latest.get("sender_name") or "Customer")
    shop = (memory.profile() or {}).get("business_name") or "Shop"
    lines = []
    for t in turns:
        text = str(t.get("message") or "").strip()
        if text:
            lines.append(f"{who}:  {text}")
        reply = str(t.get("reply_text") or "").strip()
        if reply:
            # Keep the reply readable inside one bubble.
            lines.append(f"{shop}:  " + " ".join(reply.split()))
    blank = chr(10) + chr(10)   # a blank line between turns
    joined = blank.join(lines)
    return joined if lines else str(latest.get("message") or "")


def _thread_note(latest: dict) -> str:
    n = int(latest.get("in_thread") or 1)
    platform = str(latest.get("platform") or "message").title()
    answered = "answered" if latest.get("replied") else "waiting for a reply"
    return (f"{n} message{'s' if n != 1 else ''} on {platform} — {answered}.")


def threads() -> list[dict]:
    """Customer conversations for the Customers page.

    Preferred source is `social_messages` — the shop's own inbox — because
    those rows carry the id and platform a reply needs to be sent against.
    `conversations` is what the Engagement agent writes after reading, and is
    used only when nothing has been synced yet.
    """
    synced = inbox.threads(memory.db, limit=60)
    if synced:
        rows = []
        for m in synced:
            sentiment = (m.get("sentiment") or "neutral").lower()
            label, fg, bg = _SENTIMENT.get(sentiment, _SENTIMENT["neutral"])
            answered = bool(m.get("replied"))
            name = m.get("sender_name") or "Customer"
            tags = [[label, bg, fg]]
            if m.get("kind") == "comment":
                tags.append(["Comment on an ad", NEUTRAL_TINT, BODY_FG])
            if m.get("requested_item"):
                tags.append([f"Wants {m['requested_item']}", AMBER_TINT, AMBER])
            rows.append({
                # The design keys threads by this id; using the real row id
                # is what lets the Send button post a reply to the right one.
                "id": str(m["id"]),
                "name": name,
                "initials": _initials(name),
                "channel": str(m.get("platform") or "message").title(),
                "t": str(m.get("received_at") or "")[11:16] or DASH,
                "history": str(m.get("intent") or m.get("kind") or "message"
                               ).replace("_", " "),
                "preview": (m.get("message") or "")[:110],
                # The whole back-and-forth, not just the newest line. A reply
                # the bot already sent is part of the conversation, and the
                # owner cannot judge what to say next without seeing it.
                "message": _transcript(m),
                "state": ("Answered" if answered
                          else "Waiting for your reply"),
                "stateFg": ACCENT if answered else AMBER,
                "mark": ACCENT if answered else AMBER,
                "read": _thread_note(m),
                "tags": tags,
                "draft": (m.get("reply_text") if m.get("replied")
                          else m.get("draft_reply")) or "",
                "action": (
                    "Already sent." if answered
                    else ("Your team drafted this. Nothing is sent until you "
                          "press Send.") if m.get("draft_reply")
                    else "No draft yet — ask your team to read the inbox."
                ),
            })
        return rows

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


def creatives() -> list[dict]:
    """Ad creative this shop actually has: its own copy, its own artwork.

    The bundle shipped three finished posts for a samosa business. These come
    from the campaigns table, with the picture — if one was drawn or uploaded
    for that product — served from the shop's own media. No artwork means an
    empty frame with a prompt, not somebody else's photograph.
    """
    rows = memory.db.query(
        "SELECT c.id, c.platform, c.headline, c.body, c.call_to_action, "
        "       c.product_name, c.status, m.path AS media_path "
        "FROM campaigns c LEFT JOIN media_assets m ON m.id = c.media_id "
        "ORDER BY c.id DESC LIMIT 6")
    out = []
    for r in rows:
        platform = (r.get("platform") or "").title() or "Draft"
        pic = ""
        if r.get("media_path"):
            pic = "/media/" + Path(str(r["media_path"])).name
        live = str(r.get("status") or "").lower() in ("live", "published", "running")
        out.append({
            "id": f"c{r['id']}",
            "channel": platform,
            "chanFg": ACCENT if platform.lower() != "facebook" else "#52525B",
            "spec": r.get("product_name") or "",
            "copy": " ".join(x for x in (r.get("headline"), r.get("body"),
                                         r.get("call_to_action")) if x),
            "image": pic,
            "hasImage": bool(pic),
            # Handed over as a finished CSS value: the parser sees an
            # unparseable url() before binding and skips it, where an
            # <img src> would have been fetched literally.
            "imageCss": f"url('{pic}')" if pic else "none",
            "noImage": not pic,
            "ph": "No picture yet — make one in the Ad studio",
            "pending": not live,
            "border": BORDER if live else AMBER_TINT,
        })
    return out


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
        # The node id as well as the label. The graph used to look agents up
        # by display name, and the run player writes "Inventory" where the
        # roster says "Inventory Agent" — so nothing matched and the flow
        # never drew. An id matches or it does not.
        "id": NODE_ID.get(str(ev.get("actor") or ""), ""),
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


def _owner_prefix(session_id: str) -> str:
    """The part of a run id that names the owner: "sess-<tag>-".

    Returns something unmatchable rather than "" when the id has no owner
    tag, because an empty prefix would match every shop on the machine —
    the exact failure this exists to prevent.
    """
    parts = str(session_id or "").split("-")
    if len(parts) >= 3 and parts[0] == "sess":
        return f"{parts[0]}-{parts[1]}-"
    return "\x00no-owner"


def runs(current_session: str) -> list[dict]:
    """Real runs for the design's Runs player, newest first.

    Replaces the bundle's scripted demo run. Steps come from the durable
    trace, so a run recorded before this process started still plays back.
    """
    out = []
    for s in bus.sessions(30):
        # Only *this owner's* sessions. The trace database is one file for
        # the whole machine, so without this filter every shop reads every
        # other shop's activity — their products, their customers, their
        # name. Matching the owner prefix rather than the exact run keeps
        # yesterday's runs visible after a restart.
        if not str(s["session_id"]).startswith(_owner_prefix(current_session)):
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


def history(current_session: str = "") -> list[dict]:
    """What *this* team has actually done, newest first.

    Shape: {id, cat, text, by, t, dot, why}. Built from the durable trace so
    it survives a restart, with each agent's own summary as the `why`.

    Scoped to the signed-in owner's session for the same reason as `runs`:
    the trace is a single machine-wide file, and an unfiltered read hands one
    shop the contents of another's day.
    """
    rows = []
    for s in bus.sessions(30):
        if not str(s["session_id"]).startswith(_owner_prefix(current_session)):
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
# The values the design used to hard-code
# ---------------------------------------------------------------------------


def today_label() -> str:
    """Today, as the dashboard's date line.

    The bundle shipped with "Tuesday, 12 August" typed into the markup, which
    is wrong every day but one.
    """
    now = datetime.now()
    return f"{now:%A}, {now.day} {now:%B}"


def _best_seller() -> dict | None:
    """The product the shop actually sells most of, by money taken."""
    rows = memory.db.query(
        "SELECT product_name, SUM(amount) AS taken, SUM(quantity) AS units, "
        "       AVG(unit_price) AS price, AVG(unit_cost) AS cost "
        "FROM orders WHERE product_name IS NOT NULL AND product_name != '' "
        "GROUP BY product_name ORDER BY taken DESC LIMIT 1")
    return rows[0] if rows else None


def margin() -> dict[str, str]:
    """What the shop keeps per sale, from its own orders.

    The design carried "33.1% · down from 37% — oil got dearer" as a literal.
    Every figure here is computed, and when there is nothing to compute from
    it says so instead of inventing a percentage.
    """
    empty = {
        "now": DASH, "note": "no sales recorded yet",
        "noteColor": MUTED, "keepPerPiece": DASH, "packPrice": DASH,
        "product": "", "title": "Nothing costed yet",
        "subtitle": "Log a sale, or tell your team what a piece costs you, "
                    "and the real breakdown appears here.",
    }
    row = _best_seller()
    if not row or not row.get("price"):
        return empty

    price = float(row.get("price") or 0)
    cost = float(row.get("cost") or 0)
    if price <= 0:
        return empty
    if cost <= 0:
        return {**empty,
                "packPrice": _cur(price),
                "product": row.get("product_name") or "",
                "title": f"{row.get('product_name') or 'Your best seller'}, "
                         f"selling at {_cur(price)}",
                "subtitle": "What it costs you to make is not recorded yet, "
                            "so the margin cannot be worked out. Tell your "
                            "team the unit cost and this fills in."}

    pct = (price - cost) / price * 100
    # Compare with the margin before the most recent price change, if there
    # is one on record — that is what makes a note about direction honest.
    hist = memory.db.query(
        "SELECT margin_pct FROM pricing_history "
        "WHERE margin_pct IS NOT NULL ORDER BY id DESC LIMIT 2")
    note, colour = "on the sales you have logged", MUTED
    if len(hist) >= 2 and hist[1].get("margin_pct"):
        was = float(hist[1]["margin_pct"])
        if abs(pct - was) >= 0.5:
            direction = "up from" if pct > was else "down from"
            note = f"{direction} {was:.0f}% at your last price"
            colour = ACCENT if pct > was else AMBER
    return {
        "now": f"{pct:.1f}%",
        "note": note,
        "noteColor": colour,
        "keepPerPiece": _cur(price - cost),
        "packPrice": _cur(price),
        "product": row.get("product_name") or "",
        "title": f"One {row.get('product_name') or 'unit'}, honestly costed",
        "subtitle": f"From {int(row.get('units') or 0)} sold at "
                    f"{_cur(price)} each.",
    }


def cost_rows() -> list[dict]:
    """Where the money in one sale goes.

    The bundle listed beef, dough, oil and packaging — a recipe this backend
    never records. It splits what it does know instead: what the piece costs
    to make, and what is left. No invented ingredients.
    """
    row = _best_seller()
    if not row or not row.get("price"):
        return []
    price = float(row.get("price") or 0)
    cost = float(row.get("cost") or 0)
    if price <= 0 or cost <= 0:
        return []
    keep = max(0.0, price - cost)
    top = max(cost, keep) or 1
    return [
        {"k": "What it costs you to make", "v": _cur(cost),
         "pct": round(cost / top * 100), "color": ACCENT},
        {"k": "What you keep", "v": _cur(keep),
         "pct": round(keep / top * 100),
         "color": ACCENT if keep >= cost else AMBER},
    ]


def team(session_id: str) -> dict[str, str]:
    """How many specialists are working right now, and when we last heard.

    Replaces "8 assistants · 3 working now, 5 waiting for their turn. Last
    check 4 minutes ago." — which said the same thing on an idle machine at
    three in the morning.
    """
    people = roster(session_id)
    busy = sum(1 for a in people if a.get("busy"))
    waiting = sum(1 for a in people if a.get("wait"))
    events = bus.load(session_id, 5)
    last = ""
    if events:
        stamp = str(events[-1].get("ts") or "")
        try:
            then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            mins = int((datetime.now(then.tzinfo) - then).total_seconds() // 60)
            last = ("just now" if mins < 1 else
                    f"{mins} minutes ago" if mins < 90 else
                    f"{mins // 60} hours ago")
        except ValueError:
            last = ""
    n = len(people)
    if not busy and not waiting:
        body = f"{n} assistants, none working right now."
    else:
        body = (f"{n} assistants · {busy} working now, "
                f"{waiting} waiting for their turn.")
    return {"summary": body + (f" Last check {last}." if last else
                               " Nothing has run yet."),
            "working": str(busy), "waiting": str(waiting)}


def day_line(session_id: str, pending: dict | None) -> dict[str, str]:
    """The morning sentence, and what is waiting — both counted, not claimed."""
    handled = len(memory.db.query(
        "SELECT 1 FROM social_messages WHERE COALESCE(replied,0)=1"))
    waiting_rows = memory.db.query(
        "SELECT received_at FROM social_messages "
        "WHERE COALESCE(replied,0)=0 ORDER BY received_at LIMIT 1")
    open_count = 1 if pending else 0

    if is_first_run():
        line = ("Your team is ready and has not learned anything about your "
                "shop yet. Ask a question, or send a photo of what you sell.")
    elif open_count:
        line = (f"Your team worked through the inbox and handled {handled} "
                f"message(s) on its own. One thing needs your decision.")
    else:
        line = ("Everything is handled. Your team is watching the inbox, the "
                "stock and the ads, and will only interrupt you if money or "
                "a promise is at stake.")

    if not open_count:
        pend = "nothing waiting"
    else:
        oldest = str((waiting_rows or [{}])[0].get("received_at") or "")[11:16]
        pend = f"1 waiting{f' · oldest at {oldest}' if oldest else ''}"
    return {"line": line, "pending": pend}


def grow() -> dict[str, str]:
    """The Grow page's headline. Driven by what customers actually asked for."""
    wants = demands()
    if not wants:
        return {"title": "Nothing to chase yet",
                "body": "When customers start asking for something you do not "
                        "sell, the request shows up here with a count — and "
                        "your team works out whether it is worth making."}
    top = wants[0]
    name = top.get("name") or "it"
    n = top.get("n") or 0
    return {
        "title": f"{name} — {n} customer(s) have asked",
        "body": (f"{n} of your own customers asked for {name}. "
                 f"{top.get('note') or ''} Your team can price it and size a "
                 f"first batch on your numbers — ask it to."),
    }



def facts(session_id: str) -> dict[str, str]:
    """The small figures scattered through the dashboard.

    Each of these was a literal in the bundle — 38 answered, ৳30,060 total,
    18.4k reached, $11.20 this month. They are counted here, and anything the
    shop has no basis for comes back as an em dash with the tile saying why
    rather than borrowing the sample shop's number.
    """
    f: dict[str, str] = {}

    # --- inbox --------------------------------------------------------------
    msgs = memory.db.query("SELECT sentiment, COALESCE(replied,0) AS replied "
                           "FROM social_messages")
    answered = sum(1 for m in msgs if m["replied"])
    f["inboxAnswered"] = (f"{answered} answered automatically" if answered
                          else "none answered yet")
    total = len(msgs) or 1
    def _pct(kind: str) -> int:
        return round(sum(1 for m in msgs
                         if (m.get("sentiment") or "").lower() == kind)
                     / total * 100)
    happy, upset = _pct("positive"), _pct("negative")
    neutral = max(0, 100 - happy - upset)
    f["happyPct"] = f"{happy}%"
    f["neutralPct"] = f"{neutral}%"
    f["upsetPct"] = f"{upset}%"
    f["happyBar"] = f"{happy}%"
    f["neutralBar"] = f"{neutral}%"
    f["upsetBar"] = f"{upset}%"
    f["moodNote"] = (f"{happy}% happy" if msgs else "no messages yet")

    # --- promises -----------------------------------------------------------
    pre = memory.preorders()
    units = sum(int(x.get("quantity") or 0) for x in pre)
    value = 0.0
    for x in pre:
        rows = memory.db.query(
            "SELECT sell_price FROM products WHERE name=?",
            (x.get("product_name") or "",))
        if rows:
            value += float(rows[0].get("sell_price") or 0) * int(x.get("quantity") or 0)
    f["ordersFoundUnits"] = f"{units} pcs" if units else DASH
    f["ordersFoundValue"] = (f"{_cur(value)} · added to preorders" if value
                             else "no value recorded")
    f["promisedValue"] = _cur(value) if value else DASH

    # --- the reorder ---------------------------------------------------------
    low = memory.db.query(
        "SELECT p.name, p.unit_cost, i.quantity, i.reorder_level "
        "FROM inventory i JOIN products p ON p.id = i.product_id "
        "WHERE i.quantity <= i.reorder_level")
    cost = sum(float(r.get("unit_cost") or 0) * max(0, int(r.get("reorder_level") or 0) * 2
                                                    - int(r.get("quantity") or 0))
               for r in low)
    f["poTotal"] = _cur(cost) if cost else DASH
    f["poArrives"] = DASH
    f["poPayback"] = DASH

    # --- advertising ---------------------------------------------------------
    camp = memory.db.query(
        "SELECT COALESCE(SUM(spend_total),0) AS spent, "
        "       COALESCE(SUM(budget_daily),0) AS daily, COUNT(*) AS n "
        "FROM campaigns")
    spent = float(camp[0]["spent"]) if camp else 0.0
    f["adSpentWeek"] = _cur(spent) if spent else _cur(0)
    f["adSales"] = DASH
    f["adReturn"] = "no attributed sales yet"
    f["adCostPerCustomer"] = DASH
    f["adCostLimit"] = "no limit set"
    f["adReach"] = DASH
    f["adArea"] = (memory.profile() or {}).get("location") or "your area"

    # --- price advice --------------------------------------------------------
    hist = memory.pricing_history()
    latest = hist[0] if hist else {}
    f["wholesale"] = DASH
    f["rivalPrice"] = DASH
    found = memory.db.query("SELECT COUNT(*) c, AVG(price) a FROM competitors")
    n = int(found[0]["c"]) if found else 0
    if n:
        f["rivalsNote"] = (f"{n} priced listing(s) your team found, "
                           f"averaging {_cur(found[0]['a'])}.")
        f["rivalPrice"] = _cur(found[0]["a"])
    else:
        f["rivalsNote"] = ("Nobody has compared prices nearby yet — ask your "
                           "team to research who else sells this, and the "
                           "listings it finds appear here with their prices.")
    if latest.get("sell_price"):
        keep = _cur(latest["sell_price"])
        f["raiseTo"] = f"Keep {keep}"
        f["keepFor"] = "Ask for a new price"
    else:
        f["raiseTo"] = "No price set"
        f["keepFor"] = "Ask your team to price it"

    # --- grow ---------------------------------------------------------------
    wants = demands()
    top = wants[0] if wants else {}
    f["growAskedBy"] = f"{top.get('n', 0)} people" if wants else DASH
    f["growRivals"] = DASH
    f["growPrice"] = DASH
    f["growRisk"] = DASH

    # --- limits --------------------------------------------------------------
    budget = (memory.profile() or {}).get("monthly_budget")
    f["limitAds"] = _cur(budget) if budget else "not set"
    f["limitStock"] = "not set"
    f["limitDiscount"] = "not set"

    # --- what the workforce costs -------------------------------------------
    ledger = ledger_for(session_id)
    spend = sum(c.cost_usd for c in ledger.calls)
    tokens = sum(c.input_tokens + c.output_tokens for c in ledger.calls)
    rate = fx.convert(1, settings.currency, "USD") if settings.currency else None
    f["usageToday"] = f"${spend:.2f}"
    f["usageTokens"] = f"{tokens:,} tokens · {len(ledger.calls)} call(s)"
    f["usageMonth"] = f"${spend:.2f}"
    f["usageMonthNote"] = (f"\u2248 {_cur(spend * rate)}" if rate else
                           "this session only")
    f["costPerDecision"] = (f"${spend / max(1, len(ledger.calls)):.3f}"
                            if ledger.calls else DASH)
    f["decisionsNote"] = f"{len(ledger.calls)} model call(s)"
    events = bus.load(session_id, 400)
    errs = sum(1 for e in events if e.get("level") == "error")
    f["failuresCaught"] = str(errs)
    f["failuresNote"] = ("none stopped a workflow" if errs
                         else "nothing has failed")
    return f



def price_advice() -> dict[str, str]:
    """What the Pricing agent last worked out, in the shop's own numbers.

    The bundle carried a whole worked example about oil rising nine taka a
    litre. This says what was actually recorded, and says nothing when
    nothing has been.
    """
    hist = memory.pricing_history()
    if not hist:
        return {
            "headline": "No price worked out yet",
            "body": "Ask your team what to charge for something you sell and "
                    "the reasoning appears here, with the cost, the margin "
                    "and the break-even it used.",
            "source": "nothing checked yet",
            "doneText": "", "raiseLabel": "", "keepLabel": "",
        }
    latest = hist[0]
    product = latest.get("product_name") or "your product"
    price = _cur(latest.get("sell_price"))
    cost = _cur(latest.get("unit_cost"))
    margin = latest.get("margin_pct")
    body = (f"{cost} to make, {price} to sell"
            + (f" — you keep {float(margin):.0f}%." if margin is not None else ".")
            + " " + (latest.get("rationale") or "")[:400])
    return {
        "headline": f"{product} at {price}",
        "body": body.strip(),
        "source": f"from your own costs on {str(latest.get('created_at') or '')[:10]}",
        "doneText": f"Kept at {price}. Your team will tell you if what you "
                    f"keep starts dropping.",
        "raiseLabel": f"Keep {price}",
        "keepLabel": "Ask for a new price",
    }



def rivals() -> list[dict]:
    """Who else sells this, at what price — from the shop's own research.

    Rows come from searches the owner asked for, and only the results that
    actually named a price are kept, each with the page it came from. An
    empty list means nobody has looked yet, which is the honest answer until
    they do.
    """
    rows = memory.db.query(
        "SELECT name, price, currency, note, source FROM competitors "
        "ORDER BY price LIMIT 6")
    return [
        {
            "name": r.get("name") or "A seller",
            # _cur takes the whole prefix, space included.
            "price": _cur(r.get("price"),
                         f"{r.get('currency') or settings.currency} "),
            "note": (r.get("note") or "")[:80],
            "source": r.get("source") or "",
        }
        for r in rows
    ]




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
        "creatives": creatives(),
        "channels": channels(),
        "pnl": pnl(),
        "demands": demands(),
        "history": history(session_id),
        "roster": roster(session_id),
        "runs": runs(session_id),
        "memRecords": mem_records(),
        "costBars": cost_bars(session_id),
        "failures": failures(session_id),
        "todayLabel": today_label(),
        "facts": facts(session_id),
        "margin": margin(),
        "priceAdvice": price_advice(),
        "rivals": rivals(),
        "costRows": cost_rows(),
        "team": team(session_id),
        "dayLine": day_line(session_id, pending),
        "grow": grow(),
        "stats": memory.stats(),
    }
