"""CLI entry point: `uv run lc-demo <step>`."""

import argparse
import asyncio
from collections.abc import Awaitable, Callable

from langgraph.checkpoint.memory import InMemorySaver

from lc_demo.agent import build_agent, build_full_agent
from lc_demo.mcp_client import load_mcp_tools
from lc_demo.models import extract_invoice, get_model
from lc_demo.rag import search_manual
from lc_demo.tools import get_cnpj_status


def user(text: str) -> dict:
    return {"messages": [{"role": "user", "content": text}]}


def reply(result: dict) -> str:
    """Text of the agent's last message (content may be a str or a list of blocks)."""
    content = result["messages"][-1].content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


async def demo_basic() -> None:
    msg = await get_model().ainvoke("Explain Django signals in one sentence.")
    print(msg.content)


async def demo_structured() -> None:
    invoice = await asyncio.to_thread(extract_invoice, "ACME Ltda, R$ 1.250,00, due 2026-11-05")
    print(invoice.model_dump_json(indent=2))


async def demo_agent() -> None:
    agent = build_agent([get_cnpj_status])
    print(reply(await agent.ainvoke(user("Is 11.222.333/0001-81 active?"))))


async def demo_rag() -> None:
    agent = build_agent([search_manual])
    print(reply(await agent.ainvoke(user("Who is required to file the ECF?"))))


async def demo_memory() -> None:
    agent = build_agent([], checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "user-42"}}
    await agent.ainvoke(user("My name is Edu."), config)
    print(reply(await agent.ainvoke(user("What's my name?"), config)))


async def demo_mcp() -> None:
    agent = build_agent(await load_mcp_tools())
    print(reply(await agent.ainvoke(user("When is the ECF for fiscal year 2025 due?"))))


async def chat() -> None:
    """Interactive REPL with every tool and per-session memory."""
    agent = await build_full_agent(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "cli-session"}}
    print("Chat started. Ctrl+C or 'exit' to quit.")
    while (text := (await asyncio.to_thread(input, "\nyou> ")).strip()).lower() != "exit":
        if text:
            print(f"bot> {reply(await agent.ainvoke(user(text), config))}")


DEMOS: dict[str, Callable[[], Awaitable[None]]] = {
    "basic": demo_basic,
    "structured": demo_structured,
    "agent": demo_agent,
    "rag": demo_rag,
    "memory": demo_memory,
    "mcp": demo_mcp,
    "chat": chat,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="lc-demo", description=__doc__)
    parser.add_argument("step", choices=[*DEMOS, "all"])
    step = parser.parse_args().step

    async def run() -> None:
        for name, demo in DEMOS.items():
            if step in (name, "all") and not (step == "all" and name == "chat"):
                print(f"\n=== {name} ===")
                await demo()

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, EOFError):
        print("\nBye!")


if __name__ == "__main__":
    main()
