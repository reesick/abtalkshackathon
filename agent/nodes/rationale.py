"""generate_rationale node — structured explanation of editorial choices."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState

_llm = get_llm(model_id=MODEL_FAST, temperature=0.2, max_tokens=1024)

_SYSTEM = """\
You are generating an editorial rationale log for an autonomous AI publishing
agent (persona: an ML engineer voice). This is an internal transparency
record — not public copy. Be precise and honest, and sound like the
persona's actual reasoning, not a generic log line. If a selection was a
close call, say so.
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
  "selected_because": "<why this topic fits the persona's stable interests / why it's editorially strong, and what concrete mechanism/story/number it hangs on>",
  "relevant_now_because": "<what makes this timely: a release, a controversy, a pattern noticed>",
  "rejected_alternatives": "<1-2 other topics considered and why they didn't make the cut, when applicable>",
  "format_rationale": "<1 sentence: why this content_type fits the topic>",
  "sources": ["{selected_source}"]
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
            "selected_because": topic.get("title", ""),
            "relevant_now_because": "Selected by editorial judge",
            "rejected_alternatives": f"{len(rejected)} topics filtered",
            "format_rationale": state["content_type"],
            "sources": [topic.get("url", "")],
        }

    # Ensure the source URL is always present
    if topic.get("url") and topic["url"] not in rationale.get("sources", []):
        rationale.setdefault("sources", []).append(topic["url"])

    return {**state, "rationale": rationale}
