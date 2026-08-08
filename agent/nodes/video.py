"""
assemble_video node — sends frames + narration to Google Omni via Flora MCP.

Flora tool expected signature:
  google_omni_assemble(
      frames: list[str],        # list of image URLs from nano banana 2
      narration: str,           # full VO script text
      audio_direction: str,     # sound/music/SFX direction
      output_format: str,       # "mp4"
  ) -> {url: str, duration_seconds: float}

On timeout or error → sets video_asset = None so the graph degrades to
image_post (first frame stays as the media asset).
"""
import asyncio
import logging

from agent.state import AgentState
from mcp_client import get_tool

logger = logging.getLogger(__name__)

ASSEMBLY_TIMEOUT = 90  # seconds — Google Omni is the slowest step


def _audio_direction(script: dict, persona: dict) -> str:
    """
    Build a concise audio/sound direction string from script retention notes
    and persona domain.  Kept short — Omni doesn't need a novel here.
    """
    domain = persona.get("domain", "AI/tech")
    notes = script.get("retention_notes", "")
    return (
        f"Ambient, minimal electronic background music fitting a {domain} explainer. "
        f"No lyrics. Slight build toward the CTA moment. {notes}"
    ).strip()


async def assemble_video(state: AgentState) -> AgentState:
    """
    Assemble frames + narration into a final video via Google Omni (Flora MCP).

    Degradation: if no frames are available or assembly fails, sets
    video_asset = None and demotes content_type to "image_post" (if frames
    exist) or "text_post" (if no frames either).
    """
    script = state.get("script") or {}
    image_assets = state.get("image_assets") or []

    # Nothing to assemble
    if not image_assets:
        return {**state, "video_asset": None, "content_type": "text_post"}

    frame_urls = [a["url"] for a in image_assets if a.get("url")]
    narration = script.get("narration", script.get("hook", ""))

    if not narration:
        logger.warning("assemble_video: no narration in script — degrading to image_post")
        return {**state, "video_asset": None, "content_type": "image_post"}

    try:
        tool = get_tool("google_omni_assemble")
    except KeyError:
        logger.error("assemble_video: google_omni_assemble tool not registered in Flora MCP")
        return {**state, "video_asset": None, "content_type": "image_post"}

    audio_dir = _audio_direction(script, state["persona"])

    try:
        result = await asyncio.wait_for(
            tool.ainvoke({
                "frames": frame_urls,
                "narration": narration,
                "audio_direction": audio_dir,
                "output_format": "mp4",
            }),
            timeout=ASSEMBLY_TIMEOUT,
        )
        url = result.get("url") if isinstance(result, dict) else str(result)
        duration = result.get("duration_seconds") if isinstance(result, dict) else None

        video_asset = {
            "url": url,
            "prompt_used": f"frames={len(frame_urls)}, narration_chars={len(narration)}",
            "duration_seconds": duration,
        }
        logger.info("assemble_video: assembled %s (%.1fs)", url, duration or 0)
        return {**state, "video_asset": video_asset}

    except asyncio.TimeoutError:
        logger.warning(
            "assemble_video: Google Omni timed out after %ds — degrading to image_post",
            ASSEMBLY_TIMEOUT,
        )
        return {**state, "video_asset": None, "content_type": "image_post"}
    except Exception as exc:
        logger.warning("assemble_video: assembly failed — %s — degrading to image_post", exc)
        return {**state, "video_asset": None, "content_type": "image_post"}
