"""
Imgflip provider — template fetching + rendering (meme spec sections 5, 6,
58, 59, 60, 98-100).

Imgflip is used strictly as:
  template provider + renderer
NOT as the humour brain (spec section 5: "Do NOT use Imgflip's AI meme
endpoint as the primary humour engine"). /automeme, /ai_meme, /search_memes,
/get_meme are Premium-only and intentionally not used here.

Credentials: IMGFLIP_USERNAME / IMGFLIP_PASSWORD (POST body auth, per
Imgflip's docs — never in the URL, never logged). Both optional at import
time; the renderer degrades to "no meme" if absent (spec section 60: do not
waste LLM calls because an image API/credentials are unavailable).
"""
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

IMGFLIP_API_BASE = "https://api.imgflip.com"
IMGFLIP_USERNAME = os.environ.get("IMGFLIP_USERNAME", "")
IMGFLIP_PASSWORD = os.environ.get("IMGFLIP_PASSWORD", "")


class ImgflipError(Exception):
    pass


def credentials_configured() -> bool:
    return bool(IMGFLIP_USERNAME and IMGFLIP_PASSWORD)


async def get_memes(session: aiohttp.ClientSession) -> list[dict]:
    """
    GET /get_memes — free endpoint, no auth required. Returns popular
    captionable templates ordered by recent caption usage (per Imgflip's own
    docs — the list can change over time, do not assume static ordering).

    Response fields per template: id, name, url, width, height, box_count.
    """
    try:
        async with session.get(
            f"{IMGFLIP_API_BASE}/get_memes",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json()
    except Exception as exc:
        raise ImgflipError(f"get_memes request failed: {exc}") from exc

    if not data.get("success"):
        raise ImgflipError(f"get_memes returned success=false: {data.get('error_message')}")

    memes = data.get("data", {}).get("memes", [])
    logger.info("imgflip: get_memes -> %d templates", len(memes))
    return memes


async def caption_image(
    session: aiohttp.ClientSession,
    *,
    template_id: str,
    text_boxes: list[str],
) -> str:
    """
    POST /caption_image — renders a meme. Uses the `boxes[]` structure
    (spec section 58) rather than assuming a fixed text0/text1 shape, so
    this works for templates with more than 2 text areas.

    Returns the rendered image URL. Credentials are sent as POST form
    fields, never in the URL and never logged (spec section 100/81).
    """
    if not credentials_configured():
        raise ImgflipError("IMGFLIP_USERNAME/IMGFLIP_PASSWORD not configured")

    form = aiohttp.FormData()
    form.add_field("template_id", str(template_id))
    form.add_field("username", IMGFLIP_USERNAME)
    form.add_field("password", IMGFLIP_PASSWORD)
    for i, text in enumerate(text_boxes):
        form.add_field(f"boxes[{i}][text]", text)

    try:
        async with session.post(
            f"{IMGFLIP_API_BASE}/caption_image",
            data=form,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            data = await r.json()
    except Exception as exc:
        raise ImgflipError(f"caption_image request failed: {exc}") from exc

    if not data.get("success"):
        # Never echo the request body (contains credentials) into the error.
        raise ImgflipError(f"caption_image returned success=false: {data.get('error_message')}")

    url = data.get("data", {}).get("url")
    if not url:
        raise ImgflipError("caption_image succeeded but returned no url")

    logger.info("imgflip: rendered template=%s -> %s", template_id, url)
    return url


async def render_with_fallback(
    session: aiohttp.ClientSession,
    *,
    template_id: str,
    text_boxes: list[str],
) -> Optional[str]:
    """
    Spec section 60: if rendering fails, do not regenerate the joke — just
    return None so the caller can fall back to NO MEME. One retry only;
    no joke-regeneration loop here.
    """
    for attempt in range(2):
        try:
            return await caption_image(session, template_id=template_id, text_boxes=text_boxes)
        except ImgflipError as exc:
            logger.warning("imgflip: render attempt %d/2 failed — %s", attempt + 1, exc)
    return None
