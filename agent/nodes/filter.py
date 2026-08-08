"""filter_seen node — drop candidates already covered, via Breeth search_graph."""
import logging

from agent.state import AgentState
from mcp_client import get_tool

logger = logging.getLogger(__name__)

# If search_graph returns results whose score (any common field name) exceeds
# this, the topic is considered already-covered.
SIMILARITY_THRESHOLD = 0.82


def _top_score(hits) -> float:
    """Extract the best score from search_graph results regardless of field name."""
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
            # distance: lower = more similar → invert
            if key == "distance":
                return 1.0 - float(val)
            return float(val)
    # No score field — presence of a result means something was found
    return 0.5


async def filter_seen(state: AgentState) -> AgentState:
    """
    For each candidate title, search Breeth for near-duplicate prior episodes.
    Drops candidates whose top search score exceeds SIMILARITY_THRESHOLD.
    Passes through on any Breeth error so we never lose a tick.
    """
    try:
        search_tool = get_tool("search_graph")
    except KeyError:
        logger.warning("filter_seen: search_graph not available — skipping dedup")
        return state

    candidates = state["candidates"]
    fresh: list[dict] = []

    for candidate in candidates:
        query = candidate["title"]
        try:
            result = await search_tool.ainvoke({"query": query})
            hits = result if isinstance(result, list) else []
            score = _top_score(hits)
            if score < SIMILARITY_THRESHOLD:
                fresh.append(candidate)
            else:
                logger.debug("filter_seen: dropped '%s' (score=%.2f)", query[:60], score)
        except Exception as exc:
            logger.warning("filter_seen: search_graph error for '%s' — %s", query[:60], exc)
            fresh.append(candidate)  # pass through on error

    logger.info("filter_seen: %d/%d candidates passed", len(fresh), len(candidates))
    return {**state, "candidates": fresh}
