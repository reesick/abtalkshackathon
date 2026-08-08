"""write_post node — generates caption/post text in persona voice."""
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState
from agent.nodes.script import build_persona_prompt

logger = logging.getLogger(__name__)

_llm = get_llm(model_id=MODEL_FAST, temperature=0.8, max_tokens=512)

_IMAGE_INSTRUCTION = """\
Write the caption for an image post about:
Title: {title}
Summary: {summary}

The image(s) illustrate: {visual_ideas}

Rules:
- Lead sentence ≤ 50 words, carries the argument
- The image illustrates; the caption does not duplicate it
- One clear stance, not a summary
- No hashtags unless they are genuinely indexing terms
"""

_VIDEO_INSTRUCTION = """\
Write the caption that accompanies this short video:
Title: {title}
Video hook: {hook}

Rules:
- 1-3 short sentences max
- Complement the video; do not re-narrate it
- End with the one thing a viewer should take away
"""

_TEXT_INSTRUCTION = """\
Write a standalone text post about:
Title: {title}
Summary: {summary}

Rules:
- Lead sentence ≤ 280 characters — the entire argument in one breath
- If you continue, use whitespace; no wall of text
- No thread openers ("thread 🧵", "let's dive in", numbered lists as openers)
- One clear stance
"""


async def write_post(state: AgentState) -> AgentState:
    topic = state["selected_topic"]
    content_type = state["content_type"]
    script = state.get("script") or {}
    image_assets = state.get("image_assets") or []

    visual_ideas = ", ".join(
        a.get("prompt_used", "")[:80] for a in image_assets[:3]
    )

    asset_context = ""
    if image_assets:
        asset_context = f"You have {len(image_assets)} frame image(s) attached. Reference them as commissioned visuals."
    if state.get("video_asset"):
        asset_context = "You have a short video attached. Write a caption that complements it."

    system_prompt = build_persona_prompt(state, asset_context=asset_context)

    if content_type == "image_post":
        human_msg = _IMAGE_INSTRUCTION.format(
            title=topic.get("title", ""),
            summary=topic.get("summary", "")[:400],
            visual_ideas=visual_ideas or "abstract tech imagery",
        )
    elif content_type == "video_post":
        human_msg = _VIDEO_INSTRUCTION.format(
            title=topic.get("title", ""),
            hook=script.get("hook", ""),
        )
    else:
        human_msg = _TEXT_INSTRUCTION.format(
            title=topic.get("title", ""),
            summary=topic.get("summary", "")[:400],
        )

    response = await _llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    return {**state, "post_text": response.content.strip()}
