"""
Humour Skill orchestrator (meme spec sections 20, 88). Runs the full
research-inspired staged workflow for ONE template candidate:

  observe -> ideate_visual_humour -> extrapolate_narratives ->
  generate_captions -> judge_candidates -> top N

Each stage is a separate LLM call (or heuristic fallback) — generation and
evaluation are never the same call (spec section 92).
"""
import logging

from agent.state import MemeCaptionCandidate, MemeJudgeScore
from meme.humour import caption, ideation, narrative, observation, ranking

logger = logging.getLogger(__name__)

DEFAULT_AUDIENCE_PROFILE = {
    "age_band": "20s-30s",
    "platform": "X/LinkedIn/Instagram crossposting",
    "technicality": "high",
    "humour_style": "deadpan, developer-relatable, low slang",
    "slang_tolerance": "low-medium",
    "cultural_context": "AI/ML builder and developer culture, not general Gen-Z internet culture",
}


async def run_humour_skill(
    *,
    topic: dict,
    template: dict,
    audience_profile: dict | None = None,
    caption_count: int = 24,
    finalists: int = 3,
) -> tuple[list[MemeCaptionCandidate], list[MemeJudgeScore]]:
    audience_profile = audience_profile or DEFAULT_AUDIENCE_PROFILE

    obs = await observation.observe(topic=topic, template=template)
    logger.info("humour.skill: observation done for '%s' (grounding=%s)", template.get("name"), obs.get("grounding_quality"))

    angles = await ideation.ideate_visual_humour(topic=topic, template=template, observation=obs)
    logger.info("humour.skill: %d angles generated", len(angles))

    narratives = await narrative.extrapolate_narratives(topic=topic, angles=angles)
    logger.info("humour.skill: %d narrative analogies generated", len(narratives))

    candidates = await caption.generate_captions(
        topic=topic,
        template=template,
        observation=obs,
        angles=angles,
        narratives=narratives,
        audience_profile=audience_profile,
        caption_count=caption_count,
    )
    if not candidates:
        logger.warning("humour.skill: no caption candidates generated for '%s'", template.get("name"))
        return [], []

    scores = await ranking.judge_candidates(topic=topic, template=template, candidates=candidates)

    # Sort candidates+scores together by final_score, return top N of each,
    # aligned by index.
    paired = sorted(zip(candidates, scores), key=lambda cs: cs[1]["final_score"], reverse=True)
    top = paired[:finalists]
    if not top:
        return [], []
    top_candidates, top_scores = zip(*top)
    return list(top_candidates), list(top_scores)
