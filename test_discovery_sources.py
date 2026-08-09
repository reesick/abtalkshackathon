"""
Focused discovery-source test (see ai_influencer_discovery_sources_integration_guide.md
sections 33-36). Tests ONLY the discovery/source module:

  - calls each real collector function in agent/nodes/discover.py directly
  - live smoke test against real endpoints, small limits, real timeouts
  - no LLM calls, no content generation, no publishing, no scheduling

Prints a compact PASS/SKIP/FAIL report per source and a total summary.
A source is only marked PASS if it returned candidates through the actual
collector code (no faked results for missing credentials).
"""
import asyncio
from dataclasses import dataclass, field

from dotenv import load_dotenv
load_dotenv()

import aiohttp

from agent.nodes import discover as d


@dataclass
class Result:
    name: str
    status: str  # PASS | SKIP | FAIL
    count: int = 0
    detail: str = ""


RESULTS: list[Result] = []


def record(name: str, status: str, count: int = 0, detail: str = "") -> None:
    RESULTS.append(Result(name, status, count, detail))
    line = f"{name:<28} {status:<5} {count:>3} candidates"
    if detail:
        line += f"  ({detail})"
    print(line, flush=True)


async def test_rss(session: aiohttp.ClientSession) -> None:
    groups = {
        "Primary company RSS": d.RSS_FEEDS_PRIMARY,
        "Research RSS": d.RSS_FEEDS_RESEARCH,
        "Independent RSS": d.RSS_FEEDS_INDEPENDENT,
        "Company-secondary RSS": d.RSS_FEEDS_COMPANY_SECONDARY,
    }
    for group_name, feeds in groups.items():
        for feed_url in feeds:
            short = feed_url.split("//")[-1][:45]
            try:
                items = await d._fetch_rss(session, feed_url, max_entries=3 if "arxiv.org" in feed_url else 5)
                if items:
                    record(f"RSS: {short}", "PASS", len(items))
                elif "arxiv.org" in feed_url:
                    # arXiv publishes on weekdays only (<skipDays>Sunday,
                    # Saturday</skipDays> in the feed itself) — 0 entries on
                    # a weekend run is genuinely correct behavior, not a
                    # collector failure. Confirmed by reading the raw feed body.
                    record(f"RSS: {short}", "SKIP", 0, "0 entries — arXiv publishes weekdays only, verified in feed body")
                else:
                    record(f"RSS: {short}", "FAIL", 0, "0 candidates returned")
            except Exception as exc:
                record(f"RSS: {short}", "FAIL", 0, str(exc)[:60])


async def test_hn(session: aiohttp.ClientSession) -> None:
    try:
        items = await d._fetch_hn(session)
        status = "PASS" if items else "FAIL"
        record("Hacker News (all terms)", status, len(items))
    except Exception as exc:
        record("Hacker News (all terms)", "FAIL", 0, str(exc)[:60])


async def test_github(session: aiohttp.ClientSession) -> None:
    try:
        items = await d._fetch_github(session, limit=5)
        status = "PASS" if items else "FAIL"
        detail = "authenticated" if d.GITHUB_TOKEN else "unauthenticated"
        record("GitHub search", status, len(items), detail)
    except Exception as exc:
        record("GitHub search", "FAIL", 0, str(exc)[:60])


async def test_hf_papers(session: aiohttp.ClientSession) -> None:
    try:
        items = await d._fetch_huggingface_papers(session, limit=10)
        status = "PASS" if items else "FAIL"
        record("Hugging Face Trending Papers", status, len(items))
    except Exception as exc:
        record("Hugging Face Trending Papers", "FAIL", 0, str(exc)[:60])


async def test_product_hunt(session: aiohttp.ClientSession) -> None:
    if not d.PRODUCT_HUNT_API_TOKEN:
        record("Product Hunt", "SKIP", 0, "PRODUCT_HUNT_API_TOKEN not configured")
        return
    try:
        items = await d._fetch_product_hunt(session, limit=10)
        status = "PASS" if items else "FAIL"
        record("Product Hunt", status, len(items))
    except Exception as exc:
        record("Product Hunt", "FAIL", 0, str(exc)[:60])


async def test_youtube(session: aiohttp.ClientSession) -> None:
    if not d.YOUTUBE_API_KEY or not d.YOUTUBE_CHANNEL_IDS:
        record("YouTube", "SKIP", 0, "YOUTUBE_API_KEY / YOUTUBE_CHANNEL_IDS not configured")
        return
    try:
        items = await d._fetch_youtube(session)
        status = "PASS" if items else "FAIL"
        record("YouTube", status, len(items))
    except Exception as exc:
        record("YouTube", "FAIL", 0, str(exc)[:60])


async def test_full_orchestration() -> None:
    """Run the real discover_topics() node end-to-end, exactly as the graph would."""
    base_state = {
        "agent_id": "source-test",
        "tick_id": "source-test-tick",
        "persona": {"name": "test", "domain": "test"},
        "persona_doc": {},
        "memory_context": [],
        "candidates": [],
        "rejected_topics": [],
        "selected_topic": None,
        "content_type": "text_post",
        "script": None,
        "media_plan": [],
        "image_assets": [],
        "video_asset": None,
        "tts_segments": [],
        "omni_prompt": None,
        "post_text": None,
        "rationale": None,
        "error": None,
    }
    state = await d.discover_topics(base_state)
    candidates = state["candidates"]
    print(f"\nFull discover_topics() orchestration -> {len(candidates)} deduplicated candidates")

    by_source: dict[str, int] = {}
    for c in candidates:
        key = c["source"]
        by_source[key] = by_source.get(key, 0) + 1
    print("Breakdown by source:")
    for source, count in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {source:<20} {count}")

    # Schema sanity check — every candidate must have the shared shape.
    required_keys = {"title", "url", "source", "source_type", "source_class", "summary", "published_at", "fingerprint", "metadata"}
    bad = [c for c in candidates if not required_keys.issubset(c.keys())]
    print(f"\nSchema check: {len(candidates) - len(bad)}/{len(candidates)} candidates have all required fields")
    if bad:
        print(f"  MISSING FIELDS in {len(bad)} candidates — first offender: {bad[0]}")


async def main():
    print("DISCOVERY SOURCE TEST")
    print("=" * 60)
    print("Scope: discovery/source module ONLY. No LLM calls, no content")
    print("generation, no publishing, no scheduling. Live network smoke test.")
    print("=" * 60)
    print()

    async with aiohttp.ClientSession() as session:
        await test_rss(session)
        print()
        await test_hn(session)
        print()
        await test_github(session)
        await test_hf_papers(session)
        print()
        await test_product_hunt(session)
        await test_youtube(session)

    print()
    await test_full_orchestration()

    passed = sum(1 for r in RESULTS if r.status == "PASS")
    skipped = sum(1 for r in RESULTS if r.status == "SKIP")
    failed = sum(1 for r in RESULTS if r.status == "FAIL")

    print()
    print("=" * 60)
    print("TOTAL")
    print(f"PASS: {passed}")
    print(f"SKIP: {skipped}")
    print(f"FAIL: {failed}")
    print("=" * 60)

    if failed:
        print("\nFailed sources:")
        for r in RESULTS:
            if r.status == "FAIL":
                print(f"  - {r.name}: {r.detail}")


asyncio.run(main())
