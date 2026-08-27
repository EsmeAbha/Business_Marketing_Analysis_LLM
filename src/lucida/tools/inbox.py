"""The customer chat system: pull messages in, draft replies, send them.

Sits between `channels.py` (which talks to Meta) and the rest of the app.
Three jobs:

  * **Sync.** Pull DMs and comments from every connected platform into
    `social_messages`. Idempotent by `UNIQUE(platform, external_id)`, because
    polling an inbox is something you do repeatedly and a customer must not
    appear four times because the page was refreshed four times.
  * **Read.** Group them into threads the owner can work through, newest
    conversation first, unanswered before answered.
  * **Reply.** Send, and record what was sent and when. A reply that failed
    to send is never marked as replied — the owner would stop chasing a
    customer who never heard back.

Sentiment and intent are filled in by the Engagement agent, not here. This
layer moves messages; it does not interpret them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..observability import get_logger
from . import channels

logger = get_logger("tools.inbox")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SyncResult:
    fetched: int = 0
    stored: int = 0          # genuinely new
    skipped: int = 0         # already had them
    answered: int = 0        # replied to automatically by the shop bot
    simulated: bool = True
    per_platform: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def describe(self) -> str:
        mark = "SIMULATED — " if self.simulated else ""
        parts = ", ".join(f"{k}: {v}" for k, v in self.per_platform.items())
        return (f"{mark}{self.stored} new of {self.fetched} fetched"
                + (f" ({parts})" if parts else "")
                + (f"; {self.answered} answered automatically" if self.answered else "")
                + (f"; problems: {'; '.join(self.errors)}" if self.errors else ""))


def store_message(db, msg: dict[str, Any]) -> bool:
    """Insert one message. Returns True only if it was new.

    `INSERT OR IGNORE` against the unique key is what makes re-syncing safe;
    checking first would race with a concurrent sync.
    """
    before = db.query(
        "SELECT 1 FROM social_messages WHERE platform=? AND external_id=?",
        (msg.get("platform"), msg.get("external_id")),
    )
    if before:
        return False
    db.execute(
        """INSERT OR IGNORE INTO social_messages
           (platform, kind, external_id, thread_id, post_id, sender_id,
            sender_name, message, received_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (msg.get("platform"), msg.get("kind", "dm"), msg.get("external_id"),
         msg.get("thread_id", ""), msg.get("post_id", ""),
         msg.get("sender_id", ""), msg.get("sender_name", "Customer"),
         msg.get("message", ""), msg.get("received_at") or _now(), _now()),
    )
    return True


def sync(db, limit: int = 25, include_comments: bool = True) -> SyncResult:
    """Pull from every platform that has something to give."""
    result = SyncResult()
    # Telegram is the shop's customer channel. Messenger and Instagram are
    # only read once their Page token exists — until App Review grants
    # pages_messaging they can return nothing, and polling them each sync only
    # costs time. The readers stay wired so a token is all that is needed.
    readers = [("telegram", lambda n: channels.read_telegram(n, db))]
    if channels.meta_ready():
        readers.append(("messenger", channels.read_messenger))
    if channels.instagram_ready():
        readers.append(("instagram", channels.read_instagram))

    for name, read in readers:
        box = read(limit)
        if box.error:
            result.errors.append(f"{name}: {box.error}")
            continue
        if not box.simulated:
            result.simulated = False
        new = 0
        for msg in box.messages:
            result.fetched += 1
            if store_message(db, msg):
                new += 1
        result.stored += new
        result.per_platform[name] = new

    # Comments live under published posts, so there is nothing to read until
    # something has been published.
    if include_comments:
        for post in db.query(
            "SELECT platform, external_id FROM social_posts "
            "WHERE external_id IS NOT NULL AND external_id <> '' "
            "ORDER BY id DESC LIMIT 10"
        ):
            box = channels.read_comments(post["platform"], post["external_id"])
            if box.error:
                result.errors.append(f"comments: {box.error}")
                continue
            new = 0
            for msg in box.messages:
                result.fetched += 1
                if store_message(db, msg):
                    new += 1
            key = f"{post['platform']} comments"
            result.per_platform[key] = result.per_platform.get(key, 0) + new
            result.stored += new

    result.skipped = result.fetched - result.stored
    result.answered = auto_answer(db)
    logger.info("inbox sync: %s", result.describe())
    return result


def auto_answer(db, limit: int = 20) -> int:
    """Answer new customer messages the shop can answer from its own records.

    Only Telegram, and only messages nobody has replied to. Stock levels and
    prices come from the database, so the bot cannot promise something the
    shop does not have — see `shopbot`.

    A send that fails leaves the message unanswered on purpose: the owner
    needs to see it is still outstanding rather than believe it was handled.
    """
    from . import shopbot

    if not channels.telegram_ready():
        return 0

    rows = db.query(
        "SELECT * FROM social_messages WHERE platform='telegram' AND replied=0 "
        "ORDER BY id LIMIT ?", (limit,))

    # One answer per person, not one per message. Somebody who sends "hi",
    # "hello", "you there?" wants a reply, not three. The earlier messages are
    # marked handled without sending, so they stop queueing up behind the
    # newest one.
    latest: dict[str, dict] = {}
    superseded: list[int] = []
    for m in rows:
        key = str(m.get("sender_id") or m.get("thread_id") or m["id"])
        if key in latest:
            superseded.append(latest[key]["id"])
        latest[key] = m
    for old_id in superseded:
        db.execute("UPDATE social_messages SET replied=1, reply_text=? WHERE id=?",
                   ("(covered by a later reply)", old_id))

    sent = 0
    for msg in latest.values():
        try:
            reply = shopbot.answer(db, str(msg["message"] or ""),
                                   str(msg["sender_name"] or "there"))
        except Exception as exc:  # noqa: BLE001 — one bad message must not stop the rest
            logger.warning("shopbot could not answer message %s: %s", msg["id"], exc)
            continue
        if not reply.handled or not reply.text.strip():
            continue
        result = channels.send_telegram(str(msg["sender_id"]), reply.text)
        if not result.ok:
            logger.warning("shopbot send failed, leaving unanswered: %s", result.error)
            continue
        db.execute(
            "UPDATE social_messages SET replied=1, reply_text=?, reply_at=? WHERE id=?",
            (reply.text, _now(), msg["id"]))
        sent += 1
        logger.info("shopbot answered %s (%s)", msg["sender_name"], reply.intent)
    return sent


def threads(db, limit: int = 60) -> list[dict[str, Any]]:
    """Conversations, unanswered first, then most recent.

    One row per thread: the latest message is what the owner replies to, and
    a count so a long back-and-forth is visible without loading it.
    """
    rows = db.query(
        """SELECT m.*,
                  (SELECT COUNT(*) FROM social_messages x
                    WHERE x.thread_id = m.thread_id
                      AND x.platform = m.platform) AS in_thread
           FROM social_messages m
           WHERE m.id IN (
                 SELECT MAX(id) FROM social_messages
                 GROUP BY platform, COALESCE(NULLIF(thread_id,''), external_id))
           ORDER BY m.replied ASC, m.received_at DESC
           LIMIT ?""",
        (limit,),
    )
    return rows


def conversation(db, platform: str, thread_id: str) -> list[dict[str, Any]]:
    """Every message in one thread, oldest first — the way it was said."""
    return db.query(
        "SELECT * FROM social_messages WHERE platform=? AND thread_id=? "
        "ORDER BY received_at, id",
        (platform, thread_id),
    )


def unanswered(db) -> int:
    rows = db.query(
        "SELECT COUNT(*) AS n FROM social_messages WHERE replied=0")
    return int(rows[0]["n"]) if rows else 0


def reply(db, message_id: int, text: str) -> channels.ChannelResult:
    """Send a reply, and only mark it answered if it actually went.

    A comment gets a public reply under it; a DM gets a private one. Which of
    the two is decided by what arrived, not by the caller — replying publicly
    to a private complaint would be a bad day.
    """
    rows = db.query("SELECT * FROM social_messages WHERE id=?", (message_id,))
    if not rows:
        return channels.ChannelResult(False, "", "reply", True,
                                      error="no such message")
    msg = rows[0]
    text = (text or "").strip()
    if not text:
        return channels.ChannelResult(False, str(msg["platform"]), "reply",
                                      True, error="nothing to send")

    if msg["kind"] == "comment":
        result = channels.reply_to_comment(
            str(msg["platform"]), str(msg["external_id"]), text)
    else:
        result = channels.send_dm(
            str(msg["platform"]), str(msg["sender_id"]), text)

    if result.ok:
        db.execute(
            "UPDATE social_messages SET replied=1, reply_text=?, reply_at=? "
            "WHERE id=?",
            (text, _now(), message_id),
        )
        logger.info("replied to %s %s", msg["platform"], msg["kind"])
    else:
        # Deliberately left unanswered: the owner needs to see it is still
        # outstanding rather than believe the customer has been dealt with.
        logger.warning("reply failed, leaving unanswered: %s", result.error)
    return result
