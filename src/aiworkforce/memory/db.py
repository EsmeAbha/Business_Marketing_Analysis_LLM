"""Structured business database.

This is the business's system of record: profile, product catalog, inventory,
pricing history, customer conversations, extracted pre-orders, ad campaigns,
deliveries and reports. Agents write here; later agents (notably Reporting)
read what earlier ones left behind.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ..config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS business_profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    owner_name    TEXT,
    business_name TEXT,
    niche         TEXT,
    location      TEXT,
    currency      TEXT,
    monthly_budget REAL,
    notes         TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    category      TEXT,
    description   TEXT,
    unit_cost     REAL,
    sell_price    REAL,
    photo_path    TEXT,
    source_agent  TEXT,
    created_at    TEXT,
    UNIQUE(name)
);

CREATE TABLE IF NOT EXISTS inventory (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id),
    quantity      INTEGER NOT NULL DEFAULT 0,
    reorder_level INTEGER NOT NULL DEFAULT 5,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES products(id),
    delta         INTEGER NOT NULL,
    reason        TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS pricing_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER REFERENCES products(id),
    unit_cost     REAL,
    sell_price    REAL,
    margin_pct    REAL,
    breakeven_units REAL,
    rationale     TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    channel       TEXT,          -- messenger | instagram | comment
    customer      TEXT,
    message       TEXT,
    sentiment     TEXT,
    intent        TEXT,          -- preorder | question | complaint | unmet_demand | other
    requested_item TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS preorders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer      TEXT,
    product_name  TEXT,
    quantity      INTEGER DEFAULT 1,
    channel       TEXT,
    status        TEXT DEFAULT 'new',
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS campaigns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT,
    headline      TEXT,
    body          TEXT,
    call_to_action TEXT,
    product_name  TEXT,
    status        TEXT,          -- drafted | approved | published | failed
    external_id   TEXT,
    simulated     INTEGER DEFAULT 1,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS deliveries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider      TEXT,
    consignment_id TEXT,
    recipient     TEXT,
    address       TEXT,
    product_name  TEXT,
    amount        REAL,
    status        TEXT,
    simulated     INTEGER DEFAULT 1,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    title         TEXT,
    body          TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    checkpoint    TEXT,
    decision      TEXT,          -- approved | rejected | changes_requested
    feedback      TEXT,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS agent_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    sender        TEXT,
    recipient     TEXT,
    task          TEXT,
    payload       TEXT,
    created_at    TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin, thread-safe SQLite wrapper. Rows come back as dicts."""

    def __init__(self, path=DB_PATH) -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- generic helpers ---

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock, self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: tuple = ()) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid or 0

    # --- business profile ---

    def upsert_profile(self, **fields: Any) -> None:
        current = self.get_profile()
        merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
        self.execute(
            """INSERT INTO business_profile
               (id, owner_name, business_name, niche, location, currency,
                monthly_budget, notes, updated_at)
               VALUES (1,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 owner_name=excluded.owner_name, business_name=excluded.business_name,
                 niche=excluded.niche, location=excluded.location,
                 currency=excluded.currency, monthly_budget=excluded.monthly_budget,
                 notes=excluded.notes, updated_at=excluded.updated_at""",
            (
                merged.get("owner_name"),
                merged.get("business_name"),
                merged.get("niche"),
                merged.get("location"),
                merged.get("currency"),
                merged.get("monthly_budget"),
                merged.get("notes"),
                _now(),
            ),
        )

    def get_profile(self) -> dict[str, Any]:
        rows = self.query("SELECT * FROM business_profile WHERE id=1")
        return rows[0] if rows else {}

    # --- products & inventory ---

    def upsert_product(
        self,
        name: str,
        category: str = "",
        description: str = "",
        unit_cost: float | None = None,
        sell_price: float | None = None,
        photo_path: str = "",
        source_agent: str = "",
    ) -> int:
        existing = self.query("SELECT id FROM products WHERE name=?", (name,))
        if existing:
            pid = existing[0]["id"]
            self.execute(
                """UPDATE products SET category=COALESCE(NULLIF(?,''),category),
                   description=COALESCE(NULLIF(?,''),description),
                   unit_cost=COALESCE(?,unit_cost), sell_price=COALESCE(?,sell_price),
                   photo_path=COALESCE(NULLIF(?,''),photo_path) WHERE id=?""",
                (category, description, unit_cost, sell_price, photo_path, pid),
            )
            return pid
        return self.execute(
            """INSERT INTO products
               (name, category, description, unit_cost, sell_price, photo_path,
                source_agent, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                name,
                category,
                description,
                unit_cost,
                sell_price,
                photo_path,
                source_agent,
                _now(),
            ),
        )

    def set_stock(self, product_id: int, quantity: int, reorder_level: int = 5) -> None:
        existing = self.query(
            "SELECT id FROM inventory WHERE product_id=?", (product_id,)
        )
        if existing:
            self.execute(
                "UPDATE inventory SET quantity=?, reorder_level=?, updated_at=? WHERE product_id=?",
                (quantity, reorder_level, _now(), product_id),
            )
        else:
            self.execute(
                "INSERT INTO inventory (product_id, quantity, reorder_level, updated_at) VALUES (?,?,?,?)",
                (product_id, quantity, reorder_level, _now()),
            )

    def adjust_stock(self, product_id: int, delta: int, reason: str = "") -> int:
        rows = self.query(
            "SELECT quantity FROM inventory WHERE product_id=?", (product_id,)
        )
        current = rows[0]["quantity"] if rows else 0
        new_qty = max(0, current + delta)
        self.set_stock(product_id, new_qty)
        self.execute(
            "INSERT INTO stock_movements (product_id, delta, reason, created_at) VALUES (?,?,?,?)",
            (product_id, delta, reason, _now()),
        )
        return new_qty

    def inventory_view(self) -> list[dict[str, Any]]:
        return self.query(
            """SELECT p.id, p.name, p.category, p.unit_cost, p.sell_price, p.photo_path,
                      COALESCE(i.quantity,0) AS quantity,
                      COALESCE(i.reorder_level,5) AS reorder_level,
                      CASE WHEN COALESCE(i.quantity,0) <= COALESCE(i.reorder_level,5)
                           THEN 1 ELSE 0 END AS low_stock
               FROM products p LEFT JOIN inventory i ON i.product_id = p.id
               ORDER BY low_stock DESC, p.name"""
        )

    def low_stock(self) -> list[dict[str, Any]]:
        return [r for r in self.inventory_view() if r["low_stock"]]

    # --- pricing ---

    def record_pricing(
        self,
        product_id: int | None,
        unit_cost: float,
        sell_price: float,
        margin_pct: float,
        breakeven_units: float,
        rationale: str,
    ) -> int:
        return self.execute(
            """INSERT INTO pricing_history
               (product_id, unit_cost, sell_price, margin_pct, breakeven_units,
                rationale, created_at) VALUES (?,?,?,?,?,?,?)""",
            (
                product_id,
                unit_cost,
                sell_price,
                margin_pct,
                breakeven_units,
                rationale,
                _now(),
            ),
        )

    # --- customer engagement ---

    def add_conversation(self, **f: Any) -> int:
        return self.execute(
            """INSERT INTO conversations
               (channel, customer, message, sentiment, intent, requested_item, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                f.get("channel", ""),
                f.get("customer", ""),
                f.get("message", ""),
                f.get("sentiment", ""),
                f.get("intent", ""),
                f.get("requested_item", ""),
                _now(),
            ),
        )

    def add_preorder(
        self, customer: str, product_name: str, quantity: int = 1, channel: str = ""
    ) -> int:
        return self.execute(
            """INSERT INTO preorders (customer, product_name, quantity, channel, status, created_at)
               VALUES (?,?,?,?, 'new', ?)""",
            (customer, product_name, quantity, channel, _now()),
        )

    # --- campaigns / deliveries / reports ---

    def add_campaign(self, **f: Any) -> int:
        return self.execute(
            """INSERT INTO campaigns
               (platform, headline, body, call_to_action, product_name, status,
                external_id, simulated, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f.get("platform", ""),
                f.get("headline", ""),
                f.get("body", ""),
                f.get("call_to_action", ""),
                f.get("product_name", ""),
                f.get("status", "drafted"),
                f.get("external_id", ""),
                int(f.get("simulated", 1)),
                _now(),
            ),
        )

    def update_campaign(self, campaign_id: int, status: str, external_id: str = "") -> None:
        self.execute(
            "UPDATE campaigns SET status=?, external_id=COALESCE(NULLIF(?,''),external_id) WHERE id=?",
            (status, external_id, campaign_id),
        )

    def add_delivery(self, **f: Any) -> int:
        return self.execute(
            """INSERT INTO deliveries
               (provider, consignment_id, recipient, address, product_name, amount,
                status, simulated, created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f.get("provider", ""),
                f.get("consignment_id", ""),
                f.get("recipient", ""),
                f.get("address", ""),
                f.get("product_name", ""),
                float(f.get("amount", 0) or 0),
                f.get("status", "created"),
                int(f.get("simulated", 1)),
                _now(),
            ),
        )

    def add_report(self, session_id: str, title: str, body: str) -> int:
        return self.execute(
            "INSERT INTO reports (session_id, title, body, created_at) VALUES (?,?,?,?)",
            (session_id, title, body, _now()),
        )

    def add_approval(
        self, session_id: str, checkpoint: str, decision: str, feedback: str = ""
    ) -> int:
        return self.execute(
            """INSERT INTO approvals (session_id, checkpoint, decision, feedback, created_at)
               VALUES (?,?,?,?,?)""",
            (session_id, checkpoint, decision, feedback, _now()),
        )

    def add_agent_message(
        self, session_id: str, sender: str, recipient: str, task: str, payload: Any
    ) -> int:
        return self.execute(
            """INSERT INTO agent_messages (session_id, sender, recipient, task, payload, created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                session_id,
                sender,
                recipient,
                task,
                json.dumps(payload, default=str)[:20000],
                _now(),
            ),
        )

    def table_names(self) -> list[str]:
        return [
            r["name"]
            for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]


db = Database()
