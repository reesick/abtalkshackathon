"""
LangGraph StateGraph wiring.

Scope: meme subsystem integration (see
meme_intelligence_humour_system_implementation.md). Image generation is
disconnected — agent/nodes/script.py, plan_assets.py, assets.py,
validate_assets.py, and agent/nodes/format.py (decide_format) remain on
disk as a clean seam but are NOT wired into this graph. Video was already
disconnected in a prior pass (agent/nodes/video.py, omni_prompt.py — never
wired here). TTS (agent/nodes/generate_tts.py) is also left disconnected
but explicitly NOT touched/removed per instruction — it stays exactly as
it was, a clean seam, not reconnected either.

Graph shape:
  discover → filter → judge → [no topic: END] → meme_opportunity
    → [meme_post]  → meme_generate (may degrade content_type back to text_post
                       if quality gate fails or render fails) → write_post
    → [text_post] ────────────────────────────────────────────→ write_post
  → generate_rationale → persist → END
"""
import logging
import uuid
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agent.nodes.discover import discover_topics
from agent.nodes.filter import filter_seen
from agent.nodes.judge import editorial_judge
from agent.nodes.meme_generate import meme_generate_node
from agent.nodes.meme_opportunity import meme_opportunity_node
from agent.nodes.persist import persist
from agent.nodes.post import write_post
from agent.nodes.rationale import generate_rationale
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional edge helpers
# ---------------------------------------------------------------------------

def _after_judge(state: AgentState) -> Literal["meme_opportunity", "end"]:
    """If judge found nothing, abort the tick cleanly."""
    if not state.get("selected_topic") or state.get("error") == "no_candidates":
        return "end"
    return "meme_opportunity"


def _after_meme_opportunity(state: AgentState) -> Literal["meme_generate", "write_post"]:
    if state["content_type"] == "meme_post":
        return "meme_generate"
    return "write_post"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Nodes
    g.add_node("discover_topics", discover_topics)
    g.add_node("filter_seen", filter_seen)
    g.add_node("editorial_judge", editorial_judge)
    g.add_node("meme_opportunity", meme_opportunity_node)
    g.add_node("meme_generate", meme_generate_node)
    g.add_node("write_post", write_post)
    g.add_node("generate_rationale", generate_rationale)
    g.add_node("persist", persist)

    # Linear edges
    g.add_edge(START, "discover_topics")
    g.add_edge("discover_topics", "filter_seen")
    g.add_edge("filter_seen", "editorial_judge")

    # Conditional: judge may abort
    g.add_conditional_edges(
        "editorial_judge",
        _after_judge,
        {"meme_opportunity": "meme_opportunity", "end": END},
    )

    # Conditional: meme vs text routing
    g.add_conditional_edges(
        "meme_opportunity",
        _after_meme_opportunity,
        {"meme_generate": "meme_generate", "write_post": "write_post"},
    )

    # meme_generate always flows to write_post (it may have degraded
    # content_type back to text_post internally — write_post reads that).
    g.add_edge("meme_generate", "write_post")

    g.add_edge("write_post", "generate_rationale")
    g.add_edge("generate_rationale", "persist")
    g.add_edge("persist", END)

    return g


_compiled = build_graph().compile()


async def run_agent_tick(agent_id: str, persona: dict, persona_doc: dict, memory_context: list) -> None:
    """
    Entry point called by the scheduler for each tick.
    Populates the initial state and runs the compiled graph.
    """
    tick_id = str(uuid.uuid4())
    logger.info("tick start — agent=%s tick=%s", agent_id, tick_id)

    initial_state: AgentState = {
        "agent_id": agent_id,
        "tick_id": tick_id,
        "persona": persona,
        "persona_doc": persona_doc,
        "memory_context": memory_context,
        "candidates": [],
        "rejected_topics": [],
        "selected_topic": None,
        "content_type": "text_post",
        "script": None,
        "media_plan": [],
        "image_assets": [],
        "video_asset": None,
        "tts_segments": [],
        "omni_prompt": None,
        "meme_opportunity": None,
        "meme_result": None,
        "post_text": None,
        "rationale": None,
        "error": None,
    }

    try:
        await _compiled.ainvoke(initial_state)
        logger.info("tick complete — agent=%s tick=%s", agent_id, tick_id)
    except Exception as exc:
        logger.exception("tick error — agent=%s tick=%s — %s", agent_id, tick_id, exc)
        # Write a failed tick_log row
        from db.models import TickLog, get_session
        from datetime import datetime, timezone
        with get_session() as db:
            db.add(TickLog(
                agent_id=agent_id,
                tick_id=tick_id,
                tick_at=datetime.now(timezone.utc),
                published=False,
                error_msg=str(exc),
            ))
            db.commit()
