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
# Google's drawing models. Imagen 3 was retired and Imagen 4 is closed to new
# keys, so the way in is the Gemini image models, which return the picture as
# an inline part of an ordinary generateContent reply. Free-tier keys are
# granted no image quota at all — the call 429s on the per-day counter before
# it has run once — so this is the path that lights up when the owner turns on
# billing, not one that works today for free.
GEMINI_IMAGE_MODELS = (
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
)
GEMINI_IMAGE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}"
    ":generateContent"
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
    """Which provider would be tried. Never returns nothing — that is the point."""
    return "google" if settings.google_api_key else "pollinations"


def status() -> str:
    if settings.google_api_key:
        return ("Google, falling back to Pollinations — Google's drawing "
                "models need billing on, free keys are given no image quota")
    return "Pollinations (free, no account) — rough drafts only"


def quality_note() -> str:
    """What the owner should expect, and how to do better.

    Said plainly because the free model genuinely cannot draw a specific
    product reliably — it gets the colour and the setting and invents the
    object. Letting someone discover that by publishing a wrong picture is
    worse than telling them now.
    """
    common = (
        "The free drawing model gets the colours and the setting right but "
        "often invents the object itself. For a picture you would actually "
        "publish, upload your own photo and edit it here."
    )
    if settings.google_api_key:
        return (
            common + " Your Google key is set and will be tried first, but "
            "Google grants free keys no image quota — turn billing on at "
            "aistudio.google.com and the studio switches to Gemini's drawing "
            "model, which is far more accurate."
        )
    return (
        common + " Adding a free GOOGLE_API_KEY from aistudio.google.com/apikey "
        "switches photo reading on, and unlocks Google's drawing model once "
        "billing is enabled."
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


def _gemini_image(prompt: str, size: tuple[int, int]) -> Artwork:
    """Draw with Google, trying each image model in turn.

    Aspect ratio is asked for in words as well as in the config block: the
    ratio field is honoured inconsistently across these models, and a poster
    that comes back square when the owner picked a story is a wasted call.
    """
    w, h = size
    ratio = "1:1" if w == h else ("9:16" if h > w else "16:9")
    shape = {"1:1": "square", "9:16": "tall vertical", "16:9": "wide"}[ratio]
    last = ""
    for model in GEMINI_IMAGE_MODELS:
        try:
            with httpx.Client(timeout=180) as c:
                r = c.post(
                    GEMINI_IMAGE.format(model=model),
                    headers={"x-goog-api-key": settings.google_api_key},
                    json={
                        "contents": [{"parts": [
                            {"text": f"{prompt}. {shape} {ratio} composition."}
                        ]}],
                        "generationConfig": {"imageConfig":
                                             {"aspectRatio": ratio}},
                    },
                )
            if r.status_code != 200:
                last = f"{model} returned {r.status_code}"
                logger.info("%s", last)
                continue
            parts = ((r.json().get("candidates") or [{}])[0]
                     .get("content", {}).get("parts") or [])
            raw = next((p.get("inlineData", p.get("inline_data", {})).get("data")
                        for p in parts
                        if p.get("inlineData") or p.get("inline_data")), None)
            if not raw:
                last = f"{model} returned no picture"
                continue
            content = base64.b64decode(raw)
            path = _save(content, prompt, "png")
            logger.info("generated artwork via %s (%d bytes)", model, len(content))
            return Artwork(True, str(path), w, h, len(content), model, prompt)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            logger.warning("%s failed: %s", model, exc)
    return Artwork(False, provider="google", error=last or "no image returned")


def generate(prompt: str, preset: str = "square",
             seed: int | None = None) -> Artwork:
    """Make one image. Falls back to the keyless provider if the paid one fails."""
    size = PRESETS.get(preset, PRESETS["square"])
    if settings.google_api_key:
        art = _gemini_image(prompt, size)
        if art.ok:
            return art
        logger.info("Google drawing unavailable, falling back to pollinations")
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
