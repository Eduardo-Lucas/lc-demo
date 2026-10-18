"""pgvector integration tests with fake embeddings; skipped unless Postgres is up."""

import threading

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
        conn.execute(f"DROP TABLE IF EXISTS {TEST_TABLE}, {TEST_TABLE}_new")


def _query(sql_text: str):
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(sql_text).fetchall()


def test_first_search_builds_the_table(fake_rag):
    assert not rag._table_exists()
    result = rag.search_manual.invoke({"query": "who must file the ECF"})
    assert rag._table_exists()
    manual = (rag.MANUAL_DIR / "manual_ecf.txt").read_text(encoding="utf-8")
    for passage in result.split("\n\n---\n\n"):
        source, text = passage.split("\n", 1)
        assert source == "[manual_ecf.txt]" and text in manual


def test_rebuilds_replace_the_table_and_can_repeat(fake_rag):
    counts = [rag.ingest() for _ in range(3)]  # a third run would fail if index names clashed
    assert len(set(counts)) == 1
    assert _query(f"SELECT count(*), max(vector_dims(embedding)) FROM {TEST_TABLE}") == [(counts[0], 16)]
    assert _query(f"SELECT to_regclass('{TEST_TABLE}_new')") == [(None,)]  # side table swapped in, not left over
    indexes = _query(f"SELECT indexname FROM pg_indexes WHERE tablename = '{TEST_TABLE}'")
    assert indexes == [(f"{TEST_TABLE}_pkey",)]


def test_every_txt_in_the_folder_is_indexed_with_its_source(fake_rag, tmp_path):
    (tmp_path / "a_manual.txt").write_text("Regras gerais da ECF. " * 50, encoding="utf-8")
    (tmp_path / "b_errata.txt").write_text("Errata: o prazo mudou.", encoding="utf-8")
    (tmp_path / "notes.md").write_text("not indexed", encoding="utf-8")
    rag.ingest(tmp_path)
    sources = _query(f"SELECT DISTINCT langchain_metadata->>'source' FROM {TEST_TABLE} ORDER BY 1")
    assert sources == [("a_manual.txt",), ("b_errata.txt",)]


def test_non_utf8_file_is_refused_with_a_fix(tmp_path):
    (tmp_path / "manual.txt").write_bytes("Escrituração Contábil".encode("cp1252"))
    with pytest.raises(rag.ManualError, match="(?s)not UTF-8.*iconv -f WINDOWS-1252"):
        rag.load_manual(tmp_path)


def test_empty_folder_is_refused(tmp_path):
    with pytest.raises(rag.ManualError, match="No .txt files"):
        rag.load_manual(tmp_path)


def test_searches_keep_working_during_a_rebuild(fake_rag):
    rag.ingest()
    errors, counts, done = [], [], threading.Event()

    def search_continuously():
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            while not done.is_set():
                try:
                    counts.append(conn.execute(f"SELECT count(*) FROM {TEST_TABLE}").fetchone()[0])
                except psycopg.Error as e:
                    errors.append(e)

    reader = threading.Thread(target=search_continuously)
    reader.start()
    try:
        rag.ingest()
        rag.ingest()
    finally:
        done.set()
        reader.join()
    assert not errors
    assert counts and min(counts) > 0  # never saw a missing or empty table
