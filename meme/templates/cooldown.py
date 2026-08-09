"""
Repetition control (meme spec sections 14, 15, 38, 39, 44, 45).

Repetition must be tracked at three levels, not just template name:
  - same template
  - same template family (comparison, underreaction, choice, escalation, ...)
  - same humour mechanism

Cooldowns are expressed in "posts between uses" (tick-based, matching this
project's scheduler — not wall-clock time, per registry.py's record_posted).
Values are configurable, not hard-coded business logic (spec section 44).
"""
import os

MEME_TEMPLATE_COOLDOWN_POSTS = int(os.environ.get("MEME_TEMPLATE_COOLDOWN_POSTS", "5"))
MEME_FAMILY_COOLDOWN_POSTS = int(os.environ.get("MEME_FAMILY_COOLDOWN_POSTS", "2"))
MEME_MECHANISM_COOLDOWN_POSTS = int(os.environ.get("MEME_MECHANISM_COOLDOWN_POSTS", "2"))

# Longer cooldown for templates the spec explicitly calls out as overused
# (section 14): Drake, Distracted Boyfriend, This Is Fine.
_OVERUSED_TEMPLATES = {"Drake", "Distracted Boyfriend", "This Is Fine"}
MEME_OVERUSED_TEMPLATE_COOLDOWN_POSTS = int(os.environ.get("MEME_OVERUSED_TEMPLATE_COOLDOWN_POSTS", "8"))


def template_cooldown_for(name: str) -> int:
    return MEME_OVERUSED_TEMPLATE_COOLDOWN_POSTS if name in _OVERUSED_TEMPLATES else MEME_TEMPLATE_COOLDOWN_POSTS


def posts_since(current_times_posted_global: int, template_times_posted: int, last_used_global_index: int | None) -> int:
    """
    Placeholder-free helper retained for clarity but not directly used —
    see repetition_penalty() below, which works off recent-usage history
    lists rather than raw counters, since that's what meme_usage rows
    actually give us (spec section 40).
    """
    raise NotImplementedError("use repetition_penalty() with recent usage history instead")


def repetition_penalty(
    *,
    template_name: str,
    template_family: str | None,
    humour_mechanism: str | None,
    recent_usage: list[dict],
) -> float:
    """
    recent_usage: list of recent meme_usage-shaped dicts, most recent first,
    each with at least {"template_name", "template_family", "humour_mechanism"}.

    Returns a penalty in [0, 1] (0 = no penalty, 1 = maximum/should reject).
    Combines all three repetition dimensions (spec section 15).
    """
    penalty = 0.0

    template_window = recent_usage[:template_cooldown_for(template_name)]
    if any(u.get("template_name") == template_name for u in template_window):
        penalty += 0.6

    family_window = recent_usage[:MEME_FAMILY_COOLDOWN_POSTS]
    if template_family and any(u.get("template_family") == template_family for u in family_window):
        penalty += 0.3

    mechanism_window = recent_usage[:MEME_MECHANISM_COOLDOWN_POSTS]
    if humour_mechanism and any(u.get("humour_mechanism") == humour_mechanism for u in mechanism_window):
        penalty += 0.2

    return min(penalty, 1.0)


def daily_diversity_ok(
    *,
    template_name: str,
    template_family: str | None,
    humour_mechanism: str | None,
    todays_usage: list[dict],
    max_identical_template_per_day: int = 1,
    max_same_family_per_day: int = 2,
    max_same_mechanism_per_day: int = 2,
) -> bool:
    """Spec section 45 — daily diversity caps, separate from cross-tick cooldowns."""
    same_template = sum(1 for u in todays_usage if u.get("template_name") == template_name)
    same_family = sum(1 for u in todays_usage if template_family and u.get("template_family") == template_family)
    same_mechanism = sum(1 for u in todays_usage if humour_mechanism and u.get("humour_mechanism") == humour_mechanism)

    return (
        same_template < max_identical_template_per_day
        and same_family < max_same_family_per_day
        and same_mechanism < max_same_mechanism_per_day
    )
