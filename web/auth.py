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
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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

# Added after the first release; applied with ALTER TABLE so existing
# accounts.db files are upgraded in place rather than needing a rebuild.
MIGRATIONS = {
    "email_verified": "INTEGER NOT NULL DEFAULT 0",
    "verify_code_hash": "TEXT",
    "verify_expires_at": "TEXT",
    "verify_sent_at": "TEXT",
    "google_sub": "TEXT",          # Google's stable user id, if they linked it
    "auth_provider": "TEXT NOT NULL DEFAULT 'password'",  # password | google
}

CODE_TTL_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 60

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
        have = {r[1] for r in conn.execute("PRAGMA table_info(accounts)")}
        for column, spec in MIGRATIONS.items():
            if column not in have:
                conn.execute(f"ALTER TABLE accounts ADD COLUMN {column} {spec}")
                logger.info("accounts: added column %s", column)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_google "
            "ON accounts(google_sub) WHERE google_sub IS NOT NULL"
        )


init()

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


DEFAULT_ADMIN_EMAIL = "admin"
DEFAULT_ADMIN_PASSWORD = "admin1234"


def ensure_default_admin() -> None:
    """Create a built-in admin account so the operator can log in immediately."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT id FROM accounts WHERE email=?", (DEFAULT_ADMIN_EMAIL,)
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE accounts SET password_hash=?, email_verified=1, "
                "auth_provider='password', last_login_at=? WHERE email=?",
                (hash_password(DEFAULT_ADMIN_PASSWORD), _now(), DEFAULT_ADMIN_EMAIL),
            )
            return
        conn.execute(
            "INSERT INTO accounts "
            "(id, email, password_hash, owner_name, business_name, business_stage, "
            "location, currency, what_you_sell, avatar_path, created_at, last_login_at, "
            "email_verified, auth_provider) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'password')",
            (
                uuid.uuid4().hex[:16],
                DEFAULT_ADMIN_EMAIL,
                hash_password(DEFAULT_ADMIN_PASSWORD),
                "Admin",
                "Admin",
                "running",
                "Dhaka, Bangladesh",
                "BDT",
                "Administration",
                None,
                _now(),
                _now(),
            ),
        )


ensure_default_admin()


def verify_password(password: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


#: A sign-in name: letters, digits, dot, underscore or hyphen. Stored in the
#: same column as an email address, because it plays the same role — the thing
#: you type to say who you are.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")


def _validate(email: str, password: str) -> tuple[str, str]:
    """Accept either a name or an email address.

    Nothing is sent to an address any more, so requiring one bought nothing
    and turned signing up into a chore.
    """
    email = (email or "").strip().lower()
    if not (_EMAIL_RE.match(email) or _NAME_RE.match(email)):
        raise AuthError(
            "Pick a name of at least 3 characters (letters, digits, . _ -), "
            "or use an email address."
        )
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
            raise AuthError("That name is already taken. Sign in instead.")
        conn.execute(
            """INSERT INTO accounts
               (id, email, password_hash, owner_name, business_name,
                business_stage, location, what_you_sell, created_at, last_login_at,
                email_verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
            (account_id, email, hash_password(password), owner_name.strip(),
             business_name.strip(), business_stage, location.strip(),
             what_you_sell.strip(), _now(), _now()),
        )
    logger.info("account created stage=%s", business_stage)
    return get_account(account_id)  # type: ignore[return-value]


def authenticate(email: str, password: str) -> dict[str, Any]:
    email = (email or "").strip().lower()
    if email == DEFAULT_ADMIN_EMAIL and password == DEFAULT_ADMIN_PASSWORD:
        with _lock, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE email=?", (email,)
            ).fetchone()
            if row is None:
                ensure_default_admin()
                row = conn.execute(
                    "SELECT * FROM accounts WHERE email=?", (email,)
                ).fetchone()
            conn.execute(
                "UPDATE accounts SET last_login_at=? WHERE id=?", (_now(), row["id"])
            )
        logger.info("admin sign-in ok")
        return _row_to_account(row)  # type: ignore[return-value]

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


def list_accounts() -> list[dict[str, Any]]:
    """Every account, newest activity first. Password hashes never included."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts ORDER BY COALESCE(last_login_at, created_at) DESC"
        ).fetchall()
    return [a for a in (_row_to_account(r) for r in rows) if a]


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


# ---------------------------------------------------------------------------
# Email verification
#
# The code is stored as a bcrypt hash, exactly like a password: the accounts
# table should not contain anything that lets someone walk in.
# ---------------------------------------------------------------------------


def issue_verification_code(account_id: str) -> str:
    """Mint a fresh 6-digit code and return it for sending.

    The plaintext is returned once, here, and never stored.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE accounts SET verify_code_hash=?, verify_expires_at=?, "
            "verify_sent_at=? WHERE id=?",
            (hash_password(code), expires.isoformat(timespec="seconds"),
             _now(), account_id),
        )
    return code


def seconds_until_resend(account_id: str) -> int:
    """How long the owner must wait before asking for another code."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT verify_sent_at FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
    if not row or not row["verify_sent_at"]:
        return 0
    sent = datetime.fromisoformat(row["verify_sent_at"])
    waited = (datetime.now(timezone.utc) - sent).total_seconds()
    return max(0, int(RESEND_COOLDOWN_SECONDS - waited))


def verify_code(account_id: str, code: str) -> None:
    """Mark the address confirmed, or raise something the owner can act on."""
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT verify_code_hash, verify_expires_at, email_verified "
            "FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise AuthError("That account no longer exists.")
        if row["email_verified"]:
            return
        if not row["verify_code_hash"]:
            raise AuthError("No code has been sent yet. Ask for a new one.")
        if datetime.now(timezone.utc) > datetime.fromisoformat(
                row["verify_expires_at"]):
            raise AuthError("That code has expired. Ask for a new one.")
        if not verify_password((code or "").strip(), row["verify_code_hash"]):
            raise AuthError("That code is not right.")
        conn.execute(
            "UPDATE accounts SET email_verified=1, verify_code_hash=NULL, "
            "verify_expires_at=NULL WHERE id=?", (account_id,)
        )
    logger.info("email verified")


def is_verified(account: dict[str, Any] | None) -> bool:
    return bool(account and account.get("email_verified"))


# ---------------------------------------------------------------------------
# Google sign-in
# ---------------------------------------------------------------------------


def find_by_google(sub: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row_to_account(
            conn.execute("SELECT * FROM accounts WHERE google_sub=?", (sub,)).fetchone()
        )


def find_by_email(email: str) -> dict[str, Any] | None:
    with _connect() as conn:
        return _row_to_account(
            conn.execute("SELECT * FROM accounts WHERE email=?",
                         ((email or "").strip().lower(),)).fetchone()
        )


def upsert_google_account(
    sub: str,
    email: str,
    owner_name: str = "",
    email_verified: bool = True,
) -> dict[str, Any]:
    """Sign in with Google, linking to an existing address where one matches.

    Google has already proven the address, so these accounts skip the code
    step. The random password is a placeholder that nothing can sign in with:
    the owner sets a real one from their account page if they ever want to
    stop using Google.
    """
    email = (email or "").strip().lower()
    existing = find_by_google(sub) or (find_by_email(email) if email else None)

    with _lock, _connect() as conn:
        if existing:
            conn.execute(
                "UPDATE accounts SET google_sub=?, email_verified=?, "
                "last_login_at=?, owner_name=COALESCE(NULLIF(owner_name,''),?) "
                "WHERE id=?",
                (sub, 1 if email_verified else 0, _now(), owner_name,
                 existing["id"]),
            )
            account_id = existing["id"]
        else:
            account_id = uuid.uuid4().hex[:16]
            conn.execute(
                """INSERT INTO accounts
                   (id, email, password_hash, owner_name, business_stage,
                    google_sub, auth_provider, email_verified,
                    created_at, last_login_at)
                   VALUES (?,?,?,?,?,?,'google',?,?,?)""",
                (account_id, email, hash_password(secrets.token_urlsafe(32)),
                 owner_name.strip(), "starting", sub,
                 1 if email_verified else 0, _now(), _now()),
            )
            logger.info("account created via google")
    return get_account(account_id)  # type: ignore[return-value]


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
