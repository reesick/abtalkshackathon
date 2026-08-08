"""
generate_assets node — real Flora REST API image generation (Nano Banana 2),
replacing the broken MCP-based placeholder. Uses the layered prompt
architecture from spec section 5 and the locked style reference from
style_reference.py.

Confirmed working model/params tonight:
  model: is2i-gemini-3.1-flash-image (images-to-image, multi-ref)
  params: {aspect_ratio, resolution, image_urls}
"""
import asyncio
import logging

import aiohttp

from agent.flora_client import FloraGenerationError, generate_and_wait
from agent.state import AgentState, MediaAsset
from agent.style_reference import STYLE_GRAMMAR, STYLE_REFERENCE_IMAGES, build_negative_constraints

logger = logging.getLogger(__name__)

MODEL_PRIMARY = "is2i-gemini-3.1-flash-image"       # Nano Banana 2, with refs
MODEL_FALLBACK = "is2i-nano-banana-2-lite-is2i-google-gemini"  # cheaper retry
MAX_RETRIES = 2


def build_asset_prompt(media_asset: MediaAsset) -> str:
    """
    Layered prompt construction per spec section 5's table:
    Subject/action -> Materials -> Depth/shadows -> Palette -> Lighting/camera
    -> Style/frame -> Continuity -> Negative constraints
    """
    return (
        f"{STYLE_GRAMMAR['rendering_method']}: a figure with "
        f"{STYLE_GRAMMAR['character_construction']}, "
        f"{media_asset['visual_role']}. "
        f"{STYLE_GRAMMAR['materials']}. "
        f"{STYLE_GRAMMAR['depth']}. "
        f"Palette: {STYLE_GRAMMAR['palette']}. "
        f"{STYLE_GRAMMAR['lighting']}, {STYLE_GRAMMAR['camera']}. "
        f"{STYLE_GRAMMAR['editorial_reference']}. {STYLE_GRAMMAR['frame']}. "
        f"{media_asset.get('continuity_notes', '')} "
        f"{build_negative_constraints()}"
    ).strip()


async def _generate_one(session: aiohttp.ClientSession, media_asset: MediaAsset) -> MediaAsset:
    prompt = build_asset_prompt(media_asset)
    updated = {**media_asset, "prompt": prompt, "status": "generating"}

    model = MODEL_PRIMARY
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await generate_and_wait(
                session,
                gen_type="image",
                prompt=prompt,
                model=model,
                params={
                    "aspect_ratio": "9:16",
                    "resolution": "2K",
                    "image_urls": STYLE_REFERENCE_IMAGES,
                },
            )
            outputs = result.get("outputs") or []
            if not outputs:
                raise FloraGenerationError("no outputs in completed run")
            updated["output_url"] = outputs[0]["url"]
            updated["status"] = "generated"
            return updated
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "generate_assets: %s attempt %d/%d failed — %s",
                media_asset["asset_id"], attempt + 1, MAX_RETRIES + 1, exc,
            )
            model = MODEL_FALLBACK  # switch to fallback on retry, per plan section 6

    updated["status"] = "rejected"
    updated["validation_notes"] = f"generation failed after {MAX_RETRIES + 1} attempts: {last_exc}"
    return updated


async def generate_assets(state: AgentState) -> AgentState:
    """
    Generate one image per planned media asset, in parallel.
    Degradation: if ALL assets fail -> content_type -> text_post.
    """
    media_plan = state.get("media_plan") or []
    if not media_plan:
        return {**state, "media_plan": [], "content_type": "text_post"}

    async with aiohttp.ClientSession() as session:
        tasks = [_generate_one(session, asset) for asset in media_plan]
        results = await asyncio.gather(*tasks)

    approved = [r for r in results if r["status"] == "generated"]

    if not approved:
        logger.warning("generate_assets: all assets failed — degrading to text_post")
        return {**state, "media_plan": results, "image_assets": [], "content_type": "text_post"}

    # Keep legacy image_assets shape populated for the image_post path (write_post reads this)
    image_assets = [
        {"url": a["output_url"], "prompt_used": a["prompt"], "beat_index": i}
        for i, a in enumerate(results) if a["status"] == "generated"
    ]

    return {**state, "media_plan": results, "image_assets": image_assets}
