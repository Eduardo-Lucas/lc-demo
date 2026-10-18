"""Usage limits: a daily message allowance per user and a monthly spend budget for the whole app.

Providers don't expose the remaining prepaid balance, so the app meters its own spend from the
token counts each reply reports and stops before the budget is exceeded.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

import anthropic
import openai
from langchain_core.messages import AIMessage, BaseMessage
from psycopg_pool import AsyncConnectionPool

from lc_demo.config import (
    DAILY_MESSAGE_LIMIT,
    MONTHLY_BUDGET_USD,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
    TIMEZONE,
)


class Limit(Enum):
    DAILY = "daily"  # this user used today's allowance
    BUDGET = "budget"  # the app spent this month's budget


@dataclass(frozen=True)
class Status:
    messages_today: int
    month_cost_usd: float

    def blocked_by(self, daily_limit: int = DAILY_MESSAGE_LIMIT, budget: float = MONTHLY_BUDGET_USD) -> Limit | None:
        # Budget first: when the app is out of money, the per-user count is beside the point.
        if self.month_cost_usd >= budget:
            return Limit.BUDGET
        if self.messages_today >= daily_limit:
            return Limit.DAILY
        return None


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK) / 1_000_000


def tokens_used(messages: Iterable[BaseMessage]) -> tuple[int, int]:
    """(input, output) tokens across the model calls that produced these messages."""
    usage = [m.usage_metadata for m in messages if isinstance(m, AIMessage) and m.usage_metadata]
    return sum(u["input_tokens"] for u in usage), sum(u["output_tokens"] for u in usage)


async def record(pool: AsyncConnectionPool, username: str, input_tokens: int, output_tokens: int) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO usage_log (username, input_tokens, output_tokens, cost_usd) VALUES (%s, %s, %s, %s)",
            (username, input_tokens, output_tokens, cost_usd(input_tokens, output_tokens)),
        )


async def status(pool: AsyncConnectionPool, username: str) -> Status:
    # "Today" and "this month" start at local midnight in TIMEZONE, where the users are.
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT
                 (SELECT count(*) FROM usage_log WHERE username = %(user)s
                    AND created_at >= date_trunc('day', now() AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s),
                 (SELECT coalesce(sum(cost_usd), 0) FROM usage_log
                    WHERE created_at >= date_trunc('month', now() AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s)""",
            {"user": username, "tz": TIMEZONE},
        )
        row = await cur.fetchone()
    messages_today, month_cost = row.values()
    return Status(messages_today=messages_today, month_cost_usd=float(month_cost))


def is_out_of_credit(exc: BaseException) -> bool:
    """True when a provider refused a call because the account has no credit left."""
    while exc is not None:
        if isinstance(exc, openai.RateLimitError) and exc.code == "insufficient_quota":
            return True
        # Anthropic reports an empty prepaid balance as a 400 with this wording.
        if isinstance(exc, anthropic.BadRequestError) and "credit balance" in str(exc).lower():
            return True
        exc = exc.__cause__
    return False
