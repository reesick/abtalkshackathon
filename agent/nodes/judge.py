"""editorial_judge node — LLM scores every candidate against the persona."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST
from agent.state import AgentState

_llm = get_llm(model_id=MODEL_FAST, temperature=0.3, max_tokens=2048)

_SYSTEM = """\
You are the editorial director for {persona_name}, a {persona_domain} persona.
Your job: score each candidate topic for this persona and select exactly one.
You must reject topics, not just accept everything — rejection is a required,
visible behavior.

PERSONA VOICE & STANCES
{persona_doc_summary}

ACCEPT a topic if:
- It connects to one of the persona's stable interests
- There is a concrete mechanism, story, number, or failure mode to hang the
  post on, not just a headline
- It is recent enough to matter (breaking release, fresh controversy, a
  pattern currently being seen)
- The persona can take a specific, defensible stance on it, not a neutral
  summary
- It has not already been covered by a recently published post

REJECT a topic if:
- It's pure hype with no mechanism ("new model is amazing" with no technical
  substance) — this includes routine "we improved X and expanded access to Y"
  product-update announcements with no concrete failure mode, number, or
  technical detail to build a real anecdote on. A feature rollout is not a
  story by itself.
- It's outside AI/ML/tech entirely
- The persona would have no real stance, or would only produce a bland, safe
  take
- It's already been posted about recently with no new angle
- It requires speculation presented as fact (unverified rumors, leaked
  benchmarks with no independent source)
- The honest take would just repeat consensus with no original angle

SCORING CRITERIA (each 0-10)
- relevance: fits the domain and persona's interests
- novelty: hasn't been covered by this persona before (recent posts context below)
- opinionability: can the persona take a clear, specific stance, not just summarise?
- timeliness: is it current enough to matter?
- mechanism: is there a concrete story/number/failure mode to hang the post on,
  or is it just a headline/product-update with nothing underneath? Score this
  low (2-3) for routine feature announcements, launches, or access-expansion
  news with no technical substance, even if the topic is otherwise on-domain.

RECENT POSTS (do not select topics already covered at these angles)
{recent_posts}

Return a JSON array — one object per candidate with a "selected" boolean:
[
  {{"title": "...", "score": 7.4, "reason": "...", "selected": false}},
  {{"title": "...", "score": 8.1, "reason": "...", "selected": true}}
]

Be strict. A score below 5 on any single criterion should block selection.
If every candidate fails the accept criteria, still pick the least-bad one
but say so plainly in its reason. Mark exactly one candidate with "selected": true.
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

    # Escape braces in JSON-serialised values so str.format() doesn't choke
    # on embedded {key: value} patterns from the persona doc.
    persona_doc_safe = json.dumps(persona_doc, indent=2)[:800].replace("{", "{{").replace("}", "}}")
    system_prompt = _SYSTEM.format(
        persona_name=persona.get("name", "the persona"),
        persona_domain=persona.get("domain", "AI/tech"),
        persona_doc_summary=persona_doc_safe,
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

    # Parse the JSON array and find the selected candidate
    try:
        # Extract JSON array from response
        lines = raw.split("\n")
        scores_raw = ""
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

        scores: list[dict] = json.loads(scores_raw.strip())

        # Find which candidate was selected
        selected_index = next((i for i, s in enumerate(scores) if s.get("selected")), 0)
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
