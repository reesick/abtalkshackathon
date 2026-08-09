"""
Meme usage memory (meme spec section 40) — records what was actually
posted, backed by db.models.MemeUsage.
"""
import json
import logging
from datetime import datetime

from db.models import MemeUsage, get_session

logger = logging.getLogger(__name__)


def record_usage(
    *,
    agent_id: str,
    post_id: int | None,
    template_id: str,
    template_name: str,
    template_family: str | None,
    humour_mechanism: str | None,
    topic_title: str,
    topic_source: str,
    text_boxes: list[str],
    humour_score: float | None,
    judge_score: dict | None,
) -> None:
    with get_session() as db:
        db.add(MemeUsage(
            agent_id=agent_id,
            post_id=post_id,
            template_id=template_id,
            template_family=template_family,
            humour_mechanism=humour_mechanism,
            topic_title=topic_title,
            topic_source=topic_source,
            caption_json=json.dumps(text_boxes),
            humour_score=int(humour_score) if humour_score is not None else None,
            judge_score_json=json.dumps(judge_score) if judge_score else None,
            published_at=datetime.utcnow(),
        ))
    logger.info("meme.memory.usage: recorded template=%s mechanism=%s", template_name, humour_mechanism)


def recent_usage(agent_id: str, limit: int = 20) -> list[dict]:
    """
    Returns recent usage rows shaped for cooldown.py's repetition_penalty()
    — most recent first. Note the key is "template_name" for compatibility
    with cooldown.py, resolved via a join-free lookup (we store template_id,
    but cooldown logic works off name/family/mechanism which we also store
    or can derive).
    """
    with get_session() as db:
        rows = (
            db.query(MemeUsage)
            .filter(MemeUsage.agent_id == agent_id)
            .order_by(MemeUsage.created_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for r in rows:
            result.append({
                "template_id": r.template_id,
                "template_name": r.template_id.split(":")[-1] if r.template_id else None,
                "template_family": r.template_family,
                "humour_mechanism": r.humour_mechanism,
                "created_at": r.created_at,
            })
        return result


def todays_usage(agent_id: str) -> list[dict]:
    """Spec section 45 — daily diversity caps need just-today's usage."""
    today = datetime.utcnow().date()
    all_recent = recent_usage(agent_id, limit=50)
    return [u for u in all_recent if u["created_at"] and u["created_at"].date() == today]
