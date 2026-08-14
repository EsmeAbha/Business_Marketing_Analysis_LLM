"""SharedMemory — the single facade agents use to read and write state.

Agents never talk to SQLite or the vector store directly. They call
`memory.remember(...)` to publish a finding and `memory.recall(...)` to pull
relevant context written by *other* agents in earlier stages. This is what
makes collaboration durable rather than message-passing-only: the Reporting
agent can read the Market Research agent's conclusions three stages later, and
across process restarts.
"""

from __future__ import annotations

from typing import Any

from ..config import SHOPS_DIR
from ..observability import get_logger
from .db import Database, db
from .vector import Document, VectorStore, vectors

logger = get_logger("memory")


class SharedMemory:
    def __init__(self) -> None:
        self.db = db
        self.vectors = vectors
        self.shop_id: str | None = None

    def use_shop(self, shop_id: str | None) -> None:
        """Point this memory at one owner's private store.

        Every agent imports this same singleton, so swapping the backing
        database and vector store here redirects all of them at once. That is
        why isolation is done by file rather than by adding an owner column to
        twelve tables: no query has to remember to filter, and a missed filter
        cannot leak one shop's business into another's.

        The web layer calls this once per request, before any agent runs.
        """
        if shop_id == self.shop_id:
            return
        if shop_id is None:
            self.db, self.vectors, self.shop_id = db, vectors, None
            return

        safe = "".join(c for c in str(shop_id) if c.isalnum() or c in "-_")
        if not safe:
            raise ValueError(f"unusable shop id: {shop_id!r}")

        shop_dir = SHOPS_DIR / safe
        shop_dir.mkdir(parents=True, exist_ok=True)
        self.db = Database(shop_dir / "shop.db")
        self.vectors = VectorStore(shop_dir / "knowledge.jsonl")
        self.shop_id = safe
        logger.info("memory bound to shop %s", safe)

    # --- semantic (RAG) side ---

    def remember(
        self,
        text: str,
        agent: str,
        kind: str,
        session_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> str:
        """Publish a finding so every later agent can retrieve it."""
        meta = {"agent": agent, "kind": kind, "session_id": session_id, **(extra or {})}
        doc_id = self.vectors.add(text, meta)
        logger.info("remember kind=%s agent=%s chars=%d", kind, agent, len(text))
        return doc_id

    def recall(
        self, query: str, k: int = 5, kind: str | None = None
    ) -> list[tuple[Document, float]]:
        return self.vectors.search(query, k=k, where={"kind": kind} if kind else None)

    def recall_text(
        self, query: str, k: int = 5, kind: str | None = None, chars: int | None = None
    ) -> str:
        """Retrieved context formatted for direct injection into a prompt.

        Snippet length defaults to the provider's prompt budget — providers with
        a tight per-minute token cap get shorter excerpts.
        """
        from ..config import settings

        if chars is None:
            chars = 320 if settings.compact_prompts else 700

        hits = self.recall(query, k=k, kind=kind)
        if not hits:
            return "(no prior knowledge stored yet)"
        lines = []
        for doc, score in hits:
            agent = doc.metadata.get("agent", "?")
            dkind = doc.metadata.get("kind", "?")
            lines.append(f"- [{agent}/{dkind}, relevance {score:.2f}] {doc.text[:chars]}")
        return "\n".join(lines)

    # --- structured side (delegated, kept explicit for discoverability) ---

    def profile(self) -> dict[str, Any]:
        return self.db.get_profile()

    def set_profile(self, **fields: Any) -> None:
        self.db.upsert_profile(**fields)

    def inventory(self) -> list[dict[str, Any]]:
        return self.db.inventory_view()

    def low_stock(self) -> list[dict[str, Any]]:
        return self.db.low_stock()

    def products(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM products ORDER BY name")

    def conversations(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
        )

    def preorders(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM preorders ORDER BY id DESC")

    def campaigns(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM campaigns ORDER BY id DESC")

    def deliveries(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM deliveries ORDER BY id DESC")

    def reports(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,))

    def approvals(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            return self.db.query(
                "SELECT * FROM approvals WHERE session_id=? ORDER BY id DESC",
                (session_id,),
            )
        return self.db.query("SELECT * FROM approvals ORDER BY id DESC")

    def agent_messages(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            return self.db.query(
                "SELECT * FROM agent_messages WHERE session_id=? ORDER BY id",
                (session_id,),
            )
        return self.db.query("SELECT * FROM agent_messages ORDER BY id DESC LIMIT 200")

    def pricing_history(self) -> list[dict[str, Any]]:
        return self.db.query(
            """SELECT ph.*, p.name AS product_name FROM pricing_history ph
               LEFT JOIN products p ON p.id = ph.product_id ORDER BY ph.id DESC"""
        )

    # --- snapshot used to brief agents on current business state ---

    def business_snapshot(self) -> str:
        profile = self.profile()
        inv = self.inventory()
        low = [r for r in inv if r["low_stock"]]
        pre = self.preorders()
        camps = self.campaigns()

        parts = ["BUSINESS STATE SNAPSHOT"]
        if profile:
            parts.append(
                f"Profile: {profile.get('business_name') or 'unnamed'} | "
                f"niche={profile.get('niche') or 'undecided'} | "
                f"location={profile.get('location') or '?'} | "
                f"currency={profile.get('currency') or '?'}"
            )
        else:
            parts.append("Profile: not yet established.")

        if inv:
            parts.append(f"Catalog ({len(inv)} products):")
            for r in inv[:12]:
                parts.append(
                    f"  - {r['name']}: qty={r['quantity']} cost={r['unit_cost']} "
                    f"price={r['sell_price']}{'  [LOW STOCK]' if r['low_stock'] else ''}"
                )
        else:
            parts.append("Catalog: empty — no products registered yet.")

        if low:
            parts.append(f"Low stock alerts: {', '.join(r['name'] for r in low)}")
        if pre:
            parts.append(f"Open pre-orders: {len(pre)}")
        if camps:
            published = sum(1 for c in camps if c["status"] == "published")
            parts.append(f"Campaigns: {len(camps)} total, {published} published")
        return "\n".join(parts)

    def stats(self) -> dict[str, int]:
        return {
            "products": len(self.products()),
            "conversations": len(self.conversations(10_000)),
            "preorders": len(self.preorders()),
            "campaigns": len(self.campaigns()),
            "deliveries": len(self.deliveries()),
            "reports": len(self.reports(10_000)),
            "knowledge_documents": self.vectors.count(),
        }


memory = SharedMemory()
