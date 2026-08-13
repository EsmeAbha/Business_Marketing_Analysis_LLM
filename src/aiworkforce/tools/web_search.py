"""Web search with graceful degradation.

Tavily (best quality, needs a key) -> DuckDuckGo via `ddgs` (free, no key) ->
a labelled simulated adapter so a demo never hard-fails offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import settings
from ..observability import get_logger

logger = get_logger("tools.web_search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


@dataclass
class SearchResponse:
    query: str
    provider: str          # "tavily" | "duckduckgo" | "simulated"
    simulated: bool
    results: list[SearchResult] = field(default_factory=list)
    error: str = ""

    def as_prompt_context(self, limit: int = 8, snippet: int | None = None) -> str:
        """Format for prompt injection, trimmed to the provider's token budget."""
        from ..config import settings

        if settings.compact_prompts:
            limit = min(limit, 3)
            snippet = snippet or 220
        snippet = snippet or 400

        if not self.results:
            return f"(no results for '{self.query}'{'; ' + self.error if self.error else ''})"
        header = f"Search results for '{self.query}' via {self.provider}"
        if self.simulated:
            header += "  [SIMULATED — no live search provider available]"
        lines = [header]
        for i, r in enumerate(self.results[:limit], 1):
            lines.append(f"{i}. {r.title}\n   {r.url}\n   {r.snippet[:snippet]}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider": self.provider,
            "simulated": self.simulated,
            "error": self.error,
            "results": [r.__dict__ for r in self.results],
        }


def _search_tavily(query: str, max_results: int) -> SearchResponse:
    from tavily import TavilyClient  # imported lazily; optional dependency

    client = TavilyClient(api_key=settings.tavily_api_key)
    raw = client.search(query=query, max_results=max_results, search_depth="advanced")
    results = [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
            source="tavily",
        )
        for item in raw.get("results", [])
    ]
    return SearchResponse(query=query, provider="tavily", simulated=False, results=results)


def _search_duckduckgo(query: str, max_results: int) -> SearchResponse:
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS  # type: ignore[no-redef]

    results: list[SearchResult] = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=max_results):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("href") or item.get("url", ""),
                    snippet=item.get("body", ""),
                    source="duckduckgo",
                )
            )
    return SearchResponse(
        query=query, provider="duckduckgo", simulated=False, results=results
    )


def _search_simulated(query: str, note: str) -> SearchResponse:
    """Last resort. Explicitly labelled so nothing downstream mistakes it for real data."""
    canned = [
        SearchResult(
            title=f"[SIMULATED] Market overview: {query}",
            url="https://example.invalid/market-overview",
            snippet=(
                "Simulated result. No live search provider was reachable, so this "
                "placeholder stands in for competitor and demand data. Treat any "
                "conclusion drawn from it as unverified."
            ),
            source="simulated",
        ),
        SearchResult(
            title=f"[SIMULATED] Pricing signals: {query}",
            url="https://example.invalid/pricing",
            snippet="Simulated pricing snippet — no real competitor prices retrieved.",
            source="simulated",
        ),
    ]
    return SearchResponse(
        query=query,
        provider="simulated",
        simulated=True,
        results=canned,
        error=note,
    )


def web_search(query: str, max_results: int = 6) -> SearchResponse:
    """Run a search, trying each provider in order of quality."""
    query = (query or "").strip()
    if not query:
        return SearchResponse(query="", provider="none", simulated=True, error="empty query")

    if settings.has_tavily:
        try:
            resp = _search_tavily(query, max_results)
            logger.info("tavily returned %d results for %r", len(resp.results), query)
            return resp
        except Exception as exc:  # noqa: BLE001 — fall through to next provider
            logger.warning("tavily failed (%s), falling back to duckduckgo", exc)

    try:
        resp = _search_duckduckgo(query, max_results)
        if resp.results:
            logger.info("duckduckgo returned %d results for %r", len(resp.results), query)
            return resp
        logger.warning("duckduckgo returned no results for %r", query)
    except Exception as exc:  # noqa: BLE001
        logger.warning("duckduckgo failed (%s), using simulated search", exc)
        return _search_simulated(query, f"duckduckgo error: {exc}")

    return _search_simulated(query, "no results from any live provider")
