# Individual contribution

**Esme Moula Chowdhury Abha — 26-94089-2**

I am the sole author of Lucida. There is no team; the repository has one
contributor across every commit, and this document names the specific files
so the claim is checkable rather than asserted.

## Authorship, from the repository itself

```
$ git log --format='%an <%ae>' | sort | uniq -c
     47 EsmeAbha <esmechowdhuryabha@gmail.com>
     27 Esme Abha <esmechowdhuryabha.com>
      7 Esme Abha <esmechowdhuryabha@gmail.com>
```

Three spellings of my own name and email appear because I committed from two
machines before standardising the git identity. Every commit is mine; no
other contributor exists in the history.

```
$ git rev-list --count HEAD
81 commits, 2026-08-14 to 2026-09-02
```

## The agents I wrote

Each specialist is one file. The supervisor routes to them; they never call
each other.

| Agent | File | Lines |
|---|---|---|
| `ad_creative` | `src/lucida/agents/ad_creative.py` | 271 |
| `delivery` | `src/lucida/agents/delivery.py` | 187 |
| `engagement` | `src/lucida/agents/engagement.py` | 213 |
| `inventory` | `src/lucida/agents/inventory.py` | 137 |
| `market_research` | `src/lucida/agents/market_research.py` | 179 |
| `pricing_agent` | `src/lucida/agents/pricing_agent.py` | 226 |
| `product_vision` | `src/lucida/agents/product_vision.py` | 250 |
| `reporting` | `src/lucida/agents/reporting.py` | 225 |
| supervisor | `src/lucida/supervisor.py` | 696 |

## The rest of the system, by subsystem

| Subsystem | Files I wrote |
|---|---|
| Graph / state machine | `src/lucida/graph.py`, `src/lucida/state.py` |
| Memory (SQLite, 22 tables) | `src/lucida/memory/db.py`, `shared.py` |
| Memory (vector store, RAG) | `src/lucida/memory/vector.py` |
| Model layer + failover | `src/lucida/llm.py`, `src/lucida/pricing.py` |
| Observability / trace | `src/lucida/observability.py` |
| Couriers (Pathao, Steadfast) | `src/lucida/tools/courier.py`, `connections.py`, `delivery_pricing.py` |
| Customer channels | `src/lucida/tools/channels.py`, `inbox.py` |
| Research and images | `src/lucida/tools/web_search.py`, `research.py`, `imagegen.py` |
| Web application | `serve.py`, `web/app_ui.py`, `web/bridge.py`, `web/auth.py`, `web/credits.py` |
| Tests | `tests/test_workforce.py` (87 tests) |

## Design decisions I would defend in a viva

**Per-shop isolation by file, not by column.** Every agent shares one `memory`
singleton, rebound to the signed-in owner before any agent runs. No query has
to remember `WHERE owner_id = ?`, so a forgotten filter cannot leak one
business into another.

**Triage before planning.** The supervisor asks a single cheap question —
does this message need specialists at all? — before drafting a plan. Planning
reads the whole business snapshot, so doing it for "hi" cost ~1,400 tokens
that the router then discarded. Triage cut a greeting from 42,082 tokens to
462.

**Approval gates as graph interrupts, not confirmation dialogs.** Publishing
an ad, spending money and booking a courier suspend the LangGraph run at an
interrupt. Approving resumes from that exact point rather than re-running the
work. The booking gate is enforced server-side, so a replayed request cannot
book.

**Metering on tokens, not on money.** The provider returns token counts with
every reply; the price of a token is a rate table this project cannot keep
accurate for every model it can reach. Earlier builds showed a dollar figure
derived from a generic fallback rate — a real number multiplied by a guess —
and it was removed rather than left to look measured.

## Honest limitations

- Messenger, Facebook and Instagram are implemented but unverified in
  production: they need a Meta app, App Review and Business Verification.
  Telegram was added because it has no review process, so a real customer can
  message the shop today.
- Ad artwork on the free provider is weak; it gets colour and setting right
  and invents the object.
- The vector store is a small JSONL-backed store, not a production vector
  database.
- Anything not connected runs against a simulated adapter that is labelled as
  such everywhere it appears, and nothing simulated is written to a shop's
  records as though a real customer sent it.
