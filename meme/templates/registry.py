"""
Template registry — persistent store backed by db.models.MemeTemplate
(meme spec sections 7, 8, 73). Provides the sync (cheap, provider list ->
DB) and lookup operations used by retrieval/ranking. Semantic enrichment
lives in semantics.py and is a separate, infrequent job (section 74).
"""
import json
import logging
from datetime import datetime

from db.models import MemeTemplate, get_session

logger = logging.getLogger(__name__)

# Starter curated set (spec section 10: "50-150 templates", "do not
# manually annotate 1 million templates"). These are pre-annotated with
# semantic metadata so the system has usable semantics from day one,
# without waiting on a vision-enrichment pass we can't run yet (no
# vision-capable model available in this project's Bedrock account —
# see meme/templates/semantics.py for the honest limitation this creates).
CURATED_SEMANTICS: dict[str, dict] = {
    "Drake": {
        "semantic_format": "comparison",
        "template_family": "comparison",
        "visual_grammar": {"panel_1": "reject", "panel_2": "approve"},
        "humour_mechanisms": ["contrast", "preference", "irony"],
        "best_for": ["old vs new", "bad vs good", "traditional workflow vs AI workflow", "choosing between tools"],
        "bad_for": ["serious announcements", "long explanations"],
        "caption_structure": {"text_areas": 2, "short_text_preferred": True},
    },
    "This Is Fine": {
        "semantic_format": "underreaction",
        "template_family": "underreaction",
        "visual_grammar": {"situation": "character remains calm during obvious disaster"},
        "humour_mechanisms": ["understatement", "irony", "escalation"],
        "best_for": ["bugs", "production failures", "AI hallucinations", "startup chaos", "broken infrastructure"],
        "bad_for": ["genuinely serious incidents"],
        "caption_structure": {"text_areas": 1, "short_text_preferred": True},
    },
    "Two Buttons": {
        "semantic_format": "impossible_choice",
        "template_family": "choice",
        "visual_grammar": {"character": "forced to choose between two options"},
        "humour_mechanisms": ["choice", "conflict", "tradeoff"],
        "best_for": ["developer decisions", "AI model comparisons", "tool choices", "contradictory requirements"],
        "bad_for": ["single-option announcements"],
        "caption_structure": {"text_areas": 2, "short_text_preferred": True},
    },
    "Distracted Boyfriend": {
        "semantic_format": "comparison",
        "template_family": "comparison",
        "visual_grammar": {"character": "abandons current option for a flashier new one"},
        "humour_mechanisms": ["contrast", "temptation", "irony"],
        "best_for": ["new tool hype", "switching frameworks", "abandoning old workflow"],
        "bad_for": ["serious topics"],
        "caption_structure": {"text_areas": 3, "short_text_preferred": True},
    },
    "Galaxy Brain": {
        "semantic_format": "escalation",
        "template_family": "escalation",
        "visual_grammar": {"panels": "ascending absurdity/enlightenment"},
        "humour_mechanisms": ["escalation", "absurdity", "overstatement"],
        "best_for": ["overengineering", "escalating workarounds", "increasingly unhinged solutions"],
        "bad_for": ["single simple facts"],
        "caption_structure": {"text_areas": 4, "short_text_preferred": True},
    },
    "Expanding Brain": {
        "semantic_format": "escalation",
        "template_family": "escalation",
        "visual_grammar": {"panels": "ascending absurdity/enlightenment"},
        "humour_mechanisms": ["escalation", "absurdity", "overstatement"],
        "best_for": ["overengineering", "escalating workarounds", "increasingly unhinged solutions"],
        "bad_for": ["single simple facts"],
        "caption_structure": {"text_areas": 4, "short_text_preferred": True},
    },
    "Change My Mind": {
        "semantic_format": "blunt_stance",
        "template_family": "confession",
        "visual_grammar": {"character": "sits behind a sign stating an opinion"},
        "humour_mechanisms": ["deadpan", "sarcasm", "status_inversion"],
        "best_for": ["contrarian takes", "unpopular opinions in dev culture"],
        "bad_for": ["neutral factual statements"],
        "caption_structure": {"text_areas": 1, "short_text_preferred": False},
    },
    "Roll Safe Think About It": {
        "semantic_format": "false_wisdom",
        "template_family": "confession",
        "visual_grammar": {"character": "taps head, implying clever workaround"},
        "humour_mechanisms": ["false_equivalence", "irony", "self_deprecation"],
        "best_for": ["bad workarounds framed as smart", "avoiding real fixes"],
        "bad_for": ["genuinely good solutions"],
        "caption_structure": {"text_areas": 1, "short_text_preferred": True},
    },
    "Is This a Pigeon": {
        "semantic_format": "misidentification",
        "template_family": "misidentification",
        "visual_grammar": {"character": "confidently mislabels something ordinary"},
        "humour_mechanisms": ["misdirection", "absurdity", "incongruity"],
        "best_for": ["mislabeling hype as innovation", "confused categorization"],
        "bad_for": ["accurate technical claims"],
        "caption_structure": {"text_areas": 3, "short_text_preferred": True},
    },
    "Waiting Skeleton": {
        "semantic_format": "prolonged_wait",
        "template_family": "underreaction",
        "visual_grammar": {"character": "waits so long they become a skeleton"},
        "humour_mechanisms": ["overstatement", "escalation", "relatable_struggle"],
        "best_for": ["slow builds", "long-awaited releases", "waiting on API responses"],
        "bad_for": ["fast/instant events"],
        "caption_structure": {"text_areas": 1, "short_text_preferred": True},
    },
}


def _template_id(provider: str, provider_template_id: str) -> str:
    return f"{provider}:{provider_template_id}"


def sync_meme_templates(raw_templates: list[dict], provider: str = "imgflip") -> dict:
    """
    Cheap sync operation (spec section 73): fetch provider templates, upsert
    metadata, preserve existing semantic annotations, update popularity,
    detect new templates. Never resets last_used_at/times_used/performance/
    semantic metadata for existing rows.

    raw_templates: the list returned by meme.providers.imgflip.get_memes().
    Returns a summary dict for logging/testing.
    """
    created, updated = 0, 0
    with get_session() as db:
        for rank, tpl in enumerate(raw_templates):
            provider_template_id = str(tpl["id"])
            tid = _template_id(provider, provider_template_id)
            existing = db.get(MemeTemplate, tid)

            if existing is None:
                curated = CURATED_SEMANTICS.get(tpl["name"])
                row = MemeTemplate(
                    id=tid,
                    provider=provider,
                    provider_template_id=provider_template_id,
                    name=tpl["name"],
                    image_url=tpl["url"],
                    width=tpl.get("width"),
                    height=tpl.get("height"),
                    box_count=tpl.get("box_count"),
                    popularity_score=len(raw_templates) - rank,  # higher rank -> higher score
                )
                if curated:
                    row.semantic_format = curated["semantic_format"]
                    row.template_family = curated["template_family"]
                    row.visual_grammar_json = json.dumps(curated["visual_grammar"])
                    row.humour_mechanisms_json = json.dumps(curated["humour_mechanisms"])
                    row.best_for_json = json.dumps(curated["best_for"])
                    row.bad_for_json = json.dumps(curated["bad_for"])
                    row.caption_structure_json = json.dumps(curated["caption_structure"])
                db.add(row)
                created += 1
            else:
                # Update only provider-sourced fields; never touch semantic
                # metadata, usage counters, or last_used_at here.
                existing.name = tpl["name"]
                existing.image_url = tpl["url"]
                existing.width = tpl.get("width")
                existing.height = tpl.get("height")
                existing.box_count = tpl.get("box_count")
                existing.popularity_score = len(raw_templates) - rank
                existing.updated_at = datetime.utcnow()
                updated += 1

    logger.info("meme.templates.registry: sync created=%d updated=%d", created, updated)
    return {"created": created, "updated": updated, "total_seen": len(raw_templates)}


def get_template(template_id: str) -> MemeTemplate | None:
    with get_session() as db:
        return db.get(MemeTemplate, template_id)


def list_active_templates(limit: int = 150) -> list[dict]:
    """Returns plain dicts (detached from session) for use outside the DB context."""
    with get_session() as db:
        rows = (
            db.query(MemeTemplate)
            .filter(MemeTemplate.active.is_(True))
            .order_by(MemeTemplate.popularity_score.desc())
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: MemeTemplate) -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "provider_template_id": row.provider_template_id,
        "name": row.name,
        "image_url": row.image_url,
        "width": row.width,
        "height": row.height,
        "box_count": row.box_count,
        "semantic_format": row.semantic_format,
        "template_family": row.template_family,
        "visual_grammar": json.loads(row.visual_grammar_json) if row.visual_grammar_json else {},
        "humour_mechanisms": json.loads(row.humour_mechanisms_json) if row.humour_mechanisms_json else [],
        "best_for": json.loads(row.best_for_json) if row.best_for_json else [],
        "bad_for": json.loads(row.bad_for_json) if row.bad_for_json else [],
        "caption_structure": json.loads(row.caption_structure_json) if row.caption_structure_json else {},
        "popularity_score": row.popularity_score,
        "freshness_score": row.freshness_score,
        "times_selected": row.times_selected,
        "times_rendered": row.times_rendered,
        "times_posted": row.times_posted,
        "last_used_at": row.last_used_at,
        "cooldown_until": row.cooldown_until,
        "average_humour_score": row.average_humour_score,
        "average_engagement_score": row.average_engagement_score,
        "active": row.active,
        "health": row.health,
    }


def record_selection(template_id: str) -> None:
    with get_session() as db:
        row = db.get(MemeTemplate, template_id)
        if row:
            row.times_selected += 1


def record_render(template_id: str) -> None:
    with get_session() as db:
        row = db.get(MemeTemplate, template_id)
        if row:
            row.times_rendered += 1


def record_posted(template_id: str, cooldown_posts: int = 5) -> None:
    """
    Marks a template as used for cooldown purposes (spec section 14).
    cooldown_until is stored as a post-count marker via last_used_at +
    times_posted, since this project's scheduler is tick-based, not
    calendar-based — cooldown.py interprets "posts between uses" using
    times_posted deltas, not wall-clock time.
    """
    with get_session() as db:
        row = db.get(MemeTemplate, template_id)
        if row:
            row.times_posted += 1
            row.last_used_at = datetime.utcnow()
