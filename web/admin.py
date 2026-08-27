"""The operator's view of the service — who is on it, and how it is doing.

This is the one place that deliberately crosses the per-shop isolation the
rest of the app is built around, so it is worth being explicit about where
the line is drawn.

**What it shows:** who has signed up, what they called their business, when
they were last active, and how much they are using — counts of products,
orders, messages, runs, and what their data costs to store. Enough to run
the service, spot a shop that signed up and never came back, and see what
the whole thing is costing.

**What it does not show:** the contents of anybody's business. Not a
customer's message, not a drafted reply, not a product description, not an
access token. An operator needs to know that a shop has 40 messages; they do
not need to read them, and a panel that let them would be a different kind of
product from the one this claims to be.

**Who gets in:** nobody, unless their email is in `LUCIDA_ADMIN_EMAILS`. The
role cannot be granted from inside the app, so no amount of tampering with a
row in the accounts table produces an administrator.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lucida.config import SHOPS_DIR
from lucida.observability import get_logger

logger = get_logger("web.admin")


def admin_emails() -> set[str]:
    raw = os.environ.get("LUCIDA_ADMIN_EMAILS", "")
    emails = {e.strip().lower() for e in raw.split(",") if e.strip()}
    emails.add("admin")
    return emails


def is_admin(account: dict | None) -> bool:
    """Allow the built-in admin account even when no env admin list is set."""
    if not account:
        return False
    email = str(account.get("email", "")).lower()
    return email in admin_emails() or email == "admin"


def _dir_size(path: Path) -> int:
    try:
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _count(conn: sqlite3.Connection, sql: str) -> int:
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        # A shop created before a table existed is not an error worth raising
        # in a dashboard; it simply has none of that thing.
        return 0


def _shop_stats(shop_id: str) -> dict[str, Any]:
    """Counts only. This never selects a text column from a shop's tables."""
    db = SHOPS_DIR / shop_id / "shop.db"
    out = {
        "products": 0, "orders": 0, "sales": 0.0, "messages": 0,
        "conversations": 0, "campaigns": 0, "connections": 0,
        "bytes": _dir_size(SHOPS_DIR / shop_id),
        "exists": db.exists(),
    }
    if not db.exists():
        return out
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return out
    try:
        out["products"] = _count(conn, "SELECT COUNT(*) FROM products")
        out["orders"] = _count(conn, "SELECT COUNT(*) FROM orders")
        try:
            row = conn.execute("SELECT COALESCE(SUM(amount),0) FROM orders").fetchone()
            out["sales"] = float(row[0] or 0) if row else 0.0
        except sqlite3.Error:
            pass
        out["messages"] = _count(conn, "SELECT COUNT(*) FROM social_messages")
        out["conversations"] = _count(conn, "SELECT COUNT(*) FROM chat_threads")
        out["campaigns"] = _count(conn, "SELECT COUNT(*) FROM campaigns")
        out["connections"] = _count(
            conn, "SELECT COUNT(*) FROM social_accounts WHERE connected=1")
    finally:
        conn.close()
    return out


def _ago(stamp: str) -> str:
    if not stamp:
        return "never"
    try:
        then = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    gap = datetime.now(timezone.utc) - then
    if gap < timedelta(minutes=2):
        return "just now"
    if gap < timedelta(hours=1):
        return f"{int(gap.total_seconds() // 60)} min ago"
    if gap < timedelta(days=1):
        return f"{int(gap.total_seconds() // 3600)} hours ago"
    if gap.days == 1:
        return "yesterday"
    if gap.days < 30:
        return f"{gap.days} days ago"
    return then.strftime("%d %b %Y")


def _active_within(stamp: str, days: int) -> bool:
    if not stamp:
        return False
    try:
        then = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - then < timedelta(days=days)


def overview() -> dict[str, Any]:
    """Every account with its usage, newest first, plus service totals."""
    from . import auth

    rows: list[dict[str, Any]] = []
    with auth._connect() as conn:  # noqa: SLF001 — same package, one owner
        conn.row_factory = sqlite3.Row
        # Named columns, not SELECT * — the row also holds the password hash
        # and the verification code, and neither belongs anywhere near a page.
        accounts = [dict(r) for r in conn.execute(
            "SELECT id, email, owner_name, business_name, business_stage, "
            "       location, currency, created_at, last_login_at, "
            "       COALESCE(email_verified,0) AS email_verified, "
            "       COALESCE(auth_provider,'password') AS auth_provider "
            "FROM accounts ORDER BY COALESCE(last_login_at, created_at) DESC")]

    totals = {
        "accounts": len(accounts), "verified": 0, "active7": 0, "active30": 0,
        "products": 0, "orders": 0, "sales": 0.0, "messages": 0,
        "conversations": 0, "connections": 0, "bytes": 0, "dormant": 0,
    }

    for a in accounts:
        stats = _shop_stats(a["id"])
        last = a.get("last_login_at") or a.get("created_at") or ""
        a.update(stats)
        a["verified"] = bool(a.get("email_verified"))
        a["last_seen"] = _ago(last)
        a["joined"] = _ago(a.get("created_at") or "")
        a["active7"] = _active_within(last, 7)
        # A shop with nothing recorded has signed up and not started.
        a["dormant"] = (stats["products"] + stats["orders"]
                        + stats["conversations"]) == 0

        totals["verified"] += 1 if a["verified"] else 0
        totals["active7"] += 1 if a["active7"] else 0
        totals["active30"] += 1 if _active_within(last, 30) else 0
        totals["dormant"] += 1 if a["dormant"] else 0
        for k in ("products", "orders", "messages", "conversations",
                  "connections", "bytes"):
            totals[k] += stats[k]
        totals["sales"] += stats["sales"]
        rows.append(a)

    # Signups per day for the last fortnight, for the little chart.
    signups: dict[str, int] = {}
    for a in accounts:
        day = str(a.get("created_at") or "")[:10]
        if day:
            signups[day] = signups.get(day, 0) + 1
    recent = []
    for i in range(13, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        recent.append({"day": day[5:], "n": signups.get(day, 0)})

    logger.info("admin overview served: %d accounts", len(rows))
    return {"accounts": rows, "totals": totals, "signups": recent}
