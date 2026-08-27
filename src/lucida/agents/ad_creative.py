"""Ad Creation & Publishing Agent — writes the campaign, then waits for the owner.

Publishing is irreversible and spends the owner's reputation (and potentially
budget), so this agent always drafts first, blocks on a human-in-the-loop
approval checkpoint, and only publishes what was approved. A "request changes"
decision sends it back to rewrite with the owner's feedback.
"""

from __future__ import annotations

from ..config import settings
from ..memory import memory
from ..observability import bus
from ..state import WorkforceState
from ..tools.social import social
from .base import AgentResult, BaseAgent
from .schemas import AdCreativeResult

SYSTEM = """You are the Ad Creation & Publishing Agent in an AI workforce running a real small business.

You write ad copy that a real small-business owner would be happy to put their name on.

Rules:
- Write one creative per platform requested, tuned to that platform: Facebook is
  conversational and can be longer; Instagram is visual-first with a punchy caption;
  YouTube needs a searchable title plus a description.
- Match the local market's language and register. If the owner writes in Bangla or
  Banglish, write copy the same way — do not translate them into corporate English.
- Never claim anything the product data does not support. No fake scarcity, no
  invented certifications, no health claims.
- Include the actual price and how to order. An ad the customer can't act on is waste.
- `visual_direction` tells the owner what photo or video to pair with the copy.
"""

REVISION_NOTE = """
The owner reviewed your previous draft and requested changes. Their feedback:

"{feedback}"

Rewrite the creatives to address this feedback directly. Do not ignore any part of it.
"""


class AdCreativeAgent(BaseAgent):
    name = "ad_creative"
    title = "Ad Creation & Publishing Agent"
    description = (
        "Generates platform-specific ad copy and creative direction, then publishes "
        "to Facebook after owner approval."
    )
    tools_used = ("Meta Graph API", "shared memory (RAG)")
    requires_approval = True
    approval_checkpoint = "publish_ads"

    MAX_REVISIONS = 2

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        outputs = state.get("agent_outputs", {})
        product, price = self._subject(outputs)
        platforms = state.get("owner_context", {}).get(
            "platforms", ["facebook"]
        )

        feedback = ""
        result: AdCreativeResult | None = None
        decision: dict = {}

        for attempt in range(self.MAX_REVISIONS + 1):
            result = self._draft(state, product, price, platforms, feedback)

            preview = self._render_preview(result, product, price)
            decision = self.request_approval(
                state,
                title=f"Publish {len(result.creatives)} ad creative(s) for {product}?",
                detail=preview,
                payload={
                    "creatives": [c.model_dump() for c in result.creatives],
                    "platforms": platforms,
                    "attempt": attempt + 1,
                },
            )

            choice = str(decision.get("decision", "approve")).lower()
            if choice != "request_changes":
                break
            feedback = str(decision.get("feedback", "")).strip()
            bus.emit(
                session_id,
                kind="handoff",
                actor=self.name,
                summary=f"owner requested changes (revision {attempt + 1}); rewriting",
                payload={"feedback": feedback},
            )
        else:
            decision = {"decision": "reject", "feedback": "revision limit reached"}

        assert result is not None
        choice = str(decision.get("decision", "approve")).lower()

        # Draft every creative into the database regardless of the decision, so
        # the owner keeps the copy even if they decline to publish.
        campaign_ids = []
        for c in result.creatives:
            campaign_ids.append(
                memory.db.add_campaign(
                    platform=c.platform,
                    headline=c.headline,
                    body=c.body,
                    call_to_action=c.call_to_action,
                    product_name=product,
                    status="drafted",
                    simulated=1,
                )
            )

        if choice != "approve":
            reason = decision.get("feedback") or "no reason given"
            self.remember(
                state,
                f"Owner declined to publish ads for {product}. Reason: {reason}",
                kind="ad_campaign",
            )
            return AgentResult(
                summary=(
                    f"Owner **rejected** publication. {len(result.creatives)} creative(s) "
                    f"saved as drafts for {product}. Reason: {reason}"
                ),
                payload={
                    **result.model_dump(),
                    "published": False,
                    "decision": decision,
                    "campaign_ids": campaign_ids,
                },
            )

        # Approved — publish.
        publish_log = []
        for c, campaign_id in zip(result.creatives, campaign_ids):
            full_text = f"{c.headline}\n\n{c.body}\n\n{c.call_to_action}"
            if c.hashtags:
                full_text += "\n\n" + " ".join(
                    h if h.startswith("#") else f"#{h}" for h in c.hashtags
                )

            platform = c.platform.lower()
            if platform == "facebook":
                res = social.publish_facebook(full_text)
            elif platform == "instagram":
                res = social.publish_instagram(full_text)
            elif platform == "youtube":
                res = social.publish_youtube(c.headline, full_text)
            else:
                continue

            memory.db.update_campaign(
                campaign_id,
                status="published" if res.ok else "failed",
                external_id=res.external_id,
            )
            memory.db.execute(
                "UPDATE campaigns SET simulated=? WHERE id=?",
                (1 if res.simulated else 0, campaign_id),
            )
            publish_log.append(res.describe())
            bus.emit(
                session_id,
                kind="tool_call",
                actor=self.name,
                summary=res.describe(),
                payload={"platform": platform, "simulated": res.simulated, "ok": res.ok},
                level="info" if res.ok else "warning",
            )

        result.publish_results = publish_log
        self.remember(
            state,
            (
                f"Ad campaign published for {product} at {price} {settings.currency}. "
                f"Target audience: {result.target_audience}. "
                f"Headlines: {'; '.join(c.headline for c in result.creatives)}. "
                f"Results: {'; '.join(publish_log)}"
            ),
            kind="ad_campaign",
            extra={"product": product},
        )

        return AgentResult(
            summary=(
                f"Owner approved. Published {len(publish_log)} creative(s) for "
                f"{product}.\n" + "\n".join(f"- {p}" for p in publish_log)
            ),
            payload={
                **result.model_dump(),
                "published": True,
                "decision": decision,
                "campaign_ids": campaign_ids,
            },
        )

    # --- helpers ---

    def _draft(
        self,
        state: WorkforceState,
        product: str,
        price: float,
        platforms: list[str],
        feedback: str,
    ) -> AdCreativeResult:
        prompt = f"""PRODUCT: {product}
PRICE: {price:.0f} {settings.currency}
MARKET: {settings.location}
PLATFORMS TO WRITE FOR: {', '.join(platforms)}

OWNER'S ORIGINAL REQUEST
{state.get('owner_input', '')}

{self.context_block(state, f'ad copy marketing audience {product}')}

Write one creative per platform listed above, plus the target audience and a suggested
starting budget."""

        if feedback:
            prompt += REVISION_NOTE.format(feedback=feedback)

        return self.ask(state, AdCreativeResult, SYSTEM, prompt)

    def _subject(self, outputs: dict) -> tuple[str, float]:
        pricing = (outputs.get("pricing") or {}).get("payload") or {}
        if pricing.get("product_name"):
            return pricing["product_name"], float(pricing.get("recommended_price") or 0)

        vision = (outputs.get("product_vision") or {}).get("payload") or {}
        if vision.get("product_name"):
            return vision["product_name"], float(vision.get("suggested_price_high") or 0)

        research = (outputs.get("market_research") or {}).get("payload") or {}
        if research.get("recommended_niche"):
            return research["recommended_niche"], float(
                research.get("competitor_price_high") or 0
            )

        products = memory.products()
        if products:
            return products[0]["name"], float(products[0].get("sell_price") or 0)
        return "the product", 0.0

    def _render_preview(self, result: AdCreativeResult, product: str, price: float) -> str:
        lines = [
            f"**Product:** {product} — {price:.0f} {settings.currency}",
            f"**Target audience:** {result.target_audience}",
            f"**Suggested budget:** {result.suggested_budget}",
            "",
        ]
        for c in result.creatives:
            tags = " ".join(h if h.startswith("#") else f"#{h}" for h in c.hashtags)
            lines += [
                f"### {c.platform.title()}",
                f"**{c.headline}**",
                "",
                c.body,
                "",
                f"➡️ {c.call_to_action}",
                f"{tags}" if tags else "",
                f"*Visual: {c.visual_direction}*" if c.visual_direction else "",
                "",
            ]
        mode = "LIVE" if settings.has_meta else "SIMULATED"
        lines.append(f"_Publishing mode: **{mode}**_")
        return "\n".join(l for l in lines if l is not None)
