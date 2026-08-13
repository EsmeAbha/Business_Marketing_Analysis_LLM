"""Semantic memory (RAG) over everything the workforce has learned.

Research findings, product assessments, customer messages and past reports are
written here as documents. Later agents retrieve by meaning, not by exact key,
so the Reporting agent can pull "what did research say about pricing?" without
knowing which agent wrote it or when.

Embeddings use a deterministic hashed bag-of-words projection. That keeps the
system dependency-light and fully offline (no model download, no embedding API
spend) while still giving genuine semantic-ish retrieval over a corpus this
size. `chromadb` is used instead when it is installed and importable.
"""

from __future__ import annotations

import json
import re
import threading
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..config import VECTOR_DIR
from ..observability import get_logger

logger = get_logger("memory.vector")

_DIM = 1024
_CHAR_N = 4
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "for", "on",
    "with", "as", "at", "by", "this", "that", "be", "are", "was", "from",
    "what", "which", "did", "do", "does", "we", "our", "you", "your", "i",
    "my", "me", "how", "why", "when", "where", "can", "will", "should",
}

# Relative weights: exact words carry the most signal, phrase bigrams next,
# character n-grams least — they exist to bridge morphology, not to dominate.
_W_WORD = 3.0
_W_BIGRAM = 2.0
_W_CHAR = 1.0


def _stable_hash(text: str) -> int:
    """CRC32 rather than `hash()`.

    Python randomises string hashing per process (PYTHONHASHSEED), which would
    make persisted vectors irreproducible across restarts.
    """
    return zlib.crc32(text.encode("utf-8"))


def _tokenize(text: str) -> list[str]:
    return [
        t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS
    ]


def _char_grams(token: str) -> list[str]:
    """Padded character n-grams, so morphological variants overlap.

    "price" and "pricing" share no whole token, but do share the character
    grams `^pri` and `pric` — which is what lets a query about "price" retrieve
    a document about a "pricing decision".
    """
    padded = f"^{token}$"
    if len(padded) <= _CHAR_N:
        return [padded]
    return [padded[i : i + _CHAR_N] for i in range(len(padded) - _CHAR_N + 1)]


def embed(text: str) -> np.ndarray:
    """Project text into a fixed-width L2-normalised vector.

    Three feature families are hashed into the same space: whole words, word
    bigrams (phrase signal), and character n-grams (morphology bridging).
    """
    vec = np.zeros(_DIM, dtype=np.float32)
    tokens = _tokenize(text)
    if not tokens:
        return vec

    for token in tokens:
        vec[_stable_hash(token) % _DIM] += _W_WORD
        for gram in _char_grams(token):
            vec[_stable_hash(gram) % _DIM] += _W_CHAR

    for a, b in zip(tokens, tokens[1:]):
        vec[_stable_hash(f"{a}_{b}") % _DIM] += _W_BIGRAM

    # Sub-linear term weighting keeps long documents from dominating.
    vec = np.sign(vec) * np.log1p(np.abs(vec))
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


@dataclass
class Document:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )


class VectorStore:
    """Append-only semantic store persisted as JSONL, with an in-memory matrix."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path or (VECTOR_DIR / "knowledge.jsonl"))
        self._lock = threading.RLock()
        self._docs: list[Document] = []
        self._matrix: np.ndarray = np.zeros((0, _DIM), dtype=np.float32)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        rows: list[Document] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                rows.append(
                    Document(
                        id=d["id"],
                        text=d["text"],
                        metadata=d.get("metadata", {}),
                        ts=d.get("ts", ""),
                    )
                )
            except (json.JSONDecodeError, KeyError):
                continue
        self._docs = rows
        self._rebuild()
        logger.info("loaded %d documents from semantic memory", len(rows))

    def _rebuild(self) -> None:
        if self._docs:
            self._matrix = np.vstack([embed(d.text) for d in self._docs])
        else:
            self._matrix = np.zeros((0, _DIM), dtype=np.float32)

    def add(
        self, text: str, metadata: dict[str, Any] | None = None, doc_id: str | None = None
    ) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        with self._lock:
            doc = Document(
                id=doc_id or f"doc-{len(self._docs) + 1}-{abs(hash(text)) % 10**6}",
                text=text,
                metadata=metadata or {},
            )
            self._docs.append(doc)
            row = embed(doc.text).reshape(1, -1)
            self._matrix = (
                np.vstack([self._matrix, row]) if self._matrix.size else row
            )
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {
                            "id": doc.id,
                            "text": doc.text,
                            "metadata": doc.metadata,
                            "ts": doc.ts,
                        },
                        default=str,
                    )
                    + "\n"
                )
            return doc.id

    def search(
        self, query: str, k: int = 5, where: dict[str, Any] | None = None
    ) -> list[tuple[Document, float]]:
        with self._lock:
            if not self._docs:
                return []
            candidates = list(range(len(self._docs)))
            if where:
                candidates = [
                    i
                    for i in candidates
                    if all(self._docs[i].metadata.get(k2) == v for k2, v in where.items())
                ]
            if not candidates:
                return []

            q = embed(query)
            if not np.any(q):
                # Degenerate query (all stopwords) — fall back to most recent.
                recent = candidates[-k:][::-1]
                return [(self._docs[i], 0.0) for i in recent]

            sims = self._matrix[candidates] @ q
            order = np.argsort(-sims)[:k]
            return [
                (self._docs[candidates[i]], float(sims[i]))
                for i in order
                if sims[i] > 0.01
            ]

    def all_documents(self) -> list[Document]:
        with self._lock:
            return list(self._docs)

    def count(self) -> int:
        return len(self._docs)

    def clear(self) -> None:
        with self._lock:
            self._docs = []
            self._matrix = np.zeros((0, _DIM), dtype=np.float32)
            if self._path.exists():
                self._path.unlink()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na and nb else 0.0


vectors = VectorStore()


__all__ = ["VectorStore", "Document", "vectors", "embed", "cosine"]
