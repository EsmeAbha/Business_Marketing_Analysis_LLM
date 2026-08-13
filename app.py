"""AI Business Workforce — conversational interface.

The owner talks to the workforce the way they'd talk to a person: plain
language, photos dropped straight into the composer. Agent activity is narrated
inline as it happens, and approval checkpoints appear as messages in the thread
rather than as a separate control panel.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make `src/` importable without requiring an editable install.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aiworkforce.agents.base import ledger_for  # noqa: E402
from aiworkforce.config import UPLOAD_DIR, settings  # noqa: E402
from aiworkforce.graph import WorkforceRuntime, agent_roster  # noqa: E402
from aiworkforce.memory import memory  # noqa: E402
from aiworkforce.observability import bus  # noqa: E402
from ui import panels  # noqa: E402

st.set_page_config(
    page_title="AI Business Workforce",
    page_icon="🏪",
    layout="centered",
    initial_sidebar_state="expanded",
)

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

CSS = """
<style>
  /* Roomier, more readable conversation column */
  .block-container { padding-top: 2.2rem; max-width: 52rem; }
  [data-testid="stChatMessage"] { padding: 0.25rem 0; }
  [data-testid="stChatMessageContent"] p { line-height: 1.65; }
  /* Quieter status blocks so narration doesn't shout over the answer */
  [data-testid="stExpander"] summary { font-size: 0.9rem; }
  .aiw-suggestion { font-size: 0.85rem; color: #8b93a7; }
  .aiw-strip {
      font-size: 0.78rem; color: #8b93a7; padding: 0.35rem 0 0.9rem 0;
      border-bottom: 1px solid rgba(140,150,175,0.18); margin-bottom: 1.1rem;
  }
</style>
"""

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
    ss.setdefault("show_inspector", False)


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
    """An approval checkpoint, shown as a message in the thread."""
    pending = msg["pending"]
    resolved = msg.get("resolved")

    with st.chat_message("assistant", avatar="🙋"):
        st.markdown(f"**{pending.get('title', 'I need your go-ahead')}**")
        st.markdown(pending.get("detail", ""))

        if resolved:
            verdict = {
                "approve": "✅ You approved this.",
                "reject": "❌ You rejected this.",
                "request_changes": "✏️ You asked for changes.",
            }.get(resolved["decision"], resolved["decision"])
            note = f" — *{resolved['feedback']}*" if resolved.get("feedback") else ""
            st.caption(verdict + note)
            return

        st.caption("I won't do this until you say so.")
        feedback = st.text_area(
            "Anything you want changed?",
            key=f"fb_{msg['id']}",
            placeholder="e.g. make the Bangla less formal and lead with the price",
            height=72,
        )
        a, b, c = st.columns(3)
        if a.button("✅ Go ahead", key=f"ok_{msg['id']}", type="primary",
                    use_container_width=True):
            _resolve(msg, "approve", feedback)
        if b.button("✏️ Change it", key=f"ch_{msg['id']}", use_container_width=True):
            if not feedback.strip():
                st.error("Tell me what to change first.")
            else:
                _resolve(msg, "request_changes", feedback)
        if c.button("❌ Don't", key=f"no_{msg['id']}", use_container_width=True):
            _resolve(msg, "reject", feedback)


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
# Sidebar
# ---------------------------------------------------------------------------


def sidebar() -> dict:
    ss = st.session_state

    with st.sidebar:
        st.markdown("### 🏪 AI Business Workforce")
        st.caption("A supervisor and eight specialists, working for your shop.")

        if not settings.has_llm:
            st.error(
                "**No API key.** Copy `.env.example` to `.env`, add "
                "`ANTHROPIC_API_KEY`, then restart."
            )

        if st.button("✨ New conversation", use_container_width=True):
            reset_conversation()
            st.rerun()

        ss.show_inspector = st.toggle(
            "🔬 Inspector",
            value=ss.show_inspector,
            help="Execution trace, agent messages, graph, cost, logs and memory.",
        )

        st.divider()
        with st.expander("⚙️ Business details", expanded=False):
            st.caption("Optional — the agents estimate anything you leave blank.")
            location = st.text_input("Where you sell", value=settings.location)
            unit_cost = st.number_input("Your unit cost", min_value=0.0, value=0.0, step=1.0)
            fixed_costs = st.number_input(
                "Fixed monthly costs", min_value=0.0, value=0.0, step=100.0
            )
            expected_units = st.number_input(
                "Expected monthly sales", min_value=0, value=0, step=10
            )
            platforms = st.multiselect(
                "Ad platforms",
                ["facebook", "instagram", "youtube"],
                default=["facebook", "instagram"],
            )

        with st.expander("📦 Stock you've bought", expanded=False):
            stock_name = st.text_input("Product")
            c1, c2 = st.columns(2)
            stock_qty = c1.number_input("Qty", min_value=0, value=0, step=1)
            stock_cost = c2.number_input("Cost each", min_value=0.0, value=0.0, step=1.0)

        with st.expander("🚚 Delivery details", expanded=False):
            provider = st.selectbox("Courier", ["steadfast", "pathao", "uber"])
            recipient = st.text_input("Customer name")
            phone = st.text_input("Phone")
            address = st.text_area("Address", height=68)
            cod = st.number_input("Cash on delivery", min_value=0.0, value=0.0, step=10.0)

        st.divider()
        ledger = ledger_for(ss.session_id)
        if ledger.calls:
            st.caption(
                f"This conversation: {len(ledger.calls)} calls · "
                f"{ledger.total_tokens:,} tokens · ${ledger.total_cost_usd:.4f}"
            )

        with st.expander("🔌 Integrations", expanded=False):
            for label, status in settings.integration_status().items():
                icon = (
                    "🟢" if status.startswith("LIVE")
                    else ("🔴" if "MISSING" in status else "🟡")
                )
                st.markdown(
                    f"<div style='font-size:0.78rem'>{icon} {label} — <code>{status}</code></div>",
                    unsafe_allow_html=True,
                )
            st.caption("🟡 simulated adapter — add the API key in `.env` to go live.")

    context = {
        "location": location,
        "unit_cost": unit_cost or None,
        "fixed_costs": fixed_costs,
        "expected_monthly_units": expected_units,
        "platforms": platforms,
    }
    if stock_name and stock_qty:
        context["stock_items"] = [
            {"product_name": stock_name, "quantity": int(stock_qty), "unit_cost": stock_cost}
        ]
    if recipient and address:
        context["delivery"] = {
            "provider": provider,
            "recipient": recipient,
            "phone": phone,
            "address": address,
            "cod_amount": cod,
            "product_name": stock_name,
        }
    return context


# ---------------------------------------------------------------------------
# Inspector
# ---------------------------------------------------------------------------


def render_inspector(runtime: WorkforceRuntime) -> None:
    st.divider()
    st.markdown("#### 🔬 Inspector")
    tabs = st.tabs(
        ["Dashboard", "Trace", "Agent comms", "Graph", "Cost", "Logs", "Memory", "Reports"]
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


def main() -> None:
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)
    runtime = get_runtime()
    ss = st.session_state

    context = sidebar()

    # Compact live strip: what stage we're at, and what the shop looks like.
    values = runtime.state_values(ss.session_id)
    stage = (values.get("stage") or "").replace("_", " ")
    stats = memory.stats()
    bits = [f"stage: **{stage}**"] if stage else []
    if stats["products"]:
        bits.append(f"{stats['products']} product(s)")
    if stats["preorders"]:
        bits.append(f"{stats['preorders']} pre-order(s)")
    low = memory.low_stock()
    if low:
        bits.append(f"⚠️ {len(low)} low on stock")
    if bits:
        st.markdown(
            f"<div class='aiw-strip'>{' &nbsp;·&nbsp; '.join(bits)}</div>",
            unsafe_allow_html=True,
        )

    # --- opening state ---
    if not ss.messages:
        st.markdown("## What can I help you with?")
        st.caption(
            "Tell me about your business, or drop in a photo of what you make. "
            "I'll pull in whichever specialists the job needs."
        )
        cols = st.columns(2)
        for i, opener in enumerate(OPENERS):
            if cols[i % 2].button(opener, use_container_width=True, key=f"op{i}"):
                ss.messages.append({"role": "user", "content": opener, "images": []})
                ss.run_request = {
                    "kind": "start", "text": opener, "images": [], "context": context,
                }
                st.rerun()

    # --- conversation ---
    for msg in ss.messages:
        render_message(msg)

    # --- run a pending turn ---
    if ss.run_request:
        request = ss.run_request
        ss.run_request = None
        execute_turn(runtime, request)
        st.rerun()

    # --- composer ---
    submitted = st.chat_input(
        "Message the workforce…  (attach a product photo with 📎)",
        accept_file="multiple",
        file_type=["jpg", "jpeg", "png", "webp", "gif"],
        disabled=not settings.has_llm,
    )

    if submitted:
        text = (getattr(submitted, "text", "") or "").strip()
        files = getattr(submitted, "files", None) or []
        paths = _save_uploads(files)
        if not text and paths:
            text = "Here's a photo of what I make — take a look and tell me what you think."
        if text or paths:
            ss.messages.append({"role": "user", "content": text, "images": paths})
            ss.run_request = {
                "kind": "start", "text": text, "images": paths, "context": context,
            }
            st.rerun()

    if ss.show_inspector:
        render_inspector(runtime)


if __name__ == "__main__":
    main()
