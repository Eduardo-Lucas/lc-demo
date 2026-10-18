"""Step 7: load tools from MCP servers and expose them as LangChain tools."""

import sys

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from lc_demo.config import MCP_SERVERS_DIR


def get_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "fiscal": {
                # Same interpreter as the app, so the server sees the uv env.
                "command": sys.executable,
                "args": [str(MCP_SERVERS_DIR / "fiscal_server.py")],
                "transport": "stdio",
            },
            # Remote servers work the same way:
            # "langchain_docs": {
            #     "url": "https://docs.langchain.com/mcp",
            #     "transport": "streamable_http",
            # },
        }
    )


async def load_mcp_tools(allow: set[str] | None = None) -> list[BaseTool]:
    """Fetch MCP tools, optionally keeping only the names in `allow`."""
    tools = await get_mcp_client().get_tools()
    return [t for t in tools if allow is None or t.name in allow]
