# Read first — corrected resubmission

**Esme Moula Chowdhury Abha — 26-94089-2 — Lucida**

## Why this package exists

My first submission was marked **73 / C+**, and the marking notes were right
about what they saw. The zip I uploaded contained slide assets, markdown
documents and a 52-line PDF-rendering helper — **no application source code**.
The Evidence Audit recorded, accurately, what could be verified from it:

| Audited from my first zip | Actual, in this package |
|---|---|
| Code files: 1 | **~50 Python files** |
| Lines of code: 52 | **~21,500** |
| Agent definitions in code: 0 | **8 specialists + 1 supervisor** |
| RAG / vector store: No | `src/lucida/memory/vector.py` |
| Logging: No | `src/lucida/observability.py` + trace database |
| Tests: No | **87 tests, all passing** |
| Dashboard: No | 9 screens, live SSE execution trace |
| Architecture diagram: No | `docs/architecture.svg` and `.png` |

None of that was a claim I could not support — it simply was not in the file I
uploaded. The marking note said *"Resubmitting the repository would raise this
materially"*, and the integrity flag suggested *"Request the repository; the
live Railway deployment suggests the work exists."* This is that repository.

## What is in here

```
README.md                  what the system is, and how to run it
docs/architecture.svg      the architecture diagram (also .png)
docs/INDIVIDUAL-CONTRIBUTION.md   named files, named agents, commit evidence
docs/Lucida_Presentation.pptx     slides
src/lucida/                the system: agents, graph, memory, tools
  agents/                  8 specialists, one file each
  supervisor.py            the router and aggregator
  memory/                  SQLite schema + vector store
  tools/                   couriers, channels, search, image generation
web/                       the dashboard
tests/                     87 tests
serve.py                   the application entry point
```

## Running it

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # add an OPENAI_API_KEY
python serve.py                 # http://127.0.0.1:8000
```

Tests need no API key:

```
python -m pytest tests -q       # 87 passed
```

## Verifying the claims quickly

Every command below prints the number next to it. They are listed so the
claims in this document do not have to be taken on trust.

```
git log --format='%ae' | sort -u                  # one address, every commit
git shortlog -sn --all                            # one author, and the count
ls src/lucida/agents/*.py                         # 8 specialists + base, schemas, __init__
git ls-files '*.py' | wc -l                       # ~50 Python files
git ls-files '*.py' | xargs wc -l | tail -1       # ~21,500 lines
python -m pytest tests -q                         # 87 passed
```

Repository history runs 2026-08-14 to 2026-09-05, one author throughout.

Exact commit, file and line counts are not written out here. They change
every time the repository is touched, and a number that rots is worse than no
number — an earlier version of this document claimed 81 commits and 52 files
within a day of both being wrong. The commands above print the current
figures, and `tools/make_submission.py` stamps every package it builds with
the commit it came from.

The architecture diagram is not drawn by hand against the code — the
dashboard builds it *from* the compiled graph. `/api/graph` on the running
app returns the live topology, and the Workforce screen prints LangGraph's
own `draw_mermaid()` of the same object, so the picture cannot drift from
what actually executes:

```
python -c "import sys; sys.path.insert(0,'src'); from lucida.graph import topology; \
t=topology(); print(t['agents'],'agents,',len(t['nodes']),'nodes,',len(t['edges']),'edges')"
# 8 agents, 12 nodes, 19 edges
```

## Building this package

The zip is built by script rather than assembled by hand, because the first
submission failed on exactly that step:

```
python tools/make_submission.py
```

It uses `git archive`, so only tracked files ship — `.env`, the session key
and every shop database are excluded by construction rather than by
remembering — and it then audits its own output against the assignment's
deliverable list, refusing to pass if anything required is missing or
anything sensitive is present.
