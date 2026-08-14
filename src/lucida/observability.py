"""Structured logging, the execution-trace event bus, and error capture.

Every agent action, tool call, hand-off and failure lands here with a
timestamp. The Streamlit UI reads the same store, so what the user sees in the
live trace is exactly what was persisted — there is no second code path.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import traceback
import uuid
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import DB_PATH, LOG_PATH

# --- Python logging --------------------------------------------------------

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("lucida")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(stream_handler)
    return logger


log = _build_logger()


def get_logger(name: str) -> logging.Logger:
    return log.getChild(name)


# --- Trace events ----------------------------------------------------------

EventLevel = str  # "info" | "warning" | "error"


@dataclass
class TraceEvent:
    """One row in the execution trace."""

    session_id: str
    kind: str  # agent_start | agent_end | tool_call | handoff | approval | llm_usage | error
    actor: str  # which agent / component emitted it
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    level: EventLevel = "info"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_row(self) -> tuple:
        return (
            self.id,
            self.session_id,
            self.ts,
            self.kind,
            self.actor,
            self.level,
            self.summary,
            json.dumps(self.payload, default=str),
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_events (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    ts          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    actor       TEXT NOT NULL,
    level       TEXT NOT NULL,
    summary     TEXT NOT NULL,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trace_session ON trace_events(session_id, ts);
"""


class EventBus:
    """Thread-safe append-only trace store: SQLite for durability, deque for UI polling."""

    def __init__(self, db_path=DB_PATH, buffer_size: int = 2000) -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        self._buffer: deque[TraceEvent] = deque(maxlen=buffer_size)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, timeout=30, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def emit(
        self,
        session_id: str,
        kind: str,
        actor: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        level: EventLevel = "info",
    ) -> TraceEvent:
        event = TraceEvent(
            session_id=session_id,
            kind=kind,
            actor=actor,
            summary=summary,
            payload=payload or {},
            level=level,
        )
        with self._lock:
            self._buffer.append(event)
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO trace_events VALUES (?,?,?,?,?,?,?,?)",
                        event.to_row(),
                    )
            except sqlite3.Error as exc:  # never let telemetry break the workflow
                log.warning("trace persist failed: %s", exc)

        logger = log.getChild(actor)
        getattr(logger, "error" if level == "error" else "info")(
            "[%s] %s", kind, summary
        )
        return event

    def recent(self, session_id: str | None = None, limit: int = 500) -> list[TraceEvent]:
        with self._lock:
            events = list(self._buffer)
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        return events[-limit:]

    def load(self, session_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        """Read the durable trace back — survives a Streamlit process restart."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, session_id, ts, kind, actor, level, summary, payload "
                "FROM trace_events WHERE session_id=? ORDER BY ts, rowid LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "session_id": r[1],
                    "ts": r[2],
                    "kind": r[3],
                    "actor": r[4],
                    "level": r[5],
                    "summary": r[6],
                    "payload": json.loads(r[7]),
                }
            )
        return out

    def as_dicts(self, session_id: str | None = None) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.recent(session_id)]

    def sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """Every run the trace remembers, newest first.

        Reads the durable table rather than the in-process buffer, so a UI
        started after a run still lists it — and so a separate web process
        sees runs the Streamlit process recorded, and vice versa.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, COUNT(*) AS steps, MIN(ts) AS started, "
                "       MAX(ts) AS ended, "
                "       SUM(CASE WHEN level='error' THEN 1 ELSE 0 END) AS errors "
                "FROM trace_events GROUP BY session_id "
                "ORDER BY MAX(ts) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "session_id": r[0],
                "steps": r[1],
                "started": r[2],
                "ended": r[3],
                "errors": r[4],
            }
            for r in rows
        ]


bus = EventBus()


# --- Error handling --------------------------------------------------------


class AgentError(Exception):
    """Raised when an agent cannot complete its task.

    Always caught by the graph: the failure is logged, surfaced to the owner,
    and the workflow continues with a degraded result rather than crashing.
    """

    def __init__(self, agent: str, message: str, cause: Exception | None = None):
        self.agent = agent
        self.cause = cause
        super().__init__(f"[{agent}] {message}")


@contextmanager
def guarded(session_id: str, actor: str, action: str) -> Iterator[dict[str, Any]]:
    """Run a block, converting any exception into a logged, non-fatal trace event.

    Yields a mutable dict; on failure it gets `ok=False` and `error` set, so the
    caller can degrade gracefully instead of propagating the exception.
    """
    outcome: dict[str, Any] = {"ok": True, "error": None}
    try:
        yield outcome
    except Exception as exc:  # noqa: BLE001 — deliberate catch-all boundary
        outcome["ok"] = False
        outcome["error"] = f"{type(exc).__name__}: {exc}"
        bus.emit(
            session_id,
            kind="error",
            actor=actor,
            summary=f"{action} failed: {type(exc).__name__}: {exc}",
            payload={"traceback": traceback.format_exc(limit=6)},
            level="error",
        )
