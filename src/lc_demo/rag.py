"""Step 5: RAG exposed as a tool, so the agent decides when to search.

Every UTF-8 `.txt` file in data/manual/ is chunked, embedded and stored in Postgres/pgvector
(`docker-compose up -d`). The table is built on first use; after adding or replacing files,
rebuild it with `uv run lc-demo-ingest`. Rebuilds don't interrupt searches (see `ingest`).
"""

from functools import cache
from pathlib import Path

import psycopg
from langchain.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg import sql

from lc_demo.config import DATA_DIR, DATABASE_URL, EMBEDDING_MODEL

MANUAL_DIR = DATA_DIR / "manual"
TABLE = "manual_chunks"


class ManualError(Exception):
    """The manual folder can't be indexed as it is (missing, empty, or not UTF-8)."""


@cache
def get_engine() -> PGEngine:
    # langchain-postgres goes through SQLAlchemy, which needs the driver in the URL.
    # pool_pre_ping replaces connections dropped while the database was idle (e.g. Neon scale-to-zero).
    url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    return PGEngine.from_connection_string(url, pool_pre_ping=True)


@cache
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def load_manual(folder: Path | None = None) -> list[tuple[str, str]]:
    """(file name, text) for every .txt in the folder, sorted by name."""
    folder = folder or MANUAL_DIR
    files = sorted(folder.glob("*.txt"))
    if not files:
        raise ManualError(f"No .txt files in {folder}.")
    manual = []
    for path in files:
        try:
            manual.append((path.name, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError as e:
            raise ManualError(
                f"{path.name} is not UTF-8 (byte {e.start}). Government exports are often Windows-1252; convert with:\n"
                f"  iconv -f WINDOWS-1252 -t UTF-8 '{path}' -o '{path}.utf8' && mv '{path}.utf8' '{path}'"
            ) from e
    return manual


def _swap_in(new_table: str) -> None:
    """Replace TABLE with new_table in one transaction, renaming its indexes to match."""
    with psycopg.connect(DATABASE_URL) as conn, conn.transaction():
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(TABLE)))
        conn.execute(sql.SQL("ALTER TABLE {} RENAME TO {}").format(sql.Identifier(new_table), sql.Identifier(TABLE)))
        # Indexes keep their old names (e.g. manual_chunks_new_pkey), which would clash with the next rebuild.
        indexes = conn.execute(
            "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE i.indrelid = %s::regclass",
            (TABLE,),
        ).fetchall()
        for (index,) in indexes:
            if index.startswith(new_table):
                renamed = TABLE + index.removeprefix(new_table)
                rename = sql.SQL("ALTER INDEX {} RENAME TO {}")
                conn.execute(rename.format(sql.Identifier(index), sql.Identifier(renamed)))


def ingest(folder: Path | None = None) -> int:
    """Rebuild the vector table from the manual folder; returns the chunk count.

    The new index is built in a side table while the current one keeps serving searches, then
    swapped in atomically, so a search during a rebuild sees either the old or the new manual.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    texts, metadatas = [], []
    for name, text in load_manual(folder):
        for chunk in splitter.split_text(text):
            texts.append(chunk)
            metadatas.append({"source": name})
    vectors = get_embeddings().embed_documents(texts)

    new_table = f"{TABLE}_new"
    # Size comes from the model's output, so switching LC_EMBEDDING_MODEL just needs a re-ingest.
    get_engine().init_vectorstore_table(new_table, len(vectors[0]), overwrite_existing=True)
    PGVectorStore.create_sync(get_engine(), get_embeddings(), new_table).add_embeddings(texts, vectors, metadatas)
    _swap_in(new_table)
    get_store.cache_clear()
    return len(texts)


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
    return "\n\n---\n\n".join(f"[{doc.metadata.get('source', '?')}]\n{doc.page_content}" for doc in docs)


def main() -> None:
    try:
        files = [name for name, _ in load_manual()]
        count = ingest()
    except ManualError as e:
        raise SystemExit(f"Can't index the manual: {e}") from e
    print(f"Indexed {count} chunks from {len(files)} file(s) in {MANUAL_DIR} into {TABLE!r}: {', '.join(files)}")
