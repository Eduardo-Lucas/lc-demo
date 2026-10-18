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

from lc_demo.config import DATABASE_URL, redact

# OWASP-recommended scrypt cost; ~50 ms per check, which also slows brute force.
_N, _R, _P = 2**14, 8, 1

# The account id is the user's email, stored lowercased in `username` (also the key in `conversations`).
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)"""


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
        conn.execute(SCHEMA)


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
    with _connect() as conn:
        conn.execute(
            """INSERT INTO users (username, password_hash) VALUES (%s, %s)
               ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash""",
            (normalize_email(email), hash_password(password)),
        )


def authenticate(email: str, password: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = %s", (normalize_email(email),)
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return False
    return verify_password(password, row[0])


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
