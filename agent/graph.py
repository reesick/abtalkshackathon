"""
LangGraph StateGraph wiring.

Graph shape:
  discover → filter → judge → [no topic: END] → format
    → [video] → write_script → generate_assets → assemble_video → write_post
    → [image] → write_script → generate_assets ──────────────────→ write_post
    → [text] ─────────────────────────────────────────────────────→ write_post
  → generate_rationale → persist → END
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agent.nodes.assets import generate_assets
from agent.nodes.discover import discover_topics
from agent.nodes.filter import filter_seen
from agent.nodes.format import decide_format
from agent.nodes.judge import editorial_judge
from agent.nodes.persist import persist
from agent.nodes.post import write_post
from agent.nodes.rationale import generate_rationale
from agent.nodes.script import write_script
from agent.nodes.video import assemble_video
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional edge helpers
# ---------------------------------------------------------------------------

def _after_judge(state: AgentState) -> Literal["decide_format", "end"]:
    """If judge found nothing, abort the tick cleanly."""
    if not state.get("selected_topic") or state.get("error") == "no_candidates":
        return "end"
    return "decide_format"


def _after_format(state: AgentState) -> Literal["write_script", "write_post"]:
    """Text posts skip the script/asset/video nodes entirely."""
    if state["content_type"] == "text_post":
        return "write_post"
    return "write_script"


def _after_assets(state: AgentState) -> Literal["assemble_video", "write_post"]:
    """
    If asset generation degraded to text_post, skip assembly.
    Image posts also skip video assembly.
    """
    if state["content_type"] in ("text_post", "image_post"):
        return "write_post"
    return "assemble_video"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # Nodes
    g.add_node("discover_topics", discover_topics)
    g.add_node("filter_seen", filter_seen)
    g.add_node("editorial_judge", editorial_judge)
    g.add_node("decide_format", decide_format)
    g.add_node("write_script", write_script)
    g.add_node("generate_assets", generate_assets)
    g.add_node("assemble_video", assemble_video)
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
        {"decide_format": "decide_format", "end": END},
    )

    # Conditional: format router
    g.add_conditional_edges(
        "decide_format",
        _after_format,
        {"write_script": "write_script", "write_post": "write_post"},
    )

    # Script → assets always (used by both video and image paths)
    g.add_edge("write_script", "generate_assets")

    # Conditional: after assets, branch video vs image/text
    g.add_conditional_edges(
        "generate_assets",
        _after_assets,
        {"assemble_video": "assemble_video", "write_post": "write_post"},
    )

    g.add_edge("assemble_video", "write_post")
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
        "image_assets": [],
        "video_asset": None,
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
