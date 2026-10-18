"""Email/password auth backed by a Postgres `users` table of scrypt hashes.

Add a user: `uv run lc-demo-adduser <email>` (prompts for the password).
"""

import argparse
import getpass
import hashlib
import hmac
import re
import secrets
from functools import cache

import psycopg

from lc_demo.config import DATABASE_URL, REMEMBER_DAYS, RESET_LINK_MINUTES, redact

# OWASP-recommended scrypt cost; ~50 ms per check, which also slows brute force.
_N, _R, _P = 2**14, 8, 1

# The account id is the user's email, stored lowercased in `username` (also the key in `conversations`).
SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)""",
    # Password-reset links. Only a SHA-256 of each token is kept, so a database leak yields no usable links.
    """
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    username   TEXT NOT NULL REFERENCES users (username) ON DELETE CASCADE ON UPDATE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ
)""",
    # "Manter conectado": one row per remembered browser; the cookie holds the token, we keep its hash.
    """
CREATE TABLE IF NOT EXISTS remember_tokens (
    token_hash   TEXT PRIMARY KEY,
    username     TEXT NOT NULL REFERENCES users (username) ON DELETE CASCADE ON UPDATE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ
)""",
)

# At most one reset email per account in this window, so the form can't be used to flood an inbox.
RESET_COOLDOWN_SECONDS = 120


# Shape check only (something@domain.tld); proving ownership would need a confirmation email.
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    """Canonical account id, so `Ana@Example.com ` and `ana@example.com` are one account."""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return _EMAIL.fullmatch(normalize_email(email)) is not None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P)
    return hmac.compare_digest(candidate.hex(), digest)


# Checked against when the username doesn't exist, so response time doesn't reveal which names do.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


@cache
def _ensure_schema() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        for statement in SCHEMA:
            conn.execute(statement)


def _connect() -> psycopg.Connection:
    _ensure_schema()
    return psycopg.connect(DATABASE_URL, autocommit=True)


def has_users() -> bool:
    with _connect() as conn:
        return conn.execute("SELECT EXISTS (SELECT 1 FROM users)").fetchone()[0]


def check_new_credentials(email: str, password: str) -> None:
    """Raise ValueError with a message for the user (in Portuguese, like the UI) if these can't be used."""
    if not is_valid_email(email):
        raise ValueError("Informe um endereço de e-mail válido.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")


def create_user(email: str, password: str) -> bool:
    """Self-service sign-up. Never touches an existing account; returns False if the email is taken."""
    check_new_credentials(email, password)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
            (normalize_email(email), hash_password(password)),
        )
        return cur.rowcount == 1


def save_user(email: str, password: str) -> None:
    """Admin path: create the user, or reset their password if they already exist."""
    check_new_credentials(email, password)
    with _connect() as conn, conn.transaction():
        conn.execute(
            """INSERT INTO users (username, password_hash) VALUES (%s, %s)
               ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash""",
            (normalize_email(email), hash_password(password)),
        )
        # A new password signs out every remembered browser.
        conn.execute("DELETE FROM remember_tokens WHERE username = %s", (normalize_email(email),))


def authenticate(email: str, password: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = %s", (normalize_email(email),)
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, row[0])


def _token_hash(token: str) -> str:
    # Tokens are 256-bit random, so a plain fast hash is enough (no salt/scrypt needed).
    return hashlib.sha256(token.encode()).hexdigest()


def create_reset_token(email: str) -> str | None:
    """New single-use reset token for this account, or None if there's no such account or one was just sent."""
    email = normalize_email(email)
    token = secrets.token_urlsafe(32)
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO password_resets (token_hash, username, expires_at)
               SELECT %(hash)s, u.username, now() + make_interval(mins => %(minutes)s)
               FROM users u
               WHERE u.username = %(email)s
                 AND NOT EXISTS (SELECT 1 FROM password_resets r WHERE r.username = u.username
                                 AND r.created_at > now() - make_interval(secs => %(cooldown)s))""",
            {
                "hash": _token_hash(token),
                "email": email,
                "minutes": RESET_LINK_MINUTES,
                "cooldown": RESET_COOLDOWN_SECONDS,
            },
        )
        return token if cur.rowcount == 1 else None


def reset_token_is_valid(token: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM password_resets WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()",
            (_token_hash(token),),
        ).fetchone()
    return row is not None


def reset_password(token: str, new_password: str) -> str | None:
    """Set a new password from a reset link; returns the account's email, or None if the link is invalid/expired.

    Raises ValueError (message for the user) if the new password isn't acceptable.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    with _connect() as conn, conn.transaction():
        row = conn.execute(
            """UPDATE password_resets SET used_at = now()
               WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
               RETURNING username""",
            (_token_hash(token),),
        ).fetchone()
        if row is None:
            return None
        (email,) = row
        conn.execute("UPDATE users SET password_hash = %s WHERE username = %s", (hash_password(new_password), email))
        # Any other outstanding links for this account stop working too.
        conn.execute("UPDATE password_resets SET used_at = now() WHERE username = %s AND used_at IS NULL", (email,))
        # A new password signs out every remembered browser (e.g. a lost laptop).
        conn.execute("DELETE FROM remember_tokens WHERE username = %s", (email,))
        return email


def create_remember_token(email: str) -> str:
    """Token for the "Manter conectado" cookie; valid for REMEMBER_DAYS."""
    token = secrets.token_urlsafe(32)
    with _connect() as conn:
        conn.execute(
            """INSERT INTO remember_tokens (token_hash, username, expires_at)
               VALUES (%s, %s, now() + make_interval(days => %s))""",
            (_token_hash(token), normalize_email(email), REMEMBER_DAYS),
        )
    return token


def user_for_remember_token(token: str) -> str | None:
    """Email of the account this cookie token signs in, or None if it's unknown, revoked or expired."""
    with _connect() as conn:
        row = conn.execute(
            """UPDATE remember_tokens SET last_used_at = now()
               WHERE token_hash = %s AND expires_at > now() RETURNING username""",
            (_token_hash(token),),
        ).fetchone()
    return row[0] if row else None


def revoke_remember_token(token: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM remember_tokens WHERE token_hash = %s", (_token_hash(token),))


def main() -> None:
    parser = argparse.ArgumentParser(prog="lc-demo-adduser", description="Add a web UI user or reset their password.")
    parser.add_argument("email")
    email = normalize_email(parser.parse_args().email)
    if not is_valid_email(email):
        parser.error(f"{email!r} is not a valid email address")
    try:
        password = getpass.getpass("Password: ")
        repeated = getpass.getpass("Repeat: ")
    except EOFError:
        parser.exit(1, "\nNo terminal to read the password from; run this in an interactive shell.\n")
    if password != repeated:
        parser.error("passwords do not match")
    try:
        save_user(email, password)
    except ValueError as e:
        parser.error(str(e))
    except psycopg.OperationalError:
        parser.exit(1, f"Can't reach Postgres at {redact(DATABASE_URL)}. Is it running and is DATABASE_URL right?\n")
    print(f"Saved {email!r}.")
