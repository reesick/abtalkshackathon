"""
Template semantic enrichment (meme spec sections 9, 11, 74).

HONEST LIMITATION: the spec calls for a vision-capable model to inspect
each template image and produce semantic metadata (meaning, visual
structure, panels, character roles, humour mechanisms, best/bad topics).
This project's only available model provider is AWS Bedrock with Mistral
text models (mistral.mistral-7b-instruct-v0:2 / mixtral-8x7b) — no
vision-capable model is available on this account (confirmed in earlier
sessions: Claude/vision models are rejected). This function is written to
the correct interface and DOES call a real model, but degrades to
text-only enrichment using the template NAME as the only signal, not
actual image content. This is flagged in the enrichment output itself so
nothing pretends to be vision analysis that didn't happen.

If a vision-capable model becomes available later, only the prompt/image
payload in _enrich_one needs to change — the interface and DB write path
stay the same.
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST, repair_json
from db.models import MemeTemplate, get_session

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.3, max_tokens=768)

_SYSTEM = """\
You are annotating a meme template with semantic metadata for a humour
generation system. You are NOT being shown the actual template image —
only its name — because no vision-capable model is available. Use your
general knowledge of well-known meme templates by name. If you don't
recognize the template well enough to say anything specific and accurate,
say so honestly in "confidence_note" rather than inventing plausible-
sounding details.

Return ONLY a JSON object with this exact shape:
{
  "semantic_format": "<short label, e.g. comparison, underreaction, choice, escalation, confession>",
  "template_family": "<coarser category matching semantic_format unless a broader grouping fits better>",
  "visual_grammar": {"<free-form key>": "<value>"},
  "humour_mechanisms": ["<2-4 from: absurdity, irony, contrast, understatement, overstatement, expectation_vs_reality, role_reversal, misdirection, incongruity, self_deprecation, observational, social_comparison, false_equivalence, escalation, deadpan, sarcasm, wordplay, relatable_struggle, status_inversion, analogy>"],
  "best_for": ["<2-4 short topic types this template suits>"],
  "bad_for": ["<1-2 topic types this template is wrong for>"],
  "caption_structure": {"text_areas": <int>, "short_text_preferred": <bool>},
  "confidence_note": "<honest one-line note on how confident this annotation is, given no image was actually seen>"
}
"""


async def _enrich_one(template_name: str) -> dict | None:
    try:
        response = await _llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=f"Template name: {template_name}"),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(repair_json(raw.strip()))
    except Exception as exc:
        logger.warning("meme.semantics: enrichment failed for '%s' — %s", template_name, exc)
        return None


async def enrich_templates(template_ids: list[str]) -> dict:
    """
    Spec section 74: only enrich new/missing-metadata/explicitly-refreshed
    templates — never re-run this on every sync. Callers are responsible
    for passing only the template_ids that actually need enrichment.
    """
    enriched, failed = 0, 0
    for tid in template_ids:
        with get_session() as db:
            row = db.get(MemeTemplate, tid)
            if row is None:
                failed += 1
                continue
            name = row.name

        result = await _enrich_one(name)
        if result is None:
            failed += 1
            continue

        with get_session() as db:
            row = db.get(MemeTemplate, tid)
            if row is None:
                continue
            row.semantic_format = result.get("semantic_format")
            row.template_family = result.get("template_family")
            row.visual_grammar_json = json.dumps(result.get("visual_grammar", {}))
            row.humour_mechanisms_json = json.dumps(result.get("humour_mechanisms", []))
            row.best_for_json = json.dumps(result.get("best_for", []))
            row.bad_for_json = json.dumps(result.get("bad_for", []))
            row.caption_structure_json = json.dumps(result.get("caption_structure", {}))
        enriched += 1
        logger.info(
            "meme.semantics: enriched '%s' (confidence note: %s)",
            name, result.get("confidence_note", "(none given)"),
        )

    return {"enriched": enriched, "failed": failed}


def templates_needing_enrichment(limit: int = 50) -> list[str]:
    """Returns template IDs with no semantic_format set yet."""
    with get_session() as db:
        rows = (
            db.query(MemeTemplate)
            .filter(MemeTemplate.semantic_format.is_(None))
            .filter(MemeTemplate.active.is_(True))
            .limit(limit)
            .all()
        )
        return [r.id for r in rows]
