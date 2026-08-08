"""discover_topics node — RSS, HN Algolia, Reddit (.json, no auth)"""
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any

import aiohttp
import feedparser

from agent.state import AgentState

RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss",
    "https://blog.google/technology/ai/rss",
    "https://huggingface.co/blog/feed.xml",
]

HN_QUERY_TERMS = ["LLM", "large language model", "AI agent", "open weights", "inference"]
REDDIT_SUBREDDITS = ["MachineLearning", "LocalLLaMA"]


def _fingerprint(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


async def _fetch_rss(session: aiohttp.ClientSession, url: str) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            text = await r.text()
        feed = feedparser.parse(text)
        return [
            {
                "title": e.get("title", ""),
                "url": e.get("link", ""),
                "source": "rss",
                "summary": e.get("summary", "")[:400],
                "published_at": e.get("published", ""),
                "fingerprint": _fingerprint(e.get("link", "")),
            }
            for e in feed.entries[:5]
            if e.get("link")
        ]
    except Exception:
        return []


async def _fetch_hn(session: aiohttp.ClientSession) -> list[dict]:
    results: list[dict] = []
    for term in HN_QUERY_TERMS[:3]:
        try:
            url = f"https://hn.algolia.com/api/v1/search_by_date?tags=story&query={term}&hitsPerPage=5"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data: Any = await r.json()
            for hit in data.get("hits", []):
                if hit.get("url"):
                    results.append({
                        "title": hit.get("title", ""),
                        "url": hit["url"],
                        "source": "hn",
                        "summary": hit.get("story_text", "")[:400],
                        "published_at": hit.get("created_at", ""),
                        "fingerprint": _fingerprint(hit["url"]),
                    })
        except Exception:
            continue
    return results


async def _fetch_reddit(session: aiohttp.ClientSession) -> list[dict]:
    results: list[dict] = []
    for sub in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
            headers = {"User-Agent": "abtalks-agent/1.0"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data: Any = await r.json()
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                link = post.get("url", "")
                if not link or link.startswith("https://www.reddit.com"):
                    continue
                results.append({
                    "title": post.get("title", ""),
                    "url": link,
                    "source": f"reddit/{sub}",
                    "summary": post.get("selftext", "")[:400],
                    "published_at": datetime.fromtimestamp(
                        post.get("created_utc", 0), tz=timezone.utc
                    ).isoformat(),
                    "fingerprint": _fingerprint(link),
                })
        except Exception:
            continue
    return results


async def discover_topics(state: AgentState) -> AgentState:
    """
    Fetch candidates from RSS, HN, and Reddit in parallel.
    De-duplicates by URL fingerprint before returning.
    """
    async with aiohttp.ClientSession() as session:
        rss_tasks = [_fetch_rss(session, feed) for feed in RSS_FEEDS]
        rss_results, hn_results, reddit_results = await asyncio.gather(
            asyncio.gather(*rss_tasks),
            _fetch_hn(session),
            _fetch_reddit(session),
        )

    # flatten RSS results
    rss_flat: list[dict] = [item for sublist in rss_results for item in sublist]

    all_items = rss_flat + hn_results + reddit_results

    # dedup by fingerprint, preserve insertion order
    seen: set[str] = set()
    candidates: list[dict] = []
    for item in all_items:
        fp = item["fingerprint"]
        if fp not in seen:
            seen.add(fp)
            candidates.append(item)

    return {**state, "candidates": candidates}
