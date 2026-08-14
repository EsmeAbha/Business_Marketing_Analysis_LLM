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
from ..tools import inbox
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

        # Pull anything new from Messenger, Instagram and the comments under
        # published posts into the shop's own inbox first, then read from
        # there. Storing before analysing means a message survives a failed
        # run, and the same message is never analysed twice.
        synced = inbox.sync(memory.db, limit=limit)
        simulated = synced.simulated
        rows = inbox.threads(memory.db, limit=limit)
        messages = [
            {
                "id": r["id"],
                "customer": r.get("sender_name") or "Customer",
                "channel": r.get("platform") or "message",
                "message": r.get("message") or "",
                "kind": r.get("kind") or "dm",
            }
            for r in rows
        ]

        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"synced {synced.stored} new of {synced.fetched} fetched; "
                    f"{len(messages)} conversation(s) to read"
            + (" [SIMULATED inbox]" if simulated else " [LIVE]"),
            payload={
                "fetched": synced.fetched, "new": synced.stored,
                "per_platform": synced.per_platform,
                "unanswered": inbox.unanswered(memory.db),
                "simulated": simulated,
                "errors": synced.errors,
            },
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

Analyse every message above. Copy each message's `id` into the `id` field of your
analysis, unchanged — that is how a draft reply gets attached to the right customer.
Anything a customer asks for that is not in the product list is unmet demand — capture
it in `requested_item` and `unmet_demand`."""

        result = self.ask(state, EngagementResult, SYSTEM, prompt)

        # The drafts are what the Customers page offers the owner to send, so
        # every one has to land on the right row. Three ways of finding it,
        # in order of how much they can be trusted:
        #   1. the id the model was given and asked to echo back;
        #   2. the message text, normalised — the model often tidies wording,
        #      punctuation or spacing while meaning the same message;
        #   3. nothing. A draft that cannot be placed is dropped rather than
        #      guessed onto a customer it might not answer.
        # One text can map to several rows: the same question often arrives on
        # Messenger and Instagram both, and every unanswered copy gets it.
        def _key(text: str) -> str:
            plain = " ".join(str(text or "").lower().split())
            return "".join(c for c in plain if c.isalnum() or c.isspace())

        by_id = {r["id"]: [r["id"]] for r in rows}
        by_text: dict[str, list[int]] = {}
        for r in rows:
            by_text.setdefault(_key(r.get("message")), []).append(r["id"])

        drafted, unplaced = 0, 0
        for m in result.analysed:
            reply_text = (m.suggested_reply or "").strip()
            if not reply_text:
                continue
            targets = by_id.get(getattr(m, "id", None) or -1) \
                or by_text.get(_key(m.message), [])
            if not targets:
                unplaced += 1
                self.log.info("a draft reply matched no message; dropped it")
                continue
            for row_id in targets:
                memory.db.execute(
                    "UPDATE social_messages SET draft_reply=?, sentiment=?, "
                    "intent=?, requested_item=? WHERE id=? AND replied=0",
                    (reply_text, m.sentiment, m.intent, m.requested_item,
                     row_id),
                )
                drafted += 1

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
        if drafted:
            summary += f" ✍️ {drafted} reply/replies drafted for you to send."
        if unplaced:
            summary += (f" ({unplaced} draft(s) could not be matched to a "
                        f"message and were discarded rather than sent to the "
                        f"wrong customer.)")
        if simulated:
            summary += " (Inbox came from the SIMULATED adapter.)"

        return AgentResult(
            summary=summary,
            payload={**result.model_dump(), "simulated": simulated, "raw_messages": messages},
        )
