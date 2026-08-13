"""LLM factory.

One place builds every Claude client so model IDs, effort, and the parameters
that current models reject (temperature / top_p / top_k, and explicit thinking
budgets) are handled consistently.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from .config import settings
from .observability import get_logger

logger = get_logger("llm")

# Models that reject temperature/top_p/top_k and `budget_tokens` thinking config.
# On these, reasoning depth is controlled by `output_config.effort` instead.
_NO_SAMPLING_PARAMS = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-fable-5",
    "claude-mythos-5",
    "claude-sonnet-5",
)


def _supports_effort(model: str) -> bool:
    return model.startswith(
        (
            "claude-opus-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-opus-4-5",
            "claude-sonnet-5",
            "claude-sonnet-4-6",
            "claude-fable-5",
            "claude-mythos-5",
        )
    )


def _rejects_sampling(model: str) -> bool:
    return model.startswith(_NO_SAMPLING_PARAMS)


@lru_cache(maxsize=8)
def get_llm(model: str | None = None, max_tokens: int | None = None) -> ChatAnthropic:
    """Build (and cache) a Claude client.

    Thinking is deliberately left unconfigured: on Claude Opus 5 adaptive
    thinking is the default, and passing an explicit thinking budget is a 400.
    `max_tokens` therefore needs headroom, because it caps thinking + response
    text together.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    model_id = model or settings.model
    tokens = max_tokens or settings.max_tokens

    kwargs: dict = {
        "model": model_id,
        "max_tokens": tokens,
        "api_key": settings.anthropic_api_key,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": 2,
    }

    if _supports_effort(model_id):
        # `effort` lives inside output_config, not at the top level.
        kwargs["model_kwargs"] = {"output_config": {"effort": settings.effort}}
    elif not _rejects_sampling(model_id):
        kwargs["temperature"] = 0.3

    logger.info("building client model=%s max_tokens=%s", model_id, tokens)
    return ChatAnthropic(**kwargs)


def get_fast_llm(max_tokens: int = 2000) -> ChatAnthropic:
    """Cheaper client for routing/classification-shaped calls."""
    return get_llm(settings.fast_model, max_tokens)
