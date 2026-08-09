"""
Template retrieval + filtering (meme spec sections 12, 13). Narrows the
full active-template pool down to a manageable candidate set (15-30) before
any LLM call sees them — never hand the model 150 templates at once.
"""
from meme.templates.registry import list_active_templates


def retrieve_candidates(
    *,
    humour_mechanisms: list[str],
    limit: int = 25,
) -> list[dict]:
    """
    Coarse pre-filter: templates whose declared humour_mechanisms overlap
    with the requested mechanisms, or that have no semantic annotation yet
    (so newly-synced, unenriched templates still get a chance to appear —
    they'll just score lower on semantic_fit during ranking). Excludes
    inactive/unhealthy templates.
    """
    templates = list_active_templates(limit=200)
    mechanisms_set = set(m.lower() for m in humour_mechanisms)

    scored = []
    for t in templates:
        if t["health"] != "active":
            continue
        t_mechanisms = set(m.lower() for m in t.get("humour_mechanisms", []))
        overlap = len(mechanisms_set & t_mechanisms)
        has_annotation = bool(t.get("semantic_format"))
        # Unannotated templates get a small non-zero score so they aren't
        # permanently excluded, but annotated overlapping ones sort first.
        relevance = overlap if has_annotation else 0.1
        scored.append((relevance, t))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [t for _, t in scored[:limit]]


def filter_candidates(
    candidates: list[dict],
    *,
    min_box_count: int = 1,
    max_box_count: int = 5,
) -> list[dict]:
    """
    Spec section 13 — remove templates that are broken/unsafe/incompatible
    before they reach ranking. Cooldown filtering happens in cooldown.py,
    applied separately in the ranking stage since it needs recent-usage
    context, not just static template metadata.
    """
    result = []
    for t in candidates:
        if not t.get("image_url"):
            continue
        box_count = t.get("box_count") or 0
        if not (min_box_count <= box_count <= max_box_count):
            continue
        if t.get("health") not in ("active", None):
            continue
        result.append(t)
    return result
