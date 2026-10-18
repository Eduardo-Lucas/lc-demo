import psycopg
import pytest

from lc_demo.auth import _connect, authenticate, has_users, hash_password, save_user, verify_password


def test_hash_roundtrip():
    stored = hash_password("s3cret")
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_is_rejected():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "md5$00$00")


@pytest.fixture
def users_db():
    """Real `users` table; test rows are prefixed with `test-` and removed afterwards."""
    try:
        conn = _connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    yield
    with conn:
        conn.execute("DELETE FROM users WHERE username LIKE 'test-%'")


def test_users_table(users_db):
    save_user("test-edu", "pw1")
    save_user("test-ana", "pw2")
    assert has_users()
    assert authenticate("test-edu", "pw1")
    assert not authenticate("test-edu", "pw2")
    assert not authenticate("test-nobody", "pw1")
    save_user("test-edu", "new")  # saving again resets the password
    assert authenticate("test-edu", "new")
    assert not authenticate("test-edu", "pw1")


def test_password_is_stored_hashed(users_db):
    save_user("test-edu", "plain-text-pw")
    with _connect() as conn:
        (stored,) = conn.execute("SELECT password_hash FROM users WHERE username = 'test-edu'").fetchone()
    assert stored.startswith("scrypt$") and "plain-text-pw" not in stored
