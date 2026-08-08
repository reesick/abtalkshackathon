"""
build_omni_prompt node — structured 9-section master brief per spec section
13, built from structured metadata (media_plan + tts_segments), not by
concatenating arbitrary LLM output (spec section 17).
"""
import logging

from agent.state import AgentState
from agent.style_reference import STYLE_GRAMMAR

logger = logging.getLogger(__name__)


def _video_intent(state: AgentState) -> str:
    topic = state.get("selected_topic") or {}
    persona = state.get("persona") or {}
    return (
        f"A 10-12 second hook/teaser video for {persona.get('name', 'the persona')} "
        f"({persona.get('domain', 'AI/tech')}) about: {topic.get('title', '')}. "
        f"This is NOT a full explainer — it delivers one hook line and one "
        f"stance, then stops. No summary of the whole story, no call-to-action, "
        f"no 'stay tuned' or teaser-to-elsewhere language. "
        f"Tone: terse, technically skeptical, one clear stance."
    )


def _asset_inventory(media_plan: list[dict]) -> str:
    lines = []
    for a in media_plan:
        if a["status"] != "approved":
            continue
        lines.append(f"{a['asset_id']} ({a['scene_id']}): {a['visual_role']} — {a['output_url']}")
    return "\n".join(lines) or "(no approved assets)"


def _style_block() -> str:
    return (
        f"Preserve: {STYLE_GRAMMAR['rendering_method']}, "
        f"{STYLE_GRAMMAR['character_construction']}, "
        f"{STYLE_GRAMMAR['materials']}, {STYLE_GRAMMAR['depth']}. "
        f"Palette: {STYLE_GRAMMAR['palette']}. "
        f"Lighting: {STYLE_GRAMMAR['lighting']}. "
        f"{STYLE_GRAMMAR['editorial_reference']}."
    )


def _audio_block(tts_segments: list[dict]) -> str:
    if not tts_segments:
        return "No narration audio available — video should communicate visually with on-screen text if needed."
    return "Use the supplied TTS narration as the timing backbone. Do not alter the spoken content."


def _scene_timeline(media_plan: list[dict], tts_segments: list[dict]) -> str:
    tts_by_scene = {t["scene_id"]: t for t in tts_segments}
    lines = []
    cursor = 0.0
    for a in media_plan:
        if a["status"] != "approved":
            continue
        tts = tts_by_scene.get(a["scene_id"])
        duration = tts["duration_seconds"] if tts else 3.0
        narration_text = tts["text"] if tts else "(no narration for this scene)"
        lines.append(
            f"Scene {a['scene_id']} — {cursor:.1f}s to {cursor + duration:.1f}s\n"
            f"  Assets: {a['asset_id']}\n"
            f"  Action: {a['script_beat']} — {a['visual_role']}\n"
            f"  Camera: {STYLE_GRAMMAR['camera']}\n"
            f"  Narration: {narration_text}"
        )
        cursor += duration
    return "\n\n".join(lines) or "(no approved scenes)"


def _total_duration(tts_segments: list[dict]) -> float:
    """
    Target is always 10-12s per the persona's content format (short hook/
    teaser, not a full explainer). Clamp the TTS-derived sum into that range
    rather than trusting it unbounded — narration length estimates can drift,
    and the video model needs an explicit, in-range target regardless.
    """
    if not tts_segments:
        return 11.0  # midpoint default when no audio drives timing
    raw = sum(t["duration_seconds"] for t in tts_segments)
    return round(min(max(raw, 10.0), 12.0), 1)


def build_omni_prompt(state: AgentState) -> AgentState:
    media_plan = state.get("media_plan") or []
    tts_segments = state.get("tts_segments") or []

    approved_count = sum(1 for a in media_plan if a["status"] == "approved")
    if approved_count == 0:
        logger.warning("build_omni_prompt: no approved assets — cannot build prompt")
        return {**state, "omni_prompt": None, "content_type": "text_post"}

    sections = [
        f"1. VIDEO INTENT\n{_video_intent(state)}",
        f"2. REFERENCE ASSETS\n{_asset_inventory(media_plan)}\nUse the supplied assets as visual sources of truth.",
        f"3. VISUAL STYLE\n{_style_block()}",
        f"4. AUDIO / NARRATION\n{_audio_block(tts_segments)}",
        f"5. SCENE TIMELINE\n{_scene_timeline(media_plan, tts_segments)}",
        "6. CONTINUITY\nDo not redesign characters, props, palette or materials between shots. Do not introduce new visual styles.",
        f"7. CAMERA / MOTION\n{STYLE_GRAMMAR['camera']}. Preserve composition when the scene calls for a locked-off camera.",
        "8. NEGATIVE CONSTRAINTS\nDo not add unrequested objects, text, logos, photorealistic elements, palette changes, camera movements, or character changes.",
        f"9. OUTPUT\nFormat: mp4. Aspect ratio: 9:16. Target duration: {_total_duration(tts_segments)}s (must be 10-12 seconds total, no longer).",
    ]
    omni_prompt = "\n\n".join(sections)

    logger.info("build_omni_prompt: built prompt (%d chars, %d approved assets)", len(omni_prompt), approved_count)
    return {**state, "omni_prompt": omni_prompt}
