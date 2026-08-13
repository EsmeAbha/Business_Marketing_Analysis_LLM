"""Product Vision Agent — turns an uploaded photo into a go/no-go business call.

This is the system's signature flow: the owner photographs a product or dish,
and the agent identifies it, cross-references live market data for it, estimates
a price band, and returns a GO / NO-GO / CONDITIONAL recommendation.
"""

from __future__ import annotations

from ..config import settings
from ..observability import AgentError, bus
from ..state import WorkforceState
from ..tools.web_search import web_search
from .base import AgentResult, BaseAgent
from .schemas import ProductVisionResult

IDENTIFY_SYSTEM = """You are the Product Vision Agent in an AI workforce running a real small business.

You are shown a photograph the business owner took. Identify the product truthfully.

Rules:
- Describe only what is actually visible. Do not invent brand names, ingredients or
  packaging you cannot see.
- If the photo is unclear, say so plainly in `quality_notes` and lower your confidence
  in `reasoning` rather than guessing.
- Judge sale-readiness honestly: presentation, packaging, portioning, and anything
  that would put a buyer off.
- `recommendation` must be exactly GO, NO-GO or CONDITIONAL. CONDITIONAL means it is
  viable only if a specific fixable problem is addressed — name that problem.
"""

ASSESS_SYSTEM = """You are the Product Vision Agent completing a product validation.

You have already identified the product from a photo. Now you are given live market
evidence about it. Produce the final assessment.

Rules:
- Price estimates must sit inside or near the competitor band in the evidence. If they
  do not, justify why in `reasoning`.
- `demand_assessment` must reference the evidence, not general intuition.
- Keep `recommendation` honest — a NO-GO that saves the owner money is a good outcome.
"""


class ProductVisionAgent(BaseAgent):
    name = "product_vision"
    title = "Product Vision Agent"
    description = (
        "Identifies a product or food item from the owner's photo, estimates demand "
        "and price fit, and issues a go/no-go recommendation."
    )
    tools_used = ("Claude vision", "web search", "shared memory (RAG)")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        image_paths = state.get("image_paths") or []

        if not image_paths:
            raise AgentError(
                self.name,
                "no image was uploaded — ask the owner to attach a product photo, "
                "or route this request to the Market Research agent instead",
            )

        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"vision analysis of {len(image_paths)} image(s)",
            payload={"images": [str(p) for p in image_paths]},
        )

        # Pass 1 — identify from the photo alone, no market context to bias it.
        identify_prompt = f"""The business owner uploaded this photo and said:
"{state.get('owner_input', '')}"

Task: {state.get('current_task', 'Identify this product and assess whether it can be sold.')}
Market: {settings.location}. Currency: {settings.currency}.

Identify the product and give a first-pass assessment."""

        first_pass = self.call_vision(
            state, ProductVisionResult, IDENTIFY_SYSTEM, identify_prompt, image_paths
        )

        # Pass 2 — enrich with live market data for the identified product.
        queries = [
            f"{first_pass.product_name} price {settings.location}",
            f"{first_pass.product_name} demand small business sell online",
        ]
        evidence = []
        for q in queries:
            resp = web_search(q, max_results=4)
            evidence.append(resp.as_prompt_context(limit=4))
            bus.emit(
                session_id,
                kind="tool_call",
                actor=self.name,
                summary=f"web_search({q!r}) -> {len(resp.results)} results",
                payload={"provider": resp.provider, "simulated": resp.simulated},
            )

        assess_prompt = f"""PRODUCT IDENTIFIED FROM PHOTO
Name: {first_pass.product_name}
Category: {first_pass.category}
What is visible: {first_pass.description}
Quality/presentation notes: {first_pass.quality_notes}
First-pass cost estimate: {first_pass.estimated_unit_cost} {settings.currency}

{self.context_block(state, f"product validation pricing demand {first_pass.product_name}")}

=== LIVE MARKET EVIDENCE ===
{chr(10).join(evidence)}
=== END EVIDENCE ===

Produce the final validated assessment for this product in {settings.location}."""

        final = self.ask(state, ProductVisionResult, ASSESS_SYSTEM, assess_prompt)

        # Register the product so Inventory and Pricing can pick it up.
        from ..memory import memory

        product_id = memory.db.upsert_product(
            name=final.product_name,
            category=final.category,
            description=final.description,
            unit_cost=final.estimated_unit_cost or None,
            photo_path=str(image_paths[0]),
            source_agent=self.name,
        )

        self.remember(
            state,
            (
                f"Product validated from photo: {final.product_name} ({final.category}). "
                f"{final.description} Estimated unit cost {final.estimated_unit_cost} "
                f"{settings.currency}; suggested price {final.suggested_price_low}-"
                f"{final.suggested_price_high}. Demand: {final.demand_assessment} "
                f"Recommendation: {final.recommendation}. {final.reasoning}"
            ),
            kind="product_validation",
            extra={"product": final.product_name, "product_id": product_id},
        )

        return AgentResult(
            summary=(
                f"Identified **{final.product_name}** ({final.category}). "
                f"Recommendation: **{final.recommendation}**. "
                f"Suggested price {final.suggested_price_low:.0f}–"
                f"{final.suggested_price_high:.0f} {settings.currency}. "
                f"{final.reasoning}"
            ),
            payload={**final.model_dump(), "product_id": product_id},
        )
