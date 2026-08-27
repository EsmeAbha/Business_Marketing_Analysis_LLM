"""The LangGraph state machine and the runtime the UI drives.

Topology:

    START -> supervisor -> (conditional) -> <one of eight agents> -> supervisor
                        \\-> finalize -> END

Every agent returns to the supervisor, which re-decides. Two agents
(ad_creative, delivery) call `interrupt()` mid-node, which suspends the whole
graph to the SQLite checkpointer until the owner answers — that is the
human-in-the-loop mechanism, and it is what makes pause/resume/retry real
rather than cosmetic.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from typing import Any, Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .agents import build_agents
from .agents.base import AGENT_REGISTRY, ledger_for
from .config import CHECKPOINT_PATH
from .memory import memory
from .observability import bus, get_logger
from .state import WorkforceState, new_state
from .supervisor import supervisor

logger = get_logger("graph")

_AGENTS = build_agents()
AGENT_NAMES = tuple(_AGENTS.keys())


def _route_from_supervisor(state: WorkforceState) -> str:
    """Conditional edge: the supervisor's choice, validated against the roster."""
    choice = (state.get("next_agent") or "FINISH").strip()
    if choice in _AGENTS:
        return choice
    if choice != "FINISH":
        logger.warning("supervisor returned unknown agent %r; finalizing", choice)
        bus.emit(
            state.get("session_id", "unknown"),
            kind="error",
            actor="supervisor",
            summary=f"unknown agent {choice!r} — finalizing instead",
            level="warning",
        )
    return "finalize"


def _finalize(state: WorkforceState) -> dict[str, Any]:
    session_id = state.get("session_id", "unknown")
    bus.emit(
        session_id,
        kind="handoff",
        actor="supervisor",
        summary="aggregating specialist outputs into the owner's answer",
        payload={"agents_run": state.get("completed_agents", [])},
    )
    report = supervisor.aggregate(state)

    ledger = ledger_for(session_id)
    bus.emit(
        session_id,
        kind="session_end",
        actor="supervisor",
        summary=(
            f"run complete — {len(state.get('completed_agents', []))} agent runs, "
            f"{ledger.total_tokens:,} tokens, ${ledger.total_cost_usd:.4f}"
        ),
        payload={
            "total_tokens": ledger.total_tokens,
            "cost_usd": round(ledger.total_cost_usd, 6),
            "errors": state.get("errors", []),
        },
    )
    return {"final_report": report, "finished": True, "next_agent": "FINISH"}


def build_graph(checkpointer=None):
    """Assemble and compile the state graph."""
    graph = StateGraph(WorkforceState)

    graph.add_node("supervisor", supervisor)
    for name, agent in _AGENTS.items():
        graph.add_node(name, agent)
    graph.add_node("finalize", _finalize)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {**{n: n for n in AGENT_NAMES}, "finalize": "finalize"},
    )
    for name in AGENT_NAMES:
        graph.add_edge(name, "supervisor")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------
# Runtime
# --------------------------------------------------------------------------


class WorkforceRuntime:
    """Owns the checkpointer connection and exposes start/resume to the UI."""

    def __init__(self) -> None:
        # check_same_thread=False: Streamlit reruns can touch this from
        # different threads, and SqliteSaver serialises its own writes.
        self._conn = sqlite3.connect(
            str(CHECKPOINT_PATH), check_same_thread=False, timeout=30
        )
        self.checkpointer = SqliteSaver(self._conn)
        self.app = build_graph(self.checkpointer)
        self._lock = threading.RLock()
        # Sessions executing *right now*. The checkpoint cannot answer this:
        # it records where the graph got to, not whether anyone is working.
        self._in_flight: set[str] = set()
        logger.info("workforce runtime ready with %d agents", len(_AGENTS))

    # --- lifecycle ---

    @staticmethod
    def new_session_id() -> str:
        return f"sess-{uuid.uuid4().hex[:10]}"

    def config_for(self, session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}, "recursion_limit": 60}

    def start(
        self,
        owner_input: str,
        image_paths: list[str] | None = None,
        owner_context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Begin a run. Yields each node's state update as it completes."""
        session_id = session_id or self.new_session_id()
        state = new_state(session_id, owner_input, image_paths, owner_context)

        bus.emit(
            session_id,
            kind="session_start",
            actor="supervisor",
            summary=f"owner request received: {owner_input[:200]}",
            payload={
                "images": len(image_paths or []),
                "context_keys": sorted((owner_context or {}).keys()),
            },
        )
        yield from self._stream(state, session_id)

    def assign(
        self,
        agent: str,
        task: str,
        owner_context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Run a job the owner handed to one named specialist.

        It still enters through the supervisor, so the plan, the handoff and
        the write-back all happen the way they always do — the only
        difference is that the first routing decision is already made.
        """
        session_id = session_id or self.new_session_id()
        state = new_state(session_id, task, None, owner_context)
        state["requested_agent"] = agent

        bus.emit(
            session_id,
            kind="session_start",
            actor="supervisor",
            summary=f"{agent} asked directly: {task[:180]}",
            payload={"directed_to": agent},
        )
        yield from self._stream(state, session_id)

    def resume(self, session_id: str, decision: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Answer a pending approval and continue from the interrupt point."""
        from langgraph.types import Command

        bus.emit(
            session_id,
            kind="approval",
            actor="owner",
            summary=f"owner resumed with decision: {decision.get('decision')}",
            payload=decision,
        )
        yield from self._stream(Command(resume=decision), session_id)

    def retry(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Re-enter the graph from the last checkpoint without new input.

        Used after a transient failure — the supervisor sees the error in state
        and decides whether to re-run the agent or route around it.
        """
        bus.emit(
            session_id,
            kind="handoff",
            actor="owner",
            summary="owner requested a retry from the last checkpoint",
        )
        yield from self._stream(None, session_id)

    def _stream(self, payload, session_id: str) -> Iterator[dict[str, Any]]:
        config = self.config_for(session_id)
        try:
            with self._lock:
                self._in_flight.add(session_id)
                for chunk in self.app.stream(payload, config, stream_mode="updates"):
                    for node, update in chunk.items():
                        # A suspended graph arrives as `__interrupt__` carrying a
                        # tuple of Interrupt objects rather than a state dict.
                        # Normalise it so every consumer sees the same shape.
                        if node == "__interrupt__":
                            items = (
                                update
                                if isinstance(update, (list, tuple))
                                else (update,)
                            )
                            value = next(
                                (
                                    getattr(i, "value", None)
                                    for i in items
                                    if getattr(i, "value", None) is not None
                                ),
                                None,
                            )
                            yield {
                                "node": "__interrupt__",
                                "update": {"interrupt": value},
                                "session_id": session_id,
                            }
                            continue
                        if not isinstance(update, dict):
                            update = {}
                        yield {"node": node, "update": update, "session_id": session_id}
        except Exception as exc:  # noqa: BLE001 — surface, never crash the UI
            logger.exception("graph execution failed")
            bus.emit(
                session_id,
                kind="error",
                actor="graph",
                summary=f"graph execution failed: {type(exc).__name__}: {exc}",
                level="error",
            )
            yield {
                "node": "__error__",
                "update": {"errors": [f"{type(exc).__name__}: {exc}"]},
                "session_id": session_id,
            }
        finally:
            self._in_flight.discard(session_id)

    # --- inspection ---

    def snapshot(self, session_id: str):
        return self.app.get_state(self.config_for(session_id))

    def pending_approval(self, session_id: str) -> dict[str, Any] | None:
        """Return the interrupt payload if the graph is suspended, else None."""
        try:
            snap = self.snapshot(session_id)
        except Exception:  # noqa: BLE001 — no checkpoint yet
            return None

        interrupts = getattr(snap, "interrupts", None) or ()
        for intr in interrupts:
            value = getattr(intr, "value", None)
            if isinstance(value, dict):
                return value

        # Older LangGraph builds surface interrupts on the pending tasks instead.
        for task in getattr(snap, "tasks", ()) or ():
            for intr in getattr(task, "interrupts", ()) or ():
                value = getattr(intr, "value", None)
                if isinstance(value, dict):
                    return value
        return None

    def is_running(self, session_id: str) -> bool:
        """Is the graph executing for this session at this moment?

        This used to ask the checkpoint whether it had a next node, which is a
        different question. A checkpoint keeps its pending node when a run is
        suspended for an approval *and* when a run dies mid-flight — so a run
        killed by an exhausted API quota left the session marked "working"
        permanently, and the owner could never hand out another job. Only a
        run actually in progress registers here, and it deregisters however
        it ends.
        """
        return session_id in self._in_flight

    def is_suspended(self, session_id: str) -> bool:
        """Does the checkpoint hold unfinished work — a gate, or a dead run?

        True does not mean anybody is working: pair it with `is_running` to
        tell a paused graph from a busy one, and with `pending_approval` to
        tell a gate from wreckage.
        """
        try:
            snap = self.snapshot(session_id)
        except Exception:  # noqa: BLE001
            return False
        return bool(getattr(snap, "next", ()))

    def state_values(self, session_id: str) -> dict[str, Any]:
        try:
            return dict(self.snapshot(session_id).values or {})
        except Exception:  # noqa: BLE001
            return {}

    # --- visualisation ---

    def mermaid(self) -> str:
        """Execution graph as Mermaid, for the UI's diagram panel."""
        try:
            return self.app.get_graph().draw_mermaid()
        except Exception as exc:  # noqa: BLE001 — fall back to a hand-written diagram
            logger.warning("could not render graph mermaid: %s", exc)
            lines = [
                "graph TD",
                "    START([__start__]) --> SUP[supervisor]",
            ]
            for name in AGENT_NAMES:
                approval = " 🔒" if _AGENTS[name].requires_approval else ""
                lines.append(f"    SUP -->|routes| {name}[{name}{approval}]")
                lines.append(f"    {name} --> SUP")
            lines.append("    SUP -->|FINISH| FIN[finalize]")
            lines.append("    FIN --> END([__end__])")
            return "\n".join(lines)

    def png(self) -> bytes | None:
        try:
            return self.app.get_graph().draw_mermaid_png()
        except Exception:  # noqa: BLE001 — needs network/graphviz; Mermaid is the fallback
            return None

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def agent_roster() -> dict[str, dict[str, str]]:
    """Metadata for the dashboard's agent table."""
    return dict(AGENT_REGISTRY)


__all__ = [
    "WorkforceRuntime",
    "build_graph",
    "agent_roster",
    "AGENT_NAMES",
    "memory",
]
