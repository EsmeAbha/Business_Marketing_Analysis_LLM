"""The LangGraph state object — the shared blackboard every node reads and writes.

Reducers matter here: `operator.add` on the list fields means a node returning
`{"agent_messages": [msg]}` appends rather than replacing, so parallel or
repeated agent visits accumulate history instead of clobbering it.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

# Lifecycle stages, in the order the business moves through them.
Stage = Literal[
    "idea_research",
    "product_validation",
    "owner_decision",
    "inventory_setup",
    "marketing_launch",
    "customer_engagement",
    "reporting",
    "delivery",
    "complete",
]

STAGE_ORDER: tuple[Stage, ...] = (
    "idea_research",
    "product_validation",
    "owner_decision",
    "inventory_setup",
    "marketing_launch",
    "customer_engagement",
    "reporting",
    "delivery",
    "complete",
)

# Every routable worker. "FINISH" ends the run.
AgentName = Literal[
    "market_research",
    "product_vision",
    "pricing",
    "inventory",
    "ad_creative",
    "engagement",
    "delivery",
    "reporting",
    "FINISH",
]


class AgentMessage(TypedDict, total=False):
    """One structured hand-off between two agents, via the supervisor."""

    sender: str
    recipient: str
    task: str
    summary: str
    payload: dict[str, Any]
    ts: str


class ApprovalRequest(TypedDict, total=False):
    """A human-in-the-loop checkpoint the graph is currently blocked on."""

    checkpoint: str        # e.g. "publish_ads"
    agent: str
    title: str
    detail: str
    options: list[str]     # approve | reject | request_changes
    payload: dict[str, Any]


class WorkforceState(TypedDict, total=False):
    # --- session identity ---
    session_id: str
    thread_id: str

    # --- owner input ---
    owner_input: str
    image_paths: list[str]
    owner_context: dict[str, Any]

    # --- supervisor control ---
    stage: Stage
    plan: list[str]
    next_agent: str
    routing_reason: str
    current_task: str
    step_count: int

    # --- accumulated work ---
    agent_messages: Annotated[list[AgentMessage], operator.add]
    agent_outputs: dict[str, Any]
    completed_agents: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]

    # --- human in the loop ---
    pending_approval: ApprovalRequest
    approvals: Annotated[list[dict[str, Any]], operator.add]

    # --- output ---
    final_report: str
    finished: bool


def new_state(
    session_id: str,
    owner_input: str,
    image_paths: list[str] | None = None,
    owner_context: dict[str, Any] | None = None,
) -> WorkforceState:
    return WorkforceState(
        session_id=session_id,
        thread_id=session_id,
        owner_input=owner_input,
        image_paths=image_paths or [],
        owner_context=owner_context or {},
        stage="idea_research",
        plan=[],
        next_agent="",
        routing_reason="",
        current_task="",
        step_count=0,
        agent_messages=[],
        agent_outputs={},
        completed_agents=[],
        errors=[],
        pending_approval={},
        approvals=[],
        final_report="",
        finished=False,
    )
