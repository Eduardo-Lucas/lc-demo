"""pgvector integration test with fake embeddings; skipped unless Postgres is up."""

import psycopg
import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from lc_demo import rag
from lc_demo.config import DATABASE_URL

TEST_TABLE = "test_manual_chunks"


@pytest.fixture
def fake_rag(monkeypatch):
    try:
        psycopg.connect(DATABASE_URL, connect_timeout=2).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    monkeypatch.setattr(rag, "TABLE", TEST_TABLE)
    monkeypatch.setattr(rag, "get_embeddings", lambda: DeterministicFakeEmbedding(size=16))
    rag.get_store.cache_clear()
    yield
    rag.get_store.cache_clear()
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {TEST_TABLE}")


def test_first_search_builds_the_table(fake_rag):
    assert not rag._table_exists()
    result = rag.search_manual.invoke({"query": "who must file the ECF"})
    assert rag._table_exists()
    passages = result.split("\n\n---\n\n")
    manual = rag.MANUAL_PATH.read_text(encoding="utf-8")
    assert len(passages) == min(4, rag.ingest())
    assert all(p in manual for p in passages)


def test_reingest_replaces_rows(fake_rag):
    count = rag.ingest()
    assert rag.ingest() == count
    with psycopg.connect(DATABASE_URL) as conn:
        rows, dims = conn.execute(f"SELECT count(*), max(vector_dims(embedding)) FROM {TEST_TABLE}").fetchone()
    assert (rows, dims) == (count, 16)
