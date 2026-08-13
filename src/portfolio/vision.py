"""Gemini vision captions for uploaded/rasterized images.

Bounded and cached: `extract.extract_all` already caps the image count at
`config.PORTFOLIO_MAX_VISION_IMAGES` before this module ever runs; each
call additionally gets its own timeout, and results are cached by image
content hash (not filename) so re-analyzing an unchanged image -- e.g. the
same past-portfolio page across a retried run -- doesn't re-pay for a
vision call within the process's cache TTL.

A failed or timed-out analysis for one image never fails the whole run --
`analyze_images` simply omits that image's caption, and `compose.py`
treats a missing caption the same as "no vision data available".
"""
import base64
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

import config
from clients import get_portfolio_llm
from logging_setup import get_logger
from tools.cache import TTLCache

from .extract import ExtractedImage

logger = get_logger(__name__)

_cache = TTLCache(ttl_seconds=config.PORTFOLIO_VISION_CACHE_TTL_MINUTES * 60)

_VISION_PROMPT = (
    "This image was uploaded by an FTC (FIRST Tech Challenge) robotics team for their "
    "engineering portfolio. It may be a CAD render, a robot photo, a whiteboard/notes photo, "
    "or an outreach/event photo. Describe only what is visibly present -- never invent a "
    "mechanism, part name, or event you cannot actually see."
)


class ImageCaption(BaseModel):
    caption: str = Field(max_length=200, description="One plain sentence describing what the image shows.")
    alt_text: str = Field(max_length=120, description="Short accessibility alt text for this image.")
    observations: str = Field(
        default="",
        max_length=600,
        description="Design/engineering details visible in the image relevant to a portfolio write-up, if any.",
    )


def to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _content_hash(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return hashlib.sha256(buf.getvalue()).hexdigest()


def _analyze_one(extracted: ExtractedImage) -> ImageCaption:
    cache_key = f"vision:{_content_hash(extracted.image)}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    llm = get_portfolio_llm().with_structured_output(ImageCaption)
    message = HumanMessage(
        content=[
            {"type": "text", "text": _VISION_PROMPT},
            {"type": "image_url", "image_url": to_data_uri(extracted.image)},
        ]
    )
    result = llm.invoke([message])
    _cache.set(cache_key, result)
    return result


def analyze_images(images: list[ExtractedImage], *, timeout: "float | None" = None) -> dict[str, ImageCaption]:
    """Returns `{filename: ImageCaption}` for whichever images finished
    within `timeout` (default `config.PORTFOLIO_VISION_TIMEOUT_SECONDS`
    per image); a missing key means that image's analysis failed, timed
    out, or was never attempted."""
    if not images:
        return {}
    timeout = timeout if timeout is not None else config.PORTFOLIO_VISION_TIMEOUT_SECONDS

    results: dict[str, ImageCaption] = {}
    with ThreadPoolExecutor(max_workers=len(images)) as executor:
        futures = {executor.submit(_analyze_one, img): img.filename for img in images}
        for future in as_completed(futures, timeout=timeout * len(images)):
            filename = futures[future]
            try:
                results[filename] = future.result(timeout=timeout)
            except Exception:
                logger.warning("vision analysis failed for %s", filename, exc_info=True)
    return results
