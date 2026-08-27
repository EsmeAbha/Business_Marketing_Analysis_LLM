"""Market Research Agent — finds low-competition, high-demand niches.

Runs several real web searches (competitors, demand, pricing, local signals),
feeds the evidence to Claude, and returns a ranked niche recommendation with a
competitor price band that the Pricing agent consumes directly.
"""

from __future__ import annotations

from ..config import settings
from ..observability import bus
from ..state import WorkforceState
from ..tools.web_search import web_search
from .base import AgentResult, BaseAgent
from .schemas import MarketResearchResult

SYSTEM = """You are the Market Research Agent in an AI workforce running a real small business.

Your job: identify what the owner should sell, backed by evidence from the search
results supplied to you — not from memory or assumption.

Rules:
- Ground every demand and competition claim in the supplied search results. If the
  evidence is thin, say so in `key_risks` rather than inventing confidence.
- Prefer niches with genuine demand signals and beatable competition over trendy ones.
- `competitor_price_low` / `competitor_price_high` must be a realistic band in the
  owner's local currency. If the searches surfaced no prices, estimate from the
  closest comparable and flag the assumption in `summary`.
- Consider local buying power, delivery logistics, and perishability where relevant.
- Be concrete. "Homemade frozen paratha for working families in Dhaka" beats "food".

Sourcing and demand — the owner has to act on this, so it must be practical:
- `where_to_buy` must name real, local places a person can reach: a named wholesale
  market, a bazar, a supplier type. "Karwan Bazar for vegetables" is useful;
  "a local supplier" is not. If the evidence names none, say so in `note` rather
  than inventing a company.
- `demand_level` is one of high, steady, seasonal or low, and must cite what in the
  evidence supports it.
- `suggested_first_order` is a number of units and the reason. Err small: a first
  order the owner can afford to be wrong about is worth more than an optimal one.
- `restock_signal` is the observable thing that should trigger a bigger order —
  for example selling out inside a week, or repeat buyers.
"""


class MarketResearchAgent(BaseAgent):
    name = "market_research"
    title = "Market Research Agent"
    description = (
        "Scans the web for niche demand, competitor density and price bands, then "
        "recommends what the owner should sell."
    )
    tools_used = ("web search", "shared memory (RAG)")

    def execute(self, state: WorkforceState) -> AgentResult:
        session_id = state.get("session_id", "")
        owner_input = state.get("owner_input", "")
        task = state.get("current_task", owner_input)
        location = (
            state.get("owner_context", {}).get("location")
            or (self._profile_location())
            or settings.location
        )

        queries = self._build_queries(task or owner_input, location)
        evidence: list[str] = []
        sources: list[str] = []
        simulated_any = False

        for q in queries:
            resp = web_search(q, max_results=5)
            simulated_any = simulated_any or resp.simulated
            evidence.append(resp.as_prompt_context(limit=5))
            sources.extend(r.url for r in resp.results if r.url)
            bus.emit(
                session_id,
                kind="tool_call",
                actor=self.name,
                summary=f"web_search({q!r}) -> {len(resp.results)} results via {resp.provider}",
                payload={"provider": resp.provider, "simulated": resp.simulated},
                level="warning" if resp.simulated else "info",
            )

        prompt = f"""OWNER REQUEST
{owner_input}

SPECIFIC TASK FROM SUPERVISOR
{task}

MARKET LOCATION: {location}
CURRENCY: {settings.currency}

{self.context_block(state, f"market research niche demand competition {task}")}

=== WEB SEARCH EVIDENCE ===
{chr(10).join(evidence)}
=== END EVIDENCE ===

Produce a market research result. Recommend ONE niche, with 2-3 alternatives ranked
below it. Ground your reasoning in the evidence above."""

        result = self.ask(state, MarketResearchResult, SYSTEM, prompt)

        # Publish to shared memory so Pricing, Ads and Reporting can retrieve it later.
        self.remember(
            state,
            (
                f"Market research recommendation: {result.recommended_niche}. "
                f"{result.summary} Competitor price band: "
                f"{result.competitor_price_low}-{result.competitor_price_high} {settings.currency}. "
                f"Key risks: {'; '.join(result.key_risks)}. "
                f"Demand: {result.demand_level}. "
                f"Where to buy: "
                f"{'; '.join(o.where for o in result.where_to_buy) or 'not established'}. "
                f"Suggested first order: {result.suggested_first_order}"
            ),
            kind="market_research",
            extra={
                "niche": result.recommended_niche,
                "price_low": result.competitor_price_low,
                "price_high": result.competitor_price_high,
            },
        )

        # The recommended niche becomes part of the durable business profile.
        self._persist_profile(result.recommended_niche, location)

        summary = (
            f"Recommends **{result.recommended_niche}**. {result.summary} "
            f"Competitor prices run {result.competitor_price_low:.0f}–"
            f"{result.competitor_price_high:.0f} {settings.currency}."
        )
        if result.demand_level:
            summary += f" Demand looks **{result.demand_level}**."
        if result.where_to_buy:
            places = "; ".join(
                f"{o.where}" + (f" ({o.typical_cost})" if o.typical_cost else "")
                for o in result.where_to_buy[:3])
            summary += f" 🛒 Buy from: {places}."
        if result.suggested_first_order:
            summary += f" First order: {result.suggested_first_order}"
        if simulated_any:
            summary += " (Some evidence came from the SIMULATED search adapter.)"

        return AgentResult(
            summary=summary,
            payload={
                **result.model_dump(),
                "sources": sources[:20],
                "search_simulated": simulated_any,
                "location": location,
            },
        )

    # --- helpers ---

    def _build_queries(self, topic: str, location: str) -> list[str]:
        """Fewer, broader queries when the provider has a tight token budget."""
        topic = (topic or "small business").strip()
        queries = [
            f"{topic} business {location} demand 2026",
            f"{topic} competitors {location} price",
            # Where to buy is a different question from who is selling, and the
            # owner cannot start without an answer to it.
            f"{topic} wholesale market {location} where to buy bulk price",
            f"best selling {topic} products online {location}",
            f"{topic} profit margin startup cost small business",
        ]
        return queries[:3] if settings.compact_prompts else queries

    def _profile_location(self) -> str:
        from ..memory import memory

        return (memory.profile() or {}).get("location") or ""

    def _persist_profile(self, niche: str, location: str) -> None:
        from ..memory import memory

        memory.set_profile(niche=niche, location=location, currency=settings.currency)
