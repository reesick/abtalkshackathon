"""
persist node — write post to DB and push memory update to Breeth.

Breeth tool mapping (real names from check_tools.py):
  add_episode   — store an episode (text) in the knowledge graph
  record_fact   — store a subject/predicate/object triple
Both are scoped to the Bearer token; no agent_id param needed.
add_episode is async (returns task_id); we fire-and-forget.
"""
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agent.state import AgentState
from db.models import Post, TickLog, get_session
from mcp_client import get_tool

logger = logging.getLogger(__name__)


def _media_url(state: AgentState) -> tuple[str | None, str | None]:
    """
    Image generation is disconnected (meme subsystem integration). The
    only media path now is a rendered meme, if the meme engine produced
    and rendered one for this post.
    """
    meme_result = state.get("meme_result")
    if meme_result and meme_result.get("rendered_url"):
        return meme_result["rendered_url"], "meme"
    return None, None


async def _push_breeth_memory(state: AgentState) -> None:
    """
    Two Breeth writes per published post:
    1. add_episode — rich episode text so search_graph can find it later
       (this is what filter_seen searches against)
    2. record_fact — SPO triple locking the edge: persona covered topic
       (Breeth recommends record_fact when the edge structure matters)
    """
    topic = state["selected_topic"]
    persona = state["persona"]
    persona_name = persona.get("name", "the_persona")
    topic_title = topic.get("title", "")
    topic_url = topic.get("url", "")
    stance = (state.get("rationale") or {}).get("selected_because", "")[:200]
    content_type = state["content_type"]

    # 1. add_episode — full episode text for semantic recall
    episode_text = (
        f"{persona_name} published a {content_type} about: {topic_title}. "
        f"Source: {topic_url}. "
        f"Stance: {stance}"
    ).strip()

    try:
        add_tool = get_tool("add_episode")
        await add_tool.ainvoke({"text": episode_text})
        # Returns task_id — pipeline is async, we don't wait
    except Exception as exc:
        logger.warning("persist: add_episode failed — %s", exc)

    # 2. record_fact — locks the persona→topic edge
    try:
        fact_tool = get_tool("record_fact")
        await fact_tool.ainvoke({
            "subject": persona_name,
            "predicate": "published about",
            "object": topic_title,
        })
    except Exception as exc:
        logger.warning("persist: record_fact failed — %s", exc)


async def persist(state: AgentState) -> AgentState:
    """Write post to DB and fire Breeth memory updates."""
    topic = state["selected_topic"]
    media_url, media_type = _media_url(state)
    rationale = state.get("rationale") or {}
    now = datetime.now(timezone.utc)

    with get_session() as db:
        post = Post(
            agent_id=state["agent_id"],
            tick_id=state.get("tick_id", ""),
            text=state.get("post_text", ""),
            media_url=media_url,
            media_type=media_type,
            content_type=state["content_type"],
            topic_title=topic.get("title", ""),
            topic_url=topic.get("url", ""),
            topic_source=topic.get("source", ""),
            rationale=json.dumps(rationale),
            sources=json.dumps(rationale.get("sources", [])),
            created_at=now,
        )
        db.add(post)

        tick = TickLog(
            agent_id=state["agent_id"],
            tick_id=state.get("tick_id", ""),
            tick_at=now,
            published=True,
            content_type=state["content_type"],
            error_msg=state.get("error"),
        )
        db.add(tick)
        db.commit()
        db.refresh(post)
        post_id = post.id

    meme_result = state.get("meme_result")
    if meme_result and meme_result.get("rendered_url"):
        from meme.memory.usage import record_usage
        record_usage(
            agent_id=state["agent_id"],
            post_id=post_id,
            template_id=meme_result["template_id"],
            template_name=meme_result["template_name"],
            template_family=meme_result.get("template_family"),
            humour_mechanism=meme_result.get("humour_mechanism"),
            topic_title=topic.get("title", ""),
            topic_source=topic.get("source", ""),
            text_boxes=meme_result.get("text_boxes", []),
            humour_score=meme_result.get("score"),
            judge_score=None,
        )

    await _push_breeth_memory(state)

    logger.info("persist: post %s saved (%s)", post_id, state["content_type"])
    return state
