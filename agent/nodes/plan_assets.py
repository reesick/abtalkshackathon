"""
plan_media_assets node — converts script beats into a structured asset plan
before any image generation happens. Per spec section 4: "the system should
not immediately ask an image model to 'make visuals'. It should first convert
the script into a structured asset plan."
"""
import json
import logging
import uuid

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState, MediaAsset
from agent.style_reference import STYLE_GRAMMAR, STYLE_REFERENCE_IMAGES

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.4, max_tokens=1536)

_SYSTEM = """\
You are a media producer planning visual assets for a short video, given a
script's beats. This is a planning step — you decide WHAT needs to exist,
not the final image prompt wording.

STYLE (locked, do not deviate)
{style_grammar}

For each beat in the script, produce one asset plan entry describing:
- asset_type: what kind of visual this is (character_action, prop, background, graphic)
- visual_role: what this asset contributes to the shot, in plain language
- continuity_notes: anything that must stay consistent with other assets in this plan (e.g. same character, same color accent)

Return ONLY a JSON array, one object per beat, in beat order:
[
  {{"asset_type": "...", "visual_role": "...", "continuity_notes": "..."}},
  ...
]
"""

_HUMAN = """\
Topic: {title}
Script beats:
{beats_block}
"""


def _fallback_plan(beats: list[dict]) -> list[dict]:
    return [
        {
            "asset_type": "character_action",
            "visual_role": beat.get("visual_idea", beat.get("beat", "scene")),
            "continuity_notes": "maintain consistent character and palette across all beats",
        }
        for beat in beats
    ]


async def plan_media_assets(state: AgentState) -> AgentState:
    script = state.get("script") or {}
    beats = script.get("beats", [])
    topic = state.get("selected_topic") or {}

    if not beats:
        return {**state, "media_plan": []}

    beats_block = "\n".join(
        f"{i}. [{b.get('beat', '')}] {b.get('visual_idea', '')}" for i, b in enumerate(beats)
    )
    style_grammar_text = "\n".join(f"- {k}: {v}" for k, v in STYLE_GRAMMAR.items())

    system_prompt = _SYSTEM.format(style_grammar=style_grammar_text)
    human_msg = _HUMAN.format(title=topic.get("title", ""), beats_block=beats_block)

    try:
        response = await _llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_msg),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan_entries = json.loads(raw.strip())
        if not isinstance(plan_entries, list) or len(plan_entries) != len(beats):
            raise ValueError("plan length mismatch")
    except Exception as exc:
        logger.warning("plan_media_assets: LLM planning failed (%s) — using fallback", exc)
        plan_entries = _fallback_plan(beats)

    media_plan: list[MediaAsset] = []
    for i, (beat, entry) in enumerate(zip(beats, plan_entries)):
        media_plan.append(MediaAsset(
            asset_id=f"asset_{i:02d}_{uuid.uuid4().hex[:6]}",
            scene_id=f"scene_{i:02d}",
            asset_type=entry.get("asset_type", "character_action"),
            script_beat=beat.get("beat", ""),
            visual_role=entry.get("visual_role", beat.get("visual_idea", "")),
            prompt="",  # filled in by generate_assets node
            reference_asset=STYLE_REFERENCE_IMAGES,
            continuity_notes=entry.get("continuity_notes", ""),
            reuse=False,
            status="planned",
            output_url=None,
            validation_notes=None,
            retry_count=0,
        ))

    logger.info("plan_media_assets: planned %d assets", len(media_plan))
    return {**state, "media_plan": media_plan}
