"""
Safety and AI-ishness detection (meme spec sections 52, 97). Code-level
checks, not just prompt instructions — same philosophy as the persona's
banned-phrase sanitizer in agent/nodes/post.py: prompts alone don't
reliably stop the model from producing these patterns.
"""
import re

_AI_ISH_PATTERNS = [
    r"\bpov:\s",
    r"bro really said",
    r"ai is taking over",
    r"we are cooked",
    r"this is literally me\b",
    r"\bunlock\b.*\bpotential\b",
    r"game[\s-]?changer",
    r"\bleverage\b",
    r"\bseamless\b",
]

# Topics/content the humour system must reject or handle very carefully
# (spec section 97) — this is a coarse denylist for obviously unsafe
# framing, not a substitute for human judgment on edge cases.
_UNSAFE_PATTERNS = [
    r"\bdi(e|ed|es)\b", r"\bdying\b", r"\bdeath\b", r"\bsuicide\b", r"\bkill(ed|ing|s)?\b",
    r"\brape\b", r"\bassault\b", r"\bterror(ist|ism)\b",
]


def is_ai_ish(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _AI_ISH_PATTERNS)


def is_unsafe(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in _UNSAFE_PATTERNS)


def caption_text_fits(text_boxes: list[str], *, max_chars_per_box: int = 60, max_words_per_box: int = 12) -> bool:
    """Spec section 95 — conservative default box-length validation."""
    for box in text_boxes:
        if len(box) > max_chars_per_box:
            return False
        if len(box.split()) > max_words_per_box:
            return False
    return True
