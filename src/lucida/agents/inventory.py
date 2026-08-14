"""Inventory Agent — records purchased stock and flags what needs refilling.

The owner uploads photos plus quantities after buying stock; this agent writes
the structured record (product, quantity, cost, photo reference) that every
later stage depends on, and raises low-stock alerts.
"""

from __future__ import annotations

from ..config import settings
from ..memory import memory
from ..observability import bus
from ..state import WorkforceState
from .base import AgentResult, BaseAgent
from .schemas import InventoryResult

SYSTEM = """You are the Inventory Agent in an AI workforce running a real small business.

You maintain the stock record and tell the owner what to reorder.

Rules:
- Only record items you were actually told about, either in the owner's message, the
  photo analysis, or the existing catalog. Never invent stock.
- Set `reorder_level` sensibly: roughly one week of expected sales, minimum 3 for slow
  movers and higher for perishables or fast sellers.
- `restock_advice` should be specific and actionable — what to buy, how much, and why.
- If quantities are missing, say so in `summary` and ask for them rather than guessing.
"""


class InventoryAgent(BaseAgent):
    name = "inventory"
    title = "Inventory Agent"
    description = (
        "Stores product photos, quantities and costs; tracks stock levels and flags "
        "items below their reorder point."
    )
    tools_used = ("SQLite database", "image storage", "shared memory (RAG)")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        outputs = state.get("agent_outputs", {})
        ctx = state.get("owner_context", {})

        current = memory.inventory()
        vision = (outputs.get("product_vision") or {}).get("payload") or {}
        pricing = (outputs.get("pricing") or {}).get("payload") or {}

        prompt = f"""OWNER MESSAGE
{state.get('owner_input', '')}

SUPERVISOR TASK
{state.get('current_task', 'Record the stock the owner has purchased.')}

STRUCTURED STOCK DETAILS SUPPLIED BY THE OWNER (may be empty)
{self.as_json(ctx.get('stock_items', []))}

PRODUCT IDENTIFIED FROM PHOTO (if any)
{self.as_json({k: vision.get(k) for k in ('product_name', 'category', 'estimated_unit_cost')} if vision else {})}

AGREED PRICING (if any)
{self.as_json({k: pricing.get(k) for k in ('product_name', 'unit_cost', 'recommended_price')} if pricing else {})}

CURRENT CATALOG AND STOCK LEVELS
{self.as_json(current)}

{self.context_block(state, 'inventory stock levels reorder')}

Currency: {settings.currency}.

Record the stock, then report levels and reorder advice."""

        result = self.ask(state, InventoryResult, SYSTEM, prompt)

        # Persist every item the agent recorded.
        recorded = []
        for item in result.items_recorded:
            product_id = memory.db.upsert_product(
                name=item.product_name,
                unit_cost=item.unit_cost or None,
                photo_path=str((state.get("image_paths") or [""])[0]),
                source_agent=self.name,
            )
            if product_id is None:      # a placeholder name, refused
                continue
            memory.db.set_stock(product_id, item.quantity, item.reorder_level)
            memory.db.execute(
                "INSERT INTO stock_movements (product_id, delta, reason, created_at) "
                "VALUES (?,?,?,datetime('now'))",
                (product_id, item.quantity, "owner stock intake"),
            )
            recorded.append({"product_id": product_id, **item.model_dump()})
            bus.emit(
                session_id,
                kind="tool_call",
                actor=self.name,
                summary=f"recorded stock: {item.product_name} x{item.quantity}",
                payload=item.model_dump(),
            )

        # Recompute alerts from the database rather than trusting the model.
        low = memory.low_stock()
        alerts = [
            f"{r['name']}: {r['quantity']} left (reorder at {r['reorder_level']})"
            for r in low
        ]
        stock_value = sum(
            (r["quantity"] or 0) * (r["unit_cost"] or 0) for r in memory.inventory()
        )
        result.low_stock_alerts = alerts
        result.total_stock_value = round(stock_value, 2)

        self.remember(
            state,
            (
                f"Inventory update: {len(recorded)} item(s) recorded. "
                f"Total stock value {stock_value:.2f} {settings.currency}. "
                f"Low stock: {'; '.join(alerts) if alerts else 'none'}. "
                f"{result.restock_advice}"
            ),
            kind="inventory",
        )

        summary = result.summary
        if alerts:
            summary += f" ⚠️ Low stock on {len(alerts)} item(s): {', '.join(alerts)}."
        summary += f" Total stock value {stock_value:,.0f} {settings.currency}."

        return AgentResult(
            summary=summary,
            payload={
                **result.model_dump(),
                "recorded": recorded,
                "inventory_snapshot": memory.inventory(),
            },
        )
