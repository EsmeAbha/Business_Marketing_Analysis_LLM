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
from .config import settings
from .llm import active_model_name, get_llm
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
- FINISH IMMEDIATELY, before any agent runs, when the message does not need
  specialist work: a greeting, thanks, an acknowledgement, small talk, or a
  question about you and what you can do. You will still write the reply
  yourself, so the owner is answered — they simply do not need eight
  specialists and a web search to be told hello. Dispatching the workforce
  at "hi" costs the owner minutes and thousands of tokens for a sentence.
- Do NOT re-run an agent that has already completed successfully unless its output was an
  error, or new information genuinely changes its inputs.
- Answer the question that was asked, and stop. Once the agents that were run
  can answer it, choose FINISH — do not add adjacent work the owner did not
  ask for. "Which product should I reorder first?" is answered by stock
  alone; sending it on to market research, pricing and reporting turns a
  ten-second answer into a four-minute report about something else.
- Route to market_research ONLY when the answer genuinely lies outside the
  business: what rivals charge, what the market wants, what is selling
  elsewhere. Anything answerable from the shop's own records — stock,
  products, prices, orders, customers — must not go to web search.
- Respect data dependencies: pricing needs a product; ad_creative needs a price;
  reporting is most useful once the other relevant agents have run.
- Never route to product_vision when no image was uploaded.
- If the plan is complete, or the remaining steps cannot proceed (missing owner input,
  repeated failures), choose FINISH rather than looping.
- `task` is the concrete instruction that agent will receive. Be specific — it is the only
  instruction they get from you.
"""

# Where a run's answer should be streamed to, keyed by session. The web
# layer registers a sink before the graph starts and removes it afterwards;
# with none registered `aggregate` behaves exactly as it did, which keeps
# the Telegram poller and the tests on the non-streaming path.
_SINKS: dict[str, Any] = {}


def stream_to(session_id: str, sink) -> None:
    """Send this run's final answer to `sink`, one chunk at a time."""
    _SINKS[session_id] = sink


def clear_stream(session_id: str) -> None:
    _SINKS.pop(session_id, None)


CHAT_SYSTEM = """You are the Supervisor of an AI workforce that runs a small
shop. The owner has said something that needs no specialist work - a
greeting, thanks, or a question about what you can do.

You have eight specialists, and this is the whole of what you do:
market research (what sells, what rivals charge), product photos (is this
worth selling), pricing and margins, stock and reordering, writing and
publishing ads, reading and answering customer messages, quoting and
booking couriers, and writing up how the business is doing.

Reply as their team would: warmly, in one or two short sentences.

Rules:
- You are not a general writing assistant. Never offer to draft emails,
  write copy in a chosen tone, or do anything outside the list above -
  stripped of context the model invents plausible skills the shop does not
  have, and the owner believes them.
- No headings, no bullet lists, no Markdown formatting.
- Do not mention stages, plans, agents, research or process.
- Do not state or invent any business figures.
- Do not ask them to supply business details unless they asked you to do
  something that genuinely needs them.
- If they asked what you can do, say it plainly in one sentence.
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

        # First turn: is this work at all? Asked before planning, because a
        # plan for "hi" is drafted from the whole business snapshot and then
        # discarded by the router one call later.
        if step == 0 and not self._needs_specialists(state):
            bus.emit(
                session_id,
                kind="handoff",
                actor=self.name,
                summary="-> FINISH: answered directly, no specialist needed",
                payload={"recipient": "FINISH"},
            )
            return {**update, "next_agent": "FINISH",
                    "routing_reason": "answered directly"}

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

        # The owner asking for someone by name outranks the router. It is
        # cleared as it is used, so the next hop is the supervisor's call
        # again — otherwise a directed job would never end.
        wanted = (state.get("requested_agent") or "").strip()
        if wanted and wanted in self.ALL_AGENTS:
            bus.emit(
                session_id,
                kind="handoff",
                actor=self.name,
                summary=f"-> {wanted}: asked for by name",
                payload={"recipient": wanted, "directed": True},
            )
            return {**update, "next_agent": wanted, "requested_agent": "",
                    "current_task": state.get("owner_input", ""),
                    "routing_reason": "you asked for this specialist"}

        decision = self._enforce(self._route(state), state)
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

    TRIAGE_SYSTEM = """You sort incoming messages for a small shop's AI workforce.
Answer with exactly one word.

WORK  - answering needs the shop's own records or outside research: stock,
products, prices, costs, orders, customers, ads, delivery, competitors, or
any request to make or decide something.
CHAT  - a greeting, thanks, an acknowledgement, small talk, or a question
about what you are and what you can do.

If it could plausibly be either, answer WORK."""

    def _needs_specialists(self, state: WorkforceState) -> bool:
        """One cheap call to decide whether this message needs the workforce.

        It runs before planning, which is the whole point. Planning reads the
        entire business snapshot and drafts a strategy; doing that for "hi"
        cost about 1,400 tokens that the router then threw away one call
        later, because the plan for a greeting is never used. Triage sees the
        owner's sentence and nothing else, so it costs a fraction of that.

        Every uncertain path returns True. Wrongly deciding a message is work
        wastes tokens; wrongly deciding real work is chit-chat answers the
        owner's actual question with a pleasantry, which is much worse.
        """
        if state.get("image_paths"):
            return True                    # a photo is always work
        text = (state.get("owner_input") or "").strip()
        if not text:
            return True

        session_id = state.get("session_id", "unknown")
        llm = get_llm(max_tokens=4)
        try:
            response = llm.invoke([
                SystemMessage(content=self.TRIAGE_SYSTEM),
                HumanMessage(content=text[:400]),
            ])
        except Exception as exc:  # noqa: BLE001 — triage must never block work
            logger.warning("triage failed, treating as work: %s", exc)
            return True

        # Metered like any other call: it is small, but it is still spending
        # the owner's allowance, and a charge that is not recorded is the
        # kind of thing that makes a balance stop matching its history.
        try:
            usage = extract_usage(self.name, active_model_name(llm), response)
            ledger_for(session_id).record(usage)
        except Exception:  # noqa: BLE001
            pass

        content = response.content
        if isinstance(content, list):
            content = "".join(b.get("text", "") for b in content
                              if isinstance(b, dict) and b.get("type") == "text")
        return "CHAT" not in str(content).upper()

    def _plan(self, state: WorkforceState) -> WorkPlan:
        prompt = f"""OWNER'S REQUEST
{state.get('owner_input', '')}

IMAGE UPLOADED: {'yes — ' + str(len(state.get('image_paths') or [])) + ' file(s)' if state.get('image_paths') else 'no'}

ADDITIONAL DETAILS SUPPLIED BY THE OWNER
{_json(state.get('owner_context', {}))}

{memory.business_snapshot()}

Produce the plan."""
        # A plan is a handful of short strings — reserving a large output budget
        # only eats into the provider's per-minute token cap.
        return self._call(state, WorkPlan, PLANNER_SYSTEM, prompt, max_tokens=1200)

    ALL_AGENTS = (
        "market_research",
        "product_vision",
        "pricing",
        "inventory",
        "ad_creative",
        "engagement",
        "delivery",
        "reporting",
    )

    def _allowed_agents(self, state: WorkforceState) -> list[str]:
        """Agents the router may still pick.

        An agent that already succeeded is off the list: re-running it produces
        the same answer, burns the step budget and (on rate-limited providers)
        the token budget. A failed agent gets exactly one retry. This is enforced
        here rather than left to the prompt, because smaller models will happily
        re-select the same agent forever no matter how the instruction is worded.
        """
        outputs = state.get("agent_outputs", {})
        completed = state.get("completed_agents", [])
        allowed = []
        for name in self.ALL_AGENTS:
            data = outputs.get(name)
            if data is None:
                allowed.append(name)
            elif not data.get("ok") and completed.count(name) < 2:
                allowed.append(name)  # one retry for a failure
        if not state.get("image_paths"):
            allowed = [a for a in allowed if a != "product_vision"]
        return allowed

    def _route(self, state: WorkforceState) -> RoutingDecision:
        completed = state.get("completed_agents", [])
        outputs = state.get("agent_outputs", {})
        allowed = self._allowed_agents(state)

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

YOU MAY ONLY CHOOSE FROM: {', '.join(allowed) if allowed else '(none left)'}, or FINISH.
Every other agent has already done its job — picking one is not permitted.
If nothing on that list would move the owner's request forward, choose FINISH.

Who works next?"""
        # Routing runs on every turn, so it goes to the fast model: it is a small
        # decision, and on rate-limited providers the fast model has its own
        # token bucket, which roughly doubles a run's throughput.
        return self._call(
            state, RoutingDecision, ROUTER_SYSTEM, prompt, max_tokens=700, fast=True
        )

    def _enforce(
        self, decision: RoutingDecision, state: WorkforceState
    ) -> RoutingDecision:
        """Hold the router to the allowed set.

        Models re-select an agent that has already succeeded far more often than
        the prompt suggests they should, which produces an infinite loop that
        only the step limit breaks. When that happens we fall forward to the next
        unfinished step of the plan, and finish if there isn't one.
        """
        choice = (decision.next_agent or "").strip()
        if choice == "FINISH":
            return decision

        allowed = self._allowed_agents(state)
        if choice in allowed:
            return decision

        # Prefer the next step of the original plan that is still open.
        plan_text = " ".join(state.get("plan", [])).lower()
        fallback = next((a for a in allowed if a in plan_text), None) or (
            allowed[0] if allowed else "FINISH"
        )

        bus.emit(
            state.get("session_id", "unknown"),
            kind="handoff",
            actor=self.name,
            summary=(
                f"router picked {choice!r}, which is not available "
                f"(already done or not applicable) — redirecting to {fallback!r}"
            ),
            payload={"requested": choice, "allowed": allowed, "chose": fallback},
            level="warning",
        )

        if fallback == "FINISH":
            return RoutingDecision(
                next_agent="FINISH",
                task="",
                reason="every applicable agent has already reported",
                stage=state.get("stage", "reporting"),
            )
        return RoutingDecision(
            next_agent=fallback,
            task=decision.task or f"Continue the plan: {fallback.replace('_', ' ')}.",
            reason=f"redirected from {choice} (already completed)",
            stage=decision.stage,
        )

    def aggregate(self, state: WorkforceState) -> str:
        """Compose the owner-facing answer from everything the agents produced."""
        outputs = state.get("agent_outputs", {})

        # If Reporting ran, its Markdown already is the deliverable.
        reporting = outputs.get("reporting", {})
        if reporting.get("ok") and reporting.get("payload", {}).get("full_report_markdown"):
            return reporting["payload"]["full_report_markdown"]

        from .config import settings

        payload_cap = 900 if settings.compact_prompts else 3000
        # A run with no specialists is not a failure — it is the supervisor
        # deciding the message did not need any, which is the common case for
        # a greeting. It still gets a real, model-written reply; returning a
        # canned "I wasn't able to complete any work" here told the owner the
        # app was broken when it had simply answered them directly.
        detail = []
        for agent, data in outputs.items():
            status = "completed" if data.get("ok") else f"FAILED: {data.get('error')}"
            detail.append(
                f"### {agent} [{status}]\n{data.get('summary', '')}\n\n"
                f"Structured output:\n{_json(data.get('payload', {}), payload_cap)}"
            )

        # Nothing ran, so there is nothing to summarise: the owner's sentence
        # is the entire input. Sending the stage, the approval history and a
        # set of empty report headings invites the model to talk about them.
        if not outputs:
            prompt = str(state.get("owner_input", ""))[:400]
        else:
            prompt = f"""OWNER'S ORIGINAL REQUEST
{state.get('owner_input', '')}

STAGE REACHED: {state.get('stage', '')}

APPROVAL DECISIONS THE OWNER MADE
{_json(memory.approvals(state.get('session_id', '')))}

SPECIALIST REPORTS
{chr(10).join(detail)}

Write the owner's answer."""

        session_id = state.get("session_id", "unknown")
        # A run with no specialists is not a failed report, it is a reply.
        # Handing it to the report-writing prompt produced business-speak at
        # someone who only said hello — that prompt is told to lead with
        # findings, quote concrete numbers and close with "What I need from
        # you", none of which a greeting has or wants. A smaller budget too:
        # two sentences do not need the report allowance.
        chatting = not outputs
        system = CHAT_SYSTEM if chatting else AGGREGATOR_SYSTEM
        llm = get_llm(max_tokens=300 if chatting else settings.report_tokens)
        messages = [SystemMessage(content=system), HumanMessage(content=prompt)]
        sink = _SINKS.get(session_id)
        if sink is not None:
            try:
                return self._stream_answer(llm, messages, sink, session_id,
                                           outputs)
            except Exception as exc:  # noqa: BLE001
                # Streaming is a nicety; never let it lose the answer. Fall
                # back to one ordinary call rather than showing the owner an
                # error because the transport, not the model, misbehaved.
                logger.warning("streaming failed, answering in one piece: %s",
                               exc)

        try:
            response = llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 — always return something to the owner
            bus.emit(
                session_id,
                kind="error",
                actor=self.name,
                summary=f"aggregation failed: {exc}",
                level="error",
            )
            return self._fallback_summary(outputs)

        usage = extract_usage(self.name, active_model_name(llm), response)
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

    def _stream_answer(self, llm, messages, sink, session_id, outputs) -> str:
        """Write the answer out as it arrives, and still bill for it.

        The chunks are handed to `sink` as they come and also joined into the
        return value, because the caller stores that in the thread — the
        owner should find the same text there on reload as they watched
        being typed.
        """
        parts: list[str] = []
        usage_meta = None
        for chunk in llm.stream(messages, stream_usage=True):
            content = chunk.content
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")
            if content:
                parts.append(str(content))
                sink(str(content))
            meta = getattr(chunk, "usage_metadata", None)
            if meta:
                usage_meta = meta

        # Metering must not depend on the display path. A streamed answer
        # that is never charged is a free run for anyone whose browser
        # happens to be open.
        if usage_meta:
            try:
                from .pricing import CallUsage

                usage = CallUsage(
                    agent=self.name,
                    model=active_model_name(llm),
                    input_tokens=int(usage_meta.get("input_tokens", 0)),
                    output_tokens=int(usage_meta.get("output_tokens", 0)),
                )
                ledger_for(session_id).record(usage)
                bus.emit(
                    session_id,
                    kind="llm_usage",
                    actor=self.name,
                    summary=(f"aggregation: {usage.output_tokens} out "
                             f"(streamed)"),
                    payload={"streamed": True},
                )
            except Exception:  # noqa: BLE001 — never lose the answer to billing
                logger.warning("could not record streamed usage", exc_info=True)

        return "".join(parts).strip() or self._fallback_summary(outputs)

    @staticmethod
    def _fallback_summary(outputs: dict) -> str:
        lines = ["# Results\n"]
        for agent, data in outputs.items():
            mark = "✅" if data.get("ok") else "❌"
            lines.append(f"{mark} **{agent}** — {data.get('summary', '')}\n")
        return "\n".join(lines)

    # ------------------------------------------------------------------

    def _call(
        self,
        state: WorkforceState,
        schema,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        fast: bool = False,
    ):
        session_id = state.get("session_id", "unknown")
        model = settings.fast_model if fast else None
        llm = get_llm(model, max_tokens)
        model_id = active_model_name(llm)
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
