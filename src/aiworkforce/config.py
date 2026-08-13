"""Central configuration.

Every knob the system has lives here so agents never read os.environ directly.
Missing optional credentials are not an error — they flip the corresponding
integration into a clearly-labelled simulated adapter.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Filesystem layout -----------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
VECTOR_DIR = DATA_DIR / "vectors"
DB_PATH = DATA_DIR / "aiworkforce.db"
CHECKPOINT_PATH = DATA_DIR / "checkpoints.db"
LOG_PATH = DATA_DIR / "aiworkforce.log"

for _d in (DATA_DIR, UPLOAD_DIR, VECTOR_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass(frozen=True)
class Settings:
    # --- Models ---
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    model: str = field(default_factory=lambda: _env("AIW_MODEL", "claude-opus-5"))
    fast_model: str = field(
        default_factory=lambda: _env("AIW_FAST_MODEL", "claude-haiku-4-5")
    )
    effort: str = field(default_factory=lambda: _env("AIW_EFFORT", "high"))
    max_tokens: int = 8000

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

    # --- Capability flags: which integrations are live vs simulated ---
    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_api_key)

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
        """Human-readable LIVE/SIMULATED map, rendered in the UI sidebar."""
        return {
            "Anthropic (LLM + vision)": "LIVE" if self.has_llm else "MISSING KEY",
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
