"""Run one agent tick directly and print the result. No server needed."""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

async def main():
    from mcp_client import init_mcp_client
    print("Connecting to MCP...")
    await init_mcp_client()

    from db.models import Agent, Post, get_session
    from agent.scheduler import _fetch_memory_context
    from agent.graph import run_agent_tick

    with get_session() as db:
        agent = db.query(Agent).order_by(Agent.created_at.desc()).first()
        if not agent:
            print("No agent in DB — run /init first")
            return
        agent_id = agent.id
        persona = json.loads(agent.persona_json)
        print(f"Agent: {agent_id}  ({agent.persona_name})")

    print("Fetching memory context...")
    persona_doc, memory_context = await _fetch_memory_context(agent_id)
    print(f"  persona_doc keys: {list(persona_doc.keys()) if persona_doc else '(empty)'}")
    print(f"  memory_context items: {len(memory_context)}")

    print("Running tick...")
    try:
        await run_agent_tick(agent_id, persona, persona_doc, memory_context)
        print("Tick finished.")
    except Exception as exc:
        import traceback
        print(f"\n=== TICK ERROR ===\n{exc}\n")
        traceback.print_exc()
        return

    with get_session() as db:
        post = db.query(Post).filter(Post.agent_id == agent_id).order_by(Post.id.desc()).first()
        if post:
            print(f"\n=== POST CREATED ===")
            print(f"  ID:      {post.id}")
            print(f"  Type:    {post.content_type}")
            print(f"  Topic:   {post.topic_title}")
            print(f"  Text:    {post.text[:400]}")
        else:
            print("\nTick ran but no post was written.")

asyncio.run(main())
