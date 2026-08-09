"""
Humour Skill — Stage 5: Caption Ranking / Judge (meme spec sections 31-35,
66-68, 92, 93). Paper reference: HumorSkills section 3.1.5 — a dedicated
"Gen-Z humor expert" agent, SEPARATE from the generation call, ranks all
candidates. Generation and evaluation must never be the same call (spec
section 92: "Do not let the same generation prompt decide 'I wrote this,
therefore it is funny.'").

Multimodal judging (spec section 66-67, "does the text fit the rendered
image") is not possible here — no vision model available (same limitation
noted in observation.py/semantics.py). The judge below scores from
template metadata + caption text only, and this is logged honestly rather
than silently pretending to have seen a rendered preview.
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, repair_json
from agent.state import MemeCaptionCandidate, MemeJudgeScore
from meme.humour.safety import is_ai_ish, is_unsafe, caption_text_fits

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.3, max_tokens=4096)

_SYSTEM = """\
You are a dedicated humour judge — NOT the same process that wrote these
captions. Score each caption candidate on multiple dimensions, each 0-10:

humour_score, originality_score, surprise_score, relevance_score,
template_fit_score, relatability_score, brevity_score, naturalness_score,
clarity_score

Then apply penalties (0-10, higher = worse) where they apply:
generic_ai_penalty, repetition_penalty (leave at 0, repetition is scored
elsewhere), forced_slang_penalty

Be honest and critical. A caption that is grammatically fine but boring
should score low on humour_score and surprise_score. A caption that
over-explains the joke should score low on naturalness_score.

You do NOT have a rendered image to look at — you only have the template's
declared structure and the topic. Judge template fit based on whether the
caption respects the template's declared roles/structure, not visual
appearance.

Return ONLY a JSON array, one object per candidate, in the same order given:
[
  {{
    "humour_score": 7, "originality_score": 6, "surprise_score": 6,
    "relevance_score": 8, "template_fit_score": 7, "relatability_score": 7,
    "brevity_score": 9, "naturalness_score": 8, "clarity_score": 9,
    "generic_ai_penalty": 0, "forced_slang_penalty": 0,
    "reasoning": "one sentence, specific to this caption"
  }},
  ...
]
"""

_HUMAN = """\
Topic: {topic_title}

Template: {template_name}
Template structure: {template_structure}

Candidates to judge:
{candidates_block}
"""

_WEIGHTS = {
    "humour_score": 0.25,
    "template_fit_score": 0.20,
    "originality_score": 0.15,
    "relevance_score": 0.10,
    "surprise_score": 0.10,
    "relatability_score": 0.08,
    "naturalness_score": 0.07,
    "clarity_score": 0.05,
}


def _final_score(dims: dict) -> float:
    score = sum(dims.get(k, 0) * w for k, w in _WEIGHTS.items())
    score -= dims.get("generic_ai_penalty", 0)
    score -= dims.get("repetition_penalty", 0)
    score -= dims.get("forced_slang_penalty", 0)
    return round(score, 2)


def _heuristic_fallback_score(text_boxes: list[str]) -> dict:
    """
    Real fallback, not zeros. Used when the LLM judge call fails entirely
    (parse error after retry) — better to score from cheap heuristics than
    to force every candidate to 0, which would make ANY judge parse
    failure automatically reject an otherwise-good caption (a real bug
    found via direct testing of MemeEngine.process()).
    """
    caption_flat = " ".join(text_boxes)
    word_count = len(caption_flat.split())
    fits = caption_text_fits(text_boxes)
    ai_ish = is_ai_ish(caption_flat)

    # Mid-range neutral scores, nudged by cheap signals we can actually
    # compute without an LLM call: brevity from word count, clarity from
    # having non-empty boxes, naturalness penalized if ai-ish patterns hit.
    brevity = 8.0 if word_count <= 12 else (5.0 if word_count <= 20 else 2.0)
    clarity = 6.0 if all(b.strip() for b in text_boxes) else 2.0
    naturalness = 3.0 if ai_ish else 6.0

    return {
        "humour_score": 4.0, "originality_score": 4.0, "surprise_score": 4.0,
        "relevance_score": 5.0, "template_fit_score": 5.0, "relatability_score": 4.0,
        "brevity_score": brevity, "naturalness_score": naturalness, "clarity_score": clarity,
        "generic_ai_penalty": 4.0 if ai_ish else 0.0, "forced_slang_penalty": 0.0,
        "reasoning": "heuristic-only score — LLM judge call failed to parse, scored from caption structure only, not a real humour judgment",
        "_fits": fits,
    }


async def _call_judge_once(*, topic: dict, template: dict, candidates: list[MemeCaptionCandidate]) -> list[dict] | None:
    candidates_block = "\n".join(
        f"{i}. {' | '.join(c['text_boxes'])}" for i, c in enumerate(candidates)
    )
    human_msg = _HUMAN.format(
        topic_title=topic.get("title", ""),
        template_name=template.get("name", ""),
        template_structure=json.dumps(template.get("visual_grammar", {})),
        candidates_block=candidates_block,
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
        raw = repair_json(raw)
        raw_scores = json.loads(raw.strip())
        if not isinstance(raw_scores, list) or len(raw_scores) != len(candidates):
            raise ValueError(f"score count mismatch: got {len(raw_scores) if isinstance(raw_scores, list) else 'non-list'}, expected {len(candidates)}")
        return raw_scores
    except Exception as exc:
        logger.warning("humour.ranking: judge call attempt failed — %s", exc)
        return None


# Judging N candidates in one call risks truncation on a small model — the
# response has to hold N * ~10 score fields + reasoning text. Batching keeps
# each call's expected output small enough to fit reliably in max_tokens,
# which is a real structural fix (observed truncation failures directly)
# rather than just retrying the same oversized call.
JUDGE_BATCH_SIZE = 8


async def judge_candidates(
    *,
    topic: dict,
    template: dict,
    candidates: list[MemeCaptionCandidate],
) -> list[MemeJudgeScore]:
    if not candidates:
        return []

    all_dims: list[dict] = []
    for batch_start in range(0, len(candidates), JUDGE_BATCH_SIZE):
        batch = candidates[batch_start:batch_start + JUDGE_BATCH_SIZE]

        raw_scores = await _call_judge_once(topic=topic, template=template, candidates=batch)
        if raw_scores is None:
            # One retry on a fresh call (transient truncation/formatting
            # issues are common at temperature=0.3 but not deterministic).
            raw_scores = await _call_judge_once(topic=topic, template=template, candidates=batch)

        if raw_scores is None:
            logger.warning(
                "humour.ranking: judge failed twice for a batch of %d — using heuristic fallback, not zeros",
                len(batch),
            )
            raw_scores = [_heuristic_fallback_score(c["text_boxes"]) for c in batch]

        all_dims.extend(raw_scores)

    results: list[MemeJudgeScore] = []
    for cand, dims in zip(candidates, all_dims):
        caption_flat = " ".join(cand["text_boxes"])
        ai_ish = is_ai_ish(caption_flat)
        unsafe = is_unsafe(caption_flat)
        fits = caption_text_fits(cand["text_boxes"])

        # Code-level penalty enforcement — do not trust the model to always
        # self-report generic_ai_penalty correctly (same rationale as the
        # persona post sanitizer).
        generic_ai_penalty = max(dims.get("generic_ai_penalty", 0), 4 if ai_ish else 0)

        final = _final_score({**dims, "generic_ai_penalty": generic_ai_penalty})
        if unsafe:
            final = -1.0  # hard reject, never selectable
        if not fits:
            final -= 2.0

        results.append(MemeJudgeScore(
            humour_score=dims.get("humour_score", 0),
            originality_score=dims.get("originality_score", 0),
            surprise_score=dims.get("surprise_score", 0),
            relevance_score=dims.get("relevance_score", 0),
            template_fit_score=dims.get("template_fit_score", 0),
            relatability_score=dims.get("relatability_score", 0),
            brevity_score=dims.get("brevity_score", 0),
            naturalness_score=dims.get("naturalness_score", 0),
            clarity_score=dims.get("clarity_score", 0),
            generic_ai_penalty=generic_ai_penalty,
            repetition_penalty=0,  # applied at template level, not per-caption, see templates/cooldown.py
            forced_slang_penalty=dims.get("forced_slang_penalty", 0),
            final_score=final,
            reasoning=dims.get("reasoning", "(judge call failed, heuristic-only score)"),
            ai_ish=ai_ish,
        ))

    return results
