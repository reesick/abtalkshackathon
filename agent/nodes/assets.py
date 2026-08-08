"""
generate_assets node — calls Flora MCP (nano banana 2) for each script beat.

Flora tool expected signature:
  nano_banana_2_generate(prompt: str, width: int, height: int) -> {url: str}

Falls back gracefully: if Flora is unavailable or times out, sets
state["content_type"] to "text_post" so the graph skips the video path entirely.
"""
import asyncio
import logging

from agent.state import AgentState
from mcp_client import get_tool

logger = logging.getLogger(__name__)

FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
TOOL_TIMEOUT = 45  # seconds per frame


async def _generate_frame(tool, beat: dict, index: int) -> dict | None:
    """Generate one frame image for a single script beat. Returns None on failure."""
    visual_idea = beat.get("visual_idea", beat.get("beat", "abstract background"))
    prompt = (
        f"Cinematic still frame for a short-form tech video. "
        f"Scene: {visual_idea}. "
        f"Style: clean, modern, high contrast. No text overlay. 16:9."
    )
    try:
        result = await asyncio.wait_for(
            tool.ainvoke({
                "prompt": prompt,
                "width": FRAME_WIDTH,
                "height": FRAME_HEIGHT,
            }),
            timeout=TOOL_TIMEOUT,
        )
        url = result.get("url") if isinstance(result, dict) else str(result)
        return {"url": url, "prompt_used": prompt, "beat_index": index}
    except asyncio.TimeoutError:
        logger.warning("generate_assets: frame %d timed out (>%ds)", index, TOOL_TIMEOUT)
        return None
    except Exception as exc:
        logger.warning("generate_assets: frame %d failed — %s", index, exc)
        return None


async def generate_assets(state: AgentState) -> AgentState:
    """
    Generate one image per beat in state["script"]["beats"] via Flora
    nano banana 2.

    Degradation logic:
    - If ALL frames fail → content_type → "text_post", image_assets = []
    - If SOME frames fail → keep successful ones, content_type stays
      (video assembler will skip missing beats)
    """
    script = state.get("script")
    if not script:
        return {**state, "image_assets": [], "content_type": "text_post"}

    beats: list[dict] = script.get("beats", [])
    if not beats:
        return {**state, "image_assets": [], "content_type": "text_post"}

    try:
        tool = get_tool("nano_banana_2_generate")
    except KeyError:
        logger.error("generate_assets: nano_banana_2_generate tool not registered in Flora MCP")
        return {**state, "image_assets": [], "content_type": "text_post"}

    tasks = [_generate_frame(tool, beat, i) for i, beat in enumerate(beats)]
    results = await asyncio.gather(*tasks)

    image_assets = [r for r in results if r is not None]

    if not image_assets:
        logger.warning("generate_assets: all frames failed — degrading to text_post")
        return {**state, "image_assets": [], "content_type": "text_post"}

    return {**state, "image_assets": image_assets}
