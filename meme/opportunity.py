"""
Meme opportunity detector (meme spec sections 17, 18, 19, 116). Decides
whether a discovered topic should become a meme at all — "NO MEME" is a
correct, common output, not a failure (spec section 116).
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST, repair_json
from agent.state import MemeOpportunity

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.3, max_tokens=512)

_SYSTEM = """\
You assess whether a discovered AI/tech topic has real comedic potential —
not whether it's interesting, whether it's INHERENTLY FUNNY or ABSURD in a
way a meme could exploit.

Strong meme candidates usually contain: absurdity, unexpected behaviour,
developer pain, AI hype, AI failure, ridiculous product behaviour,
contradiction, strong before/after, unexpected benchmark result,
human-vs-AI contrast, industry irony, relatable workflow pain.

Weak candidates: routine product update, minor API change, dry corporate
announcement, complex research detail with no relatable hook, or anything
touching a genuine tragedy/serious safety incident (never meme those,
regardless of technical content).

First normalise the topic into its event/actors/action/impact/unexpected-
element/contradiction shape before judging it. This is required — do not
skip straight to a yes/no.

Return ONLY a JSON object:
{
  "event": "...", "unexpected_element": "...", "contradiction": "...",
  "is_meme_worthy": true/false,
  "confidence": 0.0-1.0,
  "humour_potential": 0-10,
  "recommended_mechanisms": ["2-4 from: absurdity, irony, contrast, understatement, overstatement, expectation_vs_reality, role_reversal, misdirection, self_deprecation, relatable_struggle, status_inversion"],
  "reason": "one specific sentence grounded in the actual topic, not generic"
}
"""

_HUMAN = """\
Topic: {title}
Source: {source}
Summary: {summary}
"""

MIN_MEME_CONFIDENCE = 0.60


async def assess_opportunity(topic: dict) -> MemeOpportunity:
    human_msg = _HUMAN.format(
        title=topic.get("title", ""),
        source=topic.get("source", ""),
        summary=(topic.get("summary", "") or "")[:400],
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
        result = json.loads(repair_json(raw.strip()))
    except Exception as exc:
        logger.warning("meme.opportunity: assessment failed for '%s' — %s — defaulting to NO MEME", topic.get("title"), exc)
        return MemeOpportunity(
            is_meme_worthy=False,
            confidence=0.0,
            humour_potential=0,
            recommended_mechanisms=[],
            reason=f"opportunity assessment failed ({exc}); defaulting to no meme rather than guessing",
        )

    is_meme_worthy = bool(result.get("is_meme_worthy")) and float(result.get("confidence", 0)) >= MIN_MEME_CONFIDENCE

    return MemeOpportunity(
        is_meme_worthy=is_meme_worthy,
        confidence=float(result.get("confidence", 0)),
        humour_potential=int(result.get("humour_potential", 0)),
        recommended_mechanisms=result.get("recommended_mechanisms", []),
        reason=result.get("reason", ""),
    )
