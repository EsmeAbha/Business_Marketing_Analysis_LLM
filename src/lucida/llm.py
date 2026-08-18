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

from pydantic import SecretStr

from .config import TEXT_DEFAULTS, settings
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


def _secret(api_key: str) -> SecretStr:
    """Keys are declared as SecretStr so they cannot be printed by accident.

    The value is the same either way at runtime; wrapping it is what stops a
    stray log line or traceback from carrying the owner's key with it.
    """
    return SecretStr(api_key)


def _build_groq(model: str, max_tokens: int, api_key: str):
    from langchain_groq import ChatGroq

    return ChatGroq(
        model=model,
        max_tokens=max_tokens,
        api_key=_secret(api_key),
        temperature=settings.temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.max_retries,
    )


def _build_anthropic(model: str, max_tokens: int, api_key: str):
    from langchain_anthropic import ChatAnthropic

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "api_key": _secret(api_key),
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


# Gemini 3 thinks before it answers and charges the thinking to the same
# output budget — a 200-token cap was spent entirely on reasoning and came
# back empty. The budget cannot be switched off, so it has to be paid for.
GOOGLE_THINKING_FLOOR = 3000


def _build_google(model: str, max_tokens: int, api_key: str):
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        max_output_tokens=max(max_tokens, GOOGLE_THINKING_FLOOR),
        google_api_key=_secret(api_key),
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
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
)


def is_rate_limited(exc: Exception) -> bool:
    text = str(exc).lower()
    return "rate_limit" in text or "429" in text or "rate limit" in text


def is_gone(exc: Exception) -> bool:
    """The model was retired, or this key was never allowed to use it.

    Providers decommission models without warning — `llama-3.3-70b-versatile`
    started 404ing mid-project — and that used to kill the whole run, because
    only a rate limit moved the chain along. A model that is not there is
    every bit as unusable as one that is busy, so it is treated the same.
    """
    text = str(exc).lower()
    return ("does not exist" in text or "model_not_found" in text
            or "decommission" in text
            or ("404" in text and "model" in text))


def is_flaky_tool_call(exc: Exception) -> bool:
    """The model wrote the right answer but not as a tool call.

    Groq enforces tool choice server-side and rejects the reply when the
    model emits the JSON as plain text instead. It is intermittent — the
    same model and prompt succeed on a retry — so it should cost one hop
    down the chain, not the whole run.
    """
    return "tool_use_failed" in str(exc)


def should_try_next(exc: Exception) -> bool:
    return is_rate_limited(exc) or is_gone(exc) or is_flaky_tool_call(exc)


def retry_after(exc: Exception) -> str:
    """The wait the provider asked for, as it wrote it. '' when it did not."""
    m = re.search(r"try again in ([0-9hms\.]+)", str(exc))
    return m.group(1) if m else ""


def _why(exc: Exception) -> str:
    if is_gone(exc):
        return "has been retired"
    if is_flaky_tool_call(exc):
        return "did not answer as a tool call"
    return "is over its cap"


class AllModelsBusy(ProviderError):
    """Every model we can reach is over its cap.

    Carries the wait so the caller can tell the owner when to come back
    rather than making them read a provider traceback.
    """

    def __init__(self, wait: str = "") -> None:
        self.wait = wait
        # Only suggest the key the owner has not already added, or the advice
        # reads as though the app has not noticed what they did.
        more = (" Wait it out, or add a paid key to keep going."
                if settings.google_api_key else
                " Wait it out, or add a free GOOGLE_API_KEY from"
                " aistudio.google.com/apikey in .env to keep going.")
        super().__init__(
            "Every model we can reach is over its cap"
            + (f" — the next resets in about {wait}." if wait else ".")
            + " Nothing is broken; the models are just rationed." + more
        )


def _chain(chosen: str) -> list[tuple[str, str]]:
    """Every (provider, model) worth trying, in the order to try them.

    Groq's caps are per-model and per-day, so one being exhausted says nothing
    about the next. When the whole of Groq is spent, a Google key — if the
    owner has added one for photo reading — keeps the shop working rather
    than closing it until tomorrow.
    """
    chain = [("groq", chosen)]
    chain += [("groq", m) for m in GROQ_FALLBACKS if m != chosen]
    if settings.google_api_key:
        chain.append(("google", TEXT_DEFAULTS["google"][0]))
    return chain


class _Failover:
    """A client that moves to the next model when one is capped.

    Wraps rather than subclasses because each provider returns its own client
    type, and the only thing every caller uses is `.invoke`.
    """

    def __init__(self, models: list[tuple[str, str]], max_tokens: int) -> None:
        self._models = models
        self._max_tokens = max_tokens

    def invoke(self, *args, **kwargs):
        last: Exception | None = None
        for i, (provider, model) in enumerate(self._models):
            try:
                return build_client(provider, model,
                                    self._max_tokens).invoke(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                if not should_try_next(exc):
                    raise
                last = exc
                if i + 1 < len(self._models):
                    logger.warning("%s %s; trying %s", model, _why(exc),
                                   self._models[i + 1][1])
        raise AllModelsBusy(retry_after(last) if last else "")

    def with_structured_output(self, *args, **kwargs):
        """Structured calls fail over too — that is most of the agent work."""
        outer = self

        class _Structured:
            def invoke(self, *a, **kw):
                last: Exception | None = None
                for i, (provider, model) in enumerate(outer._models):
                    try:
                        client = build_client(provider, model,
                                              outer._max_tokens)
                        return client.with_structured_output(
                            *args, **kwargs).invoke(*a, **kw)
                    except Exception as exc:  # noqa: BLE001
                        if not should_try_next(exc):
                            raise
                        last = exc
                        if i + 1 < len(outer._models):
                            logger.warning(
                                "%s %s; trying %s", model, _why(exc),
                                outer._models[i + 1][1])
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
        return _Failover(_chain(chosen), budget)
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


def text_of(reply) -> str:
    """The words out of a reply, whatever shape the provider returned.

    Gemini 3 and recent Claude models return a list of content blocks with
    the thinking in front of the answer; older models return a plain string.
    Stringifying the list prints Python repr at the owner, so flatten it.
    """
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        content = "".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(content).strip()


def active_model_name(client) -> str:
    """Best-effort model id for usage accounting, across provider classes."""
    for attr in ("model", "model_name", "model_id"):
        value = getattr(client, attr, None)
        if isinstance(value, str) and value:
            return value
    return "unknown"
