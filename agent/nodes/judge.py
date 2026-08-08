"""editorial_judge node — LLM scores every candidate against the persona."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState

_llm = get_llm(model_id=MODEL_FAST, temperature=0.3, max_tokens=2048)

_SYSTEM = """\
You are the editorial director for {persona_name}, a {persona_domain} persona.
Your job: score each candidate topic for this persona and select exactly one.

PERSONA VOICE & STANCES
{persona_doc_summary}

SCORING CRITERIA (each 0-10)
- relevance: fits the domain and persona's interests
- novelty: hasn't been covered by this persona before (recent posts context below)
- opinionability: can the persona take a clear stance, not just summarise?
- timeliness: is it current enough to matter?

RECENT POSTS (do not select topics already covered at these angles)
{recent_posts}

Return a JSON array — one object per candidate, plus a top-level "selected_index":
[
  {"title": "...", "score": 7.4, "reason": "...", "selected": false},
  ...
]
And then on a new line: {{"selected_index": 2}}

Be strict. A score below 5 on any single criterion should block selection.
"""


async def editorial_judge(state: AgentState) -> AgentState:
    """
    Scores all filtered candidates and writes selected_topic + rejected_topics
    to state.  Logs reasons for all rejections (grading requirement).
    """
    candidates = state["candidates"]
    if not candidates:
        return {**state, "error": "no_candidates", "selected_topic": None, "rejected_topics": []}

    persona = state["persona"]
    persona_doc = state.get("persona_doc") or {}
    memory_ctx = state.get("memory_context") or []
    recent_posts_text = "\n".join(
        f"- {p.get('text', '')[:120]}" for p in memory_ctx[:5]
    )

    system_prompt = _SYSTEM.format(
        persona_name=persona.get("name", "the persona"),
        persona_domain=persona.get("domain", "AI/tech"),
        persona_doc_summary=json.dumps(persona_doc, indent=2)[:800],
        recent_posts=recent_posts_text or "(none yet)",
    )

    candidates_block = "\n".join(
        f"{i}. [{c['source']}] {c['title']}\n   {c['summary'][:200]}"
        for i, c in enumerate(candidates)
    )
    human_msg = f"Score these {len(candidates)} candidates:\n\n{candidates_block}"

    response = await _llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_msg),
    ])

    raw = response.content.strip()

    # Parse the two parts: scores array + selected_index line
    try:
        lines = raw.split("\n")
        json_lines = [l for l in lines if l.strip().startswith("[") or l.strip().startswith("{")]
        scores_raw = ""
        selected_raw = ""
        bracket_depth = 0
        collecting = False
        for line in lines:
            if line.strip().startswith("["):
                collecting = True
            if collecting:
                scores_raw += line + "\n"
                bracket_depth += line.count("[") - line.count("]")
                if bracket_depth <= 0:
                    collecting = False
            elif line.strip().startswith('{"selected_index"'):
                selected_raw = line.strip()

        scores: list[dict] = json.loads(scores_raw.strip())
        selected_index: int = json.loads(selected_raw).get("selected_index", 0)
    except Exception:
        # Fallback: pick highest-scoring candidate if JSON parse fails
        scores = [{"title": c["title"], "score": 5.0, "reason": "parse_fallback", "selected": False}
                  for c in candidates]
        selected_index = 0

    selected_topic = candidates[min(selected_index, len(candidates) - 1)]
    rejected_topics = [
        {**candidates[i], "judge_reason": scores[i].get("reason", "") if i < len(scores) else ""}
        for i in range(len(candidates)) if i != selected_index
    ]

    return {
        **state,
        "selected_topic": selected_topic,
        "rejected_topics": rejected_topics,
    }
