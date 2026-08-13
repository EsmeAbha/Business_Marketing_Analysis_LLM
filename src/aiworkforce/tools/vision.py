"""Image understanding for the Product Vision agent.

The owner uploads a photo of a product, a food item, or a shelf of stock; this
turns it into a base64 content block Claude can read natively.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from langchain_core.messages import HumanMessage

from ..observability import get_logger

logger = get_logger("tools.vision")

_SUPPORTED = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_BYTES = 5 * 1024 * 1024  # Anthropic's practical per-image ceiling


def encode_image(path: str | Path) -> tuple[str, str]:
    """Return (media_type, base64_data) for an image on disk."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"image not found: {p}")

    media_type = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    if media_type not in _SUPPORTED:
        raise ValueError(
            f"unsupported image type {media_type!r}; use JPEG, PNG, GIF or WebP"
        )

    raw = p.read_bytes()
    if len(raw) > _MAX_BYTES:
        raw = _downscale(p, raw)

    return media_type, base64.standard_b64encode(raw).decode("utf-8")


def _downscale(path: Path, raw: bytes) -> bytes:
    """Shrink oversized uploads rather than rejecting the owner's photo."""
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        img.thumbnail((1568, 1568))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        logger.info("downscaled %s from %d to %d bytes", path.name, len(raw), buf.tell())
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not downscale %s (%s); sending original", path.name, exc)
        return raw


def build_image_message(prompt: str, image_paths: list[str | Path]) -> HumanMessage:
    """Compose a multimodal user turn: images first, then the instruction."""
    content: list[dict] = []
    for p in image_paths:
        media_type, data = encode_image(p)
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )
    content.append({"type": "text", "text": prompt})
    return HumanMessage(content=content)


def describe_image(llm, prompt: str, image_paths: list[str | Path]):
    """Single-shot vision call. Returns the raw AIMessage so usage can be recorded."""
    message = build_image_message(prompt, image_paths)
    return llm.invoke([message])
