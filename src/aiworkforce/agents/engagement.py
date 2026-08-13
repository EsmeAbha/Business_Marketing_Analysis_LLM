"""Customer Engagement Agent — the continuous listening loop.

Reads Messenger/Instagram DMs and comments, classifies sentiment and intent,
extracts pre-orders into the database, and — the part that actually drives
replanning — surfaces demand for things the business does not yet sell.
"""

from __future__ import annotations

from collections import Counter

from ..memory import memory
from ..observability import bus
from ..state import WorkforceState
from ..tools.social import social
from .base import AgentResult, BaseAgent
from .schemas import EngagementResult

SYSTEM = """You are the Customer Engagement Agent in an AI workforce running a real small business.

You read incoming customer messages and turn them into structured business signal.

Rules:
- Classify every message supplied. Do not skip any, and do not invent messages.
- Messages may be in Bangla, Banglish (Bangla written in Latin script), or English.
  Read them all correctly; write `suggested_reply` in the SAME language and register
  the customer used.
- `intent` must be one of: preorder, question, complaint, unmet_demand, praise, other.
- Set `requested_item` ONLY when the customer asks for something the business does not
  currently sell — that is the signal the owner most needs. Leave it empty otherwise.
- `urgent_issues` is for things that lose a customer today: undelivered orders, damaged
  goods, a public complaint. Be specific about who and what.
- Count a preorder only when the customer states real intent to buy, not mere curiosity.
"""


class EngagementAgent(BaseAgent):
    name = "engagement"
    title = "Customer Engagement Agent"
    description = (
        "Reads DMs and comments, analyses sentiment, extracts pre-orders, and detects "
        "demand for products not yet offered."
    )
    tools_used = ("Meta Graph API (Messenger/IG)", "NLP sentiment", "shared memory (RAG)")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        limit = int(state.get("owner_context", {}).get("message_limit", 10) or 10)

        messages, simulated = social.fetch_messages(limit=limit)
        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"fetched {len(messages)} customer messages"
            + (" [SIMULATED inbox]" if simulated else " [LIVE]"),
            payload={"count": len(messages), "simulated": simulated},
            level="warning" if simulated else "info",
        )

        if not messages:
            return AgentResult(
                summary="No customer messages to analyse right now.",
                payload={"analysed": [], "simulated": simulated},
            )

        catalog = [r["name"] for r in memory.inventory()]

        prompt = f"""PRODUCTS THE BUSINESS CURRENTLY SELLS
{', '.join(catalog) if catalog else '(catalog is empty)'}

{self.context_block(state, 'customer feedback demand complaints preorders')}

=== INCOMING CUSTOMER MESSAGES ===
{self.as_json(messages, limit=8000)}
=== END MESSAGES ===

Analyse every message above. Anything a customer asks for that is not in the product
list is unmet demand — capture it in `requested_item` and `unmet_demand`."""

        result = self.ask(state, EngagementResult, SYSTEM, prompt)

        # Persist each analysed message and every extracted pre-order.
        preorder_count = 0
        for m in result.analysed:
            memory.db.add_conversation(
                channel=m.channel,
                customer=m.customer,
                message=m.message,
                sentiment=m.sentiment,
                intent=m.intent,
                requested_item=m.requested_item,
            )
            if m.intent == "preorder":
                memory.db.add_preorder(
                    customer=m.customer,
                    product_name=m.requested_item or (catalog[0] if catalog else "unspecified"),
                    quantity=1,
                    channel=m.channel,
                )
                preorder_count += 1

        # Recompute the breakdown from the records rather than trusting the model.
        counts = Counter(m.sentiment.lower() for m in result.analysed)
        result.sentiment_breakdown = dict(counts)
        result.preorders_found = preorder_count

        unmet = sorted(
            {m.requested_item.strip() for m in result.analysed if m.requested_item.strip()}
        )
        result.unmet_demand = unmet or result.unmet_demand

        self.remember(
            state,
            (
                f"Customer listening pass: {len(result.analysed)} messages. "
                f"Sentiment {dict(counts)}. {preorder_count} pre-order(s) captured. "
                f"Unmet demand: {', '.join(unmet) if unmet else 'none detected'}. "
                f"Urgent issues: {'; '.join(result.urgent_issues) if result.urgent_issues else 'none'}"
            ),
            kind="customer_engagement",
            extra={"unmet_demand": ", ".join(unmet)},
        )

        summary = (
            f"Analysed {len(result.analysed)} messages — "
            f"{counts.get('positive', 0)} positive, {counts.get('neutral', 0)} neutral, "
            f"{counts.get('negative', 0)} negative. "
            f"{preorder_count} pre-order(s) captured."
        )
        if unmet:
            summary += f" 🔎 Customers are asking for: {', '.join(unmet)}."
        if result.urgent_issues:
            summary += f" ⚠️ {len(result.urgent_issues)} urgent issue(s) need a reply today."
        if simulated:
            summary += " (Inbox came from the SIMULATED adapter.)"

        return AgentResult(
            summary=summary,
            payload={**result.model_dump(), "simulated": simulated, "raw_messages": messages},
        )
