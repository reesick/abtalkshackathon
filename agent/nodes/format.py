"""decide_format node — deterministic router, no LLM call."""
import re

from agent.state import AgentState

# Signal words that push toward a given format.
# Evaluated in order; first match wins.
_RULES: list[tuple[list[str], str]] = [
    (["released", "launches", "launch", "announces", "announcing", "v1", "v2", "v3",
      "open source", "open-source", "weights", "available now", "now available"], "video_post"),
    (["paper", "arxiv", "benchmark", "study", "research", "survey",
      "outperforms", "evals", "ablation"], "image_post"),
]
_DEFAULT = "text_post"


def decide_format(state: AgentState) -> AgentState:
    """
    Route to video_post, image_post, or text_post based on signals in the
    selected topic title + summary.  No LLM spend here — keeps the graph fast
    and the routing auditable.
    """
    topic = state.get("selected_topic") or {}
    text = (topic.get("title", "") + " " + topic.get("summary", "")).lower()

    content_type = _DEFAULT
    for signals, fmt in _RULES:
        if any(re.search(rf"\b{re.escape(s)}\b", text) for s in signals):
            content_type = fmt
            break

    return {**state, "content_type": content_type}
