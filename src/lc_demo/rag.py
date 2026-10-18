"""Step 5: RAG exposed as a tool, so the agent decides when to search.

Chunks + embeddings live in Postgres/pgvector (`docker-compose up -d`). The table is built
on first use; rebuild it after editing the manual with `uv run lc-demo-ingest`.
"""

from functools import cache

import psycopg
from langchain.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from lc_demo.config import DATA_DIR, DATABASE_URL, EMBEDDING_MODEL

MANUAL_PATH = DATA_DIR / "manual_ecf.txt"
TABLE = "manual_chunks"


@cache
def get_engine() -> PGEngine:
    # langchain-postgres goes through SQLAlchemy, which needs the driver in the URL.
    # pool_pre_ping replaces connections dropped while the database was idle (e.g. Neon scale-to-zero).
    url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    return PGEngine.from_connection_string(url, pool_pre_ping=True)


@cache
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def ingest() -> int:
    """Drop and rebuild the vector table from the manual; returns the chunk count."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_text(MANUAL_PATH.read_text(encoding="utf-8"))
    vectors = get_embeddings().embed_documents(chunks)
    # Size comes from the model's output, so switching LC_EMBEDDING_MODEL just needs a re-ingest.
    get_engine().init_vectorstore_table(TABLE, len(vectors[0]), overwrite_existing=True)
    store = PGVectorStore.create_sync(get_engine(), get_embeddings(), TABLE)
    store.add_embeddings(chunks, vectors)
    get_store.cache_clear()
    return len(chunks)


def _table_exists() -> bool:
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute("SELECT to_regclass(%s)", (TABLE,)).fetchone()[0] is not None


@cache
def get_store() -> PGVectorStore:
    if not _table_exists():
        ingest()
    return PGVectorStore.create_sync(get_engine(), get_embeddings(), TABLE)


@tool
def search_manual(query: str) -> str:
    """Search the ECF manual for passages relevant to the query."""
    docs = get_store().similarity_search(query, k=4)
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def main() -> None:
    print(f"Indexed {ingest()} chunks from {MANUAL_PATH.name} into {TABLE!r}.")
