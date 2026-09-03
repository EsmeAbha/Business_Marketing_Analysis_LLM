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
import json
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

def _env_or(name: str, fallback: str) -> str:
    import os
    return (os.environ.get(name) or "").strip() or fallback


POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}"

# OpenAI's drawing model. Unlike the others in this file it costs real money
# per picture, so it is capped rather than merely preferred.
OPENAI_IMAGE_MODEL = _env_or("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_SIZES = {"square": "1024x1024", "story": "1024x1536",
                      "wide": "1536x1024"}

# How many paid pictures this installation may ever draw. Deliberately a
# constant and not a setting: the point of it is to be hard to raise by
# accident. Reaching it is not an error - the studio drops back to the free
# provider and says so, because a shop that cannot make a poster at all is
# worse than one making rough ones.
PAID_IMAGE_LIMIT = int(_env_or("LUCIDA_PAID_IMAGE_LIMIT", "2"))

# Kept on disk, not in memory: a counter that resets when the server restarts
# is not a spending limit, it is a suggestion.
QUOTA_FILE = DATA_DIR / "paid_images.json"


def paid_images_used() -> int:
    """How many paid pictures have been drawn, across all restarts."""
    try:
        return int(json.loads(QUOTA_FILE.read_text(encoding="utf-8"))["used"])
    except Exception:  # noqa: BLE001 — a missing or corrupt file means none
        return 0


def paid_images_left() -> int:
    return max(0, PAID_IMAGE_LIMIT - paid_images_used())


def _claim_paid_image() -> bool:
    """Take one from the allowance, or refuse.

    Claimed *before* the request rather than after a successful reply,
    because the money is spent the moment OpenAI answers - including when it
    answers with a picture this code then fails to parse. Counting successes
    would let a parse bug bill an unbounded number of times.
    """
    used = paid_images_used()
    if used >= PAID_IMAGE_LIMIT:
        return False
    try:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUOTA_FILE.write_text(json.dumps({"used": used + 1}),
                              encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        # If the count cannot be written it cannot be enforced, and an
        # unenforceable limit on someone else's money is not one worth
        # proceeding under.
        logger.warning("could not record image quota, refusing to draw: %s",
                       exc)
        return False
    logger.info("paid image %d of %d", used + 1, PAID_IMAGE_LIMIT)
    return True
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
    if settings.openai_api_key and paid_images_left() > 0:
        return "openai"
    return "google" if settings.google_api_key else "pollinations"


def status() -> str:
    if settings.openai_api_key:
        left = paid_images_left()
        if left > 0:
            return (f"OpenAI {OPENAI_IMAGE_MODEL} — {left} of "
                    f"{PAID_IMAGE_LIMIT} paid pictures left, then it falls "
                    f"back to the free provider")
        return (f"Free provider — the {PAID_IMAGE_LIMIT}-picture OpenAI "
                f"allowance is used up")
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


def _openai_image(prompt: str, preset: str) -> Artwork:
    """Draw with OpenAI. Costs money, so the allowance is claimed first.

    The claim happens before the request and is never given back on failure.
    That is deliberate: a refund path is exactly where a retry loop turns a
    limit of two into a bill for twenty, and the whole reason this exists is
    that the person paying is not the person running it.
    """
    if not settings.openai_api_key:
        return Artwork(False, provider="openai", error="no OpenAI key")
    if not _claim_paid_image():
        return Artwork(False, provider="openai",
                       error=(f"the {PAID_IMAGE_LIMIT}-picture paid allowance "
                              f"is used up"))

    want = OPENAI_IMAGE_SIZES.get(preset, OPENAI_IMAGE_SIZES["square"])
    try:
        with httpx.Client(timeout=300) as c:
            r = c.post(
                f"{settings.openai_base_url}/images/generations",
                headers={"Authorization": f"Bearer {settings.openai_api_key}",
                         "Content-Type": "application/json"},
                json={"model": OPENAI_IMAGE_MODEL, "prompt": prompt,
                      "size": want, "n": 1},
            )
        if r.status_code != 200:
            return Artwork(False, provider="openai",
                           error=f"OpenAI returned {r.status_code}: "
                                 f"{r.text[:160]}")
        item = (r.json().get("data") or [{}])[0]
        # gpt-image-1 returns base64; the dall-e models return a URL. Both
        # shapes are accepted so changing the model does not break drawing.
        raw = item.get("b64_json")
        if raw:
            content = base64.b64decode(raw)
        elif item.get("url"):
            with httpx.Client(timeout=120) as c:
                content = c.get(item["url"]).content
        else:
            return Artwork(False, provider="openai",
                           error="OpenAI returned no picture")
    except Exception as exc:  # noqa: BLE001
        return Artwork(False, provider="openai", error=str(exc))

    w, h = (int(x) for x in want.split("x"))
    path = _save(content, prompt, "png")
    logger.info("generated artwork via %s (%d bytes)", OPENAI_IMAGE_MODEL,
                len(content))
    return Artwork(True, str(path), w, h, len(content), OPENAI_IMAGE_MODEL,
                   prompt)


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
    # OpenAI draws far better than the free provider and is the only one here
    # that bills, so it goes first but only while the allowance lasts. Once
    # it is gone the studio quietly carries on with the free provider rather
    # than refusing to work.
    if settings.openai_api_key and paid_images_left() > 0:
        art = _openai_image(prompt, preset)
        if art.ok:
            return art
        logger.info("OpenAI drawing unavailable (%s), falling back", art.error)
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
