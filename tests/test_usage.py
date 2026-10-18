import asyncio

import anthropic
import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from psycopg_pool import PoolTimeout

from lc_demo import db, usage
from lc_demo.usage import Limit, Status


def _response(status: int) -> httpx2.Response:
    return httpx2.Response(status, request=httpx2.Request("POST", "https://api.example.com"))


def test_cost_uses_per_million_prices():
    # Defaults: $3 input, $15 output per million tokens.
    assert usage.cost_usd(1_000_000, 0) == pytest.approx(3.0)
    assert usage.cost_usd(2_000, 1_000) == pytest.approx(0.021)


def test_tokens_used_sums_every_model_call_in_the_turn():
    def ai(i, o):
        return AIMessage("", usage_metadata={"input_tokens": i, "output_tokens": o, "total_tokens": i + o})

    turn = [HumanMessage("oi"), ai(1000, 50), ToolMessage("ATIVA", tool_call_id="1"), ai(1200, 80), AIMessage("x")]
    assert usage.tokens_used(turn) == (2200, 130)
    assert usage.tokens_used([HumanMessage("oi")]) == (0, 0)


@pytest.mark.parametrize(
    ("messages_today", "month_cost", "expected"),
    [(0, 0.0, None), (19, 19.99, None), (20, 0.0, Limit.DAILY), (0, 20.0, Limit.BUDGET), (25, 25.0, Limit.BUDGET)],
)
def test_blocked_by(messages_today, month_cost, expected):
    assert Status(messages_today, month_cost).blocked_by(daily_limit=20, budget=20.0) is expected


def test_out_of_credit_detection():
    openai_quota = openai.RateLimitError(
        "You exceeded your current quota", response=_response(429), body={"code": "insufficient_quota"}
    )
    openai_throttled = openai.RateLimitError("Rate limit reached", response=_response(429), body={"code": None})
    anthropic_empty = anthropic.BadRequestError(
        "Your credit balance is too low to access the Anthropic API.", response=_response(400), body=None
    )
    anthropic_other = anthropic.BadRequestError("max_tokens is too large", response=_response(400), body=None)

    assert usage.is_out_of_credit(openai_quota)
    assert usage.is_out_of_credit(anthropic_empty)
    assert not usage.is_out_of_credit(openai_throttled)  # plain rate limiting: retry later, not out of money
    assert not usage.is_out_of_credit(anthropic_other)
    assert not usage.is_out_of_credit(ValueError("boom"))

    wrapped = RuntimeError("tool failed")
    wrapped.__cause__ = openai_quota
    assert usage.is_out_of_credit(wrapped)


def test_status_counts_today_per_user_and_month_for_everyone():
    async def run():
        try:
            pool = await db.open_pool()
        except PoolTimeout:
            pytest.skip("Postgres not reachable")
        try:
            await db.setup(pool)
            before = await usage.status(pool, "test-a@example.com")
            await usage.record(pool, "test-a@example.com", 2_000, 1_000)  # $0.021
            await usage.record(pool, "test-a@example.com", 1_000, 0)  # $0.003
            await usage.record(pool, "test-b@example.com", 0, 1_000)  # $0.015
            a = await usage.status(pool, "test-a@example.com")
            b = await usage.status(pool, "test-b@example.com")
            assert (before.messages_today, a.messages_today, b.messages_today) == (0, 2, 1)
            assert a.month_cost_usd == pytest.approx(before.month_cost_usd + 0.039)
            assert a.month_cost_usd == b.month_cost_usd  # the budget is shared by the whole app
        finally:
            async with pool.connection() as conn:
                await conn.execute("DELETE FROM usage_log WHERE username LIKE 'test-%'")
            await pool.close()

    asyncio.run(run())
