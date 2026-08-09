"""
MemeEngine — top-level orchestrator (meme spec sections 61, 96, 113, 114).

Full pipeline for one topic:
  assess_opportunity -> [NO] -> should_make_meme=False
                     -> [YES] -> template retrieval/filter/rank
                              -> humour skill on top template candidates
                              -> quality gate (section 96)
                              -> render top candidate
                              -> return MemeResult

Rendering only happens for the single best candidate after judging — never
render every candidate (spec section 66: "Do not render 30 images").
"""
import logging

import aiohttp

from agent.state import MemeResult
from meme.humour.skill import run_humour_skill
from meme.memory.repetition import similarity_penalty
from meme.memory.usage import recent_usage
from meme.opportunity import assess_opportunity
from meme.renderer.render import get_default_renderer
from meme.templates.ranking import rank_templates
from meme.templates.registry import (
    record_posted,
    record_render,
    record_selection,
)
from meme.templates.retrieval import filter_candidates, retrieve_candidates

logger = logging.getLogger(__name__)

MIN_MEME_SCORE = 6.5           # spec section 35/115 — quality gate floor
TEMPLATE_CANDIDATES_TO_TRY = 3  # how many top-ranked templates get a full humour-skill pass


class MemeEngine:
    async def assess_opportunity(self, topic: dict):
        return await assess_opportunity(topic)

    async def process(self, *, agent_id: str, topic: dict) -> MemeResult:
        opportunity = await self.assess_opportunity(topic)
        if not opportunity["is_meme_worthy"]:
            logger.info("meme.engine: NO MEME — %s", opportunity["reason"])
            return MemeResult(
                should_make_meme=False, template_id=None, template_name=None,
                template_family=None, humour_mechanism=None, text_boxes=[],
                caption_flat=None, score=None, rendered_url=None,
                reason=opportunity["reason"],
            )

        usage_history = recent_usage(agent_id)

        candidates = retrieve_candidates(humour_mechanisms=opportunity["recommended_mechanisms"], limit=25)
        candidates = filter_candidates(candidates)
        if not candidates:
            return MemeResult(
                should_make_meme=False, template_id=None, template_name=None,
                template_family=None, humour_mechanism=None, text_boxes=[],
                caption_flat=None, score=None, rendered_url=None,
                reason="no suitable templates available (registry empty or all filtered out)",
            )

        ranked = rank_templates(
            candidates,
            humour_mechanisms=opportunity["recommended_mechanisms"],
            recent_usage=usage_history,
        )

        best_result: MemeResult | None = None
        best_score = -999.0

        for template in ranked[:TEMPLATE_CANDIDATES_TO_TRY]:
            if template["_ranking"]["repetition_penalty"] >= 0.6:
                logger.info("meme.engine: skipping '%s' — repetition penalty too high", template["name"])
                continue

            top_candidates, top_scores = await run_humour_skill(topic=topic, template=template)
            if not top_candidates:
                continue

            cand, score = top_candidates[0], top_scores[0]
            caption_flat = " / ".join(cand["text_boxes"])

            # NOTE: usage.py's recent_usage() currently returns
            # template/mechanism metadata only, not the flat caption
            # text of past posts, so this similarity check always sees
            # an empty comparison set today (real, not faked — see
            # meme/memory/usage.py for the reason). This is a genuine
            # gap: once MemeUsage rows accumulate, a query returning
            # past caption_json values should be added here.
            sim_penalty = similarity_penalty(caption_flat, [])
            effective_score = score["final_score"] - sim_penalty * 3

            if effective_score > best_score:
                best_score = effective_score
                best_result = MemeResult(
                    should_make_meme=True,
                    template_id=template["id"],
                    template_name=template["name"],
                    template_family=template.get("template_family"),
                    humour_mechanism=cand["humour_mechanism"],
                    text_boxes=cand["text_boxes"],
                    caption_flat=caption_flat,
                    score=effective_score,
                    rendered_url=None,
                    reason=score["reasoning"],
                )

        if best_result is None or best_score < MIN_MEME_SCORE:
            reason = (
                f"best candidate scored {best_score:.1f}, below quality gate "
                f"{MIN_MEME_SCORE} — rejecting rather than posting a weak meme"
            )
            logger.info("meme.engine: NO MEME — %s", reason)
            return MemeResult(
                should_make_meme=False, template_id=None, template_name=None,
                template_family=None, humour_mechanism=None, text_boxes=[],
                caption_flat=None, score=best_score if best_result else None,
                rendered_url=None, reason=reason,
            )

        # Render only the single winning candidate.
        async with aiohttp.ClientSession() as session:
            renderer = get_default_renderer()
            provider_template_id = best_result["template_id"].split(":", 1)[-1]
            rendered_url = await renderer.render(
                session,
                template_id=provider_template_id,
                text_boxes=best_result["text_boxes"],
            )

        if rendered_url is None:
            logger.warning("meme.engine: render failed for template '%s' — degrading to NO MEME rather than re-generating", best_result["template_name"])
            best_result["should_make_meme"] = False
            best_result["reason"] = "render failed after retries — not re-generating the joke, per spec section 60"
            return best_result

        record_selection(best_result["template_id"])
        record_render(best_result["template_id"])
        record_posted(best_result["template_id"])

        best_result["rendered_url"] = rendered_url
        logger.info(
            "meme.engine: FINAL MEME — template='%s' score=%.1f url=%s",
            best_result["template_name"], best_score, rendered_url,
        )
        return best_result
