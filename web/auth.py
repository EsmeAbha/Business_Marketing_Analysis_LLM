"""Accounts: sign-up, sign-in, and the owner's profile.

Kept deliberately small and separate from the shop's own memory. The accounts
database holds only who someone is; everything their business knows lives in
that owner's private shop database, which `SharedMemory.use_shop()` binds per
request.

Passwords are stored as bcrypt hashes and never logged. Sessions are signed
cookies carrying nothing but the account id, so a stolen cookie cannot be
edited into another account's.

Two kinds of owner sign up here, and the difference matters to the agents:

  * `starting`  — no business yet. The workforce begins with research and
    validation: what to sell, at what price, whether it is worth doing.
  * `running`   — already trading. Their existing product, price and costs are
    captured at sign-up so the agents manage from day one instead of
    re-deriving facts the owner already knows.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import bcrypt

from lucida.config import ACCOUNTS_DB
from lucida.observability import get_logger

logger = get_logger("auth")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id             TEXT PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    owner_name     TEXT,
    business_name  TEXT,
    business_stage TEXT NOT NULL DEFAULT 'starting',  -- starting | running
    location       TEXT,
    currency       TEXT DEFAULT 'BDT',
    what_you_sell  TEXT,
    avatar_path    TEXT,
    created_at     TEXT,
    last_login_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email);
"""

STAGES = ("starting", "running")

# Fields the owner may edit from their account page. Anything not listed here
# cannot be written through the profile form — notably id, email and
# password_hash, which have their own guarded paths.
EDITABLE = (
    "owner_name", "business_name", "business_stage",
    "location", "currency", "what_you_sell",
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_lock = threading.RLock()


class AuthError(Exception):
    """Something the owner can see and fix — never a stack trace."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(ACCOUNTS_DB), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


init()


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _validate(email: str, password: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise AuthError("That doesn't look like an email address.")
    if len(password or "") < 8:
        raise AuthError("Use at least 8 characters for your password.")
    return email, password


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def _row_to_account(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    account = dict(row)
    account.pop("password_hash", None)   # never leaves this module
    return account


def create_account(
    email: str,
    password: str,
    owner_name: str = "",
    business_name: str = "",
    business_stage: str = "starting",
    location: str = "",
    what_you_sell: str = "",
) -> dict[str, Any]:
    email, password = _validate(email, password)
    if business_stage not in STAGES:
        business_stage = "starting"

    account_id = uuid.uuid4().hex[:16]
    with _lock, _connect() as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE email=?", (email,)).fetchone():
            raise AuthError("An account with that email already exists. Sign in instead.")
        conn.execute(
            """INSERT INTO accounts
               (id, email, password_hash, owner_name, business_name,
                business_stage, location, what_you_sell, created_at, last_login_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (account_id, email, hash_password(password), owner_name.strip(),
             business_name.strip(), business_stage, location.strip(),
             what_you_sell.strip(), _now(), _now()),
        )
    logger.info("account created stage=%s", business_stage)
    return get_account(account_id)  # type: ignore[return-value]


def authenticate(email: str, password: str) -> dict[str, Any]:
    email = (email or "").strip().lower()
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE email=?", (email,)
        ).fetchone()
        # The same message either way: saying which half was wrong tells an
        # attacker whether an address is registered.
        if row is None or not verify_password(password, row["password_hash"]):
            raise AuthError("Email or password is not right.")
        conn.execute(
            "UPDATE accounts SET last_login_at=? WHERE id=?", (_now(), row["id"])
        )
    logger.info("sign-in ok")
    return _row_to_account(row)  # type: ignore[return-value]


def get_account(account_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row_to_account(
            conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        )


def update_account(account_id: str, **fields: Any) -> dict[str, Any] | None:
    """Update the profile. Only EDITABLE columns are writable."""
    changes = {
        k: (str(v).strip() if isinstance(v, str) else v)
        for k, v in fields.items()
        if k in EDITABLE and v is not None
    }
    if changes.get("business_stage") not in (None, *STAGES):
        changes.pop("business_stage")
    if not changes:
        return get_account(account_id)

    sets = ", ".join(f"{k}=?" for k in changes)
    with _lock, _connect() as conn:
        conn.execute(
            f"UPDATE accounts SET {sets} WHERE id=?",
            (*changes.values(), account_id),
        )
    return get_account(account_id)


def set_avatar(account_id: str, path: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("UPDATE accounts SET avatar_path=? WHERE id=?", (path, account_id))


def change_password(account_id: str, current: str, new: str) -> None:
    if len(new or "") < 8:
        raise AuthError("Use at least 8 characters for your new password.")
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None or not verify_password(current, row["password_hash"]):
            raise AuthError("Your current password is not right.")
        conn.execute(
            "UPDATE accounts SET password_hash=? WHERE id=?",
            (hash_password(new), account_id),
        )
    logger.info("password changed")


def count_accounts() -> int:
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0])


def initials(account: dict[str, Any] | None) -> str:
    """Monogram for the rail, from the owner's name or their email."""
    if not account:
        return "?"
    source = (account.get("owner_name") or account.get("business_name")
              or account.get("email") or "?")
    parts = [p for p in str(source).replace("@", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"
