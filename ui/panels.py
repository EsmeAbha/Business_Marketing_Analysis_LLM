"""Render functions for each dashboard panel.

Kept separate from app.py so the control flow (running the graph, handling
approvals) stays readable and the panels stay pure-render.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st
from streamlit.components.v1 import html as render_html

from aiworkforce.agents.base import ledger_for
from aiworkforce.config import settings
from aiworkforce.memory import memory
from aiworkforce.observability import bus
from aiworkforce.pricing import MODEL_RATES
from aiworkforce.state import STAGE_ORDER

# Colour + icon per trace event kind.
KIND_STYLE: dict[str, tuple[str, str]] = {
    "session_start": ("🚀", "#6366f1"),
    "session_end": ("🏁", "#6366f1"),
    "plan": ("🗺️", "#8b5cf6"),
    "handoff": ("➡️", "#0ea5e9"),
    "agent_start": ("▶️", "#22c55e"),
    "agent_end": ("✅", "#16a34a"),
    "tool_call": ("🔧", "#f59e0b"),
    "llm_call": ("🧠", "#a855f7"),
    "llm_usage": ("💰", "#64748b"),
    "approval": ("🙋", "#eab308"),
    "error": ("❌", "#ef4444"),
}

AGENT_ICONS = {
    "supervisor": "🧭",
    "market_research": "🔍",
    "product_vision": "📸",
    "pricing": "💵",
    "inventory": "📦",
    "ad_creative": "📣",
    "engagement": "💬",
    "delivery": "🚚",
    "reporting": "📊",
    "owner": "👤",
    "graph": "🕸️",
}


def _icon(actor: str) -> str:
    return AGENT_ICONS.get(actor, "🤖")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def render_dashboard(runtime, session_id: str, roster: dict[str, dict[str, str]]) -> None:
    st.subheader("Workflow stage")

    values = runtime.state_values(session_id) if session_id else {}
    current_stage = values.get("stage", "idea_research")
    completed = values.get("completed_agents", [])

    cols = st.columns(len(STAGE_ORDER))
    reached = False
    for col, stage in zip(cols, STAGE_ORDER):
        is_current = stage == current_stage
        if is_current:
            reached = True
        label = stage.replace("_", " ").title()
        marker = "🔵" if is_current else ("✅" if not reached else "⚪")
        col.markdown(
            f"<div style='text-align:center'><div style='font-size:1.4rem'>{marker}</div>"
            f"<div style='font-size:0.7rem;line-height:1.1'>{label}</div></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Agent roster")
        for name, meta in roster.items():
            runs = completed.count(name)
            status = f"✅ ran {runs}×" if runs else "⚪ idle"
            gate = " 🔒 approval-gated" if meta.get("requires_approval") == "True" else ""
            with st.expander(f"{_icon(name)} **{meta['title']}** — {status}{gate}", expanded=False):
                st.write(meta["description"])
                st.caption(f"Tools: {meta['tools']}")

    with right:
        st.subheader("Business state")
        stats = memory.stats()
        a, b = st.columns(2)
        a.metric("Products", stats["products"])
        b.metric("Knowledge docs", stats["knowledge_documents"])
        a.metric("Pre-orders", stats["preorders"])
        b.metric("Campaigns", stats["campaigns"])
        a.metric("Conversations", stats["conversations"])
        b.metric("Reports", stats["reports"])

        low = memory.low_stock()
        if low:
            st.warning(
                "**Low stock:** "
                + ", ".join(f"{r['name']} ({r['quantity']})" for r in low)
            )

        st.subheader("Plan")
        plan = values.get("plan") or []
        if plan:
            for i, step in enumerate(plan, 1):
                st.markdown(f"{i}. {step}")
        else:
            st.caption("No plan yet — send a request to start.")


# ---------------------------------------------------------------------------
# Live execution trace
# ---------------------------------------------------------------------------


def render_trace(session_id: str) -> None:
    st.subheader("Live execution trace")

    events = bus.load(session_id) if session_id else []
    if not events:
        st.info("No activity yet. Send a request from the sidebar to start the workforce.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    kinds = sorted({e["kind"] for e in events})
    actors = sorted({e["actor"] for e in events})
    kind_filter = c1.multiselect("Event type", kinds, default=kinds, key="trace_kinds")
    actor_filter = c2.multiselect("Agent", actors, default=actors, key="trace_actors")
    newest_first = c3.checkbox("Newest first", value=True, key="trace_order")

    filtered = [
        e for e in events if e["kind"] in kind_filter and e["actor"] in actor_filter
    ]
    if newest_first:
        filtered = list(reversed(filtered))

    st.caption(f"{len(filtered)} of {len(events)} events")

    for e in filtered[:400]:
        icon, colour = KIND_STYLE.get(e["kind"], ("•", "#94a3b8"))
        border = "#ef4444" if e["level"] == "error" else colour
        time = e["ts"].split("T")[-1].replace("+00:00", "")
        st.markdown(
            f"""<div style="border-left:3px solid {border};padding:2px 0 2px 10px;margin:4px 0">
            <span style="color:#94a3b8;font-family:monospace;font-size:0.75rem">{time}</span>
            &nbsp;{icon} <strong>{_icon(e['actor'])} {e['actor']}</strong>
            <span style="color:{colour};font-size:0.75rem">[{e['kind']}]</span><br>
            <span style="font-size:0.88rem">{e['summary']}</span></div>""",
            unsafe_allow_html=True,
        )
        if e["payload"]:
            with st.expander("payload", expanded=False):
                st.json(e["payload"])


# ---------------------------------------------------------------------------
# Agent-to-agent communication
# ---------------------------------------------------------------------------


def render_communication(session_id: str) -> None:
    st.subheader("Agent communication history")
    st.caption(
        "Every task the supervisor delegated and every structured result returned. "
        "This is the message bus agents collaborate over."
    )

    messages = memory.agent_messages(session_id) if session_id else []
    if not messages:
        st.info("No agent-to-agent messages yet.")
        return

    for m in messages:
        sender, recipient = m["sender"], m["recipient"]
        direction = f"{_icon(sender)} **{sender}** → {_icon(recipient)} **{recipient}**"
        time = (m["created_at"] or "").split("T")[-1].replace("+00:00", "")
        with st.expander(f"{direction} · {m['task'][:110] or '(no task)'} · {time}"):
            st.markdown(f"**Task:** {m['task'] or '_none_'}")
            try:
                payload = json.loads(m["payload"])
            except (json.JSONDecodeError, TypeError):
                payload = m["payload"]
            if isinstance(payload, dict) and payload:
                st.json(payload)
            elif payload:
                st.code(str(payload)[:4000])
            else:
                st.caption("(empty payload)")


# ---------------------------------------------------------------------------
# Execution graph
# ---------------------------------------------------------------------------


def render_graph(runtime) -> None:
    st.subheader("Execution graph (LangGraph)")
    st.caption(
        "Supervisor fans out to eight specialists; every specialist returns to the "
        "supervisor, which re-decides. 🔒 marks nodes that suspend for owner approval."
    )

    mermaid = runtime.mermaid()

    render_html(
        f"""
        <div style="background:#ffffff;border-radius:8px;padding:12px;overflow:auto">
          <pre class="mermaid">{mermaid}</pre>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <script>
          mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
        </script>
        """,
        height=620,
        scrolling=True,
    )

    with st.expander("Mermaid source (paste into any Mermaid viewer)"):
        st.code(mermaid, language="text")

    png = runtime.png()
    if png:
        st.download_button(
            "Download graph as PNG", png, "architecture.png", "image/png"
        )


# ---------------------------------------------------------------------------
# Token usage and cost
# ---------------------------------------------------------------------------


def render_cost(session_id: str) -> None:
    st.subheader("Token usage & estimated API cost")

    ledger = ledger_for(session_id) if session_id else None
    if not ledger or not ledger.calls:
        st.info("No LLM calls in this session yet.")
        _render_rate_card()
        return

    total_in = sum(c.input_tokens for c in ledger.calls)
    total_out = sum(c.output_tokens for c in ledger.calls)
    total_cached = sum(c.cache_read_tokens + c.cache_write_tokens for c in ledger.calls)

    a, b, c, d = st.columns(4)
    a.metric("LLM calls", len(ledger.calls))
    b.metric("Input tokens", f"{total_in:,}")
    c.metric("Output tokens", f"{total_out:,}")
    d.metric("Estimated cost", f"${ledger.total_cost_usd:.4f}")

    if total_cached:
        st.caption(f"Cached tokens: {total_cached:,} (billed at reduced rates)")

    st.markdown("**Cost by agent**")
    rows = [
        {
            "Agent": agent,
            "Calls": int(v["calls"]),
            "Input": int(v["input"]),
            "Output": int(v["output"]),
            "Cached": int(v["cached"]),
            "Cost (USD)": round(v["cost_usd"], 5),
        }
        for agent, v in sorted(
            ledger.by_agent().items(), key=lambda kv: -kv[1]["cost_usd"]
        )
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Share-of-spend bars, drawn without a charting dependency.
    peak = max((r["Cost (USD)"] for r in rows), default=0.0)
    for r in rows:
        share = (r["Cost (USD)"] / peak) if peak else 0.0
        st.progress(
            min(1.0, share),
            text=f"{_icon(r['Agent'])} {r['Agent']} — ${r['Cost (USD)']:.5f}",
        )

    with st.expander("Per-call detail"):
        st.dataframe(
            [
                {
                    "#": i,
                    "Agent": c.agent,
                    "Model": c.model,
                    "In": c.input_tokens,
                    "Out": c.output_tokens,
                    "Cached": c.cache_read_tokens + c.cache_write_tokens,
                    "Cost (USD)": round(c.cost_usd, 6),
                }
                for i, c in enumerate(ledger.calls, 1)
            ],
            use_container_width=True,
            hide_index=True,
        )

    _render_rate_card()


def _render_rate_card() -> None:
    with st.expander("Rate card (USD per 1M tokens)"):
        st.dataframe(
            [
                {"Model": m, "Input": f"${i:.2f}", "Output": f"${o:.2f}"}
                for m, (i, o) in MODEL_RATES.items()
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Cache reads bill at ~0.1× input; cache writes at ~1.25×. "
            f"Active model: `{settings.model}`."
        )


# ---------------------------------------------------------------------------
# Logs and errors
# ---------------------------------------------------------------------------


def render_logs(session_id: str) -> None:
    st.subheader("Execution logs & error report")

    events = bus.load(session_id) if session_id else []
    errors = [e for e in events if e["level"] == "error"]
    warnings = [e for e in events if e["level"] == "warning"]

    a, b, c = st.columns(3)
    a.metric("Total log entries", len(events))
    b.metric("Warnings", len(warnings))
    c.metric("Errors", len(errors))

    if errors:
        st.error(f"{len(errors)} error(s) recorded — the workflow continued regardless.")
        for e in errors:
            with st.expander(f"❌ {e['actor']} · {e['summary'][:120]}"):
                st.write(e["summary"])
                if e["payload"].get("traceback"):
                    st.code(e["payload"]["traceback"], language="text")
                else:
                    st.json(e["payload"])
    else:
        st.success("No errors recorded in this session.")

    if warnings:
        with st.expander(f"⚠️ {len(warnings)} warning(s)"):
            for w in warnings:
                st.markdown(f"- **{w['actor']}** · {w['summary']}")

    st.markdown("**Raw log stream**")
    level_filter = st.selectbox(
        "Minimum level", ["info", "warning", "error"], index=0, key="log_level"
    )
    order = {"info": 0, "warning": 1, "error": 2}
    lines = [
        f"{e['ts']} | {e['level'].upper():8} | {e['actor']:16} | {e['kind']:14} | {e['summary']}"
        for e in events
        if order[e["level"]] >= order[level_filter]
    ]
    st.code("\n".join(lines[-300:]) or "(nothing at this level)", language="text")

    if lines:
        st.download_button(
            "Download log", "\n".join(lines), f"{session_id}-log.txt", "text/plain"
        )


# ---------------------------------------------------------------------------
# Memory viewer
# ---------------------------------------------------------------------------


def render_memory() -> None:
    st.subheader("Shared knowledge base")
    st.caption(
        "Everything agents have written. The structured tables are the business's "
        "system of record; the semantic store is what agents retrieve from."
    )

    structured, semantic, search = st.tabs(
        ["📋 Structured store", "🧠 Semantic store", "🔎 Retrieval test"]
    )

    with structured:
        profile = memory.profile()
        if profile:
            st.markdown("**Business profile**")
            st.json({k: v for k, v in profile.items() if v is not None})

        tables = {
            "Products & inventory": memory.inventory(),
            "Pricing history": memory.pricing_history(),
            "Customer conversations": memory.conversations(200),
            "Pre-orders": memory.preorders(),
            "Campaigns": memory.campaigns(),
            "Deliveries": memory.deliveries(),
            "Approvals": memory.approvals(),
        }
        for label, rows in tables.items():
            with st.expander(f"{label} ({len(rows)})"):
                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("(empty)")

    with semantic:
        docs = memory.vectors.all_documents()
        st.metric("Documents in semantic memory", len(docs))
        for doc in reversed(docs[-60:]):
            meta = doc.metadata
            with st.expander(
                f"{_icon(meta.get('agent', ''))} {meta.get('agent', '?')} · "
                f"{meta.get('kind', '?')} · {doc.ts.split('T')[0]}"
            ):
                st.write(doc.text)
                st.caption(f"metadata: {meta}")

    with search:
        st.caption(
            "Run the same retrieval an agent runs. This is the RAG layer that lets "
            "the Reporting agent read what Market Research concluded three stages earlier."
        )
        query = st.text_input(
            "Query", value="what price did we decide and why", key="rag_query"
        )
        k = st.slider("Results", 1, 10, 5, key="rag_k")
        if st.button("Retrieve", key="rag_go") and query:
            hits = memory.recall(query, k=k)
            if not hits:
                st.warning("No matching documents.")
            for doc, score in hits:
                st.markdown(
                    f"**{doc.metadata.get('agent', '?')} / {doc.metadata.get('kind', '?')}** "
                    f"— relevance `{score:.3f}`"
                )
                st.write(doc.text)
                st.divider()


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


def render_report(session_id: str, final_report: str) -> None:
    st.subheader("Final report")

    if final_report:
        st.markdown(final_report)
        st.download_button(
            "Download this report (Markdown)",
            final_report,
            f"{session_id}-report.md",
            "text/markdown",
        )
    else:
        st.info("No report for the current session yet.")

    past = memory.reports(20)
    if past:
        st.divider()
        st.markdown("**Report archive**")
        for r in past:
            with st.expander(f"{r['title']} · {r['created_at']} · session {r['session_id']}"):
                st.markdown(r["body"])


# ---------------------------------------------------------------------------
# Approval control
# ---------------------------------------------------------------------------


def render_approval_gate(pending: dict[str, Any]) -> dict[str, Any] | None:
    """Render the HITL checkpoint. Returns a decision dict once the owner acts."""
    st.warning(f"🙋 **Owner approval required** — {pending.get('title', 'Action pending')}")

    with st.container(border=True):
        st.markdown(pending.get("detail", ""))
        st.caption(
            f"Checkpoint `{pending.get('checkpoint')}` raised by "
            f"`{pending.get('agent')}`. The workflow is suspended until you decide."
        )

        feedback = st.text_area(
            "Feedback (required if you request changes)",
            key=f"fb_{pending.get('checkpoint')}",
            placeholder="e.g. Make the Bangla copy less formal and lead with the price.",
        )

        a, b, c = st.columns(3)
        if a.button("✅ Approve", type="primary", use_container_width=True):
            return {"decision": "approve", "feedback": feedback}
        if b.button("✏️ Request changes", use_container_width=True):
            if not feedback.strip():
                st.error("Please describe what you want changed.")
            else:
                return {"decision": "request_changes", "feedback": feedback}
        if c.button("❌ Reject", use_container_width=True):
            return {"decision": "reject", "feedback": feedback}

    return None
