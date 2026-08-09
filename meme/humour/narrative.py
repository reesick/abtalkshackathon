"""
Humour Skill — Stage 3: Narrative / Conflict Extrapolation (meme spec
sections 24, 25, 90). Paper reference: HumorSkills section 3.1.3 — finds
narratives OUTSIDE the literal template/topic that can be related to it
through analogy, using relatable life-domain conflicts.

This is the stage that turns "developer chooses between two models" into
"me choosing between the model that's smarter and the one whose API won't
randomly explode" — the analogy, not the literal description.
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, repair_json

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.9, max_tokens=1024)

_NARRATIVE_DOMAINS = [
    "developer life", "startup life", "workplace behaviour", "internet culture",
    "AI hype", "AI anxiety", "tool addiction", "procrastination", "technical debt",
    "shipping", "bugs", "documentation", "meetings", "deadlines",
    "performance anxiety", "career anxiety",
]

_SYSTEM = """\
You are the Narrative and Conflict Extrapolation stage. Your job is to find
relatable real-world conflicts that are NOT literally the topic, but share
its emotional or structural shape — an analogy the audience will recognize.

Draw from these relatable domains, using only what naturally fits (do not
force one if it doesn't fit): {domains}

Given the topic and the humour angles already generated, produce 3-6
narrative analogies. Each should be a short, concrete, relatable scenario —
not a restatement of the topic.

Return ONLY a JSON array:
[
  {{"narrative": "short relatable scenario", "domain": "one of the domains above", "connects_to_angle": "which angle/mechanism this extends"}},
  ...
]
"""

_HUMAN = """\
Topic: {topic_title}
Topic summary: {topic_summary}

Humour angles already generated:
{angles_block}
"""


async def extrapolate_narratives(*, topic: dict, angles: list[dict]) -> list[dict]:
    angles_block = "\n".join(f"- [{a.get('mechanism', '')}] {a.get('angle', '')}" for a in angles)

    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        topic_summary=(topic.get("summary", "") or "")[:400],
        angles_block=angles_block or "(none)",
    )
    system_msg = _SYSTEM.format(domains=", ".join(_NARRATIVE_DOMAINS))

    try:
        response = await _llm.ainvoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=human_msg),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        narratives = json.loads(repair_json(raw.strip()))
        if not isinstance(narratives, list):
            raise ValueError("non-list narratives")
    except Exception as exc:
        logger.warning("humour.narrative: failed — %s", exc)
        narratives = []

    return narratives
