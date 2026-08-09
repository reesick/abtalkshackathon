"""
Shared MCP client — initialised once at app startup, reused across all nodes.

Breeth: Bearer-token auth via Authorization header (from screenshot config).
Flora:  same pattern — fill FLORA_API_KEY when you have it.
"""
import logging
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

BREETH_MCP_URL = os.environ.get("BREETH_MCP_URL", "")
BREETH_API_KEY = os.environ.get("BREETH_API_KEY", "")

FLORA_MCP_URL  = os.environ.get("FLORA_MCP_URL", "")
FLORA_API_KEY  = os.environ.get("FLORA_API_KEY", "")

_client: MultiServerMCPClient | None = None
_tools:  list = []


def _is_valid_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    placeholders = ["FILL_IN", "your-flora", "your_breeth", "your_flora", "example.com"]
    return not any(p in url for p in placeholders)


def _server_config() -> dict:
    config: dict = {}
    if _is_valid_url(BREETH_MCP_URL):
        cfg = {
            "url": BREETH_MCP_URL,
            "transport": "streamable_http",
        }
        if BREETH_API_KEY and "your_" not in BREETH_API_KEY:
            cfg["headers"] = {"Authorization": f"Bearer {BREETH_API_KEY}"}
        config["breeth"] = cfg

    if _is_valid_url(FLORA_MCP_URL):
        cfg = {
            "url": FLORA_MCP_URL,
            "transport": "streamable_http",
        }
        if FLORA_API_KEY and "your_" not in FLORA_API_KEY:
            cfg["headers"] = {"Authorization": f"Bearer {FLORA_API_KEY}"}
        config["flora"] = cfg

    return config


async def init_mcp_client() -> None:
    """Call once inside the FastAPI lifespan before the scheduler starts."""
    global _client, _tools
    config = _server_config()
    if not config:
        logger.warning("mcp_client: No active MCP server URLs configured (or placeholder URLs found). Skipping MCP connection.")
        _tools = []
        return

    try:
        _client = MultiServerMCPClient(config)
        _tools = await _client.get_tools()
        logger.info("MCP tools registered (%d tools): %s", len(_tools), [t.name for t in _tools])
    except Exception as exc:
        logger.warning("mcp_client: Could not connect to MCP servers (%s). Operating in fallback mode.", exc)
        _tools = []


def get_tools() -> list:
    return _tools


def get_tool(name: str):
    """Return a single MCP tool by its declared name (returns None if not found or empty)."""
    for t in get_tools():
        if t.name == name:
            return t
    logger.warning("MCP tool '%name' not found. Operating with empty/fallback tool.", name)
    return None

