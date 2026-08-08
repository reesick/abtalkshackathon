"""
ElevenLabs TTS client. One call per script beat (see MEDIA_PIPELINE_PLAN.md
section 7.5) — avoids needing the timestamp-alignment API entirely, since
each beat's narration becomes its own audio clip with a known duration.
"""
import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "TX3LPaxmHKxFdv7VOQHJ")  # Liam - premade, free-tier usable
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")


class ElevenLabsError(Exception):
    pass


async def synthesize_speech(session: aiohttp.ClientSession, text: str) -> bytes:
    """Call ElevenLabs TTS for a single beat's narration text. Returns raw audio bytes (mpeg)."""
    async with session.post(
        f"{ELEVENLABS_API_BASE}/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        },
        timeout=aiohttp.ClientTimeout(total=30),
    ) as resp:
        if resp.status != 200:
            body = await resp.text()
            raise ElevenLabsError(f"TTS failed: {resp.status} {body}")
        audio_bytes = await resp.read()

    logger.info("elevenlabs_client: synthesized %d bytes for %d chars", len(audio_bytes), len(text))
    return audio_bytes
