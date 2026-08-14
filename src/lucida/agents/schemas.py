"""Structured outputs every agent produces.

Agents return validated Pydantic objects rather than free text, which is what
lets one agent consume another's result programmatically — Market Research's
`competitor_price_range` flows straight into the Pricing agent's inputs.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Supervisor ------------------------------------------------------------


class RoutingDecision(BaseModel):
    """The supervisor's choice of who works next."""

    next_agent: str = Field(
        description=(
            "Exactly one of: market_research, product_vision, pricing, inventory, "
            "ad_creative, engagement, delivery, reporting, FINISH"
        )
    )
    task: str = Field(description="The specific task to hand that agent, in one or two sentences.")
    reason: str = Field(description="Why this agent, now. One sentence.")
    stage: str = Field(
        description=(
            "Current lifecycle stage: idea_research, product_validation, owner_decision, "
            "inventory_setup, marketing_launch, customer_engagement, reporting, delivery, complete"
        )
    )


class WorkPlan(BaseModel):
    """The supervisor's up-front plan, shown to the owner before work starts."""

    goal: str = Field(description="What the owner is actually trying to achieve.")
    steps: list[str] = Field(description="3-6 ordered steps naming the agent responsible for each.")
    stage: str = Field(description="The lifecycle stage this request starts from.")


# --- Market Research -------------------------------------------------------


class NicheOption(BaseModel):
    name: str
    rationale: str
    demand_signal: str = Field(description="Evidence of demand, citing what was found in search.")
    competition_level: str = Field(description="low | medium | high")
    startup_cost_estimate: str
    estimated_margin_pct: float = Field(default=0.0, description="Best estimate of gross margin %.")


class MarketResearchResult(BaseModel):
    summary: str
    recommended_niche: str
    options: list[NicheOption] = Field(default_factory=list)
    competitor_price_low: float = Field(default=0.0)
    competitor_price_high: float = Field(default=0.0)
    key_risks: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)


# --- Product Vision --------------------------------------------------------


class ProductVisionResult(BaseModel):
    product_name: str
    category: str
    description: str = Field(description="What is visible in the photo, factually.")
    estimated_unit_cost: float = Field(default=0.0)
    suggested_price_low: float = Field(default=0.0)
    suggested_price_high: float = Field(default=0.0)
    demand_assessment: str
    quality_notes: str = Field(default="", description="Presentation/packaging issues visible.")
    recommendation: str = Field(description="GO, NO-GO or CONDITIONAL")
    reasoning: str


# --- Pricing ---------------------------------------------------------------


class PricingResult(BaseModel):
    product_name: str
    unit_cost: float
    recommended_price: float
    unit_margin: float = 0.0
    margin_pct: float = 0.0
    breakeven_units: float = 0.0
    projected_monthly_profit: float = 0.0
    competitor_comparison: str = ""
    rationale: str = ""
    calculation_log: str = Field(default="", description="Output of the executed calculation.")


# --- Inventory -------------------------------------------------------------


class InventoryItem(BaseModel):
    product_name: str
    quantity: int
    unit_cost: float = 0.0
    reorder_level: int = 5


class InventoryResult(BaseModel):
    summary: str
    items_recorded: list[InventoryItem] = Field(default_factory=list)
    low_stock_alerts: list[str] = Field(default_factory=list)
    total_stock_value: float = 0.0
    restock_advice: str = ""


# --- Ad Creation -----------------------------------------------------------


class AdCreative(BaseModel):
    platform: str = Field(description="facebook | instagram | youtube")
    headline: str
    body: str
    call_to_action: str
    hashtags: list[str] = Field(default_factory=list)
    visual_direction: str = Field(default="", description="What the image/video should show.")


class AdCreativeResult(BaseModel):
    summary: str
    creatives: list[AdCreative] = Field(default_factory=list)
    target_audience: str = ""
    suggested_budget: str = ""
    publish_results: list[str] = Field(default_factory=list)


# --- Customer Engagement ---------------------------------------------------


class AnalysedMessage(BaseModel):
    customer: str
    channel: str
    message: str
    sentiment: str = Field(description="positive | neutral | negative")
    intent: str = Field(description="preorder | question | complaint | unmet_demand | praise | other")
    requested_item: str = Field(default="", description="Product asked for but not offered, if any.")
    suggested_reply: str = ""


class EngagementResult(BaseModel):
    summary: str
    analysed: list[AnalysedMessage] = Field(default_factory=list)
    sentiment_breakdown: dict[str, int] = Field(default_factory=dict)
    preorders_found: int = 0
    unmet_demand: list[str] = Field(default_factory=list)
    urgent_issues: list[str] = Field(default_factory=list)


# --- Delivery --------------------------------------------------------------


class DeliveryResultModel(BaseModel):
    summary: str
    provider: str = ""
    consignment_id: str = ""
    tracking_code: str = ""
    status: str = ""
    eta: str = ""
    cod_amount: float = 0.0
    simulated: bool = True


# --- Reporting -------------------------------------------------------------


class ReportingResult(BaseModel):
    title: str
    executive_summary: str
    stock_alerts: list[str] = Field(default_factory=list)
    demand_shifts: list[str] = Field(default_factory=list)
    financials: str = ""
    revised_plan: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    full_report_markdown: str = ""
