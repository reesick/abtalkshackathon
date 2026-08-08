"""
APScheduler setup — one job per agent, jittered 150-240 min interval.

Breeth tool mapping (real names):
  get_unified_profile — merged persona profile across all groups (no params)
  search_graph        — semantic search for recent episodes
"""
import json
import logging
import random
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agent.graph import run_agent_tick
from db.models import Agent, get_session
from mcp_client import get_tool

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()
_scheduler_started = False


async def _fetch_memory_context(agent_id: str) -> tuple[dict, list]:
    """
    Pull persona profile + recent published episodes from Breeth.
    Returns (persona_doc, recent_posts_list).
    Silently degrades to empty values if Breeth is unavailable.
    """
    persona_doc: dict = {}
    recent_posts: list = []

    # Get the unified director profile — this is the long-term persona memory
    try:
        profile_tool = get_tool("get_unified_profile")
        raw = await profile_tool.ainvoke({})
        persona_doc = raw if isinstance(raw, dict) else {}
    except Exception as exc:
        logger.warning("scheduler: get_unified_profile failed — %s", exc)

    # Search for recent published episodes for tone/continuity context
    try:
        search_tool = get_tool("search_graph")
        raw = await search_tool.ainvoke({"query": "published post about AI technology"})
        recent_posts = raw if isinstance(raw, list) else []
    except Exception as exc:
        logger.warning("scheduler: search_graph (recent posts) failed — %s", exc)

    return persona_doc, recent_posts


async def _tick(agent_id: str) -> None:
    """Single scheduler tick — fetches fresh context, then runs the graph."""
    logger.info("scheduler: _tick fired for agent=%s", agent_id)
    try:
        with get_session() as db:
            agent_row = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent_row:
                logger.error("scheduler: agent %s not found in DB — removing job", agent_id)
                _scheduler.remove_job(agent_id)
                return
            persona = json.loads(agent_row.persona_json)

        persona_doc, memory_context = await _fetch_memory_context(agent_id)
        await run_agent_tick(agent_id, persona, persona_doc, memory_context)
    except Exception as exc:
        logger.exception("scheduler: _tick unhandled exception for agent=%s — %s", agent_id, exc)


def _jitter_minutes() -> int:
    return random.randint(150, 240)


def start_agent_job(agent_id: str) -> None:
    """
    Register (or replace) a jittered scheduler job for the given agent.
    Fires ~5 seconds after registration so the eval window sees the first post fast.
    """
    global _scheduler_started

    if not _scheduler_started:
        _scheduler.start()
        _scheduler_started = True

    if _scheduler.get_job(agent_id):
        _scheduler.remove_job(agent_id)

    _scheduler.add_job(
        _tick,
        trigger="interval",
        minutes=_jitter_minutes(),
        id=agent_id,
        args=[agent_id],
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5),
        replace_existing=True,
    )
    logger.info("scheduler: job registered for agent=%s", agent_id)


def stop_agent_job(agent_id: str) -> None:
    if _scheduler.get_job(agent_id):
        _scheduler.remove_job(agent_id)
        logger.info("scheduler: job removed for agent=%s", agent_id)
