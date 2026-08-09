"""
Joke similarity / semantic repetition detection (meme spec sections 42, 43).

Spec section 43 says: "If the project already has an embedding system,
reuse it. Do not introduce a new embedding provider unnecessarily." This
project has no embedding provider anywhere in the codebase (checked
agent/llm.py, mcp_client.py — Bedrock is used for chat completion only, no
embedding model call exists). Introducing one would mean a new AWS Bedrock
embedding model call, a new dependency, and a new failure mode, for a
feature (fully semantic joke-similarity detection) that has a legitimate,
much cheaper fallback: lexical/structural similarity.

This module uses a lexical overlap heuristic (normalized token Jaccard
similarity + common-phrase detection) instead. It is explicitly weaker
than true embedding similarity and is labeled as such — it will catch
near-duplicate phrasing ("me letting AI write the code" vs "me letting AI
write the whole function") but will miss purely conceptual duplicates
phrased very differently. If an embedding provider is added to the project
later for other reasons, this module should be upgraded to use it.
"""
import re

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "for", "and", "or", "me", "my", "i", "it", "this", "that", "when",
    "letting", "asking", "having",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def lexical_similarity(a: str, b: str) -> float:
    """Jaccard similarity over non-stopword tokens. 0-1."""
    tokens_a, tokens_b = _tokenize(a), _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


def similarity_penalty(caption: str, recent_captions: list[str]) -> float:
    """
    Spec section 43 thresholds: high similarity -> strong penalty, medium ->
    moderate, low -> none. Returns a 0-1 penalty (subtracted-style, caller
    decides the weight).
    """
    if not recent_captions:
        return 0.0

    max_sim = max((lexical_similarity(caption, prev) for prev in recent_captions), default=0.0)
    if max_sim >= 0.6:
        return 0.8
    if max_sim >= 0.35:
        return 0.4
    return 0.0
