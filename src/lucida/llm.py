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

import re
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
        max_retries=settings.max_retries,
    )


def _build_anthropic(model: str, max_tokens: int, api_key: str):
    from langchain_anthropic import ChatAnthropic

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "api_key": api_key,
        "timeout": settings.llm_timeout_seconds,
        "max_retries": settings.max_retries,
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
        max_retries=settings.max_retries,
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


# Groq meters each model separately, so a daily cap on one says nothing about
# the others. Ordered by capability: drop only as far as needed.
GROQ_FALLBACKS = (
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
)


def is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "rate_limit" in text or "429" in text or "rate limit" in text


def retry_after(exc: Exception) -> str:
    """The wait the provider asked for, as it wrote it. '' when it did not."""
    m = re.search(r"try again in ([0-9hms\.]+)", str(exc))
    return m.group(1) if m else ""


class AllModelsBusy(ProviderError):
    """Every model we can reach is over its cap.

    Carries the wait so the caller can tell the owner when to come back
    rather than making them read a provider traceback.
    """

    def __init__(self, wait: str = "") -> None:
        self.wait = wait
        super().__init__(
            "Your daily free allowance with Groq is used up"
            + (f" — it resets in about {wait}." if wait else ".")
            + " Nothing is broken; the model is just rationed. Wait it out, or"
              " add a paid key or a GOOGLE_API_KEY in .env to keep going."
        )


class _Failover:
    """A client that moves to the next model when one is capped.

    Wraps rather than subclasses because each provider returns its own client
    type, and the only thing every caller uses is `.invoke`.
    """

    def __init__(self, models: list[str], max_tokens: int) -> None:
        self._models = models
        self._max_tokens = max_tokens

    def invoke(self, *args, **kwargs):
        last: Exception | None = None
        for i, model in enumerate(self._models):
            try:
                return build_client(settings.provider, model,
                                    self._max_tokens).invoke(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                if not is_rate_limited(exc):
                    raise
                last = exc
                if i + 1 < len(self._models):
                    logger.warning("%s is over its daily cap; trying %s",
                                   model, self._models[i + 1])
        raise AllModelsBusy(retry_after(last) if last else "")

    def with_structured_output(self, *args, **kwargs):
        """Structured calls fail over too — that is most of the agent work."""
        outer = self

        class _Structured:
            def invoke(self, *a, **kw):
                last: Exception | None = None
                for i, model in enumerate(outer._models):
                    try:
                        client = build_client(settings.provider, model,
                                              outer._max_tokens)
                        return client.with_structured_output(
                            *args, **kwargs).invoke(*a, **kw)
                    except Exception as exc:  # noqa: BLE001
                        if not is_rate_limited(exc):
                            raise
                        last = exc
                        if i + 1 < len(outer._models):
                            logger.warning("%s is over its daily cap; trying %s",
                                           model, outer._models[i + 1])
                raise AllModelsBusy(retry_after(last) if last else "")

        return _Structured()


def get_llm(model: str | None = None, max_tokens: int | None = None):
    """The main text client used by the supervisor and every text agent.

    On Groq this fails over between models rather than surfacing a 429: the
    caps are per-model and per-day, so one being exhausted is not the same as
    having no model at all.
    """
    chosen = model or settings.model
    budget = max_tokens or settings.max_tokens

    if settings.provider == "groq":
        chain = [chosen] + [m for m in GROQ_FALLBACKS if m != chosen]
        return _Failover(chain, budget)
    return build_client(settings.provider, chosen, budget)


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
