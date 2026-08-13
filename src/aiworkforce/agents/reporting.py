"""Reporting Agent — the replanning loop that closes the business cycle.

This is the heaviest consumer of shared memory: it reads across every earlier
stage (research, pricing, inventory, campaigns, customer signal) via RAG plus
the structured tables, recomputes the financials in Python, and produces the
owner's weekly report with a revised plan.
"""

from __future__ import annotations

from ..config import settings
from ..memory import memory
from ..observability import bus
from ..state import WorkforceState
from ..tools.code_exec import run_calculation
from .base import AgentResult, BaseAgent, ledger_for
from .schemas import ReportingResult

SYSTEM = """You are the Reporting Agent in an AI workforce running a real small business.

You write the owner's periodic business report and the revised plan that follows from it.

Rules:
- The computed financials supplied to you are authoritative — use those numbers.
- Connect the dots across stages: if customers keep asking for something the catalog
  lacks, that belongs in `revised_plan`, not just `demand_shifts`.
- `next_actions` must be things the owner can do this week, each naming who or what
  does it. "Reorder 40 units of X before Friday" beats "improve inventory management".
- Be direct about bad news. A report that hides a shrinking margin is worse than useless.
- `full_report_markdown` is what the owner actually reads: well-structured Markdown with
  headings, the key numbers up front, and no filler.
"""


class ReportingAgent(BaseAgent):
    name = "reporting"
    title = "Reporting Agent"
    description = (
        "Weekly/daily summary: restock alerts, demand shifts, profit analysis and a "
        "revised plan, synthesised from the whole shared knowledge base."
    )
    tools_used = ("RAG over shared memory", "code execution", "SQLite analytics")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")

        inventory = memory.inventory()
        low = memory.low_stock()
        preorders = memory.preorders()
        campaigns = memory.campaigns()
        conversations = memory.conversations(200)
        pricing_rows = memory.pricing_history()

        financials = self._compute_financials(
            session_id, inventory, preorders, conversations
        )

        # Deliberately broad RAG sweep — this is where cross-stage memory pays off.
        retrieved = "\n\n".join(
            f"### {label}\n{self.recall(query, k=4)}"
            for label, query in (
                ("Market research", "niche demand competition recommendation"),
                ("Product validation", "product photo validation go no-go price"),
                ("Pricing decisions", "price margin break-even cost"),
                ("Marketing", "ad campaign copy audience published"),
                ("Customer signal", "customer feedback complaints unmet demand preorder"),
            )
        )

        prompt = f"""{memory.business_snapshot()}

=== COMPUTED FINANCIALS (executed in Python — authoritative) ===
{financials['log']}
=== END FINANCIALS ===

CURRENT INVENTORY
{self.as_json(inventory)}

LOW STOCK
{self.as_json(low)}

OPEN PRE-ORDERS ({len(preorders)})
{self.as_json(preorders[:15])}

CAMPAIGNS ({len(campaigns)})
{self.as_json([{k: c[k] for k in ('platform', 'headline', 'status', 'simulated')} for c in campaigns[:10]])}

PRICING HISTORY
{self.as_json(pricing_rows[:10])}

RECENT CUSTOMER MESSAGES ({len(conversations)})
{self.as_json([{k: c[k] for k in ('channel', 'customer', 'message', 'sentiment', 'intent', 'requested_item')} for c in conversations[:25]], limit=6000)}

=== RETRIEVED FROM SHARED KNOWLEDGE BASE (written by other agents) ===
{retrieved}
=== END RETRIEVED ===

THIS SESSION'S AGENT OUTPUTS
{self._session_outputs(state)}

Write the business report and the revised plan for maximising profit."""

        result = self.ask(state, ReportingResult, SYSTEM, prompt, max_tokens=12000)

        # Recompute alerts from the database so they cannot drift from reality.
        result.stock_alerts = [
            f"{r['name']}: {r['quantity']} left (reorder at {r['reorder_level']})"
            for r in low
        ] or result.stock_alerts

        body = result.full_report_markdown or self._fallback_markdown(result, financials)
        body += "\n\n---\n" + self._run_footer(session_id, financials)

        memory.db.add_report(session_id, result.title, body)
        self.remember(
            state,
            (
                f"Business report '{result.title}': {result.executive_summary} "
                f"Stock alerts: {'; '.join(result.stock_alerts) or 'none'}. "
                f"Demand shifts: {'; '.join(result.demand_shifts) or 'none'}. "
                f"Revised plan: {'; '.join(result.revised_plan)}"
            ),
            kind="report",
        )

        return AgentResult(
            summary=result.executive_summary,
            payload={**result.model_dump(), "full_report_markdown": body, "financials": financials},
        )

    # --- helpers ---

    def _compute_financials(
        self, session_id: str, inventory: list, preorders: list, conversations: list
    ) -> dict:
        code = """
stock_value = 0.0
potential_revenue = 0.0
potential_profit = 0.0
lines = []
for row in inventory:
    qty = row.get("quantity") or 0
    cost = row.get("unit_cost") or 0
    price = row.get("sell_price") or 0
    stock_value += qty * cost
    potential_revenue += qty * price
    potential_profit += qty * (price - cost)
    margin_pct = round((price - cost) / price * 100, 1) if price else 0.0
    lines.append(
        f"{row.get('name')}: qty={qty} cost={cost} price={price} "
        f"margin={margin_pct}% stock_value={round(qty * cost, 2)}"
    )

blended_margin = round(potential_profit / potential_revenue * 100, 1) if potential_revenue else 0.0
negative_msgs = sum(1 for c in conversations if (c.get("sentiment") or "").lower() == "negative")
total_msgs = len(conversations)
negative_pct = round(negative_msgs / total_msgs * 100, 1) if total_msgs else 0.0

print("PER-PRODUCT")
for line in lines:
    print("  " + line)
print(f"TOTAL stock value (cost basis): {round(stock_value, 2)}")
print(f"TOTAL potential revenue at current prices: {round(potential_revenue, 2)}")
print(f"TOTAL potential gross profit: {round(potential_profit, 2)}")
print(f"Blended gross margin: {blended_margin}%")
print(f"Open pre-orders: {len(preorders)}")
print(f"Customer messages: {total_msgs} ({negative_msgs} negative = {negative_pct}%)")
"""
        result = run_calculation(
            code,
            inputs={
                "inventory": inventory,
                "preorders": preorders,
                "conversations": conversations,
            },
        )
        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"financial computation {'ok' if result.ok else 'failed'}",
            payload={"ok": result.ok, "error": result.error},
            level="info" if result.ok else "warning",
        )
        return {
            "log": result.summary(),
            "ok": result.ok,
            "stock_value": result.variables.get("stock_value", 0),
            "potential_revenue": result.variables.get("potential_revenue", 0),
            "potential_profit": result.variables.get("potential_profit", 0),
            "blended_margin": result.variables.get("blended_margin", 0),
        }

    def _fallback_markdown(self, r: ReportingResult, financials: dict) -> str:
        """Used only if the model returns no assembled Markdown."""
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {i}" for i in items) if items else "- (none)"

        return (
            f"# {r.title}\n\n## Executive summary\n{r.executive_summary}\n\n"
            f"## Financials\n```\n{financials['log']}\n```\n{r.financials}\n\n"
            f"## Stock alerts\n{bullets(r.stock_alerts)}\n\n"
            f"## Demand shifts\n{bullets(r.demand_shifts)}\n\n"
            f"## Revised plan\n{bullets(r.revised_plan)}\n\n"
            f"## Next actions\n{bullets(r.next_actions)}\n"
        )

    def _run_footer(self, session_id: str, financials: dict) -> str:
        ledger = ledger_for(session_id)
        return (
            f"_Generated by the AI Business Workforce. Session `{session_id}`. "
            f"{len(ledger.calls)} LLM calls, {ledger.total_tokens:,} tokens, "
            f"estimated cost ${ledger.total_cost_usd:.4f}. "
            f"Currency: {settings.currency}._"
        )
