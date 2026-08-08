"""filter_seen node — drop candidates already covered, via Breeth search_graph."""
import asyncio
import logging

from agent.state import AgentState
from mcp_client import get_tool

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.82
PER_CALL_TIMEOUT = 8  # seconds per individual search_graph call


def _top_score(hits) -> float:
    if not hits:
        return 0.0
    if not isinstance(hits, list):
        return 0.0
    first = hits[0]
    if not isinstance(first, dict):
        return 0.0
    for key in ("score", "similarity", "relevance", "distance"):
        if key in first:
            val = first[key]
            if key == "distance":
                return 1.0 - float(val)
            return float(val)
    return 0.5


async def _check_one(search_tool, candidate: dict) -> tuple[dict, bool]:
    """Return (candidate, should_keep). Passes through on any error."""
    query = candidate["title"]
    try:
        result = await asyncio.wait_for(
            search_tool.ainvoke({"query": query}),
            timeout=PER_CALL_TIMEOUT,
        )
        hits = result if isinstance(result, list) else []
        score = _top_score(hits)
        keep = score < SIMILARITY_THRESHOLD
        if not keep:
            logger.debug("filter_seen: dropped '%s' (score=%.2f)", query[:60], score)
        return candidate, keep
    except Exception as exc:
        logger.warning("filter_seen: search_graph error for '%s' — %s — passing through", query[:60], exc)
        return candidate, True  # pass through on any error


async def filter_seen(state: AgentState) -> AgentState:
    """
    Check all candidates in parallel against Breeth.
    Passes through on any Breeth error so we never lose a tick.
    """
    try:
        search_tool = get_tool("search_graph")
    except KeyError:
        logger.warning("filter_seen: search_graph not available — skipping dedup")
        return state

    candidates = state["candidates"]

    tasks = [_check_one(search_tool, c) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    fresh = [c for c, keep in results if keep]

    logger.info("filter_seen: %d/%d candidates passed", len(fresh), len(candidates))
    return {**state, "candidates": fresh}
