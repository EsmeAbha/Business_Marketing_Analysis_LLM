"""Pricing & Cost Agent — computes margins, break-even and a defensible price.

The arithmetic is executed in the restricted Python sandbox rather than done in
prose, so every number in the plan is reproducible. Competitor bands come from
the Market Research agent's output via shared memory — a direct agent-to-agent
data dependency.
"""

from __future__ import annotations

from ..config import settings
from ..observability import bus
from ..state import WorkforceState
from ..tools.code_exec import margin_analysis, run_calculation
from .base import AgentResult, BaseAgent
from .schemas import PricingResult

SYSTEM = """You are the Pricing & Cost Agent in an AI workforce running a real small business.

You set prices that are both competitive and actually profitable.

Rules:
- The computed figures supplied to you are authoritative. Do not restate them
  differently; if you disagree with a price, change the recommended price and explain.
- Undercutting the competitor band is only worth it if the margin still clears ~25%.
  Say so explicitly when you choose to sit above or below the band.
- `rationale` must reference the actual competitor band and the margin maths.
- Prices should be psychologically sensible for the local market (round numbers where
  customers expect them).
"""


class PricingAgent(BaseAgent):
    name = "pricing"
    title = "Pricing & Cost Agent"
    description = (
        "Cost-plus pricing with margin, break-even and competitor comparison, "
        "computed in a real Python sandbox."
    )
    tools_used = ("code execution (sandboxed Python)", "shared memory (RAG)")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        outputs = state.get("agent_outputs", {})

        product_name, unit_cost, price_low, price_high = self._gather_inputs(state, outputs)
        fixed_costs = float(state.get("owner_context", {}).get("fixed_costs", 0) or 0)
        expected_units = int(
            state.get("owner_context", {}).get("expected_monthly_units", 0) or 0
        )

        # Provisional price: mid-band if we have one, else cost-plus 60%.
        provisional = (
            (price_low + price_high) / 2 if price_high > 0 else unit_cost * 1.6
        )

        # Deterministic core metrics, computed in Python.
        base = margin_analysis(unit_cost, provisional, fixed_costs, expected_units)
        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"margin_analysis(cost={unit_cost}, price={provisional:.2f})",
            payload=base,
        )

        # A scenario sweep, executed in the sandbox, so the model can see trade-offs.
        sweep_code = """
scenarios = []
for multiplier in (1.3, 1.5, 1.7, 2.0, 2.5):
    price = round(unit_cost * multiplier)
    margin = price - unit_cost
    margin_pct = round(margin / price * 100, 1) if price else 0
    breakeven = round(fixed_costs / margin, 1) if margin > 0 else -1
    monthly = round(margin * expected_units - fixed_costs, 2)
    scenarios.append({
        "price": price, "margin": margin, "margin_pct": margin_pct,
        "breakeven_units": breakeven, "monthly_profit": monthly,
    })
for s in scenarios:
    print(f"price={s['price']} margin={s['margin']} margin_pct={s['margin_pct']}% "
          f"breakeven={s['breakeven_units']} monthly_profit={s['monthly_profit']}")
"""
        sweep = run_calculation(
            sweep_code,
            inputs={
                "unit_cost": unit_cost,
                "fixed_costs": fixed_costs,
                "expected_units": expected_units,
            },
        )
        bus.emit(
            session_id,
            kind="tool_call",
            actor=self.name,
            summary=f"sandboxed price sweep {'ok' if sweep.ok else 'failed'}",
            payload={"ok": sweep.ok, "error": sweep.error},
            level="info" if sweep.ok else "warning",
        )

        prompt = f"""PRODUCT: {product_name}
CURRENCY: {settings.currency}
MARKET: {settings.location}

INPUTS
- Unit cost: {unit_cost}
- Competitor price band (from the Market Research agent): {price_low} - {price_high}
- Fixed monthly costs: {fixed_costs}
- Expected monthly units: {expected_units or 'not supplied by owner'}

COMPUTED METRICS AT A PROVISIONAL PRICE OF {provisional:.2f} (executed in Python)
{self.as_json(base)}

PRICE SCENARIO SWEEP (executed in the sandbox)
{sweep.summary()}

{self.context_block(state, f"pricing competitor cost margin {product_name}")}

Choose the recommended selling price and justify it. Fill every numeric field using
the computed metrics for the price you actually choose — recompute proportionally if
you pick a price not in the sweep."""

        result = self.ask(state, PricingResult, SYSTEM, prompt)

        # Recompute authoritatively at the model's chosen price — the model
        # explains the decision, Python owns the arithmetic.
        final = margin_analysis(
            unit_cost or result.unit_cost,
            result.recommended_price,
            fixed_costs,
            expected_units,
        )
        result.unit_cost = final["unit_cost"]
        result.unit_margin = final["unit_margin"]
        result.margin_pct = final["margin_pct"]
        result.breakeven_units = final["breakeven_units"]
        result.projected_monthly_profit = final["projected_monthly_profit"]
        result.calculation_log = sweep.summary()[:2000]

        self._persist(product_name, result)
        self.remember(
            state,
            (
                f"Pricing decision for {product_name}: sell at {result.recommended_price} "
                f"{settings.currency} on unit cost {result.unit_cost}. Margin "
                f"{result.margin_pct}% ({result.unit_margin} per unit). Break-even "
                f"{result.breakeven_units} units. {result.rationale}"
            ),
            kind="pricing",
            extra={"product": product_name, "price": result.recommended_price},
        )

        return AgentResult(
            summary=(
                f"Price **{result.recommended_price:.0f} {settings.currency}** for "
                f"{product_name} on a {result.unit_cost:.0f} unit cost — "
                f"{result.margin_pct:.1f}% margin, break-even at "
                f"{result.breakeven_units:.0f} units. {result.rationale}"
            ),
            payload=result.model_dump(),
        )

    # --- helpers ---

    def _gather_inputs(
        self, state: WorkforceState, outputs: dict
    ) -> tuple[str, float, float, float]:
        """Pull cost and competitor band from upstream agents, then memory, then defaults."""
        product_name = "the product"
        unit_cost = 0.0
        low = high = 0.0

        vision = (outputs.get("product_vision") or {}).get("payload") or {}
        if vision:
            product_name = vision.get("product_name") or product_name
            unit_cost = float(vision.get("estimated_unit_cost") or 0)
            low = float(vision.get("suggested_price_low") or 0)
            high = float(vision.get("suggested_price_high") or 0)

        research = (outputs.get("market_research") or {}).get("payload") or {}
        if research:
            low = float(research.get("competitor_price_low") or low)
            high = float(research.get("competitor_price_high") or high)
            if product_name == "the product":
                product_name = research.get("recommended_niche") or product_name

        ctx = state.get("owner_context", {})
        unit_cost = float(ctx.get("unit_cost") or unit_cost)

        if not unit_cost:
            # Fall back to the catalog, which earlier sessions may have populated.
            from ..memory import memory

            for row in memory.products():
                if row["name"] == product_name and row.get("unit_cost"):
                    unit_cost = float(row["unit_cost"])
                    break

        if not unit_cost:
            unit_cost = max(1.0, (low or 100.0) * 0.45)  # assume ~45% cost ratio

        return product_name, unit_cost, low, high

    def _persist(self, product_name: str, result: PricingResult) -> None:
        from ..memory import memory

        # A price for something the shop does not sell is advice, not stock.
        # create=False keeps a recommendation out of the catalogue until the
        # owner actually records the product.
        product_id = memory.db.upsert_product(
            name=product_name,
            unit_cost=result.unit_cost,
            sell_price=result.recommended_price,
            source_agent=self.name,
            create=False,
        )
        if product_id is None:
            return
        memory.db.record_pricing(
            product_id=product_id,
            unit_cost=result.unit_cost,
            sell_price=result.recommended_price,
            margin_pct=result.margin_pct,
            breakeven_units=result.breakeven_units,
            rationale=result.rationale,
        )
