"""write_script node — LLM produces hook/beats/narration for video posts."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE
from agent.state import AgentState
from agent.prompts.persona import PERSONA_SYSTEM_PROMPT

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.7, max_tokens=2048)

_SCRIPT_INSTRUCTION = """\
Write a short-form video script (30-60 seconds) about the topic below.

TOPIC
Title: {title}
Source: {source}
Summary: {summary}

Return ONLY a JSON object with this exact shape (no markdown wrapper):
{{
  "hook": "<opening line, ≤ 12 words, grabs attention immediately>",
  "beats": [
    {{"beat": "problem_framing", "visual_idea": "<concrete, camera-describable scene>"}},
    {{"beat": "solution_reveal", "visual_idea": "<concrete scene>"}},
    {{"beat": "retention_cta", "visual_idea": "<concrete scene>"}}
  ],
  "narration": "<full VO script, natural spoken cadence, first person>",
  "retention_notes": "<one line on the pattern interrupt technique used>"
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
    Used for both video_post and image_post paths.
    For image posts the beats[] are used as image prompts; narration is unused.
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
    # Strip any accidental markdown code fence
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        script = json.loads(raw.strip())
    except Exception:
        # Minimal fallback so the graph doesn't die here
        script = {
            "hook": topic.get("title", "")[:80],
            "beats": [{"beat": "overview", "visual_idea": "text overlay on dark background"}],
            "narration": topic.get("summary", "")[:300],
            "retention_notes": "none",
        }

    return {**state, "script": script}


# Re-export the helper so write_post can reuse it
build_persona_prompt = _build_persona_prompt
