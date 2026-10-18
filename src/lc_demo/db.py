"""Postgres persistence: LangGraph checkpoints (memory) + a per-user conversations index."""

from uuid import uuid4

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from lc_demo.config import DATABASE_URL

SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS conversations (
    thread_id  TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    title      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
    "CREATE INDEX IF NOT EXISTS conversations_user_idx ON conversations (username, created_at DESC)",
)


async def open_pool(url: str = DATABASE_URL) -> AsyncConnectionPool:
    # Connection settings AsyncPostgresSaver requires (autocommit, dict rows), per the LangGraph docs.
    pool = AsyncConnectionPool(
        url,
        open=False,
        # Neon scales to zero and drops idle connections; check before handing one out.
        check=AsyncConnectionPool.check_connection,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )
    await pool.open(wait=True, timeout=10)
    return pool


async def setup(pool: AsyncConnectionPool) -> AsyncPostgresSaver:
    """Create checkpoint + conversations tables (idempotent) and return the checkpointer."""
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    async with pool.connection() as conn:
        # One statement per execute: prepared statements can't hold several.
        for statement in SCHEMA:
            await conn.execute(statement)
    return checkpointer


async def list_conversations(pool: AsyncConnectionPool, username: str) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT thread_id, title FROM conversations WHERE username = %s ORDER BY created_at DESC",
            (username,),
        )
        return await cur.fetchall()


async def create_conversation(pool: AsyncConnectionPool, username: str, first_message: str) -> str:
    """Register a new thread, titled after its first message."""
    thread_id = uuid4().hex
    title = " ".join(first_message.split())
    title = title if len(title) <= 40 else title[:39] + "…"
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO conversations (thread_id, username, title) VALUES (%s, %s, %s)",
            (thread_id, username, title),
        )
    return thread_id


async def delete_conversation(
    pool: AsyncConnectionPool, checkpointer: AsyncPostgresSaver, username: str, thread_id: str
) -> None:
    """Remove the index row and its checkpoints; the username check stops cross-user deletes."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM conversations WHERE thread_id = %s AND username = %s",
            (thread_id, username),
        )
        if cur.rowcount:
            await checkpointer.adelete_thread(thread_id)
