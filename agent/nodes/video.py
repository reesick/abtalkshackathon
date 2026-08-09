"""
assemble_video node — real Flora REST API call, trying Gemini-Omni-Flash
first, falling back to Seedance 2.0 Reference (Fast) if Omni's pricing/
generation step rejects the request (observed failure: "Could not price
this generation" when passing image_urls — Omni's params schema doesn't
list an image-input field, unlike Seedance's which is also unconfirmed but
worth trying since duration/resolution/aspect_ratio are all supported there).
"""
import logging
import os

import aiohttp

from agent.flora_client import FloraGenerationError, generate_and_wait
from agent.state import AgentState

logger = logging.getLogger(__name__)

FLORA_VIDEO_MODEL_PRIMARY = os.environ.get("FLORA_VIDEO_MODEL", "r2v-gengateway-omni-flash-gg")
FLORA_VIDEO_MODEL_FALLBACK = os.environ.get("FLORA_VIDEO_MODEL_FALLBACK", "r2v-seedance-2.0-fast-enhancor")


async def _try_model(session: aiohttp.ClientSession, model: str, omni_prompt: str, frame_urls: list[str]) -> dict:
    """One attempt against a specific model. Raises on failure."""
    params: dict = {
        "aspect_ratio": "9:16",
        "resolution": "720p",
        "duration": "12",
    }
    # Only include image_urls if approved frame URLs exist and model is reference-based
    if frame_urls and "omni" not in model:
        params["image_urls"] = frame_urls

    result = await generate_and_wait(
        session,
        gen_type="video",
        prompt=omni_prompt,
        model=model,
        params=params,
    )
    outputs = result.get("outputs") or []
    if not outputs:
        raise FloraGenerationError(f"no outputs in completed run for model={model}")
    return {
        "url": outputs[0]["url"],
        "prompt_used": omni_prompt[:200] + "...",
        "model_used": model,
    }



async def assemble_video(state: AgentState) -> AgentState:
    """
    Try Gemini-Omni-Flash first (per user's explicit request to attempt Omni
    before falling back). On any failure, retry once against Seedance 2.0
    Reference (Fast). Degradation: if both fail, fall back to image_post.
    """
    omni_prompt = state.get("omni_prompt")
    media_plan = state.get("media_plan") or []
    approved = [a for a in media_plan if a["status"] == "approved"]

    if not omni_prompt or not approved:
        logger.warning("assemble_video: missing omni_prompt or approved assets — degrading to image_post")
        return {**state, "video_asset": None, "content_type": "image_post"}

    frame_urls = [a["output_url"] for a in approved]

    async with aiohttp.ClientSession() as session:
        try:
            logger.info("assemble_video: trying primary model %s", FLORA_VIDEO_MODEL_PRIMARY)
            video_asset = await _try_model(session, FLORA_VIDEO_MODEL_PRIMARY, omni_prompt, frame_urls)
            logger.info("assemble_video: assembled with primary model — %s", video_asset["url"])
            return {**state, "video_asset": video_asset}
        except Exception as exc:
            logger.warning("assemble_video: primary model %s failed — %s — trying fallback", FLORA_VIDEO_MODEL_PRIMARY, exc)

        try:
            video_asset = await _try_model(session, FLORA_VIDEO_MODEL_FALLBACK, omni_prompt, frame_urls)
            logger.info("assemble_video: assembled with fallback model — %s", video_asset["url"])
            return {**state, "video_asset": video_asset}
        except Exception as exc:
            logger.warning("assemble_video: fallback model %s also failed — %s — degrading to image_post", FLORA_VIDEO_MODEL_FALLBACK, exc)
            return {**state, "video_asset": None, "content_type": "image_post"}
