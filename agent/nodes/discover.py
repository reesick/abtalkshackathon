"""
discover_topics node — multi-source discovery layer.

Sources (see ai_influencer_discovery_sources_integration_guide.md for the
full design doc this implements):
  - RSS: primary company feeds + independent/research/news feeds
  - Hacker News (Algolia search, all configured query terms)
  - GitHub (REST search API, momentum signal via stars/forks/recency)
  - Hugging Face Trending Papers (public page, best-effort HTML extraction)
  - Product Hunt (GraphQL v2, requires PRODUCT_HUNT_API_TOKEN — skips
    gracefully if not configured)
  - YouTube (Data API v3, requires YOUTUBE_API_KEY — skips gracefully if
    not configured)
  - Reddit (kept, but public .json endpoints currently return 403 — see
    guide section 25. Not required, fails visibly, not silently.)

Design principles carried over from the guide:
  - Every collector fails in isolation; one broken source never kills the
    whole discovery run.
  - Every candidate uses the same normalised schema (see _normalize below).
  - No silent failure — every source logs its own outcome (status/count).
  - No guessed/undocumented endpoints — every URL here was verified live
    via curl before being wired in.
"""
import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp
import feedparser

from agent.state import AgentState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source classification (guide section 32) — not used for filtering, just
# carried through on each candidate so downstream nodes (or a future human
# reviewer) can tell "company announced X" apart from "independent source
# discovered X".
# ---------------------------------------------------------------------------
_SOURCE_CLASS: dict[str, str] = {
    "openai.com": "primary",
    "anthropic.com": "primary",
    "blog.google": "primary",
    "aws.amazon.com": "primary",
    "blogs.nvidia.com": "primary",
    "microsoft.com": "research",
    "deepmind.google": "research",
    "bair.berkeley.edu": "research",
    "arxiv.org": "research",
    "huggingface.co": "community/research",
    "simonwillison.net": "independent/practitioner",
    "techcrunch.com": "independent/news",
    "github.com": "community",
    "hn": "community",
    "product_hunt": "product",
    "youtube": "community",
    "reddit": "community",
}


def _classify(domain_or_source: str) -> str:
    for key, cls in _SOURCE_CLASS.items():
        if key in domain_or_source:
            return cls
    return "independent"


# ---------------------------------------------------------------------------
# RSS feeds
# ---------------------------------------------------------------------------

# Existing primary company sources. Anthropic's own site no longer serves a
# native RSS feed (verified live: https://www.anthropic.com/news/rss -> 404,
# checked 2026-08-09). Using the actively-maintained community mirror from
# github.com/Olshansk/rss-feeds (hourly-refreshed, verified live) instead of
# dropping the source entirely.
RSS_FEEDS_PRIMARY = [
    "https://openai.com/news/rss.xml",
    "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
    "https://blog.google/technology/ai/rss",
    "https://huggingface.co/blog/feed.xml",
]

# New sources — all verified live (200, or 301/308 redirecting to 200) before
# being added here. Do NOT add a feed URL that wasn't actually checked.
RSS_FEEDS_RESEARCH = [
    "http://export.arxiv.org/rss/cs.LG",       # arXiv cs.LG (Machine Learning)
    "http://export.arxiv.org/rss/cs.CL",       # arXiv cs.CL (Computation & Language)
    "https://bair.berkeley.edu/blog/feed.xml",  # Berkeley AI Research
    "https://deepmind.google/blog/rss.xml",     # DeepMind
    "https://www.microsoft.com/en-us/research/feed/",  # Microsoft Research
]

RSS_FEEDS_INDEPENDENT = [
    "https://simonwillison.net/atom/everything/",  # Simon Willison (Atom, feedparser handles it)
    "https://techcrunch.com/category/artificial-intelligence/feed/",
]

RSS_FEEDS_COMPANY_SECONDARY = [
    "https://aws.amazon.com/blogs/machine-learning/feed/",
    "https://blogs.nvidia.com/feed/",
]

# All RSS feeds combined for the fetch loop. arXiv feeds are high-volume, so
# they get a smaller per-feed cap applied in _fetch_rss via max_entries.
ALL_RSS_FEEDS = (
    RSS_FEEDS_PRIMARY + RSS_FEEDS_RESEARCH + RSS_FEEDS_INDEPENDENT + RSS_FEEDS_COMPANY_SECONDARY
)

# Kept for backwards compatibility with anything importing the old name.
RSS_FEEDS = RSS_FEEDS_PRIMARY

# ---------------------------------------------------------------------------
# Hacker News
# ---------------------------------------------------------------------------

# All terms now used (guide section 6: "open weights" and "inference" were
# previously defined but never queried — [:3] slice removed). Extra terms
# from the guide added, capped so the request count stays sane.
HN_QUERY_TERMS = [
    "LLM",
    "large language model",
    "AI agent",
    "open weights",
    "inference",
    "AI coding",
    "agentic",
    "RAG",
    "local LLM",
    "reasoning model",
]

# Reddit removed — see the removed-collector comment further down for why.

# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_SEARCH_TERMS = ["LLM", "AI agent", "RAG", "multimodal AI"]

# ---------------------------------------------------------------------------
# Product Hunt
# ---------------------------------------------------------------------------

PRODUCT_HUNT_API_TOKEN = os.environ.get("PRODUCT_HUNT_API_TOKEN", "")
PRODUCT_HUNT_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"
_PH_AI_KEYWORDS = {
    "ai", "artificial intelligence", "llm", "agent", "agents", "generative ai",
    "image", "video", "voice", "speech", "coding", "developer tools",
    "automation", "rag", "machine learning",
}

# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
# Curated channel IDs — resolved and verified against the live YouTube Data
# API (channels.list) rather than guessed from memory (guide section 18).
YOUTUBE_CHANNEL_IDS: list[str] = [
    cid.strip() for cid in os.environ.get("YOUTUBE_CHANNEL_IDS", "").split(",") if cid.strip()
]


def _fingerprint(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _normalize(
    *,
    title: str,
    url: str,
    source: str,
    summary: str,
    published_at: str,
    source_type: str = "article",
    metadata: dict | None = None,
) -> dict:
    """
    Shared candidate shape across every collector (guide section 26).
    Keeps the original flat fields (title/url/source/summary/published_at/
    fingerprint) that existing downstream nodes (filter_seen, editorial_judge)
    already depend on, and adds source_type/source_class/metadata as new,
    additive fields — nothing existing breaks if a node ignores them.
    """
    return {
        "title": title,
        "url": url,
        "source": source,
        "source_type": source_type,
        "source_class": _classify(source if source not in ("hn", "product_hunt", "youtube") else source),
        "summary": (summary or "")[:400],
        "published_at": published_at or "",
        "fingerprint": _fingerprint(url),
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# RSS collector
# ---------------------------------------------------------------------------

async def _fetch_rss(session: aiohttp.ClientSession, url: str, max_entries: int = 5) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                logger.warning("discover: RSS %s returned HTTP %d", url, r.status)
                return []
            text = await r.text()
        feed = feedparser.parse(text)
        domain = url.split("/")[2] if "//" in url else url
        results = [
            _normalize(
                title=e.get("title", ""),
                url=e.get("link", ""),
                source="rss",
                summary=e.get("summary", ""),
                published_at=e.get("published", ""),
                source_type="article",
                metadata={"feed_url": url, "feed_domain": domain},
            )
            for e in feed.entries[:max_entries]
            if e.get("link")
        ]
        logger.info("discover: RSS %s -> %d candidates", url, len(results))
        return results
    except Exception as exc:
        logger.warning("discover: RSS %s failed — %s", url, exc)
        return []


# ---------------------------------------------------------------------------
# Hacker News collector
# ---------------------------------------------------------------------------

async def _fetch_hn(session: aiohttp.ClientSession) -> list[dict]:
    results: list[dict] = []
    for term in HN_QUERY_TERMS:
        try:
            url = f"https://hn.algolia.com/api/v1/search_by_date?tags=story&query={term}&hitsPerPage=5"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    logger.warning("discover: HN query '%s' returned HTTP %d", term, r.status)
                    continue
                data: Any = await r.json()
            term_count = 0
            for hit in data.get("hits", []):
                if hit.get("url"):
                    title = hit.get("title", "")
                    is_show_or_ask = title.lower().startswith(("show hn", "ask hn"))
                    results.append(_normalize(
                        title=title,
                        url=hit["url"],
                        source="hn",
                        summary=hit.get("story_text", ""),
                        published_at=hit.get("created_at", ""),
                        source_type="discussion" if is_show_or_ask else "article",
                        metadata={
                            "query_term": term,
                            "points": hit.get("points", 0),
                            "num_comments": hit.get("num_comments", 0),
                            "is_show_or_ask_hn": is_show_or_ask,
                        },
                    ))
                    term_count += 1
            logger.info("discover: HN query '%s' -> %d candidates", term, term_count)
        except Exception as exc:
            logger.warning("discover: HN query '%s' failed — %s", term, exc)
            continue
    return results


# ---------------------------------------------------------------------------
# Reddit — REMOVED. Public .json endpoints confirmed returning 403 (verified
# live, not assumed). Not required per the integration guide (section 25),
# and no bypass/workaround was attempted. If Reddit is revisited later, use
# the official OAuth API instead of the public .json endpoint.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GitHub collector — REST search API, no auth required (subject to GitHub's
# unauthenticated rate limit of 10 req/min for the search endpoint). Uses
# GITHUB_TOKEN if configured to raise that limit; skips cleanly, does not
# fail the whole run, if rate-limited.
# ---------------------------------------------------------------------------

async def _fetch_github(session: aiohttp.ClientSession, limit: int = 10) -> list[dict]:
    results: list[dict] = []
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    # Momentum signal: repos created in the last 14 days, sorted by stars.
    since = (datetime.now(timezone.utc).date().isoformat())
    for term in GITHUB_SEARCH_TERMS:
        try:
            query = f'{term} in:name,description,topics created:>{_days_ago(14)}'
            url = (
                "https://api.github.com/search/repositories"
                f"?q={query}&sort=stars&order=desc&per_page={limit}"
            )
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 403:
                    logger.warning("discover: GitHub search rate-limited (403) — skipping remaining terms")
                    break
                if r.status != 200:
                    logger.warning("discover: GitHub search '%s' returned HTTP %d", term, r.status)
                    continue
                data: Any = await r.json()
            term_count = 0
            for repo in data.get("items", []):
                results.append(_normalize(
                    title=repo.get("full_name", ""),
                    url=repo.get("html_url", ""),
                    source="github",
                    summary=repo.get("description", "") or "",
                    published_at=repo.get("created_at", ""),
                    source_type="repository",
                    metadata={
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "language": repo.get("language"),
                        "topics": repo.get("topics", []),
                        "search_term": term,
                    },
                ))
                term_count += 1
            logger.info("discover: GitHub search '%s' -> %d candidates", term, term_count)
        except Exception as exc:
            logger.warning("discover: GitHub search '%s' failed — %s", term, exc)
            continue
    return results


def _days_ago(n: int) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=n)).date().isoformat()


# ---------------------------------------------------------------------------
# Hugging Face Trending Papers collector — public page, best-effort HTML
# extraction. No documented API exists for this (verified before writing
# this — guide section 7 explicitly warns not to invent an endpoint). The
# page is server-rendered enough that paper links/titles/summaries can be
# pulled out with a targeted regex; this is inherently more brittle than an
# API and is isolated so a markup change only degrades this one source.
# ---------------------------------------------------------------------------

"""
Hugging Face Trending Papers collector — public page, structured extraction.

No documented API exists for this (verified before writing this — guide
section 7 explicitly warns not to invent an endpoint). The rendered page is
a SvelteKit app, but the paper list is embedded as HTML-entity-escaped JSON
inside a `data-target="DailyPapers" data-props="..."` attribute — this is
far more reliable than parsing rendered markup, and was confirmed by
downloading and inspecting the real page (not guessed).
"""

import html as _html_module
import json as _json_module

_HF_DAILY_PAPERS_RE = re.compile(
    r'data-target="DailyPapers"\s+data-props="(.*?)"><', re.DOTALL
)


async def _fetch_huggingface_papers(session: aiohttp.ClientSession, limit: int = 10) -> list[dict]:
    url = "https://huggingface.co/papers/trending"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                logger.warning("discover: HF trending papers returned HTTP %d", r.status)
                return []
            html_text = await r.text()
    except Exception as exc:
        logger.warning("discover: HF trending papers failed — %s", exc)
        return []

    match = _HF_DAILY_PAPERS_RE.search(html_text)
    if not match:
        logger.warning("discover: HF trending papers — DailyPapers block not found (page structure may have changed)")
        return []

    try:
        raw_json = _html_module.unescape(match.group(1))
        data = _json_module.loads(raw_json)
        entries = data.get("dailyPapers", [])
    except Exception as exc:
        logger.warning("discover: HF trending papers — failed to parse embedded JSON — %s", exc)
        return []

    results: list[dict] = []
    for entry in entries[:limit]:
        paper = entry.get("paper", {})
        paper_id = paper.get("id", "")
        if not paper_id:
            continue
        results.append(_normalize(
            title=entry.get("title") or paper.get("title", ""),
            url=f"https://huggingface.co/papers/{paper_id}",
            source="huggingface_papers",
            summary=entry.get("summary") or paper.get("summary", ""),
            published_at=entry.get("publishedAt") or paper.get("publishedAt", ""),
            source_type="paper",
            metadata={
                "paper_id": paper_id,
                "upvotes": paper.get("upvotes", 0),
                "github_stars": paper.get("githubStars"),
                "github_repo": paper.get("githubRepo"),
            },
        ))

    logger.info("discover: HF trending papers -> %d candidates", len(results))
    return results


# ---------------------------------------------------------------------------
# Product Hunt collector — GraphQL v2, requires PRODUCT_HUNT_API_TOKEN.
# Verified live: POST to the endpoint without a token returns a real
# "invalid_oauth_token" GraphQL error (401), confirming the endpoint and
# schema shape are live before wiring this in.
# ---------------------------------------------------------------------------

_PH_QUERY = """
query TrendingPosts($first: Int!) {
  posts(order: VOTES, first: $first) {
    edges {
      node {
        id
        name
        tagline
        description
        url
        createdAt
        featuredAt
        votesCount
        commentsCount
        topics {
          edges { node { name } }
        }
      }
    }
  }
}
"""


def _ph_is_ai_relevant(name: str, tagline: str, topics: list[str]) -> bool:
    haystack = f"{name} {tagline} {' '.join(topics)}".lower()
    return any(kw in haystack for kw in _PH_AI_KEYWORDS)


async def _fetch_product_hunt(session: aiohttp.ClientSession, limit: int = 10) -> list[dict]:
    if not PRODUCT_HUNT_API_TOKEN:
        logger.info("discover: Product Hunt skipped — PRODUCT_HUNT_API_TOKEN not configured")
        return []

    try:
        async with session.post(
            PRODUCT_HUNT_GRAPHQL_URL,
            json={"query": _PH_QUERY, "variables": {"first": limit}},
            headers={
                "Authorization": f"Bearer {PRODUCT_HUNT_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data: Any = await r.json()
            if r.status != 200 or "errors" in data:
                logger.warning("discover: Product Hunt returned HTTP %d — %s", r.status, data.get("errors"))
                return []
    except Exception as exc:
        logger.warning("discover: Product Hunt failed — %s", exc)
        return []

    results: list[dict] = []
    edges = (data.get("data", {}) or {}).get("posts", {}).get("edges", [])
    for edge in edges:
        node = edge.get("node", {})
        topics = [t["node"]["name"] for t in node.get("topics", {}).get("edges", [])]
        name = node.get("name", "")
        tagline = node.get("tagline", "")
        if not _ph_is_ai_relevant(name, tagline, topics):
            continue
        results.append(_normalize(
            title=name,
            url=node.get("url", ""),
            source="product_hunt",
            summary=node.get("description", "") or tagline,
            published_at=node.get("createdAt", ""),
            source_type="product",
            metadata={
                "votes": node.get("votesCount", 0),
                "comments": node.get("commentsCount", 0),
                "topics": topics,
                "featured_at": node.get("featuredAt"),
            },
        ))

    logger.info("discover: Product Hunt -> %d AI-relevant candidates (of %d total)", len(results), len(edges))
    return results


# ---------------------------------------------------------------------------
# YouTube collector — Data API v3, requires YOUTUBE_API_KEY and a curated
# channel list (YOUTUBE_CHANNEL_IDS). No search-the-whole-platform behavior
# per guide section 18.
# ---------------------------------------------------------------------------

async def _fetch_youtube(session: aiohttp.ClientSession, max_per_channel: int = 3) -> list[dict]:
    if not YOUTUBE_API_KEY:
        logger.info("discover: YouTube skipped — YOUTUBE_API_KEY not configured")
        return []
    if not YOUTUBE_CHANNEL_IDS:
        logger.info("discover: YouTube skipped — YOUTUBE_CHANNEL_IDS not configured")
        return []

    results: list[dict] = []
    for channel_id in YOUTUBE_CHANNEL_IDS:
        try:
            url = (
                "https://www.googleapis.com/youtube/v3/search"
                f"?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet"
                f"&order=date&type=video&maxResults={max_per_channel}"
            )
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    logger.warning("discover: YouTube channel %s returned HTTP %d", channel_id, r.status)
                    continue
                data: Any = await r.json()
            chan_count = 0
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId")
                if not video_id:
                    continue
                results.append(_normalize(
                    title=snippet.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    source="youtube",
                    summary=snippet.get("description", ""),
                    published_at=snippet.get("publishedAt", ""),
                    source_type="video",
                    metadata={"channel_id": channel_id, "channel_title": snippet.get("channelTitle", "")},
                ))
                chan_count += 1
            logger.info("discover: YouTube channel %s -> %d candidates", channel_id, chan_count)
        except Exception as exc:
            logger.warning("discover: YouTube channel %s failed — %s", channel_id, exc)
            continue
    return results


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def discover_topics(state: AgentState) -> AgentState:
    """
    Fetch candidates from every configured source in parallel.
    Every collector fails in isolation (guide section 27/28) — a broken
    optional source (missing API key, dead endpoint, rate limit) never
    kills the whole discovery run. De-duplicates by URL fingerprint before
    returning, preserving insertion order.
    """
    async with aiohttp.ClientSession() as session:
        rss_tasks = [
            _fetch_rss(session, feed, max_entries=3 if "arxiv.org" in feed else 5)
            for feed in ALL_RSS_FEEDS
        ]
        (
            rss_results,
            hn_results,
            github_results,
            hf_papers_results,
            product_hunt_results,
            youtube_results,
        ) = await asyncio.gather(
            asyncio.gather(*rss_tasks),
            _fetch_hn(session),
            _fetch_github(session),
            _fetch_huggingface_papers(session),
            _fetch_product_hunt(session),
            _fetch_youtube(session),
        )

    rss_flat: list[dict] = [item for sublist in rss_results for item in sublist]

    all_items = (
        rss_flat
        + hn_results
        + github_results
        + hf_papers_results
        + product_hunt_results
        + youtube_results
    )

    # dedup by fingerprint, preserve insertion order
    seen: set[str] = set()
    candidates: list[dict] = []
    for item in all_items:
        fp = item["fingerprint"]
        if fp not in seen:
            seen.add(fp)
            candidates.append(item)

    logger.info(
        "discover: %d total candidates after dedup (rss=%d hn=%d "
        "github=%d hf_papers=%d product_hunt=%d youtube=%d)",
        len(candidates), len(rss_flat), len(hn_results),
        len(github_results), len(hf_papers_results), len(product_hunt_results),
        len(youtube_results),
    )

    return {**state, "candidates": candidates}
