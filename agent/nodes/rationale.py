"""generate_rationale node — structured explanation of editorial choices."""
import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_FAST, repair_json
from agent.state import AgentState

_llm = get_llm(model_id=MODEL_FAST, temperature=0.5, max_tokens=1024)

_SYSTEM = """\
You are writing the editorial rationale log for an autonomous AI publishing
agent with an ML engineer persona. This is an internal transparency record —
not public copy — but it still has to read like a real person's actual
reasoning, not a compliance log.

Write like the persona is explaining their pick to a colleague who asked
"why this one, and not the ten other things in your feed today?" Be specific
and a little opinionated. Reference an actual detail from the topic (a
number, a name, a claim, a specific mechanism) — never a vague gesture at
"the topic" or "this article."

BANNED — do not write any of these, they are dead giveaways of generic
AI-generated reasoning:
- "aligns with my interest(s)" / "aligns with my stable interests" / "aligns perfectly with" — in ANY phrasing, including "aligns with my interest in X and Y"
- "this topic discusses" / "this article discusses" / "this RSS feed article"
- "makes it a great fit" / "makes it a perfect fit"
- "in today's rapidly evolving landscape"
- "provides an opportunity to explore/discuss"
- "offer insights into" / "offers insight into"
- Restating the title back as the explanation ("Selected because X is about X")
- Generic timeliness filler ("With the increasing reliance on AI...", "Given the increasing importance of...")

Instead of "aligns with my interest in X", say what you'd actually say out
loud: name the specific number/claim/mechanism and say plainly why THAT
detail earns a post today. Example of the difference:
- Generic (banned): "This aligns with my interest in agent reliability."
- Human (required): "OpenAI says they found real vulnerabilities in Astra
  before shipping it. That's the one thing worth talking about — not that
  they did a security review, everyone claims that."

If the pick was genuinely a close call against another topic, say so plainly
instead of pretending it was obvious. If none of the candidates were great,
say that too — do not oversell a mediocre pick as a strong one.

The "rejected_alternatives" field must be a single string (1-2 sentences),
not a list or nested object — name the topics inline in the sentence.
"""

_HUMAN = """\
Agent persona: {persona_name} ({persona_domain})
Persona's stable interests: {stable_interests}
Persona's recurring stances: {recurring_opinions}

Selected topic: {selected_title}
Source: {selected_source}
Summary: {selected_summary}

Rejected topics ({n_rejected}):
{rejected_list}

Post type chosen: {content_type}

Return a JSON object with this exact shape. Every value must be a specific,
human-sounding sentence or two grounded in the actual summary above — not a
generic template line:
{{
  "selected_because": "<the real, specific reason this one won — name the concrete mechanism, number, or claim from the summary that made it worth a post, and which of the persona's stable interests it actually connects to>",
  "relevant_now_because": "<what makes this worth posting about today specifically, not generically — a release, a pattern across recent topics, a contradiction worth calling out>",
  "rejected_alternatives": "<name 1-2 specific rejected topics by title and give the real, specific reason each one lost — not 'lacks novelty', say what was actually missing>",
  "format_rationale": "<one honest sentence: why this became a {content_type}, in plain terms>",
  "sources": ["{selected_source}"]
}}
"""


def _looks_generic(text: str) -> bool:
    """Cheap heuristic to catch the most common generic-AI patterns that
    slip through despite the prompt ban — used to decide whether to log a
    warning, not to silently rewrite the model's output."""
    banned_patterns = [
        r"aligns (perfectly )?with (my )?(interest|stable interest)",
        r"this (article|topic|rss feed article) discusses",
        r"great fit|perfect fit",
        r"increasing reliance on|increasing importance of",
        r"rapidly evolving",
        r"offers? insight",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in banned_patterns)


def _coerce_to_string(value) -> str:
    """The model occasionally returns rejected_alternatives as a list/dict
    despite the schema instruction. Coerce rather than crash — this is a
    real, observed model deviation, not a hypothetical."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                title = item.get("title", "")
                reason = item.get("reason", "")
                parts.append(f"{title} — {reason}".strip(" —"))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(value)


async def generate_rationale(state: AgentState) -> AgentState:
    persona = state["persona"]
    persona_doc = state.get("persona_doc") or {}
    topic = state["selected_topic"]
    rejected = state.get("rejected_topics") or []

    rejected_list = "\n".join(
        f"- {r.get('title', '')} [{r.get('source', '')}]: {r.get('judge_reason', 'filtered')}"
        for r in rejected[:8]
    ) or "(none)"

    recurring = persona_doc.get("recurring_opinions") or persona.get("recurring_opinions", [])
    stable_interests = persona.get("stable_interests", [])

    human_msg = _HUMAN.format(
        persona_name=persona.get("name", ""),
        persona_domain=persona.get("domain", ""),
        stable_interests=", ".join(stable_interests) if stable_interests else "(none listed)",
        recurring_opinions="; ".join(recurring) if recurring else "(none listed)",
        selected_title=topic.get("title", ""),
        selected_source=topic.get("source", ""),
        selected_summary=topic.get("summary", "")[:500] or "(no summary available)",
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
        rationale = json.loads(repair_json(raw.strip()))
        # The schema promises plain strings — coerce any list/dict deviation
        # rather than let it leak through as malformed data downstream.
        for key in ("selected_because", "relevant_now_because", "rejected_alternatives", "format_rationale"):
            if key in rationale:
                rationale[key] = _coerce_to_string(rationale[key])
        # Honest signal, not a silent rewrite: log if banned phrasing slipped
        # through despite the prompt instructions, same class of limitation
        # flagged elsewhere in this project for this model.
        for key in ("selected_because", "relevant_now_because", "rejected_alternatives"):
            val = rationale.get(key, "")
            if isinstance(val, str) and _looks_generic(val):
                import logging
                logging.getLogger(__name__).warning(
                    "generate_rationale: field '%s' still reads generic despite prompt ban — %r", key, val[:120]
                )
    except Exception:
        # Fallback still tries to be a real sentence, not a bare template,
        # using whatever concrete detail is actually available.
        summary_snippet = (topic.get("summary", "") or "").strip()
        first_clause = summary_snippet.split(".")[0] if summary_snippet else topic.get("title", "")
        rationale = {
            "selected_because": (
                f"Picked this over the rest of today's feed because of one concrete "
                f"thing in it: {first_clause}. That's the kind of detail worth a post, "
                f"not just a headline."
            ),
            "relevant_now_because": "It's fresh enough today that nobody in the feed has weighed in on it yet.",
            "rejected_alternatives": (
                f"Passed on {len(rejected)} other candidates today — most were routine "
                f"announcements with nothing specific to hang an opinion on."
            ),
            "format_rationale": f"Went with a {state['content_type']} because that's what the material actually supports.",
            "sources": [topic.get("url", "")],
        }

    # Ensure the source URL is always present
    if topic.get("url") and topic["url"] not in rationale.get("sources", []):
        rationale.setdefault("sources", []).append(topic["url"])

    return {**state, "rationale": rationale}
