"""
write_post node — generates the post text in Kabir Rao's voice.

Scope (ml_engineer_persona.md section 6): text + single static image per
post only. No video path anymore.
"""
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState
from agent.nodes.script import build_persona_prompt

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.8, max_tokens=768)

# Mistral-7B does not reliably follow "don't print section labels" or
# "no em dashes" as prompt-only instructions (observed repeatedly — same
# class of limitation as the narration word-count enforcement in the old
# script.py). Code-level cleanup catches what the prompt alone doesn't,
# rather than silently accepting output that violates section 5's banned
# patterns.
_SECTION_LABEL_RE = re.compile(
    r"^\s*(hook|the turn|turn|insight stack|contrast line|closer|"
    r"anecdote|parenthetical)\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _sanitize(text: str) -> str:
    # Strip leaked structural labels like "Hook:", "The Turn:", etc.
    text = _SECTION_LABEL_RE.sub("", text)
    # Em dashes are banned outright — replace with a comma or period
    # depending on surrounding spacing, defaulting to a comma.
    text = text.replace(" — ", ", ").replace("—", ", ")
    # Collapse any resulting double spaces/blank-line artifacts
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_IMAGE_INSTRUCTION = """\
Write an image post about:
Title: {title}
Source: {source_url}
Summary: {summary}

The attached image depicts: {visual_idea}

Follow the REQUIRED STRUCTURE from your system prompt in full: hook, optional
parenthetical, anecdote, the turn (named concept/analogy/sourced stat), insight
stack, contrast line, closer. The image supports the point; the caption still
carries the entire argument on its own. Write it as continuous prose — do not
print any section labels, and do not open with a question.

End with the source link on its own line.
"""

_TEXT_INSTRUCTION = """\
Write a standalone text post about:
Title: {title}
Source: {source_url}
Summary: {summary}

Follow the REQUIRED STRUCTURE from your system prompt, compressed for a
shorter post — but the hook and the contrast line are non-negotiable even
here. Use whitespace deliberately. Write it as continuous prose, with no
visible section labels and no question as the opening line.

End with the source link on its own line.
"""


async def write_post(state: AgentState) -> AgentState:
    topic = state["selected_topic"]
    content_type = state["content_type"]
    script = state.get("script") or {}
    image_assets = state.get("image_assets") or []

    beats = script.get("beats") or []
    visual_idea = beats[0].get("visual_idea", "") if beats else ""

    asset_context = ""
    if image_assets:
        asset_context = "You have one supporting static image attached. Reference it only if it genuinely helps the point — do not describe it in detail."

    system_prompt = build_persona_prompt(state, asset_context=asset_context)

    if content_type == "image_post":
        human_msg = _IMAGE_INSTRUCTION.format(
            title=topic.get("title", ""),
            source_url=topic.get("url", ""),
            summary=topic.get("summary", "")[:500],
            visual_idea=visual_idea or "an abstract illustration of the topic",
        )
    else:
        human_msg = _TEXT_INSTRUCTION.format(
            title=topic.get("title", ""),
            source_url=topic.get("url", ""),
            summary=topic.get("summary", "")[:500],
        )

    response = await _llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    post_text = _sanitize(response.content.strip())

    return {**state, "post_text": post_text}
