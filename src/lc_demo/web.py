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

from lc_demo import db, ui
from lc_demo.agent import build_full_agent
from lc_demo.auth import MIN_PASSWORD_LENGTH, authenticate, create_user, has_users, normalize_email
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


def show_signup(value: bool) -> None:
    st.session_state.signing_up = value


def login_page() -> None:
    """Split-screen intro + log-in/sign-up form; stops the script until someone is logged in."""
    intro, form = st.columns(2, gap=None)
    with intro:
        ui.intro_panel()
    with form, st.container(key="auth"):
        try:
            any_users = has_users()
        except psycopg.OperationalError:
            st.error(DB_DOWN)
            st.stop()
        if st.session_state.get("signing_up") or not any_users:
            signup_form(first_user=not any_users)
        else:
            login_form()
    st.stop()


def login_form() -> None:
    ui.auth_header("01 / Sign in", "Welcome back.", "Sign in to pick up your conversations where you left them.")
    with st.form("login"):
        email = st.text_input("Email address", placeholder="you@example.com", autocomplete="email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary", icon=":material/north_east:", width="stretch"):
            if authenticate(email, password):
                st.session_state.user = normalize_email(email)
                st.rerun()
            st.error("Invalid email or password.")
    st.button("New here? **Create an account**", type="tertiary", on_click=show_signup, args=(True,), width="stretch")


def signup_error(email: str, password: str, confirm: str) -> str | None:
    """Create the account; return a message to show if that wasn't possible."""
    if password != confirm:
        return "Passwords don't match."
    try:
        created = create_user(email, password)
    except ValueError as e:
        return str(e)
    return None if created else "An account with this email already exists. Sign in instead."


def signup_form(first_user: bool) -> None:
    if first_user:
        ui.auth_header(
            "01 / Get started", "Create the first account.", "No one has signed up yet. This account will be the first."
        )
    else:
        ui.auth_header(
            "02 / Create account",
            "Get started.",
            "Create an account to start asking questions. It takes a few seconds.",
        )
    with st.form("signup"):
        email = st.text_input("Email address", placeholder="you@example.com", autocomplete="email")
        password = st.text_input(
            "Password", type="password", autocomplete="new-password", help=f"At least {MIN_PASSWORD_LENGTH} characters."
        )
        confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")
        if st.form_submit_button("Create account", type="primary", icon=":material/north_east:", width="stretch"):
            if error := signup_error(email, password, confirm):
                st.error(error)
            else:
                st.session_state.signing_up = False
                st.session_state.user = normalize_email(email)
                st.rerun()
    if not first_user:
        st.button(
            "Already have an account? **Sign in**",
            type="tertiary",
            on_click=show_signup,
            args=(False,),
            width="stretch",
        )


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


# The login page is a full-width split screen; the chat keeps Streamlit's centered column.
st.set_page_config(page_title="lc-demo", page_icon="🧾", layout="centered" if "user" in st.session_state else "wide")
if "user" not in st.session_state:
    login_page()
chat_page(st.session_state.user)
