"""The eight specialist agents coordinated by the Supervisor."""

from .ad_creative import AdCreativeAgent
from .base import AGENT_REGISTRY, BaseAgent
from .delivery import DeliveryAgent
from .engagement import EngagementAgent
from .inventory import InventoryAgent
from .market_research import MarketResearchAgent
from .pricing_agent import PricingAgent
from .product_vision import ProductVisionAgent
from .reporting import ReportingAgent


def build_agents() -> dict[str, BaseAgent]:
    """Instantiate every agent once, keyed by its routing name."""
    agents = [
        MarketResearchAgent(),
        ProductVisionAgent(),
        PricingAgent(),
        InventoryAgent(),
        AdCreativeAgent(),
        EngagementAgent(),
        DeliveryAgent(),
        ReportingAgent(),
    ]
    return {a.name: a for a in agents}


__all__ = [
    "BaseAgent",
    "AGENT_REGISTRY",
    "build_agents",
    "MarketResearchAgent",
    "ProductVisionAgent",
    "PricingAgent",
    "InventoryAgent",
    "AdCreativeAgent",
    "EngagementAgent",
    "DeliveryAgent",
    "ReportingAgent",
]
