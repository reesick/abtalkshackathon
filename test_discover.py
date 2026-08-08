"""Test just the discovery node — RSS, HN, Reddit."""
import asyncio
from dotenv import load_dotenv
load_dotenv()

async def main():
    from agent.nodes.discover import discover_topics

    state = {
        "agent_id": "test",
        "tick_id": "test",
        "persona": {"name": "TechVoice", "domain": "AI/ML"},
        "persona_doc": {},
        "memory_context": [],
        "candidates": [],
        "rejected_topics": [],
        "selected_topic": None,
        "content_type": "text_post",
        "script": None,
        "image_assets": [],
        "video_asset": None,
        "post_text": None,
        "rationale": None,
        "error": None,
    }

    print("Running discover_topics...")
    result = await discover_topics(state)
    candidates = result["candidates"]
    print(f"\nFound {len(candidates)} candidates\n")
    for i, c in enumerate(candidates[:5]):
        print(f"  {i+1}. [{c['source']}] {c['title'][:80]}")

asyncio.run(main())
