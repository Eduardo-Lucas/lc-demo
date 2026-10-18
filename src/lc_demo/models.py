"""Steps 2 and 3: chat model + structured output."""

from functools import cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from lc_demo.config import ANTHROPIC_WORKSPACE_ID, MODEL


@cache
def get_model() -> BaseChatModel:
    """Provider-agnostic chat model; change LC_MODEL to switch providers."""
    kwargs = {}
    if ANTHROPIC_WORKSPACE_ID:
        kwargs["default_headers"] = {"anthropic-workspace-id": ANTHROPIC_WORKSPACE_ID}
    return init_chat_model(MODEL, temperature=0, **kwargs)


class Invoice(BaseModel):
    vendor: str = Field(description="Company that issued the invoice")
    total: float = Field(description="Total amount in BRL")
    due_date: str = Field(description="Due date in ISO format (YYYY-MM-DD)")


def extract_invoice(text: str) -> Invoice:
    return get_model().with_structured_output(Invoice).invoke(text)
