"""Central configuration.

Every knob the system has lives here so agents never read os.environ directly.
Missing optional credentials are not an error — they flip the corresponding
integration into a clearly-labelled simulated adapter, or degrade the feature
with an honest message.

Two independent provider choices:
  * the TEXT provider runs the supervisor and the seven text agents
  * the VISION provider runs the Product Vision agent's photo understanding

They are separate because the fastest/cheapest text provider is not always
multimodal — Groq, for instance, currently serves no vision model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Trust the operating system's certificate store rather than only certifi's
# bundle. On machines where antivirus or a corporate proxy inspects TLS, the
# intercepting root CA is installed in the OS store but not in certifi, so
# every provider call fails with CERTIFICATE_VERIFY_FAILED — which surfaces
# confusingly as `APIConnectionError: Connection error`. Best-effort: if
# truststore isn't installed we carry on with the default bundle.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 — never block startup over this
    pass

# --- Filesystem layout -----------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
VECTOR_DIR = DATA_DIR / "vectors"
DB_PATH = DATA_DIR / "lucida.db"
CHECKPOINT_PATH = DATA_DIR / "checkpoints.db"
LOG_PATH = DATA_DIR / "lucida.log"

for _d in (DATA_DIR, UPLOAD_DIR, VECTOR_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# Sensible defaults per provider: (main model, fast/routing model).
#
# Groq's free tier enforces a tokens-per-minute cap *per model*, and the
# requested `max_tokens` counts toward it. Measured caps: llama-3.3-70b 12k TPM,
# gpt-oss-120b/20b and qwen 8k, llama-3.1-8b 6k. Main and routing therefore use
# different models on purpose — each gets its own bucket, roughly doubling
# throughput for a multi-agent run.
TEXT_DEFAULTS: dict[str, tuple[str, str]] = {
    "groq": ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
    "anthropic": ("claude-opus-5", "claude-haiku-4-5"),
    "google": ("gemini-2.0-flash", "gemini-2.0-flash-lite"),
}

# Per-provider output budget and retry policy. `max_tokens` is deliberately
# small on Groq: it is charged against the per-minute cap before a single
# prompt token is counted.
PROVIDER_LIMITS: dict[str, dict[str, int]] = {
    "groq": {"max_tokens": 2500, "report_tokens": 4000, "retries": 6, "compact": 1},
    "anthropic": {"max_tokens": 8000, "report_tokens": 12000, "retries": 2, "compact": 0},
    "google": {"max_tokens": 8000, "report_tokens": 12000, "retries": 3, "compact": 0},
}

VISION_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-opus-5",
    "google": "gemini-2.0-flash",
    "groq": "",  # no multimodal model currently served
}


@dataclass(frozen=True)
class Settings:
    # --- Provider selection ---
    provider: str = field(default_factory=lambda: _env("AIW_PROVIDER", "groq").lower())

    # --- API keys ---
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    google_api_key: str = field(default_factory=lambda: _env("GOOGLE_API_KEY"))

    # --- Model overrides (blank = provider default) ---
    model_override: str = field(default_factory=lambda: _env("AIW_MODEL"))
    fast_model_override: str = field(default_factory=lambda: _env("AIW_FAST_MODEL"))
    vision_provider_override: str = field(
        default_factory=lambda: _env("AIW_VISION_PROVIDER").lower()
    )
    vision_model_override: str = field(default_factory=lambda: _env("AIW_VISION_MODEL"))

    effort: str = field(default_factory=lambda: _env("AIW_EFFORT", "high"))
    temperature: float = 0.3

    # --- Tools ---
    tavily_api_key: str = field(default_factory=lambda: _env("TAVILY_API_KEY"))

    # --- Social publishing ---
    meta_access_token: str = field(default_factory=lambda: _env("META_ACCESS_TOKEN"))
    meta_page_id: str = field(default_factory=lambda: _env("META_PAGE_ID"))
    meta_ig_user_id: str = field(default_factory=lambda: _env("META_IG_USER_ID"))
    youtube_api_key: str = field(default_factory=lambda: _env("YOUTUBE_API_KEY"))

    # --- Courier ---
    pathao_client_id: str = field(default_factory=lambda: _env("PATHAO_CLIENT_ID"))
    pathao_client_secret: str = field(
        default_factory=lambda: _env("PATHAO_CLIENT_SECRET")
    )
    steadfast_api_key: str = field(default_factory=lambda: _env("STEADFAST_API_KEY"))
    steadfast_secret_key: str = field(
        default_factory=lambda: _env("STEADFAST_SECRET_KEY")
    )

    # --- Business defaults ---
    currency: str = field(default_factory=lambda: _env("AIW_DEFAULT_CURRENCY", "BDT"))
    location: str = field(
        default_factory=lambda: _env("AIW_DEFAULT_LOCATION", "Dhaka, Bangladesh")
    )

    # --- Runtime guards ---
    max_supervisor_steps: int = 18
    llm_timeout_seconds: float = 600.0

    # ------------------------------------------------------------------
    # Text provider
    # ------------------------------------------------------------------

    def key_for(self, provider: str) -> str:
        return {
            "groq": self.groq_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }.get(provider, "")

    @property
    def api_key(self) -> str:
        return self.key_for(self.provider)

    @property
    def model(self) -> str:
        return self.model_override or TEXT_DEFAULTS.get(self.provider, ("", ""))[0]

    @property
    def fast_model(self) -> str:
        return self.fast_model_override or TEXT_DEFAULTS.get(self.provider, ("", ""))[1]

    @property
    def has_llm(self) -> bool:
        return bool(self.api_key and self.model)

    # --- output budgets, tuned to the provider's rate limits ---

    def _limits(self) -> dict[str, int]:
        return PROVIDER_LIMITS.get(self.provider, PROVIDER_LIMITS["anthropic"])

    @property
    def max_tokens(self) -> int:
        return self._limits()["max_tokens"]

    @property
    def report_tokens(self) -> int:
        """Larger budget for the two long-form calls (report + final answer)."""
        return self._limits()["report_tokens"]

    @property
    def max_retries(self) -> int:
        return self._limits()["retries"]

    @property
    def compact_prompts(self) -> bool:
        """Trim retrieved context and search evidence to fit a tight token cap."""
        return bool(self._limits()["compact"])

    # ------------------------------------------------------------------
    # Vision provider (chosen independently of the text provider)
    # ------------------------------------------------------------------

    @property
    def vision_provider(self) -> str:
        """Explicit override, else the text provider if multimodal, else any keyed one."""
        if self.vision_provider_override:
            return self.vision_provider_override
        if VISION_DEFAULTS.get(self.provider) and self.api_key:
            return self.provider
        for candidate in ("google", "anthropic"):
            if self.key_for(candidate) and VISION_DEFAULTS.get(candidate):
                return candidate
        return ""

    @property
    def vision_model(self) -> str:
        provider = self.vision_provider
        if not provider:
            return ""
        return self.vision_model_override or VISION_DEFAULTS.get(provider, "")

    @property
    def has_vision(self) -> bool:
        provider = self.vision_provider
        return bool(provider and self.key_for(provider) and self.vision_model)

    @property
    def vision_help(self) -> str:
        """Explains, in one line, how to turn photo understanding on."""
        if self.has_vision:
            return ""
        return (
            "Photo understanding is off: the current text provider "
            f"({self.provider}) serves no vision model. Add a free "
            "GOOGLE_API_KEY (aistudio.google.com/apikey) or an ANTHROPIC_API_KEY "
            "to .env to switch it on — nothing else needs to change."
        )

    # ------------------------------------------------------------------
    # Capability flags for the UI
    # ------------------------------------------------------------------

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def has_meta(self) -> bool:
        return bool(self.meta_access_token and self.meta_page_id)

    @property
    def has_youtube(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def has_courier(self) -> bool:
        return bool(self.steadfast_api_key or self.pathao_client_id)

    def integration_status(self) -> dict[str, str]:
        vision = (
            f"LIVE ({self.vision_provider}/{self.vision_model})"
            if self.has_vision
            else "UNAVAILABLE — add GOOGLE_API_KEY"
        )
        return {
            f"Text agents ({self.provider})": (
                f"LIVE ({self.model})" if self.has_llm else "MISSING KEY"
            ),
            "Photo understanding": vision,
            "Web search": (
                "LIVE (Tavily)" if self.has_tavily else "LIVE (DuckDuckGo fallback)"
            ),
            "Meta Graph API (FB/IG)": "LIVE" if self.has_meta else "SIMULATED",
            "YouTube Data API": "LIVE" if self.has_youtube else "SIMULATED",
            "Courier (Pathao/Steadfast)": "LIVE" if self.has_courier else "SIMULATED",
            "Code execution": "LIVE (restricted local sandbox)",
            "Vector memory (RAG)": "LIVE",
        }


settings = Settings()
