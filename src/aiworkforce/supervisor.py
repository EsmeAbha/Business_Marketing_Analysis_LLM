"""The Supervisor Agent — interprets the owner, plans, routes, and aggregates.

Responsibilities, in order:
  1. Read the owner's message (and any photo) and work out which lifecycle
     stage the business is actually in.
  2. Draft a plan naming which specialist handles which step.
  3. On every turn, pick exactly one agent to run next, with a reason — or
     FINISH when the objective is met.
  4. Aggregate every agent's output into the owner's final answer.

It never does specialist work itself; it only decides who works next.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .agents.base import ledger_for
from .agents.schemas import RoutingDecision, WorkPlan
from .llm import get_llm
from .memory import memory
from .observability import bus, get_logger
from .pricing import extract_usage
from .state import STAGE_ORDER, WorkforceState

logger = get_logger("supervisor")

AGENT_CATALOG = """
AVAILABLE SPECIALIST AGENTS

  market_research  — Finds low-competition/high-demand niches and competitor price bands
                     using live web search. Use when the owner is deciding WHAT to sell,
                     or asks whether something is profitable in their area.

  product_vision   — Identifies a product or food item FROM AN UPLOADED PHOTO, estimates
                     demand and price fit, gives a GO/NO-GO call. ONLY route here when an
                     image was actually uploaded.

  pricing          — Cost-plus pricing, margin, break-even, competitor comparison. Needs a
                     product and ideally a competitor band from market_research or
                     product_vision. Runs real Python for the maths.

  inventory        — Records purchased stock (product, quantity, cost, photo), tracks
                     levels, flags low stock. Use after the owner has bought stock, or when
                     they ask what needs reordering.

  ad_creative      — Writes platform-specific ad copy and publishes to Facebook/Instagram/
                     YouTube. REQUIRES OWNER APPROVAL before publishing. Needs a product and
                     a price to exist first.

  engagement       — Reads Messenger/Instagram DMs and comments, analyses sentiment,
                     extracts pre-orders, detects demand for products not yet offered.

  delivery         — Books courier pickup/delivery via Pathao/Steadfast/Uber. REQUIRES OWNER
                     APPROVAL. Needs recipient, phone and address from the owner.

  reporting        — Synthesises everything into the owner's report: restock alerts, demand
                     shifts, profit analysis, revised plan. Best run LAST.

  FINISH           — The owner's request has been fully answered. Stop.
"""

PLANNER_SYSTEM = f"""You are the Supervisor of an AI workforce that runs a small business end to end.

A business owner has sent you a request. Produce a short plan naming which specialist
handles which step.

{AGENT_CATALOG}

Rules:
- Keep the plan to the minimum number of steps that genuinely answers the request. A
  simple question does not need all eight agents.
- Only include product_vision if an image was uploaded.
- Only include delivery if the owner is actually asking to ship something.
- Put reporting last when the request spans several stages; omit it for narrow requests.
- Each step must name the agent responsible.
"""

ROUTER_SYSTEM = f"""You are the Supervisor of an AI workforce that runs a small business end to end.

Decide which single agent should work NEXT, or FINISH if the owner's request has been
fully answered.

{AGENT_CATALOG}

Rules:
- Choose exactly ONE agent name from the list, or FINISH.
- Do NOT re-run an agent that has already completed successfully unless its output was an
  error, or new information genuinely changes its inputs.
- Respect data dependencies: pricing needs a product; ad_creative needs a price;
  reporting is most useful once the other relevant agents have run.
- Never route to product_vision when no image was uploaded.
- If the plan is complete, or the remaining steps cannot proceed (missing owner input,
  repeated failures), choose FINISH rather than looping.
- `task` is the concrete instruction that agent will receive. Be specific — it is the only
  instruction they get from you.
"""

AGGREGATOR_SYSTEM = """You are the Supervisor of an AI workforce that runs a small business.

Every specialist has reported back. Write the owner's answer.

Rules:
- Lead with the outcome: what you found, decided, or did. The owner reads the first
  sentence and often nothing else.
- Write for a small-business owner, not a technical reviewer. No agent names in headings,
  no framework jargon.
- Give the concrete numbers — prices, margins, quantities, stock alerts — not vague summaries.
- Surface anything that failed or that came from a SIMULATED adapter honestly, in one line
  near the end, so the owner knows what is real.
- End with a short "What I need from you" list if anything is genuinely blocked on them.
- Use Markdown. Be complete but do not pad.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Supervisor:
    """Graph node: plans on the first turn, routes on every turn after."""

    name = "supervisor"

    def __call__(self, state: WorkforceState) -> dict[str, Any]:
        session_id = state.get("session_id", "unknown")
        step = int(state.get("step_count", 0))

        update: dict[str, Any] = {"step_count": step + 1}

        # Hard stop so a confused router can never bill an unbounded loop.
        from .config import settings

        if step >= settings.max_supervisor_steps:
            bus.emit(
                session_id,
                kind="handoff",
                actor=self.name,
                summary=f"step limit ({settings.max_supervisor_steps}) reached — finishing",
                level="warning",
            )
            return {**update, "next_agent": "FINISH", "routing_reason": "step limit reached"}

        # First turn: draft the plan the owner sees.
        if step == 0:
            plan = self._plan(state)
            update["plan"] = plan.steps
            update["stage"] = plan.stage if plan.stage in STAGE_ORDER else "idea_research"
            bus.emit(
                session_id,
                kind="plan",
                actor=self.name,
                summary=f"Plan: {plan.goal}",
                payload={"steps": plan.steps, "stage": plan.stage},
            )

        decision = self._route(state)
        update["next_agent"] = decision.next_agent
        update["current_task"] = decision.task
        update["routing_reason"] = decision.reason
        if decision.stage in STAGE_ORDER:
            update["stage"] = decision.stage

        bus.emit(
            session_id,
            kind="handoff",
            actor=self.name,
            summary=f"-> {decision.next_agent}: {decision.reason}",
            payload={"task": decision.task, "stage": decision.stage},
        )

        if decision.next_agent != "FINISH":
            memory.db.add_agent_message(
                session_id,
                "supervisor",
                decision.next_agent,
                decision.task,
                {"reason": decision.reason, "stage": decision.stage},
            )
            update["agent_messages"] = [
                {
                    "sender": "supervisor",
                    "recipient": decision.next_agent,
                    "task": decision.task,
                    "summary": decision.reason,
                    "payload": {"stage": decision.stage},
                    "ts": _now(),
                }
            ]

        return update

    # ------------------------------------------------------------------

    def _plan(self, state: WorkforceState) -> WorkPlan:
        prompt = f"""OWNER'S REQUEST
{state.get('owner_input', '')}

IMAGE UPLOADED: {'yes — ' + str(len(state.get('image_paths') or [])) + ' file(s)' if state.get('image_paths') else 'no'}

ADDITIONAL DETAILS SUPPLIED BY THE OWNER
{_json(state.get('owner_context', {}))}

{memory.business_snapshot()}

Produce the plan."""
        return self._call(state, WorkPlan, PLANNER_SYSTEM, prompt)

    def _route(self, state: WorkforceState) -> RoutingDecision:
        completed = state.get("completed_agents", [])
        outputs = state.get("agent_outputs", {})

        results = []
        for agent, data in outputs.items():
            status = "OK" if data.get("ok") else f"FAILED ({data.get('error', '')})"
            results.append(f"- {agent} [{status}]: {str(data.get('summary', ''))[:500]}")

        prompt = f"""OWNER'S REQUEST
{state.get('owner_input', '')}

IMAGE UPLOADED: {'yes' if state.get('image_paths') else 'no'}
CURRENT STAGE: {state.get('stage', 'idea_research')}
STEP: {state.get('step_count', 0)}

THE PLAN
{chr(10).join(f'{i}. {s}' for i, s in enumerate(state.get('plan', []), 1)) or '(no plan drafted)'}

AGENTS ALREADY RUN: {', '.join(completed) if completed else '(none yet)'}

WHAT THEY REPORTED
{chr(10).join(results) if results else '(nothing yet)'}

ERRORS SO FAR
{chr(10).join(state.get('errors', [])) or '(none)'}

{memory.business_snapshot()}

Who works next?"""
        return self._call(state, RoutingDecision, ROUTER_SYSTEM, prompt)

    def aggregate(self, state: WorkforceState) -> str:
        """Compose the owner-facing answer from everything the agents produced."""
        outputs = state.get("agent_outputs", {})
        if not outputs:
            return (
                "I wasn't able to complete any work on this request. "
                "Please rephrase it or supply the missing details."
            )

        # If Reporting ran, its Markdown already is the deliverable.
        reporting = outputs.get("reporting", {})
        if reporting.get("ok") and reporting.get("payload", {}).get("full_report_markdown"):
            return reporting["payload"]["full_report_markdown"]

        detail = []
        for agent, data in outputs.items():
            status = "completed" if data.get("ok") else f"FAILED: {data.get('error')}"
            detail.append(
                f"### {agent} [{status}]\n{data.get('summary', '')}\n\n"
                f"Structured output:\n{_json(data.get('payload', {}), 3000)}"
            )

        prompt = f"""OWNER'S ORIGINAL REQUEST
{state.get('owner_input', '')}

STAGE REACHED: {state.get('stage', '')}

APPROVAL DECISIONS THE OWNER MADE
{_json(memory.approvals(state.get('session_id', '')))}

SPECIALIST REPORTS
{chr(10).join(detail)}

Write the owner's answer."""

        session_id = state.get("session_id", "unknown")
        llm = get_llm(max_tokens=12000)
        try:
            response = llm.invoke(
                [SystemMessage(content=AGGREGATOR_SYSTEM), HumanMessage(content=prompt)]
            )
        except Exception as exc:  # noqa: BLE001 — always return something to the owner
            bus.emit(
                session_id,
                kind="error",
                actor=self.name,
                summary=f"aggregation failed: {exc}",
                level="error",
            )
            return self._fallback_summary(outputs)

        usage = extract_usage(self.name, getattr(llm, "model", "unknown"), response)
        ledger_for(session_id).record(usage)
        bus.emit(
            session_id,
            kind="llm_usage",
            actor=self.name,
            summary=f"aggregation: {usage.output_tokens} out (${usage.cost_usd:.4f})",
            payload={"cost_usd": round(usage.cost_usd, 6)},
        )

        content = response.content
        if isinstance(content, list):  # thinking blocks can precede the text block
            content = "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        return str(content).strip() or self._fallback_summary(outputs)

    @staticmethod
    def _fallback_summary(outputs: dict) -> str:
        lines = ["# Results\n"]
        for agent, data in outputs.items():
            mark = "✅" if data.get("ok") else "❌"
            lines.append(f"{mark} **{agent}** — {data.get('summary', '')}\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------

    def _call(self, state: WorkforceState, schema, system: str, prompt: str):
        session_id = state.get("session_id", "unknown")
        llm = get_llm()
        model_id = getattr(llm, "model", "unknown")
        structured = llm.with_structured_output(schema, include_raw=True)

        response = structured.invoke(
            [SystemMessage(content=system), HumanMessage(content=prompt)]
        )
        raw = response.get("raw")
        parsed = response.get("parsed")

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
                payload={"model": model_id, "cost_usd": round(usage.cost_usd, 6)},
            )

        if parsed is None:
            # A router that cannot parse must not spin — end the run cleanly.
            logger.warning("supervisor could not parse %s; finishing", schema.__name__)
            if schema is RoutingDecision:
                return RoutingDecision(
                    next_agent="FINISH",
                    task="",
                    reason="supervisor could not produce a valid routing decision",
                    stage=state.get("stage", "idea_research"),
                )
            return WorkPlan(goal="(unparsed)", steps=[], stage="idea_research")
        return parsed


def _json(obj: Any, limit: int = 2000) -> str:
    import json

    try:
        return json.dumps(obj, indent=2, default=str)[:limit]
    except (TypeError, ValueError):
        return str(obj)[:limit]


supervisor = Supervisor()
