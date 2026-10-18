"""Central settings, loaded once from the environment / .env file."""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("LC_MODEL", "anthropic:claude-sonnet-4-5")
EMBEDDING_MODEL = os.getenv("LC_EMBEDDING_MODEL", "text-embedding-3-small")
# Only needed for org-level Anthropic keys that aren't scoped to a workspace.
ANTHROPIC_WORKSPACE_ID = os.getenv("ANTHROPIC_WORKSPACE_ID")

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
MCP_SERVERS_DIR = ROOT_DIR / "mcp_servers"
# Matches docker-compose.yml; used for RAG (pgvector) and the web UI's users, memory and history.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lc_demo:lc_demo@localhost:5433/lc_demo")

# Usage limits for the web UI (see usage.py); override in .env or Streamlit Secrets.
DAILY_MESSAGE_LIMIT = int(os.getenv("LC_DAILY_MESSAGE_LIMIT", "20"))
MONTHLY_BUDGET_USD = float(os.getenv("LC_MONTHLY_BUDGET_USD", "20"))
# USD per million tokens for LC_MODEL; defaults are claude-sonnet-4-5's list prices.
PRICE_INPUT_PER_MTOK = float(os.getenv("LC_PRICE_INPUT_PER_MTOK", "3"))
PRICE_OUTPUT_PER_MTOK = float(os.getenv("LC_PRICE_OUTPUT_PER_MTOK", "15"))
# Where "today" and "this month" start for the limits.
TIMEZONE = os.getenv("LC_TIMEZONE", "America/Sao_Paulo")


def redact(url: str) -> str:
    """URL with the password masked, safe to show in errors or logs."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.replace(f":{parts.password}@", ":***@", 1)))
