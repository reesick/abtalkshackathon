"""generate_rationale node — structured explanation of editorial choices."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState

_llm = get_llm(model_id=MODEL_FAST, temperature=0.2, max_tokens=1024)

_SYSTEM = """\
You are generating an editorial rationale log for an autonomous AI publishing agent.
This is an internal transparency record — not public copy.
Be precise and honest. If a selection was a close call, say so.
"""

_HUMAN = """\
Agent persona: {persona_name} ({persona_domain})

Selected topic: {selected_title}
Source: {selected_source}

Rejected topics ({n_rejected}):
{rejected_list}

Post type chosen: {content_type}

Return a JSON object with this exact shape:
{{
  "why_selected": "<2-3 sentences: what made this topic the right pick now>",
  "why_now": "<1-2 sentences: timeliness or recency angle>",
  "format_rationale": "<1 sentence: why this content_type fits the topic>",
  "sources": ["{selected_source}"],
  "rejected_summary": "<1 sentence summarising the pattern of rejections>"
}}
"""


async def generate_rationale(state: AgentState) -> AgentState:
    persona = state["persona"]
    topic = state["selected_topic"]
    rejected = state.get("rejected_topics") or []

    rejected_list = "\n".join(
        f"- {r.get('title', '')} [{r.get('source', '')}]: {r.get('judge_reason', 'filtered')}"
        for r in rejected[:8]
    ) or "(none)"

    human_msg = _HUMAN.format(
        persona_name=persona.get("name", ""),
        persona_domain=persona.get("domain", ""),
        selected_title=topic.get("title", ""),
        selected_source=topic.get("source", ""),
        n_rejected=len(rejected),
        rejected_list=rejected_list,
        content_type=state["content_type"],
    )

    response = await _llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=human_msg),
    ])

    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        rationale = json.loads(raw.strip())
    except Exception:
        rationale = {
            "why_selected": topic.get("title", ""),
            "why_now": "Selected by editorial judge",
            "format_rationale": state["content_type"],
            "sources": [topic.get("url", "")],
            "rejected_summary": f"{len(rejected)} topics filtered",
        }

    # Ensure the source URL is always present
    if topic.get("url") and topic["url"] not in rationale.get("sources", []):
        rationale.setdefault("sources", []).append(topic["url"])

    return {**state, "rationale": rationale}
