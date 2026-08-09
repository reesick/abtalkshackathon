"""
meme_opportunity node — thin AgentState adapter over meme.opportunity
(meme spec section 17). The real logic lives in meme/opportunity.py so it
can be unit-tested independently of the graph.
"""
import logging

from agent.state import AgentState
from meme.opportunity import assess_opportunity

logger = logging.getLogger(__name__)


async def meme_opportunity_node(state: AgentState) -> AgentState:
    topic = state.get("selected_topic")
    if not topic:
        return {**state, "meme_opportunity": None, "content_type": "text_post"}

    opportunity = await assess_opportunity(topic)
    content_type = "meme_post" if opportunity["is_meme_worthy"] else "text_post"

    logger.info(
        "meme_opportunity_node: topic='%s' is_meme_worthy=%s confidence=%.2f -> content_type=%s",
        topic.get("title", "")[:60], opportunity["is_meme_worthy"], opportunity["confidence"], content_type,
    )

    return {**state, "meme_opportunity": opportunity, "content_type": content_type}
