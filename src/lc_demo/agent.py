"""Steps 4, 6 and 7: agent factory combining local, RAG and MCP tools."""

from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from lc_demo.mcp_client import load_mcp_tools
from lc_demo.models import get_model
from lc_demo.rag import search_manual
from lc_demo.tools import get_cnpj_status

SYSTEM_PROMPT = """\
You are a Brazilian fiscal compliance assistant.
- Use get_cnpj_status for any CNPJ question, and mention the date of the status it reports.
- Use search_manual for ECF rules and answer only from what it returns.
- Use the fiscal MCP tools for filing deadlines.
If the tools don't cover something, say so instead of guessing.
Always reply in Brazilian Portuguese, unless the user writes in another language."""


def build_agent(tools: list[BaseTool], *, checkpointer: Checkpointer = None):
    return create_agent(
        model=get_model(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


async def build_full_agent(*, checkpointer: Checkpointer = None):
    """Local + RAG + MCP tools in a single agent."""
    mcp_tools = await load_mcp_tools()
    return build_agent([get_cnpj_status, search_manual, *mcp_tools], checkpointer=checkpointer)
