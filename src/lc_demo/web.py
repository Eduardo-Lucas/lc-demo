"""Streamlit chat UI with login: `uv run streamlit run src/lc_demo/web.py`.

Users, memory and the conversation list live in Postgres (`docker-compose up -d`), so
chats survive server restarts. Each user only sees and loads their own conversations.
"""

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Coroutine, Iterator

import psycopg
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
from psycopg_pool import PoolTimeout

from lc_demo import db, ui, usage
from lc_demo.agent import build_full_agent
from lc_demo.auth import MIN_PASSWORD_LENGTH, authenticate, create_user, has_users, normalize_email
from lc_demo.config import DAILY_MESSAGE_LIMIT, DATABASE_URL, redact
from lc_demo.main import user

# The interface is in Brazilian Portuguese (the app's audience); code and logs stay in English.
DB_DOWN = (
    f"Não foi possível conectar ao Postgres em `{redact(DATABASE_URL)}`. "
    "Localmente, inicie-o com `docker-compose up -d`; caso contrário, verifique `DATABASE_URL`."
)

DAILY_LIMIT_REACHED = f"Você atingiu seu limite diário de mensagens ({DAILY_MESSAGE_LIMIT}). Volte amanhã!"
UNAVAILABLE = "O assistente está temporariamente indisponível. Por favor, volte mais tarde."
REPLY_FAILED = "Algo deu errado ao gerar a resposta. Tente novamente em instantes."

logger = logging.getLogger(__name__)

# Friendly names for the tool-call lines shown in the chat.
TOOL_LABELS = {
    "get_cnpj_status": "Consultando o CNPJ",
    "search_manual": "Pesquisando no manual da ECF",
    "ecf_deadline": "Consultando o prazo da ECF",
    "list_obligations": "Listando as obrigações",
}


def tool_label(name: str) -> str:
    return f"🔧 {TOOL_LABELS.get(name, name)}"


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
            yield f"\n\n*{tool_label(chunk.name)}*\n\n"
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
    ui.auth_header("01 / Entrar", "Que bom ver você de novo.", "Entre para continuar suas conversas de onde parou.")
    with st.form("login"):
        email = st.text_input("E-mail", placeholder="voce@exemplo.com", autocomplete="email")
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary", icon=":material/north_east:", width="stretch"):
            if authenticate(email, password):
                st.session_state.user = normalize_email(email)
                st.rerun()
            st.error("E-mail ou senha inválidos.")
    st.button(
        "Primeira vez aqui? **Crie uma conta**", type="tertiary", on_click=show_signup, args=(True,), width="stretch"
    )


def signup_error(email: str, password: str, confirm: str) -> str | None:
    """Create the account; return a message to show if that wasn't possible."""
    if password != confirm:
        return "As senhas não coincidem."
    try:
        created = create_user(email, password)
    except ValueError as e:
        return str(e)
    return None if created else "Já existe uma conta com este e-mail. Entre com ela."


def signup_form(first_user: bool) -> None:
    if first_user:
        ui.auth_header(
            "01 / Primeiros passos", "Crie a primeira conta.", "Ninguém se cadastrou ainda. Esta será a primeira conta."
        )
    else:
        ui.auth_header(
            "02 / Criar conta",
            "Comece agora.",
            "Crie uma conta para começar a fazer perguntas. Leva poucos segundos.",
        )
    with st.form("signup"):
        email = st.text_input("E-mail", placeholder="voce@exemplo.com", autocomplete="email")
        password = st.text_input(
            "Senha", type="password", autocomplete="new-password", help=f"Pelo menos {MIN_PASSWORD_LENGTH} caracteres."
        )
        confirm = st.text_input("Confirme a senha", type="password", autocomplete="new-password")
        if st.form_submit_button("Criar conta", type="primary", icon=":material/north_east:", width="stretch"):
            if error := signup_error(email, password, confirm):
                st.error(error)
            else:
                st.session_state.signing_up = False
                st.session_state.user = normalize_email(email)
                st.rerun()
    if not first_user:
        st.button(
            "Já tem uma conta? **Entrar**",
            type="tertiary",
            on_click=show_signup,
            args=(False,),
            width="stretch",
        )


def sidebar(pool, agent, username: str, messages_today: int) -> str | None:
    """Render the conversation list; return the selected thread id (None = new chat)."""
    conversations = run(db.list_conversations(pool, username))
    # Only ever load a thread this user owns, whatever is left in session state.
    if st.session_state.get("thread") not in {c["thread_id"] for c in conversations}:
        st.session_state.thread = None

    with st.sidebar:
        st.write(f"Conectado como **{username}**")
        st.caption(f"Mensagens hoje: {min(messages_today, DAILY_MESSAGE_LIMIT)} de {DAILY_MESSAGE_LIMIT}")
        if st.button("Sair"):
            st.session_state.clear()
            st.rerun()
        st.divider()
        if st.button("➕ Nova conversa", width="stretch"):
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
            if right.button("🗑", key=f"del-{thread_id}", help="Excluir conversa", type="tertiary"):
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
                    st.caption(tool_label(call["name"]))
                if msg.text:
                    st.write(msg.text)


def chat_page(username: str) -> None:
    try:
        pool, agent = get_backend()
    except PoolTimeout:
        st.error(DB_DOWN)
        st.stop()
    status = run(usage.status(pool, username))
    thread = sidebar(pool, agent, username, status.messages_today)

    st.title("Assistente fiscal")
    if thread:
        render_history(agent, {"configurable": {"thread_id": thread}})
    if text := st.chat_input("Pergunte sobre um CNPJ, as regras da ECF ou prazos de entrega…"):
        if limit := status.blocked_by():
            st.warning(DAILY_LIMIT_REACHED if limit is usage.Limit.DAILY else UNAVAILABLE)
            st.stop()
        if thread is None:
            thread = st.session_state.thread = run(db.create_conversation(pool, username, text))
        config = {"configurable": {"thread_id": thread}}
        before = len(run(agent.aget_state(config)).values.get("messages", []))
        st.chat_message("user").write(text)
        with st.chat_message("assistant"):
            try:
                st.write_stream(iter_sync(stream_reply(agent, text, config)))
                failed = False
            except Exception as e:
                failed = True
                if usage.is_out_of_credit(e):
                    logger.error("Provider out of credit: %s", e)
                    st.warning(UNAVAILABLE)
                else:
                    logger.exception("Reply failed")
                    st.error(REPLY_FAILED)
        # Bill whatever the model produced this turn, including a turn that failed halfway.
        new_messages = run(agent.aget_state(config)).values.get("messages", [])[before:]
        input_tokens, output_tokens = usage.tokens_used(new_messages)
        if input_tokens or output_tokens:
            run(usage.record(pool, username, input_tokens, output_tokens))
        if not failed:
            st.rerun()  # refresh the sidebar (new conversation, message count) from saved state


# The login page is a full-width split screen; the chat keeps Streamlit's centered column.
st.set_page_config(page_title="lc-demo", page_icon="🧾", layout="centered" if "user" in st.session_state else "wide")
if "user" not in st.session_state:
    login_page()
chat_page(st.session_state.user)
