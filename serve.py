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
import os
import secrets
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import (  # noqa: E402
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lucida.config import AVATAR_DIR, UPLOAD_DIR, settings  # noqa: E402
from lucida.graph import WorkforceRuntime  # noqa: E402
from lucida.memory import memory  # noqa: E402
from lucida.observability import bus, get_logger  # noqa: E402

from web import auth, bridge, screens  # noqa: E402

logger = get_logger("serve")

DESIGN_DIR = Path(__file__).parent / "web" / "design"
INDEX = DESIGN_DIR / "index.html"

runtime = WorkforceRuntime()

# One workforce session per signed-in account, so two owners working at once
# do not share a conversation or an approval gate.
_SESSIONS: dict[str, str] = {}


def _session_for(account_id: str) -> str:
    if account_id not in _SESSIONS:
        _SESSIONS[account_id] = WorkforceRuntime.new_session_id()
    return _SESSIONS[account_id]

# One graph run at a time — the runtime keeps per-session state in SQLite and
# concurrent turns on one session would interleave writes.
_run_lock = asyncio.Lock()


def current_account(request) -> dict | None:
    """The signed-in owner, with their private shop bound to memory.

    Binding happens here — on every authenticated request — because the agents
    all share one `memory` singleton. Rebinding before any of them runs is
    what keeps one owner's products, messages and campaigns out of another's.
    """
    account_id = request.session.get("account_id")
    if not account_id:
        return None
    account = auth.get_account(account_id)
    if account is None:            # deleted account with a live cookie
        request.session.clear()
        return None
    memory.use_shop(account["id"])
    return account


def _require(request):
    """Returns (account, session_id) or raises a redirect to sign-in."""
    account = current_account(request)
    if account is None:
        raise _NotSignedIn()
    return account, _session_for(account["id"])


class _NotSignedIn(Exception):
    """Signals an unauthenticated request; turned into a redirect or a 401."""


def _pending(session_id: str) -> dict | None:
    try:
        return runtime.pending_approval(session_id)
    except Exception:  # noqa: BLE001 — a missing checkpoint is not an error
        return None


def _snapshot(session_id: str, account: dict | None = None) -> dict:
    snap = bridge.snapshot(session_id, _pending(session_id))
    if account:
        snap["businessName"] = (account.get("business_name")
                                or account.get("owner_name") or "Your shop")
        snap["ownerName"] = account.get("owner_name") or ""
        snap["location"] = account.get("location") or snap.get("location") or ""
        snap["currency"] = account.get("currency") or snap.get("currency") or ""
        snap["account"] = {
            "id": account["id"],
            "email": account.get("email"),
            "stage": account.get("business_stage"),
            "initials": auth.initials(account),
            "avatar": f"/avatar/{account['id']}" if account.get("avatar_path") else "",
        }
    return snap


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def login(request):
    if current_account(request) is not None:
        return RedirectResponse("/", status_code=303)
    if request.method == "GET":
        return HTMLResponse(screens.login_page(
            notice=request.query_params.get("notice", "")))
    form = await request.form()
    email = str(form.get("email") or "")
    try:
        account = auth.authenticate(email, str(form.get("password") or ""))
    except auth.AuthError as exc:
        return HTMLResponse(screens.login_page(str(exc), email), status_code=401)
    request.session["account_id"] = account["id"]
    return RedirectResponse("/", status_code=303)


async def signup(request):
    if current_account(request) is not None:
        return RedirectResponse("/", status_code=303)
    if request.method == "GET":
        return HTMLResponse(screens.signup_page())

    form = await request.form()
    values = {k: str(form.get(k) or "") for k in (
        "email", "owner_name", "business_name", "business_stage",
        "location", "what_you_sell")}
    try:
        account = auth.create_account(
            email=values["email"],
            password=str(form.get("password") or ""),
            owner_name=values["owner_name"],
            business_name=values["business_name"],
            business_stage=values["business_stage"],
            location=values["location"],
            what_you_sell=values["what_you_sell"],
        )
    except auth.AuthError as exc:
        return HTMLResponse(screens.signup_page(str(exc), values), status_code=400)

    # Seed the new shop's own memory with what they just told us, so the
    # agents start from the owner's facts instead of estimating them.
    memory.use_shop(account["id"])
    memory.set_profile(
        owner_name=account.get("owner_name"),
        business_name=account.get("business_name"),
        location=account.get("location"),
        currency=account.get("currency"),
        niche=account.get("what_you_sell"),
        notes=("Owner is starting out and has no business yet."
               if account.get("business_stage") == "starting"
               else "Owner already sells and wants day-to-day management."),
    )
    request.session["account_id"] = account["id"]
    return RedirectResponse("/", status_code=303)


async def logout(request):
    request.session.clear()
    return RedirectResponse("/login?notice=You+are+signed+out.", status_code=303)


async def account_page(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)

    notice = request.query_params.get("notice", "")
    error = ""
    if request.method == "POST":
        form = await request.form()
        account = auth.update_account(
            account["id"],
            **{k: str(form.get(k) or "") for k in auth.EDITABLE},
        ) or account
        # Keep the shop's own profile in step with the account.
        memory.use_shop(account["id"])
        memory.set_profile(
            owner_name=account.get("owner_name"),
            business_name=account.get("business_name"),
            location=account.get("location"),
            currency=account.get("currency"),
            niche=account.get("what_you_sell"),
        )
        notice = "Saved."

    stats = memory.stats()
    friendly = {
        "products": stats.get("products", 0),
        "customer messages": stats.get("conversations", 0),
        "campaigns": stats.get("campaigns", 0),
        "things remembered": stats.get("knowledge_documents", 0),
    }
    return HTMLResponse(screens.account_page(account, error, notice, friendly))


async def account_avatar(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    upload = form.get("avatar")
    if upload is None or not getattr(upload, "filename", ""):
        return RedirectResponse("/account?notice=Choose+a+photo+first.",
                                status_code=303)
    suffix = Path(str(upload.filename)).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return RedirectResponse("/account?notice=Use+a+JPG,+PNG+or+WEBP.",
                                status_code=303)
    dest = AVATAR_DIR / f"{account['id']}{suffix}"
    for old in AVATAR_DIR.glob(f"{account['id']}.*"):
        if old != dest:
            old.unlink(missing_ok=True)
    dest.write_bytes(await upload.read())
    auth.set_avatar(account["id"], str(dest))
    return RedirectResponse("/account?notice=Photo+updated.", status_code=303)


async def account_password(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    try:
        auth.change_password(account["id"], str(form.get("current") or ""),
                             str(form.get("new") or ""))
    except auth.AuthError as exc:
        return HTMLResponse(screens.account_page(account, str(exc)),
                            status_code=400)
    return RedirectResponse("/account?notice=Password+changed.", status_code=303)


async def avatar(request):
    """Serve an owner's photo. Only ever your own — ids are not guessable,
    but the check makes that explicit rather than incidental."""
    account = current_account(request)
    if account is None or account["id"] != request.path_params["account_id"]:
        return JSONResponse({"error": "not found"}, status_code=404)
    stored = account.get("avatar_path")
    if not stored or not Path(stored).exists():
        return JSONResponse({"error": "no photo"}, status_code=404)
    return FileResponse(stored)


async def index(request):
    """The design, with a snapshot of real data injected ahead of the runtime."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    session_id = _session_for(account["id"])

    html = INDEX.read_text(encoding="utf-8")
    payload = json.dumps(_snapshot(session_id, account),
                         ensure_ascii=False, default=str)
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
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    return JSONResponse(_snapshot(_session_for(account["id"]), account))


async def api_ask(request):
    """Run one turn of the workforce and return the refreshed snapshot."""
    if not settings.has_llm:
        return JSONResponse(
            {"error": "No API key. Add GROQ_API_KEY to .env and restart."},
            status_code=400,
        )
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    session_id = _session_for(account["id"])

    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)

    async with _run_lock:
        try:
            # The graph is synchronous; keep the event loop free while it runs.
            answer = await asyncio.to_thread(
                _drain, session_id, text, [], _owner_context(account))
        except Exception as exc:  # noqa: BLE001 — report, never 500 the page
            logger.error("turn failed: %s", exc)
            bus.emit(session_id, "error", "web", f"turn failed: {exc}",
                     level="error")
            return JSONResponse({"error": str(exc)}, status_code=500)

    snap = _snapshot(session_id, account)
    snap["answer"] = answer
    return JSONResponse(snap)


def _owner_context(account: dict | None = None) -> dict:
    """Business facts the agents should not have to guess.

    Persisted in the business_profile table rather than held in memory, so a
    restart doesn't send the agents back to estimating. Anything still unset
    is simply absent, which is what the agents already handle.
    """
    profile = memory.profile() or {}
    account = account or {}
    context: dict = {
        "location": (account.get("location") or profile.get("location")
                     or settings.location),
        "currency": (account.get("currency") or profile.get("currency")
                     or settings.currency),
    }
    if account.get("what_you_sell"):
        context["sells"] = account["what_you_sell"]
    if account.get("business_stage"):
        context["business_stage"] = account["business_stage"]
    if profile.get("monthly_budget"):
        context["fixed_costs"] = profile["monthly_budget"]
    if profile.get("notes"):
        context["notes"] = profile["notes"]
    return context


def _drain(session_id: str, text: str, image_paths: list[str] | None = None,
           owner_context: dict | None = None) -> str:
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

    for chunk in runtime.start(owner_input=text,
                               image_paths=image_paths or [],
                               owner_context=owner_context or {},
                               session_id=session_id):
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


async def api_upload(request):
    """Photo → Product Vision. The headline flow, reachable from the design.

    Vision runs on its own provider: Groq serves no multimodal model, so with
    AIW_PROVIDER=groq and no vision key the Product Vision agent says it could
    not look at the photo rather than guessing. That degradation is reported
    here so the owner is told, instead of silently getting a worse answer.
    """
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    session_id = _session_for(account["id"])

    if not settings.has_llm:
        return JSONResponse(
            {"error": "No API key. Add GROQ_API_KEY to .env and restart."},
            status_code=400,
        )

    form = await request.form()
    upload = form.get("photo")
    if upload is None or not getattr(upload, "filename", ""):
        return JSONResponse({"error": "no photo attached"}, status_code=400)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(str(upload.filename)).name
    dest = UPLOAD_DIR / f"{session_id}-{safe}"
    dest.write_bytes(await upload.read())

    quantity = str(form.get("quantity") or "").strip()
    text = ("Here's a photo of what I make — take a look and tell me whether "
            "it's worth selling.")
    context = _owner_context(account)
    if quantity.isdigit():
        text += f" I have {quantity} pieces in stock."
        context = dict(context)
        context["stock_items"] = [
            {"product_name": "", "quantity": int(quantity), "unit_cost": 0}
        ]

    async with _run_lock:
        try:
            answer = await asyncio.to_thread(
                _drain, session_id, text, [str(dest)], context)
        except Exception as exc:  # noqa: BLE001
            logger.error("photo turn failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)

    if not settings.vision_provider:
        answer = (
            "**I could not actually look at the photo.**\n\n"
            "This provider serves no vision model, so I worked from your "
            "description instead. Add a free `GOOGLE_API_KEY` from "
            "aistudio.google.com/apikey to switch photo reading on — the text "
            "agents stay where they are.\n\n---\n\n" + answer
        )

    snap = _snapshot(session_id, account)
    snap["answer"] = answer
    return JSONResponse(snap)


async def api_decide(request):
    """Answer the human-in-the-loop gate the graph is suspended on."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    session_id = _session_for(account["id"])

    body = await request.json()
    decision = body.get("decision", "approve")
    feedback = body.get("feedback", "")
    async with _run_lock:
        try:
            await asyncio.to_thread(
                _resume, session_id, {"decision": decision, "feedback": feedback}
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("resume failed: %s", exc)
            return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse(_snapshot(session_id, account))


def _resume(session_id: str, decision: dict) -> None:
    for _ in runtime.resume(session_id, decision):
        pass


async def api_health(request):
    account = current_account(request)
    session_id = _session_for(account["id"]) if account else ""
    return JSONResponse({
        "ok": True,
        "signed_in": account is not None,
        "accounts": auth.count_accounts(),
        "session": session_id,
        "has_llm": bool(settings.has_llm),
        "pending_gate": bool(_pending(session_id)) if session_id else False,
    })


# The session cookie is signed with this. A generated key is fine for local
# use but logs everyone out on restart, so a real deployment should set
# AIW_SECRET_KEY and keep it stable.
SECRET_KEY = os.environ.get("AIW_SECRET_KEY") or secrets.token_hex(32)
if not os.environ.get("AIW_SECRET_KEY"):
    logger.info("no AIW_SECRET_KEY set — sessions reset when this restarts")

app = Starlette(
    debug=False,
    middleware=[
        Middleware(
            SessionMiddleware,
            secret_key=SECRET_KEY,
            session_cookie="lucida_session",
            max_age=14 * 24 * 3600,
            same_site="lax",
            # Set AIW_HTTPS=1 behind TLS so the cookie is never sent in clear.
            https_only=os.environ.get("AIW_HTTPS") == "1",
        )
    ],
    routes=[
        Route("/", index),
        Route("/login", login, methods=["GET", "POST"]),
        Route("/signup", signup, methods=["GET", "POST"]),
        Route("/logout", logout, methods=["POST", "GET"]),
        Route("/account", account_page, methods=["GET", "POST"]),
        Route("/account/avatar", account_avatar, methods=["POST"]),
        Route("/account/password", account_password, methods=["POST"]),
        Route("/avatar/{account_id}", avatar),
        Route("/api/state", api_state),
        Route("/api/ask", api_ask, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
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
