"""Lucida — the owner's workspace.

Laid out to the `Business Suite` design: a 244px rail of sections on the left,
the working column on the right. Streamlit is the transport, not the look —
its chrome is removed in `ui/theme.py` and the page is rebuilt to the design's
own measurements.

Today is the conversation: the owner talks to the workforce the way they'd talk
to a person, and approval checkpoints appear as decision cards in the thread.
The other sections are windows onto the same shared memory the agents write to.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make `src/` importable without requiring an editable install.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lucida.agents.base import ledger_for  # noqa: E402
from lucida.config import UPLOAD_DIR, settings  # noqa: E402
from lucida.graph import WorkforceRuntime, agent_roster  # noqa: E402
from lucida.memory import memory  # noqa: E402
from lucida.observability import bus  # noqa: E402
from ui import pages, panels, theme  # noqa: E402

st.set_page_config(
    page_title="Lucida",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# The rail, in the design's order: what the owner does, then what the
# workforce did. (key, icon, label)
NAV = [
    ("today", "◆", "Today"),
    ("customers", "◇", "Customers"),
    ("stock", "▣", "Stock"),
    ("marketing", "◈", "Marketing"),
    ("money", "◉", "Money"),
    ("grow", "◐", "Grow"),
    ("history", "▤", "History"),
    ("workforce", "⬡", "The workforce"),
    ("settings", "⚙", "Settings"),
]

# What each agent is doing, phrased the way a colleague would say it.
NARRATION = {
    "supervisor": ("🧭", "Working out who should handle this"),
    "market_research": ("🔍", "Researching the market"),
    "product_vision": ("📸", "Looking at your photo"),
    "pricing": ("💵", "Working out the numbers"),
    "inventory": ("📦", "Updating your stock records"),
    "ad_creative": ("📣", "Writing your ads"),
    "engagement": ("💬", "Reading what customers are saying"),
    "delivery": ("🚚", "Arranging the delivery"),
    "reporting": ("📊", "Pulling your report together"),
    "finalize": ("✍️", "Writing up what I found"),
}

OPENERS = [
    "What food business should I start in Dhaka with 30,000 taka?",
    "Here's a photo of what I make — is it worth selling?",
    "What are my customers asking for that I don't sell?",
    "Give me this week's report and what I should change.",
]


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Starting the workforce…")
def get_runtime() -> WorkforceRuntime:
    return WorkforceRuntime()


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("session_id", WorkforceRuntime.new_session_id())
    ss.setdefault("messages", [])       # the conversation thread
    ss.setdefault("run_request", None)  # {"kind": "start"|"resume", ...}
    ss.setdefault("nav", "today")       # which rail section is showing
    ss.setdefault("context", {})        # owner context from Settings


def reset_conversation() -> None:
    ss = st.session_state
    ss.session_id = WorkforceRuntime.new_session_id()
    ss.messages = []
    ss.run_request = None


# ---------------------------------------------------------------------------
# Conversation rendering
# ---------------------------------------------------------------------------


def render_message(msg: dict) -> None:
    role = msg["role"]

    if role == "user":
        with st.chat_message("user", avatar="👤"):
            if msg.get("content"):
                st.markdown(msg["content"])
            for path in msg.get("images", []):
                st.image(path, width=220)
        return

    if role == "approval":
        render_approval_message(msg)
        return

    with st.chat_message("assistant", avatar="🏪"):
        steps = msg.get("steps", [])
        if steps:
            done = msg.get("agents_used", 0)
            label = (
                f"Worked through {done} agent{'s' if done != 1 else ''}"
                if done
                else "Working notes"
            )
            with st.expander(label, expanded=False):
                for icon, text in steps:
                    st.markdown(f"{icon} {text}")
        if msg.get("content"):
            st.markdown(msg["content"])
        if msg.get("error"):
            st.warning(msg["error"])


def render_approval_message(msg: dict) -> None:
    """An approval checkpoint, shown as a decision card in the thread.

    The card body is design-system HTML; the controls under it are native
    widgets, because these are the buttons that actually release a spend.
    """
    pending = msg["pending"]
    resolved = msg.get("resolved")
    agent = pending.get("agent", "")
    kind = "Delivery" if "deliver" in str(agent).lower() else "Spend"

    with st.chat_message("assistant", avatar="🙋"):
        theme.card(
            title=pending.get("title", "I need your go-ahead"),
            body=pending.get("detail", ""),
            tag_text=kind,
            tone="warn",
            by=f"from {agent}" if agent else "",
        )

        if resolved:
            verdict, tone = {
                "approve": ("You approved this", "ok"),
                "reject": ("You said not now", "error"),
                "request_changes": ("You asked for changes", "warn"),
            }.get(resolved["decision"], (resolved["decision"], "idle"))
            note = f" — *{resolved['feedback']}*" if resolved.get("feedback") else ""
            st.markdown(theme.pill(verdict, tone) + note, unsafe_allow_html=True)
            return

        feedback = st.text_area(
            "Anything you want changed?",
            key=f"fb_{msg['id']}",
            placeholder="e.g. make the Bangla less formal and lead with the price",
            height=72,
        )
        a, b, c = st.columns([1, 1, 1])
        if a.button("Go ahead", key=f"ok_{msg['id']}", type="primary",
                    width="stretch"):
            _resolve(msg, "approve", feedback)
        if b.button("Change it", key=f"ch_{msg['id']}", width="stretch"):
            if not feedback.strip():
                st.error("Tell me what to change first.")
            else:
                _resolve(msg, "request_changes", feedback)
        if c.button("Not now", key=f"no_{msg['id']}", width="stretch"):
            _resolve(msg, "reject", feedback)
        st.markdown(
            f"<div class='lu-meta' style='margin-top:6px;'>"
            f"Nothing happens until you tap.</div>",
            unsafe_allow_html=True,
        )


def _resolve(msg: dict, decision: str, feedback: str) -> None:
    msg["resolved"] = {"decision": decision, "feedback": feedback}
    st.session_state.run_request = {
        "kind": "resume",
        "decision": {"decision": decision, "feedback": feedback},
    }
    st.rerun()


# ---------------------------------------------------------------------------
# Executing a turn
# ---------------------------------------------------------------------------


def execute_turn(runtime: WorkforceRuntime, request: dict) -> None:
    """Stream one graph run, narrating progress inside the assistant bubble."""
    ss = st.session_state
    steps: list[tuple[str, str]] = []
    report = ""
    error = ""
    agents_used = 0

    with st.chat_message("assistant", avatar="🏪"):
        status = st.status("Getting started…", expanded=True)

        if request["kind"] == "start":
            stream = runtime.start(
                owner_input=request["text"],
                image_paths=request["images"],
                owner_context=request["context"],
                session_id=ss.session_id,
            )
        else:
            stream = runtime.resume(ss.session_id, request["decision"])

        try:
            for chunk in stream:
                node = chunk.get("node", "")
                update = chunk.get("update") or {}

                if not isinstance(update, dict):
                    update = {}

                if node == "__error__":
                    error = "; ".join(str(e) for e in update.get("errors", []))
                    continue

                if node == "__interrupt__":
                    # The graph suspended for owner approval; the checkpoint is
                    # rendered as its own message once this turn finishes.
                    status.write("🙋 Waiting for your go-ahead…")
                    continue

                icon, phrase = NARRATION.get(node, ("•", node))

                if node == "supervisor":
                    reason = update.get("routing_reason", "")
                    nxt = update.get("next_agent", "")
                    if nxt and nxt != "FINISH":
                        n_icon, n_phrase = NARRATION.get(nxt, ("•", nxt))
                        line = f"**{n_phrase}** — {reason}" if reason else f"**{n_phrase}**"
                        steps.append((n_icon, line))
                        status.update(label=n_phrase)
                        status.write(f"{n_icon} {line}")
                    plan = update.get("plan")
                    if plan:
                        plan_text = "Here's my plan:\n" + "\n".join(
                            f"{i}. {s}" for i, s in enumerate(plan, 1)
                        )
                        steps.insert(0, ("🗺️", plan_text))
                        status.write(f"🗺️ {plan_text}")
                else:
                    agents_used += 1
                    outputs = update.get("agent_outputs", {}) or {}
                    summary = (outputs.get(node) or {}).get("summary", "")
                    if summary:
                        steps.append((icon, summary))
                        status.write(f"{icon} {summary}")
                    if update.get("final_report"):
                        report = update["final_report"]
                    if update.get("errors"):
                        error = "; ".join(str(e) for e in update["errors"])

        except Exception as exc:  # noqa: BLE001 — never hard-crash the chat
            error = f"{type(exc).__name__}: {exc}"
            bus.emit(ss.session_id, "error", "ui", f"turn failed: {exc}", level="error")

        status.update(
            label=f"Done — {agents_used} agent{'s' if agents_used != 1 else ''} worked on this"
            if agents_used
            else "Done",
            state="error" if error and not report else "complete",
            expanded=False,
        )

        if report:
            st.markdown(report)

    ss.messages.append(
        {
            "role": "assistant",
            "steps": steps,
            "content": report,
            "error": error,
            "agents_used": agents_used,
        }
    )

    # A suspended graph becomes the next message in the thread.
    pending = runtime.pending_approval(ss.session_id)
    if pending:
        ss.messages.append(
            {
                "role": "approval",
                "id": f"ap{len(ss.messages)}",
                "pending": pending,
            }
        )


# ---------------------------------------------------------------------------
# The rail
# ---------------------------------------------------------------------------


def rail() -> None:
    """The design's left rail: identity, section nav, live footer."""
    ss = st.session_state

    with st.sidebar:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;"
            f"padding:0 4px 16px;'>"
            f"<div style='width:34px;height:34px;border-radius:11px;"
            f"background:{theme.ACCENT};color:#F4EFE2;display:grid;"
            f"place-items:center;font-family:{theme.SERIF};font-size:19px;'>L</div>"
            f"<div style='display:flex;flex-direction:column;line-height:1.25;"
            f"min-width:0;'>"
            f"<span style='font-weight:600;font-size:14px;'>Lucida</span>"
            f"<span style='font-size:11.5px;color:{theme.MUTED};white-space:nowrap;"
            f"overflow:hidden;text-overflow:ellipsis;'>{theme.esc(settings.location)}"
            f"</span></div></div>",
            unsafe_allow_html=True,
        )

        if not settings.has_llm:
            st.error("**No API key.** Add `GROQ_API_KEY` to `.env`, then restart.")

        # Nav rows. The active one is `primary`, which theme.py restyles to the
        # design's tinted row rather than a filled button.
        badges = _rail_badges()
        with st.container(key="nav"):
            for key, icon, label in NAV:
                n = badges.get(key)
                text = f"{icon}  {label}" + (f"   ({n})" if n else "")
                if st.button(
                    text,
                    key=f"nav_{key}",
                    width="stretch",
                    type="primary" if ss.nav == key else "secondary",
                ):
                    ss.nav = key
                    st.rerun()

        ledger = ledger_for(ss.session_id)
        with st.container(key="railfoot"):
            theme.live_dot(
                "Workforce ready" if settings.has_llm else "Waiting for a key"
            )
            if ledger.calls:
                st.markdown(
                    f"<div style='font-size:11.5px;color:{theme.MUTED};"
                    f"line-height:1.5;padding:4px 0 10px;'>"
                    f"{len(ledger.calls)} calls · {ledger.total_tokens:,} tokens · "
                    f"${ledger.total_cost_usd:.4f}</div>",
                    unsafe_allow_html=True,
                )
            if st.button("New conversation", width="stretch"):
                reset_conversation()
                st.rerun()


def _rail_badges() -> dict[str, int]:
    """Counts shown beside rail entries, matching the design's badge dots."""
    try:
        stats = memory.stats()
        return {
            "customers": stats["conversations"],
            "stock": len(memory.low_stock()),
            "marketing": stats["campaigns"],
            "history": stats["reports"],
        }
    except Exception:  # noqa: BLE001 — a badge must never break the rail
        return {}


# ---------------------------------------------------------------------------
# The workforce section
# ---------------------------------------------------------------------------


def render_workforce(runtime: WorkforceRuntime) -> None:
    theme.page_header(
        "The workforce",
        "Who did what, which tools they called, and what it cost — the same "
        "run your agents just executed, opened up.",
    )
    tabs = st.tabs(
        ["Roster", "Trace", "Hand-offs", "Graph", "Cost", "Logs", "Memory", "Reports"]
    )
    sid = st.session_state.session_id
    with tabs[0]:
        panels.render_dashboard(runtime, sid, agent_roster())
    with tabs[1]:
        panels.render_trace(sid)
    with tabs[2]:
        panels.render_communication(sid)
    with tabs[3]:
        panels.render_graph(runtime)
    with tabs[4]:
        panels.render_cost(sid)
    with tabs[5]:
        panels.render_logs(sid)
    with tabs[6]:
        panels.render_memory()
    with tabs[7]:
        last = next(
            (m["content"] for m in reversed(st.session_state.messages)
             if m["role"] == "assistant" and m.get("content")),
            "",
        )
        panels.render_report(sid, last)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _save_uploads(files) -> list[str]:
    paths: list[str] = []
    for f in files or []:
        dest = UPLOAD_DIR / f"{st.session_state.session_id}-{f.name}"
        dest.write_bytes(f.getbuffer())
        paths.append(str(dest))
    return paths


def shop_kpis() -> None:
    """The design's KPI row, built strictly from what memory actually holds.

    The source design showed sales, days-of-cover and margin; those come from
    its demo fixture, not from this system. The row reports what Lucida
    genuinely knows instead, because a dashboard that invents numbers is worse
    than one that admits what it hasn't learned yet.
    """
    stats = memory.stats()
    low = memory.low_stock()
    if not any((stats["products"], stats["preorders"], stats["campaigns"], low)):
        return

    cards = [
        {"label": "Products", "value": stats["products"],
         "note": "in your catalogue"},
        {"label": "Pre-orders waiting", "value": stats["preorders"],
         "note": "found in customer chat"},
    ]
    if low:
        names = ", ".join(str(i.get("name", "item")) for i in low[:2])
        cards.append({"label": "Low on stock", "value": len(low),
                      "note": f"{names} running low", "tone": "warn"})
    else:
        cards.append({"label": "Low on stock", "value": 0, "note": "nothing urgent"})
    cards.append({"label": "Campaigns", "value": stats["campaigns"],
                  "note": "written so far"})
    theme.kpis(cards)


def render_today(runtime: WorkforceRuntime) -> None:
    """Today is the conversation — the design's home screen."""
    ss = st.session_state
    values = runtime.state_values(ss.session_id)
    stage = (values.get("stage") or "").replace("_", " ")

    if not ss.messages:
        theme.page_header(
            "What can I help you with?",
            "Tell me about your business, or drop in a photo of what you make. "
            "I'll pull in whichever specialists the job needs.",
        )
        shop_kpis()
        theme.section("Ask your team", "or just type below")
        with st.container(key="openers"):
            cols = st.columns(2)
            for i, opener in enumerate(OPENERS):
                if cols[i % 2].button(opener, width="stretch", key=f"op{i}"):
                    ss.messages.append(
                        {"role": "user", "content": opener, "images": []}
                    )
                    ss.run_request = {
                        "kind": "start", "text": opener,
                        "images": [], "context": ss.context,
                    }
                    st.rerun()
    else:
        theme.page_header("Today", "")
        if stage:
            st.markdown(
                f"<div style='margin:-10px 0 16px;'>{theme.pill(stage, 'ok')}</div>",
                unsafe_allow_html=True,
            )
        shop_kpis()

    for msg in ss.messages:
        render_message(msg)

    if ss.run_request:
        request = ss.run_request
        ss.run_request = None
        execute_turn(runtime, request)
        st.rerun()

    submitted = st.chat_input(
        "Message the workforce…  (attach a product photo with the clip)",
        accept_file="multiple",
        file_type=["jpg", "jpeg", "png", "webp", "gif"],
        disabled=not settings.has_llm,
    )
    if submitted:
        text = (getattr(submitted, "text", "") or "").strip()
        files = getattr(submitted, "files", None) or []
        paths = _save_uploads(files)
        if not text and paths:
            text = (
                "Here's a photo of what I make — take a look and tell me "
                "what you think."
            )
        if text or paths:
            ss.messages.append({"role": "user", "content": text, "images": paths})
            ss.run_request = {
                "kind": "start", "text": text, "images": paths,
                "context": ss.context,
            }
            st.rerun()


def main() -> None:
    init_state()
    theme.inject()
    runtime = get_runtime()
    ss = st.session_state

    rail()

    section = ss.nav
    if section == "today":
        render_today(runtime)
    elif section == "customers":
        pages.customers()
    elif section == "stock":
        pages.stock()
    elif section == "marketing":
        pages.marketing()
    elif section == "money":
        pages.money(ss.session_id, ledger_for(ss.session_id))
    elif section == "grow":
        pages.grow()
    elif section == "history":
        pages.history()
    elif section == "workforce":
        render_workforce(runtime)
    elif section == "settings":
        # Settings owns the owner-context form; the answer is cached in
        # session state so a run started from Today still sees it.
        ss.context = pages.settings_page()


if __name__ == "__main__":
    main()
