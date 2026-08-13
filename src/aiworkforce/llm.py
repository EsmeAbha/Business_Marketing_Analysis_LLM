"""LLM factory — one place builds every model client.

Three providers are supported. Keeping construction here means the agents never
know which one is active, and switching providers is a single `.env` change
rather than an edit to eight agent modules.

Parameter handling differs per provider, and getting it wrong is a hard error:
  * Groq / Google accept `temperature`.
  * Recent Claude models REJECT `temperature`/`top_p`/`top_k` and explicit
    thinking budgets; reasoning depth is set via `output_config.effort` instead.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import settings
from .observability import get_logger

logger = get_logger("llm")


class ProviderError(RuntimeError):
    """Raised when the configured provider cannot be constructed."""


# Claude models that reject sampling params and `budget_tokens` thinking config.
_CLAUDE_NO_SAMPLING = (
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-fable-5",
    "claude-mythos-5",
    "claude-sonnet-5",
)

_CLAUDE_EFFORT = _CLAUDE_NO_SAMPLING + (
    "claude-opus-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-6",
)


def _build_groq(model: str, max_tokens: int, api_key: str):
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        max_tokens=max_tokens,
        api_key=api_key,
        temperature=settings.temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


def _build_anthropic(model: str, max_tokens: int, api_key: str):
    from langchain_anthropic import ChatAnthropic

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "api_key": api_key,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": 2,
    }
    if model.startswith(_CLAUDE_EFFORT):
        # `effort` lives inside output_config, not at the top level. Thinking is
        # left unconfigured: it is adaptive by default on current models, and an
        # explicit budget is a 400.
        kwargs["model_kwargs"] = {"output_config": {"effort": settings.effort}}
    if not model.startswith(_CLAUDE_NO_SAMPLING):
        kwargs["temperature"] = settings.temperature
    return ChatAnthropic(**kwargs)


def _build_google(model: str, max_tokens: int, api_key: str):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        max_output_tokens=max_tokens,
        google_api_key=api_key,
        temperature=settings.temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    )


_BUILDERS = {
    "groq": _build_groq,
    "anthropic": _build_anthropic,
    "google": _build_google,
}

_INSTALL_HINT = {
    "groq": "pip install langchain-groq",
    "anthropic": "pip install langchain-anthropic",
    "google": "pip install langchain-google-genai",
}


@lru_cache(maxsize=12)
def build_client(provider: str, model: str, max_tokens: int):
    """Construct (and cache) a chat client for an explicit provider + model."""
    provider = (provider or "").lower()
    builder = _BUILDERS.get(provider)
    if builder is None:
        raise ProviderError(
            f"unknown provider {provider!r}; expected one of {sorted(_BUILDERS)}"
        )

    api_key = settings.key_for(provider)
    if not api_key:
        raise ProviderError(
            f"no API key for provider {provider!r}. Add {provider.upper()}_API_KEY "
            "to your .env file."
        )
    if not model:
        raise ProviderError(f"no model configured for provider {provider!r}")

    try:
        client = builder(model, max_tokens, api_key)
    except ImportError as exc:
        raise ProviderError(
            f"{provider} support is not installed — run: {_INSTALL_HINT[provider]}"
        ) from exc

    logger.info("built %s client model=%s max_tokens=%s", provider, model, max_tokens)
    return client


def get_llm(model: str | None = None, max_tokens: int | None = None):
    """The main text client used by the supervisor and every text agent."""
    return build_client(
        settings.provider, model or settings.model, max_tokens or settings.max_tokens
    )


def get_fast_llm(max_tokens: int = 2000):
    """Cheaper/faster client for routing- and classification-shaped calls."""
    return build_client(settings.provider, settings.fast_model, max_tokens)


def get_vision_llm(max_tokens: int | None = None):
    """Multimodal client for the Product Vision agent.

    May be a different provider from the text agents — Groq currently serves no
    vision model, so photo understanding falls to Google or Anthropic.
    """
    if not settings.has_vision:
        raise ProviderError(settings.vision_help)
    return build_client(
        settings.vision_provider,
        settings.vision_model,
        max_tokens or settings.max_tokens,
    )


def active_model_name(client) -> str:
    """Best-effort model id for usage accounting, across provider classes."""
    for attr in ("model", "model_name", "model_id"):
        value = getattr(client, attr, None)
        if isinstance(value, str) and value:
            return value
    return "unknown"
