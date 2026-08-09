"""
Humour Skill — Stage 2: Visual Humour Ideation (meme spec sections 23, 26,
91). Paper reference: HumorSkills section 3.1.2 — separate stage that
looks for potentially humorous elements (contrast, odd proportions,
emotional mismatch) before writing captions.

Divergent phase: target 8-12 meaningfully different angles, not 8 versions
of the same joke (spec section 26).
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, repair_json

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.9, max_tokens=1536)

_SYSTEM = """\
You are the Visual Humour Ideation stage. Given an observation of a meme
template's structure and a topic, generate 8-12 DISTINCT humour angles.

Each angle must use a genuinely different humour mechanism or point of
view — not 8 rewordings of the same joke. Look for:
- odd proportions / contrast the template structure implies
- role relationships (who has power, who is reacting, who is choosing)
- emotional mismatch between the template's tone and the topic's content
- expectation vs reality within the template's own structure

Do NOT write final captions yet. Write angle DESCRIPTIONS — the comedic
idea, not the joke text.

Return ONLY a JSON array of 8-12 objects:
[
  {"mechanism": "contrast", "angle": "one-sentence description of the comedic idea"},
  ...
]
"""

_HUMAN = """\
Topic: {topic_title}
Topic summary: {topic_summary}

Template: {template_name}
Observation: {observation_json}
"""


async def ideate_visual_humour(*, topic: dict, template: dict, observation: dict) -> list[dict]:
    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        topic_summary=(topic.get("summary", "") or "")[:400],
        template_name=template.get("name", ""),
        observation_json=json.dumps({k: v for k, v in observation.items() if not k.startswith("_")}),
    )

    try:
        response = await _llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=human_msg),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        angles = json.loads(repair_json(raw.strip()))
        if not isinstance(angles, list) or not angles:
            raise ValueError("empty or non-list angles")
    except Exception as exc:
        logger.warning("humour.ideation: failed for template '%s' — %s", template.get("name"), exc)
        # Minimal fallback drawn from the template's own declared mechanisms
        # rather than fabricating unrelated angles.
        mechanisms = template.get("humour_mechanisms") or ["observational"]
        angles = [{"mechanism": m, "angle": f"a {m} take on {topic.get('title', 'the topic')}"} for m in mechanisms]

    return angles
