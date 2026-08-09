"""
Template ingestion job (meme spec section 73) — fetches the live Imgflip
template list and syncs it into the registry. Cheap; safe to run often
(e.g. once per scheduler tick or on a daily cadence — see spec section 103).
"""
import logging

import aiohttp

from meme.providers import imgflip
from meme.templates.registry import sync_meme_templates

logger = logging.getLogger(__name__)


async def sync_from_imgflip(session: aiohttp.ClientSession) -> dict:
    try:
        templates = await imgflip.get_memes(session)
    except imgflip.ImgflipError as exc:
        logger.warning("meme.templates.ingestion: get_memes failed — %s", exc)
        return {"created": 0, "updated": 0, "total_seen": 0, "error": str(exc)}

    return sync_meme_templates(templates, provider="imgflip")
