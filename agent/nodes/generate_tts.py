"""
generate_tts node — one ElevenLabs call per script beat, uploaded to Flora
assets for a permanent HTTPS URL (spec section 7.4 recommendation: reuse the
same asset-upload flow already needed for images).

Per spec section 11: "Beat 01 -> asset_01 + asset_02 + tts_01" — this node
produces the tts_01-style segment per scene_id.
"""
import asyncio
import logging
import uuid

import aiohttp

from agent.elevenlabs_client import ElevenLabsError, synthesize_speech
from agent.flora_client import FloraGenerationError, upload_asset
from agent.state import AgentState, TTSSegment

logger = logging.getLogger(__name__)

# Rough estimate: average speaking rate ~150 words/min = 2.5 words/sec.
# Used only as a fallback duration estimate since probing the actual mp3
# duration would need an extra dependency (mutagen/pydub) not yet in
# requirements.txt.
_WORDS_PER_SECOND = 2.5


def _estimate_duration(text: str) -> float:
    word_count = len(text.split())
    return round(word_count / _WORDS_PER_SECOND, 1)


def build_narration_chunks(script: dict, n: int) -> list[str]:
    """
    Pure function: splits the script's full narration into n roughly-equal
    parts, one per approved asset's scene. No API calls.

    Prefers splitting on sentence boundaries when there are at least n
    sentences. Falls back to an even word-count split when the narration is
    fewer sentences than n (common now that scripts are hard-capped at 2
    beats / ~25-30 words, often written as a single sentence) — this avoids
    producing an empty "." chunk for the last scene(s).
    Falls back to repeating the hook line if there's no narration text at all.
    """
    full_narration = script.get("narration", "").strip()
    n = max(n, 1)

    if not full_narration:
        return [script.get("hook", "")] * n

    sentences = [s.strip() for s in full_narration.split(".") if s.strip()]

    if len(sentences) >= n:
        chunk_size = max(1, len(sentences) // n)
        chunks = []
        for i in range(n):
            start = i * chunk_size
            end = start + chunk_size if i < n - 1 else len(sentences)
            chunks.append(". ".join(sentences[start:end]) + ".")
        return chunks

    # Not enough sentences to give every scene one — split by word count instead.
    words = full_narration.split()
    chunk_size = max(1, len(words) // n)
    chunks = []
    for i in range(n):
        start = i * chunk_size
        end = start + chunk_size if i < n - 1 else len(words)
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words) if chunk_words else full_narration)
    return chunks


async def _synthesize_one(session: aiohttp.ClientSession, scene_id: str, text: str) -> TTSSegment | None:
    if not text.strip():
        return None
    try:
        audio_bytes = await synthesize_speech(session, text)
        file_name = f"tts_{scene_id}_{uuid.uuid4().hex[:6]}.mp3"
        audio_url = await upload_asset(
            session,
            file_bytes=audio_bytes,
            file_name=file_name,
            content_type="audio/mpeg",
        )
        return TTSSegment(
            scene_id=scene_id,
            audio_url=audio_url,
            duration_seconds=_estimate_duration(text),
            text=text,
        )
    except (ElevenLabsError, FloraGenerationError) as exc:
        logger.warning("generate_tts: scene %s failed — %s", scene_id, exc)
        return None


async def generate_tts(state: AgentState) -> AgentState:
    """
    Generate one TTS clip per approved media asset's beat narration.
    Splits the full script narration into N roughly-equal sentence groups
    (one per approved asset) rather than calling ElevenLabs' timestamp-
    alignment API (see MEDIA_PIPELINE_PLAN.md section 7.5 for why).
    """
    script = state.get("script") or {}
    media_plan = state.get("media_plan") or []
    approved = [a for a in media_plan if a["status"] == "approved"]

    if not approved:
        return {**state, "tts_segments": []}

    narration_chunks = build_narration_chunks(script, len(approved))

    async with aiohttp.ClientSession() as session:
        tasks = [
            _synthesize_one(session, asset["scene_id"], chunk)
            for asset, chunk in zip(approved, narration_chunks)
        ]
        results = await asyncio.gather(*tasks) if tasks else []

    tts_segments = [r for r in results if r is not None]

    if not tts_segments:
        logger.warning("generate_tts: all TTS calls failed — proceeding without audio")

    return {**state, "tts_segments": tts_segments}
