import psycopg
import pytest

from lc_demo.auth import (
    _connect,
    authenticate,
    create_remember_token,
    create_reset_token,
    create_user,
    has_users,
    hash_password,
    is_valid_email,
    reset_password,
    reset_token_is_valid,
    revoke_remember_token,
    save_user,
    user_for_remember_token,
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
    with pytest.raises(ValueError, match="pelo menos 8"):
        create("test-short@example.com", "1234567")


def test_reset_token_flow(users_db):
    save_user("test-reset@example.com", "old-password-1")
    assert create_reset_token("test-nobody@example.com") is None  # unknown account: no token, no email

    token = create_reset_token(" Test-Reset@Example.com ")
    assert token and reset_token_is_valid(token)
    with _connect() as conn:
        stored = [r[0] for r in conn.execute("SELECT token_hash FROM password_resets WHERE username LIKE 'test-%'")]
    assert stored and token not in stored  # only the hash is kept

    assert create_reset_token("test-reset@example.com") is None  # cooldown: no second email right away

    with pytest.raises(ValueError, match="pelo menos 8"):
        reset_password(token, "short")
    assert reset_token_is_valid(token)  # a rejected password doesn't burn the link

    assert reset_password(token, "new-password-1") == "test-reset@example.com"
    assert authenticate("test-reset@example.com", "new-password-1")
    assert not authenticate("test-reset@example.com", "old-password-1")
    assert not reset_token_is_valid(token)
    assert reset_password(token, "another-password") is None  # single use


def test_reset_links_expire_and_using_one_revokes_the_rest(users_db):
    save_user("test-reset2@example.com", "old-password-1")
    first = create_reset_token("test-reset2@example.com")
    with _connect() as conn:  # step past the cooldown
        conn.execute("UPDATE password_resets SET created_at = now() - interval '10 minutes'")
    second = create_reset_token("test-reset2@example.com")
    assert first and second and reset_token_is_valid(first)

    assert reset_password(second, "new-password-1")
    assert not reset_token_is_valid(first)

    with _connect() as conn:
        conn.execute("UPDATE password_resets SET created_at = now() - interval '1 hour'")
    expired = create_reset_token("test-reset2@example.com")
    with _connect() as conn:
        conn.execute("UPDATE password_resets SET expires_at = now() - interval '1 second' WHERE used_at IS NULL")
    assert not reset_token_is_valid(expired)
    assert reset_password(expired, "whatever-123") is None


def test_remember_token_lifecycle(users_db):
    save_user("test-keep@example.com", "password-123")
    token = create_remember_token("Test-Keep@Example.com")
    assert user_for_remember_token(token) == "test-keep@example.com"
    assert user_for_remember_token("not-a-real-token") is None
    with _connect() as conn:
        stored = [r[0] for r in conn.execute("SELECT token_hash FROM remember_tokens WHERE username LIKE 'test-%'")]
    assert stored and token not in stored  # only the hash is kept

    revoke_remember_token(token)  # "Sair"
    assert user_for_remember_token(token) is None

    expired = create_remember_token("test-keep@example.com")
    with _connect() as conn:
        conn.execute("UPDATE remember_tokens SET expires_at = now() - interval '1 second' WHERE username LIKE 'test-%'")
    assert user_for_remember_token(expired) is None


def test_changing_the_password_signs_out_remembered_browsers(users_db):
    save_user("test-keep2@example.com", "password-123")
    laptop, phone = create_remember_token("test-keep2@example.com"), create_remember_token("test-keep2@example.com")
    reset = create_reset_token("test-keep2@example.com")
    assert reset_password(reset, "new-password-1") == "test-keep2@example.com"
    assert user_for_remember_token(laptop) is None and user_for_remember_token(phone) is None

    tablet = create_remember_token("test-keep2@example.com")
    save_user("test-keep2@example.com", "admin-reset-1")  # lc-demo-adduser path
    assert user_for_remember_token(tablet) is None
