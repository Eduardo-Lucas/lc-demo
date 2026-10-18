"""Steps 2 and 3: chat model + structured output."""

from functools import cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from lc_demo.config import ANTHROPIC_WORKSPACE_ID, EFFORT, MODEL


@cache
def get_model() -> BaseChatModel:
    """Provider-agnostic chat model; change LC_MODEL to switch providers."""
    kwargs = {}
    if ANTHROPIC_WORKSPACE_ID:
        kwargs["default_headers"] = {"anthropic-workspace-id": ANTHROPIC_WORKSPACE_ID}
    # No temperature: current Claude models reject non-default values.
    model = init_chat_model(MODEL, **kwargs)
    # Current Claude models always think and effort sets how much; older ones (and other providers) reject it.
    if EFFORT in (model.profile or {}).get("reasoning_effort_levels", ()):
        model = init_chat_model(MODEL, effort=EFFORT, **kwargs)
    return model


class Invoice(BaseModel):
    vendor: str = Field(description="Company that issued the invoice")
    total: float = Field(description="Total amount in BRL")
    due_date: str = Field(description="Due date in ISO format (YYYY-MM-DD)")


def extract_invoice(text: str) -> Invoice:
    # Native JSON-schema output: current Claude models reject the forced tool call LangChain uses by default.
    return get_model().with_structured_output(Invoice, method="json_schema").invoke(text)
