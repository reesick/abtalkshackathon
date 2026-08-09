"""
Humour Skill — Stage 4: Caption Generation (meme spec sections 27, 28, 29,
51, 56). Paper reference: HumorSkills section 3.1.4 — generates a large
candidate pool (target 20-30) before ranking, favoring quantity/diversity
over quality at this stage, split across image-focused and narrative-driven
caption types.

Captions are ORIGINAL — generated from template + topic + humour angle,
never copied from existing meme sites (spec section 56/57).
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, repair_json
from agent.state import MemeCaptionCandidate

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=1.0, max_tokens=4096)

_SYSTEM = """\
You write original meme captions. You will be given a template's text-box
structure, a topic, humour angles, and (optionally) narrative analogies.
Generate {caption_count} caption candidates total, distributed across BOTH:
- image-focused: directly uses the template's literal structure/roles
- narrative-driven: the template is a metaphor for one of the given narratives

Every candidate must fill exactly {box_count} text box(es), in order.

BANNED — never write these, they are generic AI-slop giveaways:
- "POV:" openers
- "bro really said..."
- "AI is taking over 😂"
- "we are cooked 💀"
- "this is literally me"
- explaining the joke after the punchline
- generic corporate/inspirational phrasing

Favor: specificity, brevity, a clear setup + unexpected turn, natural
phrasing a real person would type. Do not force slang if it doesn't fit
the audience profile given.

Audience profile: {audience_profile}

Return ONLY a JSON array of exactly {caption_count} objects:
[
  {{"humour_mechanism": "...", "angle_type": "image_focused", "text_boxes": ["...", "..."], "narrative_used": null}},
  {{"humour_mechanism": "...", "angle_type": "narrative_driven", "text_boxes": ["...", "..."], "narrative_used": "the narrative sentence this used"}}
]
"""

_HUMAN = """\
Topic: {topic_title}
Topic summary: {topic_summary}

Template: {template_name} ({box_count} text box(es))
Observation: {observation_json}

Humour angles:
{angles_block}

Narrative analogies available:
{narratives_block}
"""


async def generate_captions(
    *,
    topic: dict,
    template: dict,
    observation: dict,
    angles: list[dict],
    narratives: list[dict],
    audience_profile: dict,
    caption_count: int = 24,
) -> list[MemeCaptionCandidate]:
    box_count = max(template.get("box_count") or 2, 1)

    angles_block = "\n".join(f"- [{a.get('mechanism', '')}] {a.get('angle', '')}" for a in angles) or "(none)"
    narratives_block = "\n".join(
        f"- [{n.get('domain', '')}] {n.get('narrative', '')}" for n in narratives
    ) or "(none — image-focused captions only)"

    system_msg = _SYSTEM.format(
        caption_count=caption_count,
        box_count=box_count,
        audience_profile=json.dumps(audience_profile),
    )
    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        topic_summary=(topic.get("summary", "") or "")[:400],
        template_name=template.get("name", ""),
        box_count=box_count,
        observation_json=json.dumps({k: v for k, v in observation.items() if not k.startswith("_")}),
        angles_block=angles_block,
        narratives_block=narratives_block,
    )

async def _generate_once(*, system_msg: str, human_msg: str, expected_count: int) -> list[dict] | None:
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
        raw_candidates = json.loads(repair_json(raw.strip()))
        if not isinstance(raw_candidates, list) or not raw_candidates:
            raise ValueError("empty or non-list captions")
        return raw_candidates
    except Exception as exc:
        logger.warning("humour.caption: generation attempt failed — %s", exc)
        return None


async def generate_captions(
    *,
    topic: dict,
    template: dict,
    observation: dict,
    angles: list[dict],
    narratives: list[dict],
    audience_profile: dict,
    caption_count: int = 24,
) -> list[MemeCaptionCandidate]:
    box_count = max(template.get("box_count") or 2, 1)

    angles_block = "\n".join(f"- [{a.get('mechanism', '')}] {a.get('angle', '')}" for a in angles) or "(none)"
    narratives_block = "\n".join(
        f"- [{n.get('domain', '')}] {n.get('narrative', '')}" for n in narratives
    ) or "(none — image-focused captions only)"

    system_msg = _SYSTEM.format(
        caption_count=caption_count,
        box_count=box_count,
        audience_profile=json.dumps(audience_profile),
    )
    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        topic_summary=(topic.get("summary", "") or "")[:400],
        template_name=template.get("name", ""),
        box_count=box_count,
        observation_json=json.dumps({k: v for k, v in observation.items() if not k.startswith("_")}),
        angles_block=angles_block,
        narratives_block=narratives_block,
    )

    # One retry on a fresh call before giving up — truncation/malformed
    # JSON at temperature=1.0 on a long array is common but not
    # deterministic (observed directly: same prompt succeeded on retry).
    raw_candidates = await _generate_once(system_msg=system_msg, human_msg=human_msg, expected_count=caption_count)
    if raw_candidates is None:
        raw_candidates = await _generate_once(system_msg=system_msg, human_msg=human_msg, expected_count=caption_count)
    if raw_candidates is None:
        logger.warning("humour.caption: generation failed twice for template '%s' — returning empty", template.get("name"))
        raw_candidates = []

    candidates: list[MemeCaptionCandidate] = []
    for c in raw_candidates:
        text_boxes = c.get("text_boxes") or []
        if len(text_boxes) != box_count:
            # Pad or trim to the required box count rather than reject the
            # whole candidate outright — a near-miss caption is still
            # useful ranking signal.
            text_boxes = (text_boxes + [""] * box_count)[:box_count]
        candidates.append(MemeCaptionCandidate(
            template_id=template["id"],
            humour_mechanism=c.get("humour_mechanism", "observational"),
            angle_type=c.get("angle_type", "image_focused"),
            text_boxes=text_boxes,
            narrative_used=c.get("narrative_used"),
        ))

    logger.info("humour.caption: generated %d/%d requested candidates for '%s'", len(candidates), caption_count, template.get("name"))
    return candidates
