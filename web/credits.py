"""Free credit, and a record of where every cent of it went.

Each owner starts with a small grant. Every model call the workforce makes is
priced and written to a ledger, so the balance is never a number that appeared
from nowhere — it is the grant minus a list of charges the owner can read,
line by line, with the model and the run that caused each one.

Two decisions worth stating:

**The ledger is the truth, the balance is derived.** There is no `balance`
column to drift out of step with the charges. `remaining` is always
`granted - spent`, both summed from rows. A balance that disagrees with its
own history is worse than no balance at all.

**A run is checked before it starts, and charged after it ends.** Charging
first would mean refunding work that failed; checking after would mean the
owner discovers they are out of credit having already spent it. Neither is
honest, so the gate is at the front and the meter at the back.

This lives in the accounts database rather than a shop's, because it is a
fact about the service's relationship with an owner, not about their
business.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from lucida.observability import get_logger

logger = get_logger("web.credits")

# The allowance is counted in tokens, because tokens are the one number in
# this system that is actually measured: the provider returns them with every
# reply. A dollar figure would have to be multiplied by a price this project
# does not reliably know for every model it can reach, and a made-up cost
# shown to an owner is worse than no cost at all.
#
# Presented to the owner as round credits rather than six-figure token counts.
TOKENS_PER_CREDIT = 1_000
FREE_GRANT_CREDITS = 320
FREE_GRANT_TOKENS = FREE_GRANT_CREDITS * TOKENS_PER_CREDIT


def to_credits(tokens: float) -> int:
    """Tokens as whole credits, rounded up so nothing is used for free."""
    import math
    return math.ceil(max(0.0, float(tokens)) / TOKENS_PER_CREDIT)

SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- grant | charge
    amount_usd  REAL NOT NULL,          -- tokens; the column name predates the
                                        -- switch and is kept so old rows read
    model       TEXT,
    session_id  TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_account
    ON credit_ledger(account_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init() -> None:
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001 — same package, one owner
        conn.executescript(SCHEMA)


def grant_if_new(account_id: str, amount: float = FREE_GRANT_TOKENS) -> None:
    """Give an owner their opening credit, once and only once."""
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT 1 FROM credit_ledger WHERE account_id=? AND kind='grant' "
            "LIMIT 1", (account_id,)).fetchone()
        if row:
            return
        conn.execute(
            "INSERT INTO credit_ledger (account_id, kind, amount_usd, note, "
            "created_at) VALUES (?,'grant',?,?,?)",
            (account_id, amount, "Welcome credit", _now()))
    logger.info("granted %s tokens of opening credit to %s",
                f"{int(amount):,}", account_id)


def grant(account_id: str, amount: float, note: str = "Top-up") -> None:
    """Add credit. Used by an operator, never by the owner themselves."""
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO credit_ledger (account_id, kind, amount_usd, note, "
            "created_at) VALUES (?,'grant',?,?,?)",
            (account_id, float(amount), note, _now()))
    logger.info("granted %s tokens to %s (%s)",
                f"{int(amount):,}", account_id, note)


def charge(account_id: str, amount: float, model: str = "",
           session_id: str = "", note: str = "") -> None:
    """Record what a piece of work cost. Sub-cent amounts still count."""
    if amount <= 0:
        return
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO credit_ledger (account_id, kind, amount_usd, model, "
            "session_id, note, created_at) VALUES (?,'charge',?,?,?,?,?)",
            (account_id, float(amount), model, session_id, note, _now()))
    logger.info("charged %s tokens to %s (%s)",
                f"{int(amount):,}", account_id, model or "?")


def balance(account_id: str) -> dict[str, float]:
    """Granted, spent and what is left — all summed from the ledger."""
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001
        try:
            rows = conn.execute(
                "SELECT kind, COALESCE(SUM(amount_usd),0) AS total "
                "FROM credit_ledger WHERE account_id=? GROUP BY kind",
                (account_id,)).fetchall()
        except sqlite3.Error:
            return {"granted": 0.0, "spent": 0.0, "remaining": 0.0}
    totals = {r["kind"]: float(r["total"]) for r in rows}
    granted = totals.get("grant", 0.0)
    spent = totals.get("charge", 0.0)
    remaining = max(0.0, granted - spent)
    return {
        "granted": granted, "spent": spent, "remaining": remaining,
        # What the owner is shown. Credits used is rounded down and the
        # allowance rounded to whole credits, so the bar never reads past
        # full on the last fractional token.
        "credits_total": to_credits(granted),
        "credits_used": min(to_credits(granted), to_credits(spent)),
        "credits_left": to_credits(remaining),
    }


def has_credit(account_id: str) -> bool:
    # A whole run can cost a fraction of a cent, so anything above zero is
    # worth letting through rather than rounding someone out of their last
    # tenth of a cent.
    return balance(account_id)["remaining"] > 0


def history(account_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """The charges and grants, newest first."""
    from . import auth

    with auth._connect() as conn:  # noqa: SLF001
        try:
            rows = conn.execute(
                "SELECT kind, amount_usd, model, note, created_at "
                "FROM credit_ledger WHERE account_id=? "
                "ORDER BY id DESC LIMIT ?", (account_id, limit)).fetchall()
        except sqlite3.Error:
            return []
    return [dict(r) for r in rows]


def out_of_credit_message(account_id: str) -> str:
    b = balance(account_id)
    return (
        f"You have used all {b['credits_total']} of your free credits. "
        f"Every question your team answers uses some, and Home shows what "
        f"each one took. Ask the operator for more to carry on."
    )
