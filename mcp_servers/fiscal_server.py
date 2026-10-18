"""Minimal MCP server (stdio) used by step 7. Run standalone: uv run mcp_servers/fiscal_server.py"""

from fastmcp import FastMCP

mcp = FastMCP("fiscal")


@mcp.tool
def ecf_deadline(year: int) -> str:
    """Return the ECF filing deadline for a given fiscal year."""
    # Demo rule; confirm against the current Receita Federal instructions.
    return f"ECF for fiscal year {year}: last business day of July {year + 1}."


@mcp.tool
def list_obligations() -> list[str]:
    """List the federal accounting obligations this server knows about."""
    return ["ECD", "ECF"]


if __name__ == "__main__":
    # The app starts this server once per session; skip the banner, update check and INFO logs.
    mcp.run(show_banner=False, log_level="WARNING")
