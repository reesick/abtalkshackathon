"""
Humour Skill — Stage 1: Observation (meme spec sections 21, 22, 89).

Paper reference: HumorSkills' "Visual Detail Extraction" stage (Kim &
Chilton 2025, section 3.1.1) uses GPT-4o's vision to describe who/what/
where in the image before any joke attempt. This project has no
vision-capable model available (Bedrock account exposes Mistral text
models only — see meme/templates/semantics.py for the same honest note).

Adaptation: observation here works from the TEMPLATE'S SEMANTIC METADATA
(visual_grammar, semantic_format, best_for/bad_for) plus the TOPIC, not
from actually looking at the template image. This is explicitly weaker
than the paper's method and is labeled as such in the output so downstream
stages (and any human reviewing output) know this isn't real visual
grounding.

The stage still follows the paper's key discipline: separate OBSERVATION
from INTERPRETATION, and don't jump straight to jokes (section 22).
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST, repair_json

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.4, max_tokens=768)

_SYSTEM = """\
You are the Observation stage of a humour-generation pipeline. Your job is
ONLY to observe, not to joke. Do not write anything funny in this step.

You do not have the actual template image — only its declared semantic
metadata (a template's visual grammar as previously annotated). Work from
that metadata plus the topic. Do not invent visual details that aren't in
the metadata; if the metadata is thin, say so plainly rather than filling
in plausible-sounding details.

Answer, in the structure below:
- WHO/WHAT is present (from the template's declared roles/grammar)?
- WHAT relationship or structure does the template establish (e.g. reject
  vs approve, forced choice, escalating panels)?
- WHAT is visually/structurally unusual or notable about this template,
  if the metadata suggests anything?
- WHAT is the obvious way this template is normally used?
- WHAT is a less obvious way it could be used, given the topic?

Return ONLY a JSON object:
{
  "who_what": "...",
  "structural_relationship": "...",
  "notable_details": "...",
  "obvious_use": "...",
  "less_obvious_use": "...",
  "grounding_quality": "<one of: metadata_only, thin_metadata — always metadata_only or thin_metadata, never 'visual' since no image was seen>"
}
"""

_HUMAN = """\
Topic: {topic_title}
Topic summary: {topic_summary}

Template: {template_name}
Semantic format: {semantic_format}
Template family: {template_family}
Visual grammar (declared, not actually seen): {visual_grammar}
Known humour mechanisms for this template: {humour_mechanisms}
"""


async def observe(*, topic: dict, template: dict) -> dict:
    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        topic_summary=(topic.get("summary", "") or "")[:400],
        template_name=template.get("name", ""),
        semantic_format=template.get("semantic_format") or "(unannotated)",
        template_family=template.get("template_family") or "(unannotated)",
        visual_grammar=json.dumps(template.get("visual_grammar", {})),
        humour_mechanisms=", ".join(template.get("humour_mechanisms", [])) or "(none declared)",
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
        observation = json.loads(repair_json(raw.strip()))
    except Exception as exc:
        logger.warning("humour.observation: failed for template '%s' — %s", template.get("name"), exc)
        observation = {
            "who_what": template.get("name", ""),
            "structural_relationship": template.get("semantic_format", ""),
            "notable_details": "(observation generation failed, using template metadata only)",
            "obvious_use": ", ".join(template.get("best_for", [])),
            "less_obvious_use": "",
            "grounding_quality": "thin_metadata",
        }

    observation["_grounding_disclaimer"] = (
        "No vision model available — this observation is derived from "
        "declared template metadata, not actual image inspection."
    )
    return observation
