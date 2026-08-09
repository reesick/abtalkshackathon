"""
write_script node — LLM produces a single visual idea for image_post topics.

Scope (ml_engineer_persona.md section 6): text + single static image per
post only. There is no video path anymore, so this node no longer produces
beats/narration for a video script — just one concrete, camera-describable
visual idea that the image generation node turns into a prompt.
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE
from agent.state import AgentState
from agent.prompts.persona import PERSONA_SYSTEM_PROMPT

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.7, max_tokens=512)

_SCRIPT_INSTRUCTION = """\
This topic will be published as a text post with ONE supporting static image.
Come up with a single concrete visual idea for that image — not a summary
graphic, not a logo, something a paper-cut collage illustration could depict
that supports the specific angle you'd take on this topic.

TOPIC
Title: {title}
Source: {source}
Summary: {summary}

Return ONLY a JSON object with this exact shape (no markdown wrapper):
{{
  "hook": "<the working stance/angle you'd take on this topic, \u2264 15 words>",
  "beats": [
    {{"beat": "single_image", "visual_idea": "<one concrete, camera-describable scene: subject, action, composition \u2014 no text/logos in the image>"}}
  ]
}}
"""


def _build_persona_prompt(state: AgentState, asset_context: str = "") -> str:
    persona = state["persona"]
    persona_doc = state.get("persona_doc") or {}
    memory_ctx = state.get("memory_context") or []
    recent_posts = "\n".join(
        f"- {p.get('text', '')[:150]}" for p in memory_ctx[:5]
    ) or "(none yet)"

    recurring = "\n".join(
        f"- {op}" for op in persona_doc.get("recurring_opinions", [])
    ) or persona.get("voice_rules", "")

    return PERSONA_SYSTEM_PROMPT.format(
        persona_name=persona.get("name", "the persona"),
        persona_domain=persona.get("domain", "AI/tech"),
        recurring_opinions=recurring,
        stable_interests=", ".join(persona.get("stable_interests", [])),
        pushback_list=", ".join(persona.get("pushback", [])),
        n_recent=len(memory_ctx[:5]),
        recent_posts=recent_posts,
        asset_context=asset_context,
    )


async def write_script(state: AgentState) -> AgentState:
    """
    Only used for image_post. text_post skips this node entirely (see
    agent/graph.py _after_format).
    """
    topic = state["selected_topic"]

    system_prompt = _build_persona_prompt(state)
    human_msg = _SCRIPT_INSTRUCTION.format(
        title=topic.get("title", ""),
        source=topic.get("source", ""),
        summary=topic.get("summary", "")[:500],
    )

    response = await _llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        script = json.loads(raw.strip())
    except Exception:
        script = {
            "hook": topic.get("title", "")[:80],
            "beats": [
                {"beat": "single_image", "visual_idea": "a single figure examining an abstract representation of the topic"},
            ],
        }

    return {**state, "script": script}


# Re-export the helper so write_post can reuse it
build_persona_prompt = _build_persona_prompt
