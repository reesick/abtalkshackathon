"""Run each graph node one at a time to find where it hangs."""
import asyncio
from dotenv import load_dotenv
load_dotenv()

BASE_STATE = {
    "agent_id": "test",
    "tick_id": "test-tick",
    "persona": {"name": "TechVoice", "domain": "AI/ML and emerging tech"},
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

async def main():
    # Step 1: discover
    print("Step 1: discover_topics...", flush=True)
    from agent.nodes.discover import discover_topics
    state = await asyncio.wait_for(discover_topics(dict(BASE_STATE)), timeout=30)
    print(f"  OK — {len(state['candidates'])} candidates", flush=True)

    # Step 2: filter
    print("Step 2: filter_seen...", flush=True)
    from agent.nodes.filter import filter_seen
    from mcp_client import init_mcp_client
    await init_mcp_client()
    state = await asyncio.wait_for(filter_seen(state), timeout=60)
    print(f"  OK — {len(state['candidates'])} candidates after filter", flush=True)

    # Step 3: judge
    print("Step 3: editorial_judge...", flush=True)
    from agent.nodes.judge import editorial_judge
    state = await asyncio.wait_for(editorial_judge(state), timeout=60)
    print(f"  OK — selected: {state.get('selected_topic', {}).get('title', 'none')}", flush=True)

    # Step 4: decide format
    print("Step 4: decide_format...", flush=True)
    from agent.nodes.format import decide_format
    state = decide_format(state)
    print(f"  OK — content_type: {state['content_type']}", flush=True)

    # Step 5: write_script (only if not text_post)
    if state["content_type"] != "text_post":
        print("Step 5: write_script...", flush=True)
        from agent.nodes.script import write_script
        state = await asyncio.wait_for(write_script(state), timeout=60)
        print(f"  OK — hook: {state.get('script', {}).get('hook', '')[:60]}", flush=True)
    else:
        print("Step 5: skipped (text_post)", flush=True)

    # Step 6: write_post
    print("Step 6: write_post...", flush=True)
    from agent.nodes.post import write_post
    state = await asyncio.wait_for(write_post(state), timeout=60)
    print(f"  OK — post text: {state.get('post_text', '')[:200]}", flush=True)

    print("\n=== ALL NODES PASSED ===", flush=True)

asyncio.run(main())
