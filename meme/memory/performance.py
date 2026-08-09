"""
Performance learning loop (meme spec sections 69, 70). Associates
published-meme engagement with template/mechanism for future selection
bias. No real engagement data exists yet (this agent doesn't currently
pull social engagement metrics from anywhere) — this module defines the
real update path so it's ready the moment that data becomes available,
rather than faking numbers now.
"""
import logging

from db.models import MemeTemplate, get_session

logger = logging.getLogger(__name__)


def update_template_performance(template_id: str, *, humour_score: float, engagement_score: float | None = None) -> None:
    """
    Rolling-average update to MemeTemplate.average_humour_score (and
    average_engagement_score once real engagement data exists). Spec
    section 70: do not let historical performance dominate forever — this
    is why ranking.py only weights historical_performance at 0.15 and
    exploration.py-equivalent logic in templates/ranking.py reserves
    exploration probability regardless of this score.
    """
    with get_session() as db:
        row = db.get(MemeTemplate, template_id)
        if row is None:
            logger.warning("meme.memory.performance: template %s not found", template_id)
            return

        prior = row.average_humour_score
        row.average_humour_score = int(humour_score) if prior is None else int((prior + humour_score) / 2)

        if engagement_score is not None:
            prior_eng = row.average_engagement_score
            row.average_engagement_score = (
                int(engagement_score) if prior_eng is None else int((prior_eng + engagement_score) / 2)
            )

    logger.info("meme.memory.performance: updated template=%s humour_score=%.1f", template_id, humour_score)
