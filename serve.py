"""Lucida — serves the Business Suite design, backed by the real workforce.

The design bundle in `web/design/` is served as authored: its own markup, its
own React runtime, its own fonts. Nothing is redrawn here. The server's only
job is to hand the page real data and to accept the actions it sends back.

How the data gets in
--------------------
`web/patch_design.py` rewrites each data constant in the design to prefer
`window.LUCIDA.<key>`, falling back to the design's original literal when the
key is absent or empty. This server injects that object inline, before the
runtime boots — so there is no loading flash and no fetch race. An empty
database means empty keys, which means the design renders exactly as drawn.

Run:  python serve.py         (then open http://127.0.0.1:8000)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lucida.config import settings  # noqa: E402
from lucida.graph import WorkforceRuntime  # noqa: E402
from lucida.observability import bus, get_logger  # noqa: E402

from web import bridge  # noqa: E402

logger = get_logger("serve")

DESIGN_DIR = Path(__file__).parent / "web" / "design"
INDEX = DESIGN_DIR / "index.html"

runtime = WorkforceRuntime()
SESSION = WorkforceRuntime.new_session_id()

# One graph run at a time — the runtime keeps per-session state in SQLite and
# concurrent turns on one session would interleave writes.
_run_lock = asyncio.Lock()


def _pending() -> dict | None:
    try:
        return runtime.pending_approval(SESSION)
    except Exception:  # noqa: BLE001 — a missing checkpoint is not an error
        return None


def _snapshot() -> dict:
    return bridge.snapshot(SESSION, _pending())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def index(request):
    """The design, with a snapshot of real data injected ahead of the runtime."""
    html = INDEX.read_text(encoding="utf-8")
    payload = json.dumps(_snapshot(), ensure_ascii=False, default=str)
    # `</script>` inside JSON would close the tag early; escape the only
    # sequence that can do that.
    payload = payload.replace("</", "<\\/")
    inject = (
        f"<script>window.LUCIDA = Object.assign(window.LUCIDA || {{}}, "
        f"{payload});</script>\n"
    )
    html = html.replace('<script src="./support.js">', inject + '<script src="./support.js">', 1)
    return HTMLResponse(html)


async def api_state(request):
    """The same snapshot, for polling after an action."""
    return JSONResponse(_snapshot())


async def api_ask(request):
    """Run one turn of the workforce and return the refreshed snapshot."""
    if not settings.has_llm:
        return JSONResponse(
            {"error": "No API key. Add GROQ_API_KEY to .env and restart."},
            status_code=400,
        )
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)

    async with _run_lock:
        try:
            # The graph is synchronous; keep the event loop free while it runs.
            answer = await asyncio.to_thread(_drain, text)
        except Exception as exc:  # noqa: BLE001 — report, never 500 the page
            logger.error("turn failed: %s", exc)
            bus.emit(SESSION, "error", "web", f"turn failed: {exc}", level="error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    snap = _snapshot()
    snap["answer"] = answer
    return JSONResponse(snap)


def _drain(text: str) -> str:
    """Run one turn to completion and return the workforce's written answer.

    The graph catches agent failures internally and reports them on the state
    rather than raising, so a run can finish "successfully" with nothing to
    show. Those errors are collected here and surfaced — silently returning an
    empty answer would hide a broken provider behind an HTTP 200.
    """
    report = ""
    steps: list[str] = []
    errors: list[str] = []
    gated = False

    for chunk in runtime.start(owner_input=text, image_paths=[],
                               owner_context={}, session_id=SESSION):
        node = chunk.get("node", "")
        update = chunk.get("update") or {}
        if node == "__interrupt__":
            gated = True
            continue
        if not isinstance(update, dict):
            continue
        if update.get("final_report"):
            report = update["final_report"]
        # `agent_outputs` is cumulative state — every chunk carries the whole
        # dict — so only the node that just finished is read. Iterating the
        # dict instead repeats each agent's summary once per later chunk.
        out = (update.get("agent_outputs") or {}).get(node) or {}
        summary = out.get("summary")
        if summary:
            line = f"**{node.replace('_', ' ').title()}** — {summary}"
            if line not in steps:
                steps.append(line)
        for err in update.get("errors") or []:
            if str(err) not in errors:
                errors.append(str(err))

    if report:
        return report
    if steps:
        return "\n\n".join(steps)
    if gated:
        return ("Your team needs your go-ahead before carrying on — "
                "the decision is waiting on the Today page.")
    if errors:
        return ("**The run did not finish.**\n\n"
                + "\n".join(f"- {e}" for e in errors))
    return "The run finished without producing anything to show."


async def api_decide(request):
    """Answer the human-in-the-loop gate the graph is suspended on."""
    body = await request.json()
    decision = body.get("decision", "approve")
    feedback = body.get("feedback", "")
    async with _run_lock:
        try:
            await asyncio.to_thread(
                _resume, {"decision": decision, "feedback": feedback}
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("resume failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(_snapshot())


def _resume(decision: dict) -> None:
    for _ in runtime.resume(SESSION, decision):
        pass


async def api_health(request):
    return JSONResponse({
        "ok": True,
        "session": SESSION,
        "has_llm": bool(settings.has_llm),
        "pending_gate": bool(_pending()),
    })


app = Starlette(
    debug=False,
    routes=[
        Route("/", index),
        Route("/api/state", api_state),
        Route("/api/ask", api_ask, methods=["POST"]),
        Route("/api/decide", api_decide, methods=["POST"]),
        Route("/api/health", api_health),
        # Serves support.js, image-slot.js and vendor/ alongside the page, so
        # the design's own relative script paths resolve unchanged.
        Mount("/", StaticFiles(directory=str(DESIGN_DIR)), name="design"),
    ],
)


if __name__ == "__main__":
    if not INDEX.exists():
        raise SystemExit(
            f"design bundle missing at {INDEX}\n"
            "Run: python web/patch_design.py"
        )
    print("Lucida — Business Suite  ->  http://127.0.0.1:8000")
    if not settings.has_llm:
        print("  (no API key: the page renders, but the workforce can't run)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
