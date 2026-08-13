"""AI Business Workforce — Streamlit control room.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make `src/` importable without requiring an editable install.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aiworkforce.config import UPLOAD_DIR, settings  # noqa: E402
from aiworkforce.graph import WorkforceRuntime, agent_roster  # noqa: E402
from aiworkforce.memory import memory  # noqa: E402
from aiworkforce.observability import bus  # noqa: E402
from ui import panels  # noqa: E402

st.set_page_config(
    page_title="AI Business Workforce",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Runtime (built once per Streamlit server process)
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Starting the AI workforce…")
def get_runtime() -> WorkforceRuntime:
    return WorkforceRuntime()


def init_state() -> None:
    ss = st.session_state
    ss.setdefault("session_id", WorkforceRuntime.new_session_id())
    ss.setdefault("final_report", "")
    ss.setdefault("busy", False)
    ss.setdefault("last_error", "")
    ss.setdefault("paused", False)


def drain(stream) -> None:
    """Consume a graph run to completion (or to its next interrupt)."""
    ss = st.session_state
    progress = st.empty()
    try:
        for chunk in stream:
            node = chunk.get("node", "?")
            update = chunk.get("update") or {}
            progress.info(f"⏳ Running `{node}` …")
            if isinstance(update, dict):
                if update.get("final_report"):
                    ss.final_report = update["final_report"]
                if update.get("errors"):
                    ss.last_error = "; ".join(str(e) for e in update["errors"])
    except Exception as exc:  # noqa: BLE001 — the UI must never hard-crash
        ss.last_error = f"{type(exc).__name__}: {exc}"
        bus.emit(
            ss.session_id, "error", "ui", f"run aborted: {exc}", level="error"
        )
    finally:
        progress.empty()
        ss.busy = False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def sidebar(runtime: WorkforceRuntime) -> None:
    ss = st.session_state

    with st.sidebar:
        st.title("🏪 AI Business Workforce")
        st.caption("Supervisor + 8 specialists running a small business end to end.")

        if not settings.has_llm:
            st.error(
                "**ANTHROPIC_API_KEY is not set.** Copy `.env.example` to `.env` and "
                "add your key, then restart."
            )

        st.divider()
        st.markdown(f"**Session** `{ss.session_id}`")
        c1, c2 = st.columns(2)
        if c1.button("🆕 New session", use_container_width=True):
            ss.session_id = WorkforceRuntime.new_session_id()
            ss.final_report = ""
            ss.last_error = ""
            ss.paused = False
            st.rerun()
        if c2.button("🔁 Retry", use_container_width=True, help="Resume from the last checkpoint"):
            ss.busy = True
            drain(runtime.retry(ss.session_id))
            st.rerun()

        st.divider()
        st.subheader("Ask the workforce")

        owner_input = st.text_area(
            "What do you need?",
            height=110,
            placeholder=(
                "e.g. What business should I start in Dhaka with 30,000 taka?\n"
                "or: Here's a photo of what I make — is it worth selling?"
            ),
            key="owner_input",
        )

        uploaded = st.file_uploader(
            "Product / inventory photos",
            type=["jpg", "jpeg", "png", "webp", "gif"],
            accept_multiple_files=True,
            help="Triggers the Product Vision agent's photo-to-business-plan flow.",
        )

        with st.expander("Business details (optional)"):
            location = st.text_input("Location", value=settings.location)
            unit_cost = st.number_input(
                "Your unit cost", min_value=0.0, value=0.0, step=1.0,
                help="Leave 0 to let the agents estimate it.",
            )
            fixed_costs = st.number_input(
                "Fixed monthly costs", min_value=0.0, value=0.0, step=100.0
            )
            expected_units = st.number_input(
                "Expected monthly sales (units)", min_value=0, value=0, step=10
            )
            platforms = st.multiselect(
                "Ad platforms",
                ["facebook", "instagram", "youtube"],
                default=["facebook", "instagram"],
            )

        with st.expander("Stock intake (Inventory agent)"):
            stock_name = st.text_input("Product name", key="stock_name")
            sc1, sc2 = st.columns(2)
            stock_qty = sc1.number_input("Quantity", min_value=0, value=0, step=1)
            stock_cost = sc2.number_input(
                "Unit cost", min_value=0.0, value=0.0, step=1.0, key="stock_cost"
            )

        with st.expander("Delivery details (Delivery agent)"):
            provider = st.selectbox("Courier", ["steadfast", "pathao", "uber"])
            recipient = st.text_input("Recipient name")
            phone = st.text_input("Phone")
            address = st.text_area("Address", height=68)
            cod = st.number_input("Cash on delivery", min_value=0.0, value=0.0, step=10.0)

        st.divider()
        run = st.button(
            "▶️ Run the workforce",
            type="primary",
            use_container_width=True,
            disabled=ss.busy or not settings.has_llm,
        )

        if run:
            if not owner_input.strip() and not uploaded:
                st.error("Type a request or upload a photo first.")
            else:
                paths = _save_uploads(uploaded)
                context = {
                    "location": location,
                    "unit_cost": unit_cost or None,
                    "fixed_costs": fixed_costs,
                    "expected_monthly_units": expected_units,
                    "platforms": platforms,
                }
                if stock_name and stock_qty:
                    context["stock_items"] = [
                        {
                            "product_name": stock_name,
                            "quantity": int(stock_qty),
                            "unit_cost": stock_cost,
                        }
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

                ss.busy = True
                ss.final_report = ""
                ss.last_error = ""
                drain(
                    runtime.start(
                        owner_input=owner_input.strip()
                        or "Analyse the attached photo and tell me if I should sell it.",
                        image_paths=paths,
                        owner_context=context,
                        session_id=ss.session_id,
                    )
                )
                st.rerun()

        st.divider()
        st.subheader("Integrations")
        for label, status in settings.integration_status().items():
            icon = (
                "🟢" if status.startswith("LIVE")
                else ("🔴" if "MISSING" in status else "🟡")
            )
            st.markdown(
                f"<div style='font-size:0.8rem'>{icon} {label}: <code>{status}</code></div>",
                unsafe_allow_html=True,
            )
        st.caption(
            "🟡 = simulated adapter with realistic sample responses. Supplying the "
            "relevant API key in `.env` switches it to live with no code change."
        )


def _save_uploads(files) -> list[str]:
    paths: list[str] = []
    for f in files or []:
        dest = UPLOAD_DIR / f"{st.session_state.session_id}-{f.name}"
        dest.write_bytes(f.getbuffer())
        paths.append(str(dest))
    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    init_state()
    runtime = get_runtime()
    ss = st.session_state

    sidebar(runtime)

    st.title("Business control room")

    # A suspended graph takes priority over everything else on screen.
    pending = runtime.pending_approval(ss.session_id)
    if pending:
        ss.paused = True
        decision = panels.render_approval_gate(pending)
        if decision:
            ss.paused = False
            ss.busy = True
            drain(runtime.resume(ss.session_id, decision))
            st.rerun()
        st.divider()
    else:
        ss.paused = False

    if ss.last_error:
        st.error(f"Last error: {ss.last_error}")

    tabs = st.tabs(
        [
            "📊 Dashboard",
            "⚡ Live trace",
            "🔀 Agent comms",
            "🕸️ Execution graph",
            "💰 Cost",
            "📜 Logs",
            "🧠 Memory",
            "📄 Report",
        ]
    )

    with tabs[0]:
        panels.render_dashboard(runtime, ss.session_id, agent_roster())
    with tabs[1]:
        panels.render_trace(ss.session_id)
    with tabs[2]:
        panels.render_communication(ss.session_id)
    with tabs[3]:
        panels.render_graph(runtime)
    with tabs[4]:
        panels.render_cost(ss.session_id)
    with tabs[5]:
        panels.render_logs(ss.session_id)
    with tabs[6]:
        panels.render_memory()
    with tabs[7]:
        panels.render_report(ss.session_id, ss.final_report)

    st.divider()
    st.caption(
        f"AI Business Workforce · model `{settings.model}` · "
        f"{len(agent_roster())} specialist agents + supervisor · "
        f"memory: {memory.stats()['knowledge_documents']} documents"
    )


if __name__ == "__main__":
    main()
