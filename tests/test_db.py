"""Integration tests; skipped unless Postgres is up (`docker-compose up -d`)."""

import asyncio

import pytest
from psycopg_pool import PoolTimeout

from lc_demo import db


async def _with_db(test):
    try:
        pool = await db.open_pool()
    except PoolTimeout:
        pytest.skip("Postgres not reachable")
    try:
        await test(pool, await db.setup(pool))
    finally:
        async with pool.connection() as conn:
            await conn.execute("DELETE FROM conversations WHERE username LIKE 'test-%'")
        await pool.close()


def test_conversations_are_per_user():
    async def test(pool, checkpointer):
        a = await db.create_conversation(pool, "test-a", "First question about the ECF deadline for 2025?")
        await db.create_conversation(pool, "test-b", "hi")
        convs = await db.list_conversations(pool, "test-a")
        assert [c["thread_id"] for c in convs] == [a]
        assert convs[0]["title"].endswith("…") and len(convs[0]["title"]) == 40

    asyncio.run(_with_db(test))


def test_delete_is_scoped_to_owner():
    async def test(pool, checkpointer):
        thread = await db.create_conversation(pool, "test-a", "hello")
        await db.delete_conversation(pool, checkpointer, "test-b", thread)
        assert len(await db.list_conversations(pool, "test-a")) == 1
        await db.delete_conversation(pool, checkpointer, "test-a", thread)
        assert await db.list_conversations(pool, "test-a") == []

    asyncio.run(_with_db(test))
