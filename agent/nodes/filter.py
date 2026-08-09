"""
filter_seen node — drop candidates already covered.

Primary dedup is LOCAL (our own SQLite/Postgres posts table) — this does
not depend on any third-party service and is always available. Breeth's
search_graph is used only as a secondary, best-effort signal on top of
that, since it has been confirmed unreliable this session (every call has
returned an error, and the previous code silently passed every candidate
through on that error, which is the direct cause of the same topic being
selected 6 times in a row — see ISSUES_AND_FIX_PLAN.md item 1).
"""
import asyncio
import logging
import re

from agent.state import AgentState
from db.models import Post, get_session
from mcp_client import get_tool

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.82
PER_CALL_TIMEOUT = 8  # seconds per individual search_graph call

# How many of the agent's most recent published posts to check candidates
# against. Kept small and fast — this is a per-tick check, not a full-history
# scan.
LOCAL_HISTORY_LIMIT = 100

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "for", "and", "or", "with", "at", "by", "from", "as", "its", "our",
}


def _title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", title.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity over non-stopword tokens — same approach as
    meme/memory/repetition.py, reused here since it's cheap, dependency-free,
    and already proven to catch near-duplicate phrasing in this project."""
    tokens_a, tokens_b = _title_tokens(a), _title_tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0

# A title match at or above this similarity is treated as "already covered"
# even if the URL differs (e.g. the same story re-syndicated or re-crawled
# with a slightly different title).
LOCAL_TITLE_SIMILARITY_THRESHOLD = 0.6


def _get_local_history(agent_id: str) -> tuple[set[str], list[str]]:
    """Returns (seen_urls, seen_titles) for this agent's published posts."""
    with get_session() as db:
        rows = (
            db.query(Post.topic_url, Post.topic_title)
            .filter(Post.agent_id == agent_id)
            .order_by(Post.id.desc())
            .limit(LOCAL_HISTORY_LIMIT)
            .all()
        )
    seen_urls = {r[0] for r in rows if r[0]}
    seen_titles = [r[1] for r in rows if r[1]]
    return seen_urls, seen_titles


def _local_filter(candidates: list[dict], agent_id: str) -> list[dict]:
    seen_urls, seen_titles = _get_local_history(agent_id)

    fresh = []
    dropped = 0
    for c in candidates:
        url = c.get("url", "")
        title = c.get("title", "")

        if url and url in seen_urls:
            dropped += 1
            logger.info("filter_seen: local dedup dropped '%s' — exact URL already published", title[:60])
            continue

        near_dup = next(
            (t for t in seen_titles if _title_similarity(title, t) >= LOCAL_TITLE_SIMILARITY_THRESHOLD),
            None,
        )
        if near_dup:
            dropped += 1
            logger.info(
                "filter_seen: local dedup dropped '%s' — too similar to already-published '%s'",
                title[:60], near_dup[:60],
            )
            continue

        fresh.append(c)

    logger.info("filter_seen: local dedup — %d/%d candidates passed (%d dropped)", len(fresh), len(candidates), dropped)
    return fresh


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
    Two-stage dedup:
    1. Local DB check (always available, always applied) — drops exact
       URL repeats and near-duplicate titles against this agent's own
       published post history.
    2. Breeth search_graph (best-effort secondary signal) — only run on
       whatever survives stage 1. If Breeth errors (currently: always),
       candidates pass through stage 2 unchanged, but stage 1 has already
       done the real work.
    """
    candidates = state["candidates"]
    agent_id = state["agent_id"]

    locally_fresh = _local_filter(candidates, agent_id)

    try:
        search_tool = get_tool("search_graph")
    except KeyError:
        logger.warning("filter_seen: search_graph not available — local dedup only")
        return {**state, "candidates": locally_fresh}

    tasks = [_check_one(search_tool, c) for c in locally_fresh]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    fresh = [c for c, keep in results if keep]

    logger.info("filter_seen: %d/%d candidates passed (after local + breeth)", len(fresh), len(candidates))
    return {**state, "candidates": fresh}
