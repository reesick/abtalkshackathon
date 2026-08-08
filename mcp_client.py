"""
Shared MCP client — initialised once at app startup, reused across all nodes.

Breeth: Bearer-token auth via Authorization header (from screenshot config).
Flora:  same pattern — fill FLORA_API_KEY when you have it.
"""
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

BREETH_MCP_URL = os.environ["BREETH_MCP_URL"]   # https://mcp.thebreeth.com/mcp
BREETH_API_KEY = os.environ["BREETH_API_KEY"]   # ck_live_...

FLORA_MCP_URL  = os.environ.get("FLORA_MCP_URL", "")
FLORA_API_KEY  = os.environ.get("FLORA_API_KEY", "")

_client: MultiServerMCPClient | None = None
_tools:  list | None = None


def _server_config() -> dict:
    config: dict = {
        "breeth": {
            "url": BREETH_MCP_URL,
            "transport": "streamable_http",
            "headers": {"Authorization": f"Bearer {BREETH_API_KEY}"},
        },
    }
    if FLORA_MCP_URL and not FLORA_MCP_URL.startswith("https://FILL_IN"):
        cfg = {
            "url": FLORA_MCP_URL,
            "transport": "streamable_http",
        }
        if FLORA_API_KEY:
            cfg["headers"] = {"Authorization": f"Bearer {FLORA_API_KEY}"}
        config["flora"] = cfg
    return config


async def init_mcp_client() -> None:
    """Call once inside the FastAPI lifespan before the scheduler starts."""
    global _client, _tools
    _client = MultiServerMCPClient(_server_config())
    _tools = await _client.get_tools()
    import logging
    logging.getLogger(__name__).info(
        "MCP tools registered: %s", [t.name for t in _tools]
    )


def get_tools() -> list:
    if _tools is None:
        raise RuntimeError("MCP client not initialised — call init_mcp_client() first")
    return _tools


def get_tool(name: str):
    """Return a single MCP tool by its declared name (raises KeyError if not found)."""
    for t in get_tools():
        if t.name == name:
            return t
    raise KeyError(
        f"MCP tool '{name}' not found. Available: {[t.name for t in get_tools()]}"
    )
