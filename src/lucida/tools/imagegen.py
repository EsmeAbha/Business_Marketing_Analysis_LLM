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
        return "Google Imagen (free tier, using your GOOGLE_API_KEY)"
    return "Pollinations (free, no account needed)"


def _slug(text: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    return f"{stem or 'art'}-{digest}"


def build_prompt(
    product: str,
    style: str = "",
    offer: str = "",
    audience: str = "",
) -> str:
    """Turn what the owner knows into a prompt worth sending.

    Kept explicit about it being product photography rather than a person,
    because the failure mode of a vague prompt is a stock-photo model holding
    an unrelated object.
    """
    bits = [
        f"professional product photograph of {product}",
        "clean studio lighting, shallow depth of field, appetising",
        "centred composition with empty space at the top for a headline",
    ]
    if style:
        bits.append(style)
    if audience:
        bits.append(f"styled for {audience}")
    if offer:
        bits.append(f"suggesting {offer}")
    bits.append("no text, no watermark, no logos")
    return ", ".join(bits)


def _save(content: bytes, prompt: str, ext: str = "jpg") -> Path:
    dest = MEDIA_DIR / f"{_slug(prompt)}.{ext}"
    dest.write_bytes(content)
    return dest


def _pollinations(prompt: str, size: tuple[int, int]) -> Artwork:
    w, h = size
    url = POLLINATIONS.format(prompt=urllib.parse.quote(prompt))
    try:
        with httpx.Client(timeout=90, follow_redirects=True) as c:
            r = c.get(url, params={"width": w, "height": h,
                                   "nologo": "true", "model": "flux"})
        if r.status_code != 200 or not r.content:
            return Artwork(False, provider="pollinations",
                           error=f"provider returned {r.status_code}")
        path = _save(r.content, prompt)
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


def generate(prompt: str, preset: str = "square") -> Artwork:
    """Make one image. Falls back to the keyless provider if the paid one fails."""
    size = PRESETS.get(preset, PRESETS["square"])
    if settings.google_api_key:
        art = _imagen(prompt, size)
        if art.ok:
            return art
        logger.info("imagen unavailable, falling back to pollinations")
    return _pollinations(prompt, size)


def generate_for_product(
    product: str,
    preset: str = "square",
    style: str = "",
    offer: str = "",
    audience: str = "",
) -> Artwork:
    return generate(build_prompt(product, style, offer, audience), preset)
