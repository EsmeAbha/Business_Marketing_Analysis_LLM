"""BaseAgent — shared machinery for every specialist.

Subclasses implement `execute()` and get, for free:
  * a traced, retried, usage-accounted structured LLM call
  * read/write access to shared memory (structured + semantic)
  * a human-in-the-loop approval gate that suspends the graph
  * error containment: a failing agent degrades the run, it never crashes it
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from ..llm import get_llm
from ..memory import memory
from ..observability import AgentError, bus, get_logger
from ..pricing import UsageLedger, extract_usage
from ..state import AgentMessage, WorkforceState

T = TypeVar("T", bound=BaseModel)

# One usage ledger per session, so the UI can show live cost for this run only.
LEDGERS: dict[str, UsageLedger] = {}

# Populated by the @register decorator; the UI reads it to render the roster.
AGENT_REGISTRY: dict[str, dict[str, str]] = {}


def ledger_for(session_id: str) -> UsageLedger:
    return LEDGERS.setdefault(session_id, UsageLedger())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AgentResult:
    """What an agent hands back to the supervisor."""

    summary: str
    payload: dict[str, Any]
    ok: bool = True
    error: str = ""


class BaseAgent(ABC):
    # --- identity, overridden by each subclass ---
    name: str = "base"
    title: str = "Base Agent"
    description: str = ""
    tools_used: tuple[str, ...] = ()
    #: Costly or irreversible agents block on owner approval before acting.
    requires_approval: bool = False
    approval_checkpoint: str = ""

    def __init__(self) -> None:
        self.log = get_logger(f"agent.{self.name}")

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if getattr(cls, "name", "base") != "base":
            AGENT_REGISTRY[cls.name] = {
                "title": cls.title,
                "description": cls.description,
                "tools": ", ".join(cls.tools_used),
                "requires_approval": str(cls.requires_approval),
            }

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, state: WorkforceState) -> AgentResult:
        """Do the agent's actual work. Raise AgentError on unrecoverable failure."""

    # ------------------------------------------------------------------
    # Graph node entry point
    # ------------------------------------------------------------------

    def __call__(self, state: WorkforceState) -> dict[str, Any]:
        session_id = state.get("session_id", "unknown")
        task = state.get("current_task", "") or "(no explicit task)"

        bus.emit(
            session_id,
            kind="agent_start",
            actor=self.name,
            summary=f"{self.title} started: {task[:160]}",
            payload={"task": task, "stage": state.get("stage")},
        )

        try:
            result = self.execute(state)
        except AgentError as exc:
            result = AgentResult(summary=str(exc), payload={}, ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — containment boundary
            self.log.exception("unhandled failure in %s", self.name)
            result = AgentResult(
                summary=f"{self.title} failed unexpectedly.",
                payload={},
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        bus.emit(
            session_id,
            kind="agent_end" if result.ok else "error",
            actor=self.name,
            summary=result.summary[:400] if result.ok else f"FAILED: {result.error}",
            payload={"ok": result.ok, "keys": sorted(result.payload.keys())},
            level="info" if result.ok else "error",
        )

        message: AgentMessage = {
            "sender": self.name,
            "recipient": "supervisor",
            "task": task,
            "summary": result.summary[:1500],
            "payload": result.payload,
            "ts": _now(),
        }
        memory.db.add_agent_message(
            session_id, self.name, "supervisor", task, result.payload
        )

        outputs = dict(state.get("agent_outputs", {}))
        outputs[self.name] = {
            "summary": result.summary,
            "payload": result.payload,
            "ok": result.ok,
            "error": result.error,
            "ts": _now(),
        }

        update: dict[str, Any] = {
            "agent_messages": [message],
            "agent_outputs": outputs,
            "completed_agents": [self.name],
        }
        if not result.ok:
            update["errors"] = [f"{self.name}: {result.error}"]
        return update

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def ask(
        self,
        state: WorkforceState,
        schema: type[T],
        system_prompt: str,
        user_prompt: str,
        extra_messages: list[Any] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Structured LLM call with tracing and token accounting.

        `include_raw=True` keeps the underlying AIMessage so usage metadata
        survives structured-output parsing.
        """
        session_id = state.get("session_id", "unknown")
        llm = get_llm(model, max_tokens)
        model_id = getattr(llm, "model", model or "unknown")

        structured = llm.with_structured_output(schema, include_raw=True)
        messages: list[Any] = [SystemMessage(content=system_prompt)]
        messages.extend(extra_messages or [])
        messages.append(HumanMessage(content=user_prompt))

        bus.emit(
            session_id,
            kind="llm_call",
            actor=self.name,
            summary=f"calling {model_id} for {schema.__name__}",
            payload={"prompt_chars": len(system_prompt) + len(user_prompt)},
        )

        try:
            response = structured.invoke(messages)
        except Exception as exc:  # noqa: BLE001
            raise AgentError(self.name, f"LLM call failed: {exc}", exc) from exc

        raw = response.get("raw") if isinstance(response, dict) else None
        parsed = response.get("parsed") if isinstance(response, dict) else response
        parse_error = response.get("parsing_error") if isinstance(response, dict) else None

        if raw is not None:
            usage = extract_usage(self.name, model_id, raw)
            ledger_for(session_id).record(usage)
            bus.emit(
                session_id,
                kind="llm_usage",
                actor=self.name,
                summary=(
                    f"{usage.input_tokens} in / {usage.output_tokens} out "
                    f"(${usage.cost_usd:.4f})"
                ),
                payload={
                    "model": model_id,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cache_read_tokens": usage.cache_read_tokens,
                    "cost_usd": round(usage.cost_usd, 6),
                },
            )

        if parsed is None:
            raise AgentError(
                self.name,
                f"model did not return valid {schema.__name__}: {parse_error}",
            )
        return parsed  # type: ignore[return-value]

    def call_vision(
        self,
        state: WorkforceState,
        schema: type[T],
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str],
    ) -> T:
        """Structured call with images attached to the user turn."""
        from ..tools.vision import build_image_message

        image_message = build_image_message(user_prompt, image_paths)
        return self.ask(
            state,
            schema,
            system_prompt,
            user_prompt="(see attached image(s) above)",
            extra_messages=[image_message],
        )

    # --- memory access ---

    def recall(self, query: str, k: int = 5, kind: str | None = None) -> str:
        return memory.recall_text(query, k=k, kind=kind)

    def remember(
        self, state: WorkforceState, text: str, kind: str, extra: dict | None = None
    ) -> None:
        memory.remember(
            text,
            agent=self.name,
            kind=kind,
            session_id=state.get("session_id", ""),
            extra=extra,
        )

    def context_block(self, state: WorkforceState, query: str) -> str:
        """Standard context header: business state + what other agents found."""
        return (
            f"{memory.business_snapshot()}\n\n"
            f"RELEVANT PRIOR FINDINGS FROM OTHER AGENTS (retrieved from shared memory):\n"
            f"{self.recall(query, k=6)}\n\n"
            f"OUTPUTS PRODUCED EARLIER IN THIS SESSION:\n"
            f"{self._session_outputs(state)}"
        )

    def _session_outputs(self, state: WorkforceState) -> str:
        outputs = state.get("agent_outputs", {})
        if not outputs:
            return "(none yet — you are the first agent to run)"
        lines = []
        for agent, data in outputs.items():
            if agent == self.name:
                continue
            lines.append(f"- {agent}: {str(data.get('summary', ''))[:600]}")
        return "\n".join(lines) or "(none from other agents yet)"

    # --- human in the loop ---

    def request_approval(
        self,
        state: WorkforceState,
        title: str,
        detail: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Suspend the graph until the owner approves, rejects, or requests changes.

        LangGraph's `interrupt` persists state to the checkpointer and raises;
        the run resumes from exactly here when the UI sends a `Command(resume=...)`.
        """
        from langgraph.types import interrupt

        session_id = state.get("session_id", "unknown")
        checkpoint = self.approval_checkpoint or f"{self.name}_action"

        bus.emit(
            session_id,
            kind="approval",
            actor=self.name,
            summary=f"awaiting owner approval: {title}",
            payload={"checkpoint": checkpoint, "detail": detail[:1000]},
            level="warning",
        )

        decision = interrupt(
            {
                "checkpoint": checkpoint,
                "agent": self.name,
                "title": title,
                "detail": detail,
                "options": ["approve", "reject", "request_changes"],
                "payload": payload or {},
            }
        )

        if isinstance(decision, str):
            decision = {"decision": decision, "feedback": ""}
        decision = dict(decision or {})
        decision.setdefault("decision", "approve")
        decision.setdefault("feedback", "")

        memory.db.add_approval(
            session_id, checkpoint, decision["decision"], decision["feedback"]
        )
        bus.emit(
            session_id,
            kind="approval",
            actor=self.name,
            summary=f"owner decision on {checkpoint}: {decision['decision']}",
            payload=decision,
        )
        return decision

    # --- misc ---

    @staticmethod
    def as_json(obj: Any, limit: int = 4000) -> str:
        try:
            return json.dumps(obj, indent=2, default=str)[:limit]
        except (TypeError, ValueError):
            return str(obj)[:limit]
