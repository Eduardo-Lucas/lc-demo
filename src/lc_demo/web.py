"""Streamlit chat UI with login: `uv run streamlit run src/lc_demo/web.py`.

Users, memory and the conversation list live in Postgres (`docker-compose up -d`), so
chats survive server restarts. Each user only sees and loads their own conversations.
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Coroutine, Iterator

import psycopg
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from psycopg_pool import PoolTimeout

from lc_demo import db
from lc_demo.agent import build_full_agent
from lc_demo.auth import authenticate, has_users
from lc_demo.config import DATABASE_URL, redact
from lc_demo.main import user

DB_DOWN = (
    f"Can't reach Postgres at `{redact(DATABASE_URL)}`. "
    "Locally, start it with `docker-compose up -d`; otherwise check `DATABASE_URL`."
)


# --- async bridge: Streamlit reruns are sync, the agent (MCP tools) and DB pool are async ---


@st.cache_resource
def get_loop() -> asyncio.AbstractEventLoop:
    """One long-lived event loop shared by every session."""
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def run(coro: Coroutine):
    return asyncio.run_coroutine_threadsafe(coro, get_loop()).result()


def iter_sync(agen: AsyncIterator[str]) -> Iterator[str]:
    """Drive an async iterator on the background loop, one item at a time."""
    while True:
        try:
            yield run(anext(agen))
        except StopAsyncIteration:
            return


@st.cache_resource
def get_backend():
    """(pool, agent). Not cached on failure, so a reload retries the connection."""

    async def init():
        pool = await db.open_pool()
        return pool, await build_full_agent(checkpointer=await db.setup(pool))

    return run(init())


async def stream_reply(agent, text: str, config: dict) -> AsyncIterator[str]:
    async for chunk, meta in agent.astream(user(text), config, stream_mode="messages"):
        if meta["langgraph_node"] == "tools":
            yield f"\n\n*🔧 {chunk.name}*\n\n"
        elif isinstance(chunk, AIMessage) and chunk.text:
            yield chunk.text


# --- pages ---


def login_page() -> None:
    st.title("lc-demo")
    try:
        any_users = has_users()
    except psycopg.OperationalError:
        st.error(DB_DOWN)
        st.stop()
    if not any_users:
        st.info("No users yet. Create one with `uv run lc-demo-adduser <username>`, then reload.")
        st.stop()
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in", type="primary"):
            if authenticate(username, password):
                st.session_state.user = username
                st.rerun()
            st.error("Invalid username or password.")
    st.stop()


def sidebar(pool, agent, username: str) -> str | None:
    """Render the conversation list; return the selected thread id (None = new chat)."""
    conversations = run(db.list_conversations(pool, username))
    # Only ever load a thread this user owns, whatever is left in session state.
    if st.session_state.get("thread") not in {c["thread_id"] for c in conversations}:
        st.session_state.thread = None

    with st.sidebar:
        st.write(f"Logged in as **{username}**")
        if st.button("Log out"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        if st.button("➕ New chat", width="stretch"):
            st.session_state.thread = None
            st.rerun()
        for conv in conversations:
            thread_id = conv["thread_id"]
            selected = thread_id == st.session_state.thread
            left, right = st.columns([5, 1], vertical_alignment="center")
            if left.button(
                conv["title"],
                key=f"open-{thread_id}",
                type="primary" if selected else "tertiary",
                width="stretch",
            ):
                st.session_state.thread = thread_id
                st.rerun()
            if right.button("🗑", key=f"del-{thread_id}", help="Delete conversation", type="tertiary"):
                run(db.delete_conversation(pool, agent.checkpointer, username, thread_id))
                st.rerun()
    return st.session_state.thread


def render_history(agent, config: dict) -> None:
    for msg in run(agent.aget_state(config)).values.get("messages", []):
        if isinstance(msg, HumanMessage):
            st.chat_message("user").write(msg.text)
        elif isinstance(msg, AIMessage):
            with st.chat_message("assistant"):
                for call in msg.tool_calls:
                    st.caption(f"🔧 {call['name']}")
                if msg.text:
                    st.write(msg.text)


def chat_page(username: str) -> None:
    try:
        pool, agent = get_backend()
    except PoolTimeout:
        st.error(DB_DOWN)
        st.stop()
    thread = sidebar(pool, agent, username)

    st.title("Fiscal assistant")
    if thread:
        render_history(agent, {"configurable": {"thread_id": thread}})
    if text := st.chat_input("Ask about a CNPJ, ECF rules or filing deadlines…"):
        is_new = thread is None
        if is_new:
            thread = st.session_state.thread = run(db.create_conversation(pool, username, text))
        st.chat_message("user").write(text)
        with st.chat_message("assistant"):
            st.write_stream(iter_sync(stream_reply(agent, text, {"configurable": {"thread_id": thread}})))
        if is_new:
            st.rerun()  # show the new conversation in the sidebar


st.set_page_config(page_title="lc-demo", page_icon="🧾")
if "user" not in st.session_state:
    login_page()
chat_page(st.session_state.user)
