"""Central settings, loaded once from the environment / .env file."""

import os
from pathlib import Path

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
