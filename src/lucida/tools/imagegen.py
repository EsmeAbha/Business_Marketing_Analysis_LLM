"""Generating ad artwork.

Two providers, tried in order of quality, and the choice is deliberate:

  * **Google Imagen** when a `GOOGLE_API_KEY` is set. Free tier, and the best
    of the two — but it needs an account.
  * **Pollinations** otherwise. Genuinely free and genuinely keyless, which
    matters here: every other integration in this project degrades to a
    labelled simulation when a credential is missing, and an owner with no
    accounts should still be able to make a poster.

What this does *not* do is invent product photographs. A generated image is
recorded with `source='generated'` in `media_assets` and is described as
artwork wherever it is shown, because a customer seeing an AI rendering of a
product that was never photographed is being misled — and it is the owner who
answers for that, not the model.
"""

from __future__ import annotations

import base64
import hashlib
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import DATA_DIR, settings
from ..observability import get_logger

logger = get_logger("tools.imagegen")

MEDIA_DIR = DATA_DIR / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}"
IMAGEN = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "imagen-3.0-generate-002:predict"
)

# How long the owner's description should be. Measured in words because that
# is what the owner is writing, and what the UI counts back to them.
DETAIL_MIN_WORDS = 8
DETAIL_MAX_WORDS = 25

# Sizes that suit where the artwork actually goes.
PRESETS = {
    "square": (1024, 1024),      # Instagram / Facebook feed
    "story": (1024, 1792),       # Instagram / Facebook story
    "wide": (1792, 1024),        # Facebook link card, YouTube thumbnail
}


@dataclass
class Artwork:
    ok: bool
    path: str = ""
    width: int = 0
    height: int = 0
    bytes: int = 0
    provider: str = ""
    prompt: str = ""
    error: str = ""
    generated: bool = True      # never a photograph of real stock


def available() -> str:
    """Which provider would be used. Never returns nothing — that is the point."""
    return "imagen" if settings.google_api_key else "pollinations"


def status() -> str:
    if settings.google_api_key:
        return "Google Imagen — using your GOOGLE_API_KEY"
    return "Pollinations (free, no account) — rough drafts only"


def quality_note() -> str:
    """What the owner should expect, and how to do better.

    Said plainly because the free model genuinely cannot draw a specific
    product reliably — it gets the colour and the setting and invents the
    object. Letting someone discover that by publishing a wrong picture is
    worse than telling them now.
    """
    if settings.google_api_key:
        return ""
    return (
        "The free drawing model gets the colours and the setting right but "
        "often invents the object itself. For pictures you would actually "
        "publish, upload your own photo — or add a free GOOGLE_API_KEY from "
        "aistudio.google.com/apikey and the studio switches to Google Imagen, "
        "which is far more accurate (and switches photo reading on too)."
    )


def _slug(text: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    return f"{stem or 'art'}-{digest}"


def build_prompt(
    product: str,
    style: str = "",
    offer: str = "",
    audience: str = "",
    detail: str = "",
) -> str:
    """Turn what the owner knows into a prompt worth sending.

    The product is stated first and then restated at the end. These models
    weight the opening and closing of a prompt most heavily, and the failure
    mode otherwise is exactly what it did on the first attempt: it latched
    onto "studio lighting, appetising" and drew a generic object that was not
    the thing being sold.

    `offer` and `audience` are deliberately *not* fed to the image. They are
    selling context, and a model handed "2 for 1 this week" tries to draw the
    words — which is why "no text" is stated three ways. They shape the copy
    instead, where they belong.
    """
    # A description has a useful range. Under it the model fills the gaps
    # generically; over it the later words stop getting attention, so the
    # setting the owner cared about is exactly the part dropped. The UI shows
    # a gauge, and this is the backstop for anything reaching the API directly.
    product = " ".join(str(product).split())[:120]
    words = str(detail).split()
    if len(words) > DETAIL_MAX_WORDS:
        detail = " ".join(words[:DETAIL_MAX_WORDS])
        logger.info("trimmed the description to %d words", DETAIL_MAX_WORDS)
    else:
        detail = " ".join(words)

    bits = [
        f"{product}, product photograph",
        f"the {product} fills the frame and is the only subject",
    ]
    if detail:
        bits.append(detail)
    bits.append(style or "clean studio lighting, soft shadow, plain background")
    bits.extend([
        "sharp focus on the product, realistic materials and texture",
        "space above for a headline",
        f"a photograph of {product}",
        "no text, no words, no lettering, no watermark, no logo, no hands, "
        "no people",
    ])
    return ", ".join(bits)


def _save(content: bytes, prompt: str, ext: str = "jpg") -> Path:
    dest = MEDIA_DIR / f"{_slug(prompt)}.{ext}"
    dest.write_bytes(content)
    return dest


def _pollinations(prompt: str, size: tuple[int, int],
                  seed: int | None = None) -> Artwork:
    w, h = size
    url = POLLINATIONS.format(prompt=urllib.parse.quote(prompt))
    # No `model` parameter: /models lists only "sana", and passing anything
    # else returns byte-identical output — it is ignored, so sending it just
    # implies a choice that is not being made.
    params = {"width": w, "height": h, "nologo": "true"}
    # A seed is what makes "regenerate" give a different picture of the same
    # thing rather than the identical one back — the endpoint is otherwise
    # deterministic for a given prompt.
    if seed is not None:
        params["seed"] = seed
    try:
        with httpx.Client(timeout=90, follow_redirects=True) as c:
            r = c.get(url, params=params)
        if r.status_code != 200 or not r.content:
            return Artwork(False, provider="pollinations",
                           error=f"provider returned {r.status_code}")
        path = _save(r.content, f"{prompt}|{seed or 0}")
        logger.info("generated artwork via pollinations (%d bytes)", len(r.content))
        return Artwork(True, str(path), w, h, len(r.content),
                       "pollinations", prompt)
    except Exception as exc:  # noqa: BLE001 — art is never worth an outage
        logger.warning("pollinations failed: %s", exc)
        return Artwork(False, provider="pollinations", error=str(exc))


def _imagen(prompt: str, size: tuple[int, int]) -> Artwork:
    w, h = size
    ratio = "1:1" if w == h else ("9:16" if h > w else "16:9")
    try:
        with httpx.Client(timeout=120) as c:
            r = c.post(
                IMAGEN,
                params={"key": settings.google_api_key},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {"sampleCount": 1, "aspectRatio": ratio},
                },
            )
        if r.status_code != 200:
            logger.warning("imagen returned %s", r.status_code)
            return Artwork(False, provider="imagen",
                           error=f"Imagen returned {r.status_code}")
        preds = r.json().get("predictions") or []
        raw = preds[0].get("bytesBase64Encoded") if preds else None
        if not raw:
            return Artwork(False, provider="imagen", error="no image returned")
        content = base64.b64decode(raw)
        path = _save(content, prompt, "png")
        logger.info("generated artwork via imagen (%d bytes)", len(content))
        return Artwork(True, str(path), w, h, len(content), "imagen", prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("imagen failed: %s", exc)
        return Artwork(False, provider="imagen", error=str(exc))


def generate(prompt: str, preset: str = "square",
             seed: int | None = None) -> Artwork:
    """Make one image. Falls back to the keyless provider if the paid one fails."""
    size = PRESETS.get(preset, PRESETS["square"])
    if settings.google_api_key:
        art = _imagen(prompt, size)
        if art.ok:
            return art
        logger.info("imagen unavailable, falling back to pollinations")
    return _pollinations(prompt, size, seed)


def generate_for_product(
    product: str,
    preset: str = "square",
    style: str = "",
    offer: str = "",
    audience: str = "",
    detail: str = "",
    seed: int | None = None,
) -> Artwork:
    return generate(
        build_prompt(product, style, offer, audience, detail), preset, seed)
