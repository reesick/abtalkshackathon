"""
decide_format node — deterministic router, no LLM call.

Scope (ml_engineer_persona.md section 6): text + single static image per post
only. Video is out of scope entirely — this router never returns "video_post".
"""
import re

from agent.state import AgentState

# Signal words that push toward an image post (a concrete visual is worth
# generating — a paper/benchmark/release/failure story with something to
# illustrate). Everything else defaults to a text post.
_IMAGE_SIGNALS = [
    "paper", "arxiv", "benchmark", "study", "research", "survey",
    "outperforms", "evals", "ablation", "released", "launches", "launch",
    "open source", "open-source", "weights",
]
_DEFAULT = "text_post"


def decide_format(state: AgentState) -> AgentState:
    """
    Route to image_post or text_post based on signals in the selected topic
    title + summary. No LLM spend here — keeps the graph fast and the
    routing auditable.
    """
    topic = state.get("selected_topic") or {}
    text = (topic.get("title", "") + " " + topic.get("summary", "")).lower()

    content_type = _DEFAULT
    if any(re.search(rf"\b{re.escape(s)}\b", text) for s in _IMAGE_SIGNALS):
        content_type = "image_post"

    return {**state, "content_type": content_type}
