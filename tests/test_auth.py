import psycopg
import pytest

from lc_demo.auth import (
    _connect,
    authenticate,
    create_user,
    has_users,
    hash_password,
    is_valid_email,
    save_user,
    verify_password,
)


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
    save_user("test-edu@example.com", "password-1")
    save_user("test-ana@example.com", "password-2")
    assert has_users()
    assert authenticate("test-edu@example.com", "password-1")
    assert not authenticate("test-edu@example.com", "password-2")
    assert not authenticate("test-nobody@example.com", "password-1")
    save_user("test-edu@example.com", "password-new")  # saving again resets the password
    assert authenticate("test-edu@example.com", "password-new")
    assert not authenticate("test-edu@example.com", "password-1")


def test_email_is_case_and_space_insensitive(users_db):
    save_user("  Test-Mixed@Example.COM ", "password-x")
    assert authenticate("test-mixed@example.com", "password-x")
    assert authenticate("TEST-MIXED@EXAMPLE.COM", "password-x")
    with _connect() as conn:
        rows = conn.execute("SELECT username FROM users WHERE username ILIKE 'test-mixed%'").fetchall()
    assert rows == [("test-mixed@example.com",)]


def test_invalid_email_is_rejected():
    with pytest.raises(ValueError):
        save_user("not-an-email", "pw")


@pytest.mark.parametrize("email", ["a@b.co", "Eduardo.Lucas+demo@Gmail.com", " x@y.org "])
def test_valid_emails(email):
    assert is_valid_email(email)


@pytest.mark.parametrize("email", ["", "eduardo", "a@b", "@b.co", "a b@c.co", "a@b@c.co"])
def test_invalid_emails(email):
    assert not is_valid_email(email)


def test_password_is_stored_hashed(users_db):
    save_user("test-edu@example.com", "plain-text-pw")
    with _connect() as conn:
        (stored,) = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'test-edu@example.com'"
        ).fetchone()
    assert stored.startswith("scrypt$") and "plain-text-pw" not in stored


def test_signup_creates_account(users_db):
    assert create_user("Test-New@Example.com", "long-enough-pw")
    assert authenticate("test-new@example.com", "long-enough-pw")


def test_signup_never_overwrites_an_existing_account(users_db):
    save_user("test-owner@example.com", "owners-password")
    assert not create_user("TEST-OWNER@example.com", "attackers-password")
    assert authenticate("test-owner@example.com", "owners-password")
    assert not authenticate("test-owner@example.com", "attackers-password")


@pytest.mark.parametrize("create", [create_user, save_user])
def test_short_passwords_are_rejected(create):
    with pytest.raises(ValueError, match="at least 8"):
        create("test-short@example.com", "1234567")
