"""write_script node — LLM produces hook/beats/narration for video posts."""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from agent.llm import get_llm, MODEL_CAPABLE
from agent.state import AgentState
from agent.prompts.persona import PERSONA_SYSTEM_PROMPT

_llm = get_llm(model_id=MODEL_CAPABLE, temperature=0.7, max_tokens=2048)

_SCRIPT_INSTRUCTION = """\
Write a short-form video script for a 10-12 SECOND video about the topic below.

This video is a hook/teaser, not a full explainer. The video's job is to
grab attention and state ONE sharp stance in the time it takes to say
2-3 short sentences out loud. All supporting detail, sources, and further
reading go in the POST CAPTION underneath the video (written separately) —
NOT in this script. Do not try to explain the whole story here.

TOPIC
Title: {title}
Source: {source}
Summary: {summary}

HARD CONSTRAINTS
- Total spoken narration must be 25-30 words — not fewer. At natural pace
  that reads aloud in 10-12 seconds. A narration under 20 words is TOO SHORT
  and will be rejected — use the full word budget to add one concrete detail
  (a number, a name, a specific claim) rather than stopping early.
- Exactly 2 beats. Not 3, not 4. A hook shot and a stance/payoff shot.
- Never end on a call-to-action, a teaser, or phrases like "stay tuned",
  "more updates coming", "check out our course", "want to see how it works" —
  the video must land the stance and stop. No dangling hooks to elsewhere.
- No throat-clearing. First word must be substantive, not "so" or "well".

Return ONLY a JSON object with this exact shape (no markdown wrapper):
{{
  "hook": "<opening line, ≤ 12 words, grabs attention immediately>",
  "beats": [
    {{"beat": "hook_visual", "visual_idea": "<concrete, camera-describable scene for the opening line>"}},
    {{"beat": "stance_payoff", "visual_idea": "<concrete scene for the closing stance>"}}
  ],
  "narration": "<full VO script, EXACTLY 25-30 words, natural spoken cadence, first person, ends on the stance — not a CTA>",
  "retention_notes": "<one line on the pattern interrupt technique used>"
}}
"""


_MIN_NARRATION_WORDS = 20
_MAX_NARRATION_WORDS = 35

_EXPAND_INSTRUCTION = """\
Your previous narration was too short: "{narration}" ({word_count} words).
It needs to be 25-30 words to fill a 10-12 second video.

Rewrite it, keeping the same stance and topic, but add ONE concrete detail
from the summary below (a number, a name, a specific claim) to reach the
word target. Do not add filler words or hedging — add real content.

Summary: {summary}

Return ONLY the corrected narration text, no JSON, no quotes, nothing else.
"""


def _word_count(text: str) -> int:
    return len(text.split())


async def _ensure_narration_length(script: dict, topic: dict) -> dict:
    """
    Code-level enforcement: prompt-only word-count constraints are not
    reliable on the current model (observed narrations as short as 10 words
    despite explicit 25-30 word instructions). Up to 2 retries with an
    increasingly explicit expansion instruction; if still short after both,
    leave as-is rather than fabricate padding — an honest short video beats
    a padded fake one.
    """
    narration = script.get("narration", "")

    for attempt in range(2):
        wc = _word_count(narration)
        if wc >= _MIN_NARRATION_WORDS:
            break

        expand_prompt = _EXPAND_INSTRUCTION.format(
            narration=narration,
            word_count=wc,
            summary=topic.get("summary", ""),
        )
        try:
            response = await _llm.ainvoke([HumanMessage(content=expand_prompt)])
            expanded = response.content.strip().strip('"')
            if _word_count(expanded) > wc:
                narration = expanded
        except Exception:
            break  # keep whatever we have on failure — no fabricated padding

    return {**script, "narration": narration}


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
        # Minimal fallback so the graph doesn't die here — matches the new
        # 2-beat, 10-12s hook/stance structure (not the old 3-beat explainer shape).
        script = {
            "hook": topic.get("title", "")[:80],
            "beats": [
                {"beat": "hook_visual", "visual_idea": "text overlay on dark background introducing the topic"},
                {"beat": "stance_payoff", "visual_idea": "text overlay stating the key takeaway"},
            ],
            "narration": topic.get("summary", "")[:150],
            "retention_notes": "none",
        }

    script = await _ensure_narration_length(script, topic)

    return {**state, "script": script}


# Re-export the helper so write_post can reuse it
build_persona_prompt = _build_persona_prompt
