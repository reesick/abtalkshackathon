"""
check_tools.py — run this once before starting the server to confirm
what tool names Breeth (and Flora, if configured) actually expose.

Usage:
    python check_tools.py

Prints every MCP tool name + its input schema summary so you can
update filter.py / persist.py / scheduler.py / routes.py to match.
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

from mcp_client import init_mcp_client, get_tools


async def main():
    print("Connecting to MCP servers...\n")
    await init_mcp_client()

    tools = get_tools()
    print(f"Found {len(tools)} tool(s):\n")
    for t in tools:
        schema = getattr(t, "args_schema", None)
        fields = ""
        if schema:
            try:
                props = schema.schema().get("properties", {})
                fields = ", ".join(props.keys())
            except Exception:
                fields = "(schema unavailable)"
        print(f"  {t.name}")
        print(f"    description : {getattr(t, 'description', '')[:120]}")
        print(f"    input fields: {fields}")
        print()

    print("---")
    print("Cross-check these names against the TOOL_NAME constants in:")
    print("  agent/nodes/filter.py    (breeth_search_memory)")
    print("  agent/nodes/persist.py   (breeth_store_memory, breeth_update_document)")
    print("  agent/scheduler.py       (breeth_get_document, breeth_search_memory)")
    print("  api/routes.py            (breeth_create_document)")
    print("  agent/nodes/assets.py    (nano_banana_2_generate)")
    print("  agent/nodes/video.py     (google_omni_assemble)")


if __name__ == "__main__":
    asyncio.run(main())
