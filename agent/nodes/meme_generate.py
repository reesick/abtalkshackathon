"""
meme_generate node — runs the full MemeEngine pipeline (template retrieval
-> ranking -> humour skill -> quality gate -> render) for the selected
topic (meme spec sections 61, 113, 114). Combines what the spec's suggested
file layout calls meme_select.py + meme_generate.py + meme_judge.py into
one node, since MemeEngine.process() already performs all three as one
interdependent sequence per template candidate (you can't judge captions
for a template without having generated them for that specific template
first, and you don't know which template "wins" until judging runs) —
splitting them into separate graph nodes would mean re-running template
ranking or re-fetching state between nodes for no real benefit. The
underlying stages remain separately testable via meme/engine.py and its
submodules.
"""
import logging

from agent.state import AgentState
from meme.engine import MemeEngine

logger = logging.getLogger(__name__)

_engine = MemeEngine()


async def meme_generate_node(state: AgentState) -> AgentState:
    topic = state.get("selected_topic")
    if not topic or state.get("content_type") != "meme_post":
        return state

    result = await _engine.process(agent_id=state["agent_id"], topic=topic)

    if not result["should_make_meme"]:
        logger.info("meme_generate_node: degrading to text_post — %s", result.get("reason"))
        return {**state, "meme_result": result, "content_type": "text_post"}

    return {**state, "meme_result": result}
