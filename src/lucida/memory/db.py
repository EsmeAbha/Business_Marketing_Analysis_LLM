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
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from ..config import DB_PATH, settings

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

-- Sales the owner has actually made. Everything the dashboard says about
-- money earned, order counts, how fast stock is moving and how many days of
-- cover is left is derived from this table -- so an empty table means those
-- figures are honestly unknown rather than estimated.
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER REFERENCES products(id),
    product_name  TEXT,
    quantity      INTEGER NOT NULL DEFAULT 1,
    unit_price    REAL,
    amount        REAL,          -- quantity * unit_price, stored for speed
    unit_cost     REAL,          -- cost at time of sale, for real margin
    channel       TEXT,          -- messenger | instagram | walk-in | phone
    customer      TEXT,
    status        TEXT DEFAULT 'fulfilled',   -- fulfilled | pending | cancelled
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

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
    decision      TEXT,          -- approve | reject | request_changes
    feedback      TEXT,
    created_at    TEXT
);
-- Resuming an interrupt replays the node from its start, so the code that
-- records a decision runs again on every later resume. The unique index makes
-- that write idempotent instead of accumulating duplicate rows.
CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_unique
    ON approvals(session_id, checkpoint, decision, feedback);

CREATE TABLE IF NOT EXISTS agent_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    sender        TEXT,
    recipient     TEXT,
    task          TEXT,
    payload       TEXT,
    created_at    TEXT
);

-- ===========================================================================
-- Delivery pricing
--
-- A courier quote in Bangladesh is a function of three things: how heavy the
-- parcel is, how far it is going, and which courier. Rather than hard-coding
-- one price list, zones and their rates are rows -- so an owner whose courier
-- charges differently can change the numbers without a code change, and a
-- second courier is more rows rather than another branch.
--
-- Weight is grams throughout. Storing a float of kilograms invites rounding
-- arguments at exactly the boundary where the price steps up.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS delivery_zones (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,        -- Inside Dhaka, Outside Dhaka, Sub-city
    kind          TEXT NOT NULL,        -- inside_city | outside_city | same_area
    provider      TEXT,                 -- blank = applies to every courier
    base_weight_g INTEGER NOT NULL DEFAULT 1000,   -- what base_charge covers
    base_charge   REAL NOT NULL,                   -- for anything up to base
    per_kg_extra  REAL NOT NULL DEFAULT 0,         -- each additional kg, or part
    cod_percent   REAL NOT NULL DEFAULT 1.0,       -- cash-on-delivery fee, %
    min_cod_fee   REAL NOT NULL DEFAULT 0,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT,
    UNIQUE(name, provider)
);

-- Where a customer is, resolved to a zone. Kept separate from the order so
-- one customer's address can be reused and corrected in one place.
CREATE TABLE IF NOT EXISTS addresses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer      TEXT,
    phone         TEXT,
    line1         TEXT,
    area          TEXT,                 -- Mirpur 11, Uttara Sector 7
    city          TEXT,
    zone_id       INTEGER REFERENCES delivery_zones(id),
    is_inside_city INTEGER NOT NULL DEFAULT 1,
    notes         TEXT,
    created_at    TEXT
);

-- ===========================================================================
-- Social channels
--
-- One row per connected page/account, so an owner can run two Facebook pages
-- or a personal and a shop Instagram without the credentials colliding. The
-- token lives here rather than in .env because it is per-shop, and .env is
-- per-server.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS social_accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,        -- facebook | instagram | messenger | youtube
    external_id   TEXT,                 -- page id, ig user id, channel id
    display_name  TEXT,
    access_token  TEXT,
    token_expires TEXT,
    connected     INTEGER NOT NULL DEFAULT 0,
    last_synced   TEXT,
    created_at    TEXT,
    UNIQUE(platform, external_id)
);

-- Everything that arrives from a customer, whatever the channel: a Messenger
-- DM, an Instagram DM, a comment under an ad. `external_id` is what makes
-- syncing idempotent -- polling the same inbox twice must not duplicate.
CREATE TABLE IF NOT EXISTS social_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    platform      TEXT NOT NULL,
    kind          TEXT NOT NULL,        -- dm | comment | mention
    external_id   TEXT,
    thread_id     TEXT,                 -- conversation / post this belongs to
    post_id       TEXT,                 -- the ad or post, when it is a comment
    sender_id     TEXT,
    sender_name   TEXT,
    message       TEXT,
    sentiment     TEXT,
    intent        TEXT,
    requested_item TEXT,
    replied       INTEGER NOT NULL DEFAULT 0,
    reply_text    TEXT,
    reply_at      TEXT,
    received_at   TEXT,
    created_at    TEXT,
    UNIQUE(platform, external_id)
);

-- What was published, and where it landed. Separate from `campaigns`: a
-- campaign is the idea and the copy, a post is one concrete thing live on one
-- platform with its own id to fetch comments against.
CREATE TABLE IF NOT EXISTS social_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id   INTEGER REFERENCES campaigns(id),
    platform      TEXT NOT NULL,
    external_id   TEXT,                 -- post id / media id / video id
    permalink     TEXT,
    kind          TEXT,                 -- post | reel | story | video
    caption       TEXT,
    media_id      INTEGER REFERENCES media_assets(id),
    status        TEXT,                 -- published | failed | simulated
    simulated     INTEGER NOT NULL DEFAULT 1,
    comment_count INTEGER NOT NULL DEFAULT 0,
    last_synced   TEXT,
    created_at    TEXT,
    UNIQUE(platform, external_id)
);

-- ===========================================================================
-- Media
--
-- Product photos the owner uploaded and artwork the model generated, in one
-- table: an ad needs to reference either without caring which it is. `source`
-- is what keeps that honest -- a generated image should never be mistaken for
-- a photograph of real stock.
-- ===========================================================================

CREATE TABLE IF NOT EXISTS media_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER REFERENCES products(id),
    kind          TEXT NOT NULL,        -- product_photo | ad_creative | logo
    source        TEXT NOT NULL,        -- uploaded | generated | edited
    path          TEXT,                 -- on disk, under data/media/
    url           TEXT,                 -- remote, when hosted
    prompt        TEXT,                 -- what produced it, when generated
    model         TEXT,
    width         INTEGER,
    height        INTEGER,
    bytes         INTEGER,
    created_at    TEXT
);
"""

# Columns added after the first release. Applied with ALTER TABLE against a
# PRAGMA check so existing shop databases upgrade in place instead of needing
# to be rebuilt -- an owner's trading history is not disposable.
MIGRATIONS: dict[str, dict[str, str]] = {
    "products": {
        # Weight drives the delivery quote, so it belongs on the product
        # rather than being typed in per order.
        "weight_g": "INTEGER NOT NULL DEFAULT 0",
        "length_cm": "REAL",
        "width_cm": "REAL",
        "height_cm": "REAL",
        "sku": "TEXT",
        "is_fragile": "INTEGER NOT NULL DEFAULT 0",
    },
    "orders": {
        "address_id": "INTEGER REFERENCES addresses(id)",
        "zone_id": "INTEGER REFERENCES delivery_zones(id)",
        "weight_g": "INTEGER NOT NULL DEFAULT 0",
        "delivery_charge": "REAL NOT NULL DEFAULT 0",
        "cod_fee": "REAL NOT NULL DEFAULT 0",
        "total_charge": "REAL NOT NULL DEFAULT 0",
        "is_cod": "INTEGER NOT NULL DEFAULT 1",
    },
    "social_messages": {
        # What the Engagement agent drafted, kept apart from `reply_text`
        # which is what was actually sent. Conflating the two would make an
        # unsent suggestion look like an answered customer.
        "draft_reply": "TEXT",
    },
    "campaigns": {
        "media_id": "INTEGER REFERENCES media_assets(id)",
        "budget_daily": "REAL",
        "spend_total": "REAL NOT NULL DEFAULT 0",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Thin, thread-safe SQLite wrapper. Rows come back as dicts."""

    def __init__(self, path=DB_PATH) -> None:
        self._path = str(path)
        self._lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
        self._seed_zones()

    @staticmethod
    def _migrate(conn) -> None:
        for table, columns in MIGRATIONS.items():
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column, spec in columns.items():
                if column not in have:
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {spec}"
                    )

    def _seed_zones(self) -> None:
        """Default courier rates, once, and only if the owner has none.

        These are the published Bangladeshi flat rates most couriers quote —
        a starting point the owner can edit, not a claim about their contract.
        Anything they change is never overwritten, because this only runs when
        the table is empty.
        """
        if self.query("SELECT 1 FROM delivery_zones LIMIT 1"):
            return
        for name, kind, base_g, base, per_kg in (
            ("Same area", "same_area", 1000, 60.0, 20.0),
            ("Inside city", "inside_city", 1000, 80.0, 20.0),
            ("Outside city", "outside_city", 1000, 130.0, 25.0),
        ):
            self.execute(
                """INSERT INTO delivery_zones
                   (name, kind, provider, base_weight_g, base_charge,
                    per_kg_extra, cod_percent, min_cod_fee, active, created_at)
                   VALUES (?,?,'',?,?,?,1.0,0,1,?)""",
                (name, kind, base_g, base, per_kg, _now()),
            )

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """A connection to whichever backend is configured.

        Local SQLite by default — no account, no network. If
        `AIW_DATABASE_URL` names a libSQL/Turso database, that is used
        instead: libSQL speaks SQLite's dialect, so the schema and every
        query below are identical either way.
        """
        if settings.uses_remote_db:
            import libsql  # imported lazily so the local path needs no extra dep

            conn = libsql.connect(
                database=self._path,
                sync_url=settings.database_url,
                auth_token=settings.database_auth_token,
            )
            try:
                conn.sync()          # pull anything written elsewhere
                yield conn
                conn.commit()
                conn.sync()          # push what we just wrote
            finally:
                conn.close()
            return

        conn = sqlite3.connect(self._path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- generic helpers ---

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        # Rows are built from cursor.description rather than a row_factory:
        # sqlite3.Row supports dict(), but libSQL returns plain tuples, and
        # this shape works for both without branching at every call site.
        with self._lock, self.connect() as conn:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            if not rows:
                return []
            columns = [d[0] for d in cur.description]
            return [dict(zip(columns, row)) for row in rows]

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

    # --- orders and the figures derived from them ---

    def record_order(
        self,
        product_name: str,
        quantity: int,
        unit_price: float | None = None,
        unit_cost: float | None = None,
        channel: str = "",
        customer: str = "",
        status: str = "fulfilled",
        product_id: int | None = None,
    ) -> int:
        """Log a sale, filling price and cost from the catalogue if omitted."""
        if unit_price is None or unit_cost is None:
            match = self.query(
                "SELECT id, unit_cost, sell_price FROM products WHERE name=?",
                (product_name,),
            )
            if match:
                product_id = product_id or match[0]["id"]
                unit_price = unit_price if unit_price is not None else match[0]["sell_price"]
                unit_cost = unit_cost if unit_cost is not None else match[0]["unit_cost"]
        amount = (unit_price or 0) * max(0, int(quantity))
        return self.execute(
            """INSERT INTO orders (product_id, product_name, quantity, unit_price,
                                   amount, unit_cost, channel, customer, status,
                                   created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (product_id, product_name, int(quantity), unit_price, amount,
             unit_cost, channel, customer, status, _now()),
        )

    def orders(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.query(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    def sales_since(self, days: int) -> dict[str, Any]:
        """Totals over a window. Zero rows means unknown, not zero sales."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self.query(
            """SELECT COUNT(*) AS orders, COALESCE(SUM(quantity),0) AS units,
                      COALESCE(SUM(amount),0) AS revenue,
                      COALESCE(SUM(quantity * COALESCE(unit_cost,0)),0) AS cost
               FROM orders
               WHERE status <> 'cancelled' AND created_at >= ?""",
            (cutoff,),
        )
        row = rows[0] if rows else {"orders": 0, "units": 0, "revenue": 0, "cost": 0}
        row["profit"] = (row["revenue"] or 0) - (row["cost"] or 0)
        row["known"] = bool(row["orders"])
        return row

    def run_rate(self, product_name: str, days: int = 14) -> float | None:
        """Units sold per day. None when there is nothing to measure."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self.query(
            """SELECT COALESCE(SUM(quantity),0) AS units, COUNT(*) AS n
               FROM orders
               WHERE product_name=? AND status <> 'cancelled' AND created_at >= ?""",
            (product_name, cutoff),
        )
        if not rows or not rows[0]["n"]:
            return None
        return (rows[0]["units"] or 0) / float(days)

    def days_of_cover(self, product_name: str, quantity: int) -> float | None:
        rate = self.run_rate(product_name)
        if not rate:
            return None
        return quantity / rate

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
            """INSERT OR IGNORE INTO approvals
               (session_id, checkpoint, decision, feedback, created_at)
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
