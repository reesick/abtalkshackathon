"""
write_post node — generates the post text.

Scope: text-only social posts (image/video paths disconnected per the meme
subsystem integration — see agent/graph.py). Two content types now:
  - "text_post": Kabir Rao's persona voice, in Hinglish for that "typical
    social media" feel, per explicit instruction. Structure (hook/turn/
    contrast-line/closer) is unchanged — only the language register shifts.
  - "meme_post": caption comes from the meme humour skill (meme/humour/*),
    this node writes the short accompanying post text, NOT the meme
    caption itself.
"""
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, MODEL_FAST
from agent.state import AgentState
from agent.nodes.script import build_persona_prompt

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.8, max_tokens=768)
# Hinglish generation uses MODEL_CAPABLE (Mixtral-8x7b) — confirmed via
# direct testing to produce more natural code-switching than Mistral-7b,
# which tends to append unprompted English parenthetical translations.
_llm_hinglish = get_llm(model_id=MODEL_CAPABLE, temperature=0.8, max_tokens=768)

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

_HINGLISH_INSTRUCTION = """\
Write this same post in natural Hinglish (Hindi + English code-switched,
the way Indian tech Twitter/LinkedIn actually writes) instead of pure
English. This is for the "typical social media" feel — casual, punchy,
still grounded in the persona's real technical opinion, not textbook Hindi
and not forced slang.

Title: {title}
Source: {source_url}
Summary: {summary}

Keep the same REQUIRED STRUCTURE from your system prompt (hook, anecdote,
the turn, contrast line, closer) but write the actual sentences in Hinglish.
Technical terms (model names, benchmark names, numbers) stay in English —
only the connective language, tone, and framing should code-switch
naturally. No visible section labels, no question as the opening line, no
forced/exaggerated slang just to seem "relatable."

End with the source link on its own line (keep the link itself in English/URL form).
"""


async def write_post(state: AgentState) -> AgentState:
    topic = state["selected_topic"]
    content_type = state["content_type"]

    if content_type == "meme_post":
        return await _write_meme_accompanying_post(state, topic)

    asset_context = ""
    system_prompt = build_persona_prompt(state, asset_context=asset_context)

    use_hinglish = state.get("persona", {}).get("hinglish", True)  # on by default per explicit instruction
    if use_hinglish:
        human_msg = _HINGLISH_INSTRUCTION.format(
            title=topic.get("title", ""),
            source_url=topic.get("url", ""),
            summary=topic.get("summary", "")[:500],
        )
        llm = _llm_hinglish
    else:
        human_msg = _TEXT_INSTRUCTION.format(
            title=topic.get("title", ""),
            source_url=topic.get("url", ""),
            summary=topic.get("summary", "")[:500],
        )
        llm = _llm

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    post_text = _sanitize(response.content.strip())

    return {**state, "post_text": post_text}


_MEME_ACCOMPANYING_INSTRUCTION = """\
A meme has already been generated for this topic. Write a SHORT
accompanying post text (1-3 sentences, Hinglish, casual) that sits above/
below the meme image — do not repeat the meme's caption, add the context
or stance the meme itself doesn't carry (the meme is just the joke).

Topic: {title}
Source: {source_url}
Meme template used: {template_name}
Meme caption: {caption_flat}

End with the source link on its own line.
"""


async def _write_meme_accompanying_post(state: AgentState, topic: dict) -> AgentState:
    meme_result = state.get("meme_result") or {}
    system_prompt = build_persona_prompt(state, asset_context="A meme image accompanies this post — see the caption below.")

    human_msg = _MEME_ACCOMPANYING_INSTRUCTION.format(
        title=topic.get("title", ""),
        source_url=topic.get("url", ""),
        template_name=meme_result.get("template_name", ""),
        caption_flat=meme_result.get("caption_flat", ""),
    )

    response = await _llm_hinglish.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    post_text = _sanitize(response.content.strip())
    return {**state, "post_text": post_text}
