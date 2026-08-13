"""Token accounting and USD cost estimation.

Rates are Anthropic first-party list prices in USD per 1M tokens. Cached reads
bill at ~0.1x input and cache writes at ~1.25x input, which we model explicitly
so the UI's running cost tracks reality rather than a flat approximation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# USD per 1,000,000 tokens: model id -> (input, output)
MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25

_FALLBACK_RATE = (5.00, 25.00)


def rates_for(model: str) -> tuple[float, float]:
    """Look up (input, output) rate, tolerating alias/date-suffixed IDs."""
    if model in MODEL_RATES:
        return MODEL_RATES[model]
    for known, rate in MODEL_RATES.items():
        if model.startswith(known):
            return rate
    return _FALLBACK_RATE


def estimate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """USD cost of a single call. `input_tokens` must exclude cached tokens."""
    in_rate, out_rate = rates_for(model)
    return (
        input_tokens * in_rate
        + cache_read_tokens * in_rate * CACHE_READ_MULTIPLIER
        + cache_write_tokens * in_rate * CACHE_WRITE_MULTIPLIER
        + output_tokens * out_rate
    ) / 1_000_000


@dataclass
class CallUsage:
    """Token usage for one LLM call, attributed to the agent that made it."""

    agent: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def cost_usd(self) -> float:
        return estimate_cost(
            self.model,
            self.input_tokens,
            self.output_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        )


@dataclass
class UsageLedger:
    """Running per-session token/cost tally, broken down by agent."""

    calls: list[CallUsage] = field(default_factory=list)

    def record(self, usage: CallUsage) -> CallUsage:
        self.calls.append(usage)
        return usage

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.calls)

    def by_agent(self) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for c in self.calls:
            row = out.setdefault(
                c.agent,
                {"calls": 0, "input": 0, "output": 0, "cached": 0, "cost_usd": 0.0},
            )
            row["calls"] += 1
            row["input"] += c.input_tokens
            row["output"] += c.output_tokens
            row["cached"] += c.cache_read_tokens + c.cache_write_tokens
            row["cost_usd"] += c.cost_usd
        return out


def extract_usage(agent: str, model: str, response) -> CallUsage:
    """Pull token counts off a LangChain AIMessage.

    `usage_metadata` is the normalised LangChain shape; `response_metadata`
    carries the raw Anthropic `usage` block including the cache fields, which
    LangChain nests under `input_token_details`.
    """
    meta = getattr(response, "usage_metadata", None) or {}
    details = meta.get("input_token_details") or {}

    cache_read = int(details.get("cache_read", 0) or 0)
    cache_write = int(details.get("cache_creation", 0) or 0)

    if not meta:
        raw = (getattr(response, "response_metadata", None) or {}).get("usage", {})
        return CallUsage(
            agent=agent,
            model=model,
            input_tokens=int(raw.get("input_tokens", 0) or 0),
            output_tokens=int(raw.get("output_tokens", 0) or 0),
            cache_read_tokens=int(raw.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(raw.get("cache_creation_input_tokens", 0) or 0),
        )

    # LangChain folds cached tokens into input_tokens; subtract to avoid
    # double-billing them at the full input rate.
    uncached_input = max(0, int(meta.get("input_tokens", 0) or 0) - cache_read - cache_write)

    return CallUsage(
        agent=agent,
        model=model,
        input_tokens=uncached_input,
        output_tokens=int(meta.get("output_tokens", 0) or 0),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )
