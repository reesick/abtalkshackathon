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

Generates BOTH an English and a Hinglish variant of the post text (two
real LLM calls, run in parallel) so the feed UI can offer a genuine EN/HI
toggle — not a client-side translation fake.
"""
import asyncio
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE, MODEL_FAST
from agent.state import AgentState
from agent.nodes.script import build_persona_prompt

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.8, max_tokens=1024)
# Hinglish generation uses MODEL_CAPABLE (Mixtral-8x7b) — confirmed via
# direct testing to produce more natural code-switching than Mistral-7b,
# which tends to append unprompted English parenthetical translations.
# max_tokens raised from 768 -> 1024 after observing real truncation: a
# full-structure Hinglish post (hook+anecdote+turn+insight+contrast+closer)
# genuinely needs more headroom than a compressed English draft, and 768
# cut a real post off mid-sentence in production.
_llm_hinglish = get_llm(model_id=MODEL_CAPABLE, temperature=0.8, max_tokens=1024)

# Mistral-7B does not reliably follow "don't print section labels" or
# "no em dashes" as prompt-only instructions (observed repeatedly — same
# class of limitation as the narration word-count enforcement in the old
# script.py). Code-level cleanup catches what the prompt alone doesn't,
# rather than silently accepting output that violates section 5's banned
# patterns.
_SECTION_LABEL_RE = re.compile(
    r"^\s*\**\s*(title|hook|the turn|turn|insight stack|contrast line|closer|"
    r"anecdote|parenthetical)\s*:?\s*\**\s*:?\s*",
    re.IGNORECASE | re.MULTILINE,
)

# The legitimate "Source: <url>" line sometimes gets wrapped in markdown
# bold in either order: "**Source:**" or "**Source**:" — strip just the
# bold markers, keep the label and URL intact (this line should survive,
# unlike the structural labels above which should be removed entirely).
_BOLD_SOURCE_LABEL_RE = re.compile(r"\*+\s*(source)\s*:?\s*\*+\s*:?", re.IGNORECASE)

# Strip markdown bullet-list markers ("* " at line start) that sometimes
# leak through even without a full numbered list — same "reads like a
# corporate slide" problem the numbered-list ban targets.
_BULLET_LIST_RE = re.compile(r"^\s*[\*\-]\s+", re.MULTILINE)

# Catch-all: any remaining stray markdown bold/italic asterisks left over
# after the specific label patterns above have been stripped (e.g. an
# orphaned "**" on its own line, or "**word" with no matching close on the
# same line because the label regex only consumed part of the markup).
# Applied last, after the more specific patterns, so it only mops up
# leftovers rather than doing the primary work.
_STRAY_MARKDOWN_BOLD_RE = re.compile(r"\*{1,3}")

# Real bug observed directly: on a corrective-retry pass, Mistral/Mixtral
# occasionally leak their own chat-template control tokens into the visible
# output — "<<SYS>>", "<</SYS>>", and a literal "Revised draft:" preamble.
# These are internal formatting artifacts, never meant to be shown to a
# reader, and must be stripped unconditionally.
_CHAT_TEMPLATE_TOKEN_RE = re.compile(r"<<\s*/?\s*SYS\s*>>", re.IGNORECASE)
_REVISED_DRAFT_PREAMBLE_RE = re.compile(
    r"^\s*(revised draft|here'?s the (revised|corrected|fixed) (draft|version|post))\s*:?\s*",
    re.IGNORECASE | re.MULTILINE,
)

# Both Mistral and Mixtral occasionally wrap a bare URL in angle brackets
# (markdown-style "escaping" of a URL) — observed directly in real output:
# "Source: <https://openai.com/...>". This renders as literal "<>" in the
# feed UI. Strip the brackets around any http(s) URL.
_ANGLE_BRACKET_URL_RE = re.compile(r"<(https?://[^\s<>]+)>")

# Code-level structural violation detection — same philosophy as the label/
# em-dash sanitizer above. Confirmed by direct testing (see
# ISSUES_AND_FIX_PLAN.md item 2) that prompt-only instructions are not
# reliably followed by this model: real output has shipped with question
# hooks, numbered lists, and third-person voice despite all three being
# explicitly banned in the system prompt. These checks catch that so a
# broken draft can be retried instead of silently published.
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+[\.\)]\s", re.MULTILINE)
_FIRST_PERSON_RE = re.compile(r"\b(i|i've|i'm|i'll|my|we|we've|we're|our)\b", re.IGNORECASE)
_GENERIC_CLOSER_RE = re.compile(
    r"(what (do you think|steps are you|are you doing)|"
    r"let'?s (continue|keep) the conversation|"
    r"share your thoughts|"
    r"how are you (preparing|handling))",
    re.IGNORECASE,
)
# Real bug observed directly: on a structural retry, the Hinglish generation
# call reverted to a literal-translation worksheet pattern — every Hinglish
# sentence followed immediately by "(English translation)" in parentheses.
# This is explicitly banned (the Hinglish instruction says code-switch
# naturally, not translate line by line) but the corrective instruction
# never restated that rule, so the model dropped it under retry pressure.
_PARENTHETICAL_TRANSLATION_RE = re.compile(r"\([A-Za-z][^()]{10,}\)")


def _first_line(text: str) -> str:
    for line in text.strip().split("\n"):
        if line.strip():
            return line.strip()
    return ""


def _last_line(text: str) -> str:
    for line in reversed(text.strip().split("\n")):
        if line.strip() and not line.strip().lower().startswith("source:"):
            return line.strip()
    return ""


def _structural_violations(text: str, *, is_hinglish: bool = False) -> list[str]:
    """Returns a list of specific, human-readable violations found, empty
    if the draft passes. Checked against the exact failure modes observed
    in real output this session (see ISSUES_AND_FIX_PLAN.md item 2)."""
    violations = []

    if _CHAT_TEMPLATE_TOKEN_RE.search(text) or _REVISED_DRAFT_PREAMBLE_RE.search(text):
        violations.append("contains leaked chat-template tokens (<<SYS>>) or a 'Revised draft:' preamble — never show internal formatting to the reader")

    hook = _first_line(text)
    if hook.endswith("?"):
        violations.append(f"hook ends in a question mark: \"{hook}\"")

    if _NUMBERED_LIST_RE.search(text):
        violations.append("contains a numbered list (banned — turn it into prose)")

    # Check first-person voice within roughly the first third of the post,
    # not just the first line — the anecdote section is where "I"/"we"
    # should appear, and a purely third-person recap of a company
    # announcement will have none anywhere in that span.
    first_third = text[: max(len(text) // 3, 200)]
    if not _FIRST_PERSON_RE.search(first_third):
        violations.append("no first-person voice (I/we/my/our) in the first third of the post — reads like a third-person news recap")

    closer = _last_line(text)
    if _GENERIC_CLOSER_RE.search(closer):
        violations.append(f"closer is generic engagement-bait: \"{closer}\"")

    # Truncation check: a post that doesn't end with sentence-ending
    # punctuation or a source URL likely got cut off mid-sentence by
    # max_tokens — observed directly in real output (a Hinglish post that
    # trailed off mid-word). Check the actual final non-empty line, not
    # just the very last character, since the real "Source: <url>" line
    # legitimately doesn't end in punctuation.
    if closer and not closer.lower().startswith("source:"):
        if not re.search(r'[.!?"\u2019\u201d]\s*$', closer):
            violations.append(f"post appears cut off mid-sentence (last line: \"{closer[-80:]}\")")

    if is_hinglish:
        # Count parenthetical-translation-looking spans; a couple of short
        # asides are fine (the spec allows an occasional parenthetical for
        # tension release), but a pattern of one per sentence is the
        # literal-translation-worksheet failure mode.
        translation_hits = len(_PARENTHETICAL_TRANSLATION_RE.findall(text))
        if translation_hits >= 3:
            violations.append(
                f"reads like a line-by-line translation worksheet — {translation_hits} "
                f"parenthetical English translations found (banned — code-switch naturally "
                f"instead of translating each Hinglish sentence back into English)"
            )

    return violations


_CORRECTIVE_INSTRUCTION = """\
Your previous draft had specific problems. Rewrite it, fixing EXACTLY these
issues, keeping everything else about the topic and stance the same:

{violations_list}

Remember: the hook is a flat statement (never a question), no numbered or
bulleted lists anywhere, the post is told in first person as YOUR OWN story
(not a third-person recap of the announcement), and the closer is either a
sharp specific line or a callback to the hook, never generic engagement bait.
"""

_HINGLISH_CORRECTIVE_ADDENDUM = """\

Also: write natural Hinglish throughout — code-switch Hindi and English
within sentences the way people actually text. Do NOT write an English
sentence, or a Hinglish sentence, followed by its translation in
parentheses. There should be no line-by-line translation pairs anywhere.
"""


async def _generate_with_structural_retry(
    llm, system_prompt: str, human_msg: str, max_attempts: int = 2, *, is_hinglish: bool = False,
) -> str:
    """
    Real code-level enforcement of the REQUIRED STRUCTURE rules, since
    prompt-only instructions have been directly observed to fail (question
    hooks, numbered lists, third-person voice all shipped in real posts
    despite being explicitly banned). Retries with a specific corrective
    instruction naming the exact violations found; if still failing after
    max_attempts, returns the last draft anyway with violations logged
    honestly rather than silently publishing without any record.
    """
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_msg)]
    draft = ""

    for attempt in range(max_attempts):
        response = await llm.ainvoke(messages)
        draft = _sanitize(response.content.strip())
        violations = _structural_violations(draft, is_hinglish=is_hinglish)

        if not violations:
            return draft

        logger.warning(
            "write_post: draft attempt %d/%d has structural violations — %s",
            attempt + 1, max_attempts, "; ".join(violations),
        )

        if attempt < max_attempts - 1:
            corrective = _CORRECTIVE_INSTRUCTION.format(
                violations_list="\n".join(f"- {v}" for v in violations)
            )
            if is_hinglish:
                corrective += _HINGLISH_CORRECTIVE_ADDENDUM
            messages = messages + [
                SystemMessage(content=f"Your previous draft:\n\n{draft}"),
                HumanMessage(content=corrective),
            ]

    remaining = _structural_violations(draft, is_hinglish=is_hinglish)
    if remaining:
        logger.warning(
            "write_post: draft still has violations after %d attempts, publishing anyway — %s",
            max_attempts, "; ".join(remaining),
        )
    return draft


def _sanitize(text: str) -> str:
    # Strip leaked chat-template control tokens and "Revised draft:"
    # preambles FIRST, before anything else touches the text — these are
    # the most jarring artifact and must never survive to the reader.
    text = _CHAT_TEMPLATE_TOKEN_RE.sub("", text)
    text = _REVISED_DRAFT_PREAMBLE_RE.sub("", text)
    # Strip leaked structural labels like "Hook:", "The Turn:", "**Title:**", etc.
    text = _SECTION_LABEL_RE.sub("", text)
    # Unwrap "**Source:**" / "**Source**:" back to "Source:" — keep the
    # line, drop the bold markers, before the catch-all stripper runs.
    text = _BOLD_SOURCE_LABEL_RE.sub("Source:", text)
    # Strip LLM preamble headers like "Your new draft:"
    text = re.sub(r"^(Your new draft|Here is the updated post|Revised draft):\s*", "", text, flags=re.IGNORECASE).strip()
    # Strip trailing LLM meta-talk paragraphs like "This draft now has a first-person voice..."
    text = re.sub(r"\n\n(This draft|Note:|This revision|The above post).*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
    # Strip bullet-list markers that read like corporate slide fragments.
    text = _BULLET_LIST_RE.sub("", text)
    # Catch-all: remove any remaining stray markdown emphasis asterisks
    text = _STRAY_MARKDOWN_BOLD_RE.sub("", text)
    # Strip angle brackets wrapped around bare URLs.
    text = _ANGLE_BRACKET_URL_RE.sub(r"\1", text)
    # Em dashes are banned outright — replace with a comma or period
    text = text.replace(" — ", ", ").replace("—", ", ")
    # Collapse any resulting double spaces/blank-line artifacts
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
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

    system_prompt = build_persona_prompt(state, asset_context="")

    text_human_msg = _TEXT_INSTRUCTION.format(
        title=topic.get("title", ""),
        source_url=topic.get("url", ""),
        summary=topic.get("summary", "")[:500],
    )
    hinglish_human_msg = _HINGLISH_INSTRUCTION.format(
        title=topic.get("title", ""),
        source_url=topic.get("url", ""),
        summary=topic.get("summary", "")[:500],
    )

    post_text_en, post_text_hi = await asyncio.gather(
        _generate_with_structural_retry(_llm, system_prompt, text_human_msg),
        _generate_with_structural_retry(_llm_hinglish, system_prompt, hinglish_human_msg, is_hinglish=True),
    )

    # Default display text stays Hinglish (matches the prior behavior/
    # explicit instruction), with the English variant carried alongside
    # for the feed UI's toggle.
    return {**state, "post_text": post_text_hi, "post_text_en": post_text_en, "post_text_hi": post_text_hi}


_MEME_ACCOMPANYING_INSTRUCTION = """\
A meme has already been generated for this topic. Write a SHORT
accompanying post text (1-3 sentences, casual) that sits above/below the
meme image — do not repeat the meme's caption, add the context or stance
the meme itself doesn't carry (the meme is just the joke).

Topic: {title}
Source: {source_url}
Meme template used: {template_name}
Meme caption: {caption_flat}

End with the source link on its own line.
"""

_MEME_ACCOMPANYING_INSTRUCTION_HINGLISH = _MEME_ACCOMPANYING_INSTRUCTION.replace(
    "(1-3 sentences, casual)", "(1-3 sentences, natural Hinglish, casual)"
)


async def _write_meme_accompanying_post(state: AgentState, topic: dict) -> AgentState:
    meme_result = state.get("meme_result") or {}
    system_prompt = build_persona_prompt(state, asset_context="A meme image accompanies this post — see the caption below.")

    en_human_msg = _MEME_ACCOMPANYING_INSTRUCTION.format(
        title=topic.get("title", ""),
        source_url=topic.get("url", ""),
        template_name=meme_result.get("template_name", ""),
        caption_flat=meme_result.get("caption_flat", ""),
    )
    hi_human_msg = _MEME_ACCOMPANYING_INSTRUCTION_HINGLISH.format(
        title=topic.get("title", ""),
        source_url=topic.get("url", ""),
        template_name=meme_result.get("template_name", ""),
        caption_flat=meme_result.get("caption_flat", ""),
    )

    en_response, hi_response = await asyncio.gather(
        _llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=en_human_msg)]),
        _llm_hinglish.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=hi_human_msg)]),
    )

    post_text_en = _sanitize(en_response.content.strip())
    post_text_hi = _sanitize(hi_response.content.strip())

    return {**state, "post_text": post_text_hi, "post_text_en": post_text_en, "post_text_hi": post_text_hi}
