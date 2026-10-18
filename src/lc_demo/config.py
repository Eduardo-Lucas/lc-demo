"""Central settings, loaded once from the environment / .env file."""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

# Product name shown to users (login page, browser tab, emails); the code/package stays "lc-demo".
APP_NAME = os.getenv("LC_APP_NAME", "Prumo Fiscal")

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

# Password-reset emails (mailer.py). The "forgot password" option only appears when SMTP_HOST is set.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # 587 = STARTTLS, 465 = implicit TLS
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
# Public address of the web UI; reset links point here.
APP_URL = os.getenv("APP_URL", "http://localhost:8501").rstrip("/")
RESET_LINK_MINUTES = int(os.getenv("LC_RESET_LINK_MINUTES", "30"))


def redact(url: str) -> str:
    """URL with the password masked, safe to show in errors or logs."""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.replace(f":{parts.password}@", ":***@", 1)))
