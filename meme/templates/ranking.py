"""
Template ranking (meme spec sections 36, 37, 71). Separate scoring formula
from the caption/humour judge — a semantically relevant template can still
be visually/structurally wrong (spec section 93), so this stage only
answers "which templates are worth generating captions for", not "is the
final joke good."
"""
import random

from meme.templates.cooldown import repetition_penalty

# Weights per spec section 36 — configurable, not hard-coded business logic
# in the sense that they're named constants here, easy to tune later.
_WEIGHT_SEMANTIC_FIT = 0.30
_WEIGHT_MECHANISM_FIT = 0.20
_WEIGHT_VISUAL_FIT = 0.15
_WEIGHT_POPULARITY = 0.10
_WEIGHT_FRESHNESS = 0.10
_WEIGHT_HISTORICAL_PERFORMANCE = 0.15

EXPLORATION_RATE = 0.20  # spec section 71 — 20% weight toward underused templates


def _semantic_fit(template: dict, humour_mechanisms: list[str]) -> float:
    t_mechanisms = set(m.lower() for m in template.get("humour_mechanisms", []))
    requested = set(m.lower() for m in humour_mechanisms)
    if not t_mechanisms:
        return 0.3  # unenriched template — neutral-low, not zero
    overlap = len(t_mechanisms & requested)
    return min(overlap / max(len(requested), 1), 1.0)


def _mechanism_fit(template: dict, humour_mechanisms: list[str]) -> float:
    # Same signal as semantic_fit here since this project doesn't have a
    # separate mechanism taxonomy from semantic_format; kept as a distinct
    # scoring term per the spec's formula shape for future differentiation.
    return _semantic_fit(template, humour_mechanisms)


def _visual_fit(template: dict) -> float:
    # No vision-capable model is available in this project (Bedrock account
    # only exposes Mistral text models — see meme/humour/observation.py for
    # the full honest note). Visual fit is approximated from box_count/
    # dimensions sanity rather than true image inspection.
    box_count = template.get("box_count") or 0
    if 1 <= box_count <= 3:
        return 0.7
    if box_count in (4, 5):
        return 0.5
    return 0.3


def rank_templates(
    candidates: list[dict],
    *,
    humour_mechanisms: list[str],
    recent_usage: list[dict],
    exploration_enabled: bool = True,
) -> list[dict]:
    """
    Returns candidates sorted by final_score descending, each with score
    breakdown attached under "_ranking" for observability (spec section 81).
    """
    scored = []
    max_popularity = max((t.get("popularity_score", 0) for t in candidates), default=1) or 1

    for t in candidates:
        semantic_fit = _semantic_fit(t, humour_mechanisms)
        mechanism_fit = _mechanism_fit(t, humour_mechanisms)
        visual_fit = _visual_fit(t)
        popularity = (t.get("popularity_score", 0) or 0) / max_popularity
        freshness = (t.get("freshness_score", 50) or 50) / 100
        historical = (t.get("average_humour_score") or 50) / 100

        base_score = (
            semantic_fit * _WEIGHT_SEMANTIC_FIT
            + mechanism_fit * _WEIGHT_MECHANISM_FIT
            + visual_fit * _WEIGHT_VISUAL_FIT
            + popularity * _WEIGHT_POPULARITY
            + freshness * _WEIGHT_FRESHNESS
            + historical * _WEIGHT_HISTORICAL_PERFORMANCE
        )

        rep_penalty = repetition_penalty(
            template_name=t["name"],
            template_family=t.get("template_family"),
            humour_mechanism=(t.get("humour_mechanisms") or [None])[0],
            recent_usage=recent_usage,
        )

        final_score = max(base_score - rep_penalty, 0.0)

        # Exploration bonus (spec section 71): underused templates get a
        # small random boost so the system doesn't converge on the same
        # 2-3 templates forever.
        if exploration_enabled and random.random() < EXPLORATION_RATE and (t.get("times_selected") or 0) < 3:
            final_score += 0.15

        scored.append({
            **t,
            "_ranking": {
                "semantic_fit": round(semantic_fit, 3),
                "mechanism_fit": round(mechanism_fit, 3),
                "visual_fit": round(visual_fit, 3),
                "popularity": round(popularity, 3),
                "freshness": round(freshness, 3),
                "historical_performance": round(historical, 3),
                "repetition_penalty": round(rep_penalty, 3),
                "final_score": round(final_score, 3),
            },
            "final_score": final_score,
        })

    scored.sort(key=lambda t: t["final_score"], reverse=True)
    return scored
