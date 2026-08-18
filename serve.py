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
import hashlib
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
from lucida.tools import inbox  # noqa: E402
from lucida.observability import bus, get_logger  # noqa: E402

from lucida.tools import (  # noqa: E402
    channels, connections, delivery_pricing, imagegen, research,
)
from lucida.tools.courier import courier  # noqa: E402
from web import (  # noqa: E402
    app_ui, auth, bridge, google_oauth, mailer, screens,
)

logger = get_logger("serve")


def page(markup: str, status: int = 200) -> HTMLResponse:
    """An HTML response the browser will not serve from cache.

    Every screen here is per-account and changes with the shop's data, so a
    cached copy is always the wrong one — and during development it means a
    fix that shipped looks like a fix that did not.
    """
    return HTMLResponse(markup, status_code=status, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })

DESIGN_DIR = Path(__file__).parent / "web" / "design"
INDEX = DESIGN_DIR / "index.html"

runtime = WorkforceRuntime()

# One workforce session per signed-in account, so two owners working at once
# do not share a conversation or an approval gate.
_SESSIONS: dict[str, str] = {}


def _session_for(account_id: str) -> str:
    """A fresh run id for this owner, carrying who they are.

    The trace is one file for the whole machine, so the id has to say which
    shop a run belonged to or the dashboard cannot tell them apart. The owner
    goes in as a prefix rather than the whole id: a new id per process keeps
    graph checkpoints from resuming yesterday's half-finished state, while the
    shared prefix still gathers every run this owner has ever made.
    """
    if account_id not in _SESSIONS:
        tag = hashlib.sha256(str(account_id).encode()).hexdigest()[:10]
        _SESSIONS[account_id] = (
            f"sess-{tag}-{WorkforceRuntime.new_session_id().split('-')[-1]}")
    return _SESSIONS[account_id]


def owner_runs_prefix(account_id: str) -> str:
    """Every session id this owner has ever used starts with this."""
    return "sess-" + hashlib.sha256(str(account_id).encode()).hexdigest()[:10] + "-"

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
# Delivery
# ---------------------------------------------------------------------------


async def delivery_page(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    return page(app_ui.delivery_page(
        _who(account),
        products=memory.db.query(
            "SELECT name, weight_g, sell_price FROM products ORDER BY name"),
        zones=delivery_pricing.zones(memory.db),
        courier=connections.courier_ready(memory.db),
        dispatch=memory.dispatch(),
        note=request.session.pop("delivery_note", "")))


async def api_delivery_quote(request):
    """What this parcel costs to send, before anyone commits to it."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)
    body = await request.json()

    items = [{"product_name": str(body.get("product") or ""),
              "quantity": int(body.get("quantity") or 1)}]

    # The zone decides the charge, so the owner's own choice wins. Guessing
    # from the address is only the default, and only when the shop has a real
    # town recorded — "Online" is not one, and matching it against "Dhaka"
    # would quietly price every local parcel as long-distance.
    # If the owner told us where they send from, remember it — they should
    # not have to type it for every parcel.
    from_city = str(body.get("from_city") or "").strip()
    from_area = str(body.get("from_area") or "").strip()
    if from_city:
        memory.set_dispatch(from_city, from_area)
    else:
        from_city, from_area = memory.dispatch()

    kind = str(body.get("zone") or "").strip()
    if kind not in ("same_area", "inside_city", "outside_city"):
        # Measured from where the parcel is handed over, not from the shop's
        # description of itself: "Online" is not a place a courier drives to.
        kind = delivery_pricing.classify_address(
            area=str(body.get("area") or ""),
            city=str(body.get("city") or ""),
            shop_city=from_city,
            shop_area=from_area)

    q = delivery_pricing.quote(
        memory.db, items, kind=kind,
        provider=connections.courier_ready(memory.db),
        is_cod=bool(body.get("cod", True)))

    return JSONResponse({
        "known": q.known,
        "zoneKind": kind,
        "zone": q.zone_name or kind.replace("_", " "),
        "weight_g": q.weight_g,
        "billable_kg": q.billable_kg,
        "delivery": round(q.delivery_charge, 2),
        "cod_fee": round(q.cod_fee, 2),
        "goods": round(q.goods_total, 2),
        "total": round(q.total_charge, 2),
        "currency": account.get("currency") or settings.currency,
        "problems": q.problems,
        "explain": q.explain(account.get("currency") or settings.currency)
                   if q.known else "",
    })


async def api_delivery_book(request):
    """Hand the parcel to the courier the shop connected."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)
    body = await request.json()

    provider = connections.courier_ready(memory.db)
    if not provider:
        return JSONResponse({"error": (
            "No courier connected. Add Steadfast or Pathao on the Connect "
            "screen and the booking goes through your own account.")}, 400)

    result = await asyncio.to_thread(
        courier.book,
        provider=provider,
        recipient=str(body.get("customer") or ""),
        phone=str(body.get("phone") or ""),
        address=str(body.get("address") or ""),
        product_name=str(body.get("product") or ""),
        cod_amount=float(body.get("cod_amount") or 0),
        note=str(body.get("note") or ""))

    memory.db.execute(
        "INSERT INTO deliveries (provider, consignment_id, recipient, address, "
        "product_name, amount, status, simulated, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,datetime('now'))",
        (result.provider, result.consignment_id or "", str(body.get("customer") or ""),
         str(body.get("address") or ""), str(body.get("product") or ""),
         float(body.get("cod_amount") or 0),
         "booked" if result.ok else "failed", 1 if result.simulated else 0))

    return JSONResponse({
        "ok": result.ok,
        "simulated": result.simulated,
        "consignment": result.consignment_id or "",
        "error": result.error or "",
        "provider": result.provider,
    })


async def favicon(request):
    """The tab icon. Its absence was a 404 on every single page load."""
    return FileResponse(DESIGN_DIR / "favicon.svg",
                        media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=86400"})



# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


def _catalogue() -> list[dict]:
    """Every product with its stock, in one row each."""
    return memory.db.query(
        "SELECT p.*, COALESCE(i.quantity,0) AS quantity, "
        "       COALESCE(i.reorder_level,5) AS reorder_level "
        "FROM products p LEFT JOIN inventory i ON i.product_id = p.id "
        "ORDER BY p.name")


async def products_page(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    return page(app_ui.products_page(
        _who(account), _catalogue(),
        editing=request.query_params.get("edit", ""),
        note=request.session.pop("product_note", "")))


async def product_save(request):
    """Add a product, or change one. The only place a weight can be set."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    name = str(form.get("name") or "").strip()
    if not name:
        request.session["product_note"] = "A product needs a name."
        return RedirectResponse("/products", status_code=303)

    def _num(field, cast=float):
        raw = str(form.get(field) or "").strip()
        try:
            return cast(raw) if raw else None
        except ValueError:
            return None

    pid = str(form.get("id") or "").strip()
    if pid:
        # An edit: the name may have changed, so it is written directly
        # rather than going through the upsert's fold-by-name matching.
        memory.db.execute(
            "UPDATE products SET name=?, category=?, unit_cost=?, "
            "sell_price=?, weight_g=? WHERE id=?",
            (name, str(form.get("category") or ""), _num("unit_cost"),
             _num("sell_price"), int(_num("weight_g", float) or 0), int(pid)))
        product_id = int(pid)
    else:
        product_id = memory.db.upsert_product(
            name=name,
            category=str(form.get("category") or ""),
            unit_cost=_num("unit_cost"),
            sell_price=_num("sell_price"),
            weight_g=int(_num("weight_g", float) or 0),
            source_agent="owner")
        if product_id is None:
            request.session["product_note"] = (
                f"“{name}” is not a usable product name.")
            return RedirectResponse("/products", status_code=303)

    qty = _num("quantity", float)
    if qty is not None:
        memory.db.set_stock(product_id, int(qty),
                            int(_num("reorder_level", float) or 5))

    request.session["product_note"] = f"Saved {name}."
    return RedirectResponse("/products", status_code=303)


async def product_delete(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    pid = int(request.path_params["product_id"])
    rows = memory.db.query("SELECT name FROM products WHERE id=?", (pid,))
    name = rows[0]["name"] if rows else ""
    # Orders record the product name as it was sold, and often no id at all,
    # so checking the id alone would have let a product with sales be deleted
    # and quietly changed what the dashboard reports.
    sold = memory.db.query(
        "SELECT 1 FROM orders WHERE product_id=? OR product_name=? LIMIT 1",
        (pid, name))
    if sold:
        # Deleting it would take the sales with it and change what the
        # dashboard reports. Renaming is the honest way to retire a line.
        request.session["product_note"] = (
            "That product has sales recorded against it, so removing it would "
            "change your figures. Edit it instead.")
        return RedirectResponse("/products", status_code=303)
    for table in ("inventory", "stock_movements", "pricing_history",
                  "media_assets"):
        try:
            memory.db.execute(f"DELETE FROM {table} WHERE product_id=?", (pid,))
        except Exception:  # noqa: BLE001 — an absent column is not an error
            pass
    memory.db.execute("DELETE FROM products WHERE id=?", (pid,))
    request.session["product_note"] = f"Removed {name or 'it'}."
    return RedirectResponse("/products", status_code=303)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def login(request):
    if current_account(request) is not None:
        return RedirectResponse("/", status_code=303)
    if request.method == "GET":
        return page(screens.login_page(
            notice=request.query_params.get("notice", ""),
            google=google_oauth.enabled()))
    form = await request.form()
    email = str(form.get("email") or "")
    try:
        account = auth.authenticate(email, str(form.get("password") or ""))
    except auth.AuthError as exc:
        return HTMLResponse(
            screens.login_page(str(exc), email, google=google_oauth.enabled()),
            401)
    request.session["account_id"] = account["id"]
    return RedirectResponse("/", status_code=303)


async def signup(request):
    if current_account(request) is not None:
        return RedirectResponse("/", status_code=303)
    if request.method == "GET":
        return page(screens.signup_page(google=google_oauth.enabled()))

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
        return HTMLResponse(
            screens.signup_page(str(exc), values, google=google_oauth.enabled()),
            400)

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
    _send_verification(request, account)
    return RedirectResponse("/verify", status_code=303)


def _send_verification(request, account) -> None:
    """Mint a code and try to email it, remembering what happened.

    With no mail server configured the code is carried in the session so the
    verify screen can show it — clearly labelled as un-sent, never dressed up
    as a delivered email.
    """
    code = auth.issue_verification_code(account["id"])
    result = mailer.send_code(account["email"], code,
                              account.get("owner_name") or "")
    request.session["verify_problem"] = "" if result.delivered else result.detail
    request.session["verify_dev_code"] = "" if result.delivered else code


async def verify(request):
    account_id = request.session.get("account_id")
    if not account_id:
        return RedirectResponse("/login", status_code=303)
    account = auth.get_account(account_id)
    if account is None:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    if auth.is_verified(account):
        return RedirectResponse("/", status_code=303)

    error = ""
    if request.method == "POST":
        form = await request.form()
        try:
            auth.verify_code(account_id, str(form.get("code") or ""))
        except auth.AuthError as exc:
            error = str(exc)
        else:
            request.session.pop("verify_dev_code", None)
            request.session.pop("verify_problem", None)
            return RedirectResponse("/", status_code=303)

    return HTMLResponse(
        screens.verify_page(
            email=account["email"],
            error=error,
            notice=request.query_params.get("notice", ""),
            dev_code=request.session.get("verify_dev_code", ""),
            delivery_problem=request.session.get("verify_problem", ""),
            resend_in=auth.seconds_until_resend(account_id),
        ),
        status_code=400 if error else 200,
    )


async def verify_resend(request):
    account_id = request.session.get("account_id")
    if not account_id:
        return RedirectResponse("/login", status_code=303)
    if auth.seconds_until_resend(account_id) > 0:
        return RedirectResponse("/verify", status_code=303)
    account = auth.get_account(account_id)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    _send_verification(request, account)
    return RedirectResponse("/verify?notice=A+new+code+is+on+its+way.",
                            status_code=303)


async def google_start(request):
    if not google_oauth.enabled():
        return RedirectResponse(
            "/login?notice=Google+sign-in+is+not+set+up+on+this+server.",
            status_code=303)
    state = google_oauth.new_state()
    request.session["oauth_state"] = state
    return RedirectResponse(google_oauth.authorize_url(state), status_code=303)


async def google_callback(request):
    expected = request.session.pop("oauth_state", None)
    given = request.query_params.get("state")
    # Without this check, an attacker could hand someone a callback URL and
    # sign them into an account they do not own.
    if not expected or given != expected:
        return HTMLResponse(
            screens.login_page("That sign-in link expired. Try again.",
                               google=google_oauth.enabled()),
            status_code=400)
    if request.query_params.get("error"):
        return RedirectResponse("/login?notice=Google+sign-in+was+cancelled.",
                                status_code=303)
    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/login", status_code=303)

    try:
        person = await asyncio.to_thread(google_oauth.exchange, code)
    except google_oauth.OAuthError as exc:
        return HTMLResponse(
            screens.login_page(str(exc), google=google_oauth.enabled()),
            status_code=400)

    account = auth.upsert_google_account(
        sub=person.sub, email=person.email, owner_name=person.name,
        email_verified=person.email_verified,
    )
    memory.use_shop(account["id"])
    memory.set_profile(
        owner_name=account.get("owner_name"),
        business_name=account.get("business_name"),
        location=account.get("location"),
        currency=account.get("currency"),
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
    return page(screens.account_page(account, error, notice, friendly))


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
        return page(screens.account_page(account, str(exc)),
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


def _thread_for(request, account: dict, make: bool = False) -> int | None:
    """Which conversation this request belongs to.

    Held in the session rather than the URL so a reload lands back where the
    owner was, and so one browser tab does not silently write into the
    conversation another tab is showing.
    """
    tid = request.session.get("thread_id")
    if tid:
        if memory.db.query("SELECT 1 FROM chat_threads WHERE id=?", (tid,)):
            return int(tid)
        request.session.pop("thread_id", None)
    tid = memory.db.latest_thread()
    if tid is None and make:
        tid = memory.db.new_thread()
    if tid is not None:
        request.session["thread_id"] = int(tid)
    return tid

STARTERS = [
    "What should I sell to make money this month?",
    "Write me an Instagram ad for what I sell",
    "What are customers asking for that I don't have?",
    "Am I charging enough?",
]


def _who(account: dict) -> dict:
    return {
        "name": account.get("owner_name") or "Your account",
        "email": account.get("email") or "",
        "business": account.get("business_name") or account.get("owner_name")
                    or "Lucida",
        "location": account.get("location") or "",
        "initials": auth.initials(account),
        "avatar": f"/avatar/{account['id']}" if account.get("avatar_path") else "",
    }


async def chat(request):
    """The main screen: a conversation, with the composer where it belongs."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    if not auth.is_verified(account):
        return RedirectResponse("/verify", status_code=303)
    tid = _thread_for(request, account)
    history = [
        {"role": m["role"], "text": m["text"]}
        for m in (memory.db.chat_turns(tid) if tid else [])
    ]
    return page(app_ui.chat_page(
        _who(account), history, STARTERS,
        threads=memory.db.chat_list(), current=tid))


async def chat_new(request):
    if current_account(request) is None:
        return RedirectResponse("/login", status_code=303)
    request.session["thread_id"] = memory.db.new_thread()
    return RedirectResponse("/", status_code=303)


async def chat_open(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    tid = int(request.path_params["thread_id"])
    if memory.db.query("SELECT 1 FROM chat_threads WHERE id=?", (tid,)):
        request.session["thread_id"] = tid
    return RedirectResponse("/", status_code=303)


async def chat_delete(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    tid = int(request.path_params["thread_id"])
    memory.db.delete_thread(tid)
    if request.session.get("thread_id") == tid:
        request.session.pop("thread_id", None)
    return RedirectResponse("/", status_code=303)


async def studio(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    return page(app_ui.studio_page(
        _who(account), imagegen.status(), channels.status(),
        imagegen.quality_note()))


async def connect(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    backend = ("Turso (hosted)" if settings.uses_remote_db
               else "A private SQLite file on this machine")
    note = request.session.pop("connect_note", "")
    return page(app_ui.connect_page(
        _who(account), connections.status(memory.db), imagegen.status(),
        backend, bool(settings.has_llm),
        oauth={p: connections.can_oauth(p) for p in connections.PLATFORMS},
        note=note))


def _redirect_uri(request, platform: str) -> str:
    """Where the platform sends the browser back.

    Built from the request rather than configured, because the address the
    owner reached the app on is the one that has to be registered with Meta
    or Google. Guessing localhost when they came in over the network would
    fail the redirect_uri match with an error they cannot read.
    """
    base = os.environ.get("AIW_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/connect/{platform}/callback"


async def connect_start(request):
    """The Connect button: either sign in with the platform, or paste a token."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    platform = request.path_params["platform"]
    if platform not in connections.PLATFORMS:
        return RedirectResponse("/connect", status_code=303)

    if connections.can_oauth(platform) and request.query_params.get("manual") != "1":
        state = secrets.token_urlsafe(24)
        request.session["connect_state"] = state
        uri = _redirect_uri(request, platform)
        url = (connections.google_authorize_url(uri, state)
               if platform == "youtube"
               else connections.meta_authorize_url(uri, state))
        return RedirectResponse(url, status_code=303)

    return page(app_ui.connect_form(
        _who(account), platform, connections.can_oauth(platform),
        _redirect_uri(request, platform),
        request.session.pop("connect_error", "")))


async def connect_save(request):
    """A pasted credential. Verified against the live API before it is kept."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    platform = request.path_params["platform"]
    form = await request.form()
    token = str(form.get("token") or "").strip()
    ident = str(form.get("ident") or "").strip()

    result = await asyncio.to_thread(
        connections.connect, memory.db, platform, token, ident)
    if not result.ok:
        request.session["connect_error"] = result.error
        return RedirectResponse(f"/connect/{platform}?manual=1", status_code=303)
    request.session["connect_note"] = (
        f"{platform.title()} connected as {result.display_name}.")
    return RedirectResponse("/connect", status_code=303)


async def connect_callback(request):
    """Back from the platform with a one-time code."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    platform = request.path_params["platform"]

    state = request.query_params.get("state", "")
    expected = request.session.pop("connect_state", "")
    if not expected or state != expected:
        request.session["connect_note"] = (
            "That sign-in did not come back the way it left. Nothing was "
            "saved, so start again from Connect.")
        return RedirectResponse("/connect", status_code=303)

    if request.query_params.get("error"):
        request.session["connect_note"] = (
            "You cancelled, or the platform refused: "
            + request.query_params.get("error_description",
                                       request.query_params["error"]))
        return RedirectResponse("/connect", status_code=303)

    code = request.query_params.get("code", "")
    uri = _redirect_uri(request, platform)

    if platform == "youtube":
        token, err = await asyncio.to_thread(
            connections.google_finish, code, uri)
        if err:
            request.session["connect_note"] = err
            return RedirectResponse("/connect", status_code=303)
        result = await asyncio.to_thread(
            connections.connect, memory.db, "youtube", token)
        request.session["connect_note"] = (
            f"YouTube connected as {result.display_name}." if result.ok
            else result.error)
        return RedirectResponse("/connect", status_code=303)

    pages, err = await asyncio.to_thread(connections.meta_finish, code, uri)
    if err:
        request.session["connect_note"] = err
        return RedirectResponse("/connect", status_code=303)
    if not pages:
        request.session["connect_note"] = (
            "That account administers no Facebook Page, so there is nothing "
            "to connect yet.")
        return RedirectResponse("/connect", status_code=303)

    # A Page token from /me/accounts is what the publishing and messaging
    # endpoints want; the user token they arrived with cannot post as the Page.
    top = pages[0]
    page_token = top.get("access_token") or ""
    name = top.get("name") or "your Page"
    connections.save(memory.db, "facebook", str(top.get("id")), name, page_token)
    connections.save(memory.db, "messenger", str(top.get("id")), name, page_token)
    told = [name]

    ig = top.get("instagram_business_account") or {}
    if ig.get("id"):
        handle = f"@{ig.get('username') or ig['id']}"
        connections.save(memory.db, "instagram", str(ig["id"]), handle, page_token)
        told.append(handle)

    request.session["connect_note"] = "Connected " + " and ".join(told) + "."
    return RedirectResponse("/connect", status_code=303)


async def connect_forget(request):
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    platform = request.path_params["platform"]
    connections.forget(memory.db, platform)
    # Meta treats the Page as one thing, so dropping one and keeping the other
    # would leave a connection the owner believes they removed.
    if platform in ("messenger", "facebook"):
        connections.forget(
            memory.db, "facebook" if platform == "messenger" else "messenger")
    request.session["connect_note"] = f"{platform.title()} disconnected."
    return RedirectResponse("/connect", status_code=303)


async def api_studio_generate(request):
    """Draw the poster and write the words, in one go."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)

    body = await request.json()
    product = str(body.get("product") or "").strip()
    if not product:
        return JSONResponse({"error": "what are you advertising?"},
                            status_code=400)
    offer = str(body.get("offer") or "").strip()
    audience = str(body.get("audience") or "").strip()
    style = str(body.get("style") or "").strip()
    detail = str(body.get("detail") or "").strip()
    preset = str(body.get("preset") or "square")
    try:
        seed = int(body.get("seed")) if body.get("seed") is not None else None
    except (TypeError, ValueError):
        seed = None

    art = await asyncio.to_thread(
        imagegen.generate_for_product, product, preset, style, offer,
        audience, detail, seed)

    copy_html = ""
    if settings.has_llm:
        try:
            copy_html = await asyncio.to_thread(
                _write_ad_copy, product, offer, audience)
        except Exception as exc:  # noqa: BLE001 — the poster still stands alone
            logger.warning("ad copy failed: %s", exc)
            copy_html = ("<em>Could not write the words this time — the "
                         "poster above is still yours.</em>")
    else:
        copy_html = "<em>Add an API key and your team will write the words too.</em>"

    if art.ok:
        memory.db.execute(
            """INSERT INTO media_assets (kind, source, path, prompt, model,
                                         width, height, bytes, created_at)
               VALUES ('ad_creative','generated',?,?,?,?,?,?,datetime('now'))""",
            (art.path, art.prompt, art.provider, art.width, art.height,
             art.bytes),
        )

    return JSONResponse({
        "image": f"/media/{Path(art.path).name}" if art.ok else "",
        "image_error": art.error,
        "provider": art.provider,
        "copy_html": copy_html,
    })


def _write_ad_copy(product: str, offer: str, audience: str) -> str:
    """One model call for platform-specific copy — no agent graph needed."""
    from lucida.llm import get_llm, text_of

    ask = (
        f"Write short ad copy for a small shop selling: {product}."
        + (f" Offer: {offer}." if offer else "")
        + (f" Audience: {audience}." if audience else "")
        + " Give three versions, each 2-3 lines, labelled Facebook, Instagram"
          " and YouTube. Plain text, no markdown headers, no emoji spam."
          " Write the way a shop owner speaks, not a marketer."
    )
    reply = get_llm(settings.model or "", 500).invoke(ask)
    text = text_of(reply)
    return app_ui.e(text).replace("\n", "<br>")


async def api_studio_upload(request):
    """Take the owner's own product photo into the editor.

    Their photograph of real stock is better than any generated picture, so
    this is the preferred path — the drawing tool exists for owners who have
    nothing to photograph yet.
    """
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)

    form = await request.form()
    upload = form.get("photo")
    if upload is None or not getattr(upload, "filename", ""):
        return JSONResponse({"error": "no photo attached"}, status_code=400)

    suffix = Path(str(upload.filename)).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return JSONResponse({"error": "use a JPG, PNG or WEBP"},
                            status_code=400)

    raw = await upload.read()
    if len(raw) > 12 * 1024 * 1024:
        return JSONResponse({"error": "that photo is over 12 MB"},
                            status_code=400)

    imagegen.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"own-{account['id']}-{secrets.token_hex(4)}{suffix}"
    (imagegen.MEDIA_DIR / name).write_bytes(raw)

    memory.db.execute(
        """INSERT INTO media_assets (kind, source, path, width, height, bytes,
                                     created_at)
           VALUES ('product_photo','uploaded',?,0,0,?,datetime('now'))""",
        (str(imagegen.MEDIA_DIR / name), len(raw)),
    )
    logger.info("studio: own photo uploaded (%d bytes)", len(raw))
    return JSONResponse({"image": f"/media/{name}", "source": "uploaded"})


async def media(request):
    """Serve generated artwork back to the page that asked for it."""
    if current_account(request) is None:
        return JSONResponse({"error": "not signed in"}, 401)
    name = Path(request.path_params["name"]).name      # no traversal
    path = imagegen.MEDIA_DIR / name
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path)


async def board(request):
    """The design, with a snapshot of real data injected ahead of the runtime."""
    account = current_account(request)
    if account is None:
        return RedirectResponse("/login", status_code=303)
    if not auth.is_verified(account):
        return RedirectResponse("/verify", status_code=303)
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
        return JSONResponse({"error": "not signed in"}, 401)
    return JSONResponse(_snapshot(_session_for(account["id"]), account))


# Openers that need a person, not a workforce. Running the planner, the
# router and eight specialists to answer "hey" is what emptied a day's token
# allowance — and it is a worse answer, too.
SMALL_TALK = {
    "hi", "hey", "hello", "yo", "salam", "assalamu alaikum", "hii", "helo",
    "good morning", "good afternoon", "good evening", "how are you",
    "thanks", "thank you", "ok", "okay", "cool", "nice", "test", "testing",
}


def _small_talk_reply(text: str, account: dict) -> str | None:
    """A direct answer when there is nothing to delegate.

    Deliberately not a model call: it costs nothing, cannot be rate limited,
    and a greeting has one right answer anyway.
    """
    plain = text.strip().lower().strip("!?.,")
    if plain not in SMALL_TALK and len(plain.split()) > 3:
        return None
    if plain not in SMALL_TALK:
        return None

    name = (account.get("owner_name") or "").split(" ")[0]
    hello = f"Hello {name}." if name else "Hello."
    if plain.startswith(("thank", "ok", "okay", "cool", "nice")):
        return "Any time. What next?"
    return (
        f"{hello} Your team is here — nine specialists between "
        f"research, pricing, stock, marketing, customers and delivery."
        "\n\nAsk me something real and I will put it to them. For example:"
        "\n\n- What should I sell to make money this month?"
        "\n- Write an Instagram ad for what I sell"
        "\n- Am I charging enough?"
        "\n- What are customers asking for that I don't have?"
        "\n\nOr send a photo of a product and I will tell you whether it is "
        "worth selling."
    )


# Questions that mean "go and look something up" rather than "answer from
# what you know". Matched on the verb because that is what distinguishes
# them: "what should I price this at" uses the shop's own numbers, while
# "what do rivals charge" has to go outside.
RESEARCH_WORDS = (
    "research", "find out", "look up", "search", "competitor", "competitors",
    "rival", "rivals", "market", "trend", "trending", "demand for",
    "who else sells", "what do people", "how much do others",
)


def _wants_research(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in RESEARCH_WORDS)


async def api_research_sources(request):
    """Where the team could look, and where it actually can."""
    if current_account(request) is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    return JSONResponse({
        "sources": [
            {"key": s.key, "name": s.name, "what": s.what,
             "available": s.available, "reason": s.reason,
             "default": s.default}
            for s in research.sources()
        ]
    })


async def api_research(request):
    """Search the chosen places, then have the team read what came back."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, status_code=401)
    session_id = _session_for(account["id"])

    body = await request.json()
    query = str(body.get("query") or "").strip()
    chosen = [str(k) for k in (body.get("sources") or [])]
    if not query:
        return JSONResponse({"error": "research what?"}, status_code=400)
    if not chosen:
        return JSONResponse({"error": "pick at least one place to look"},
                            status_code=400)

    tid = _thread_for(request, account, make=True)
    memory.db.add_message(tid, "user", query)

    def answered(text: str):
        memory.db.add_message(tid, "assistant", text)
        return JSONResponse({"answer": text})

    found = await asyncio.to_thread(research.run, memory.db, query, chosen)

    lines = []
    for key, n in found.per_source.items():
        name = next((s.name for s in research.sources() if s.key == key), key)
        lines.append(f"- **{name}** — {n} result(s)")
    header = (f"I looked in {len(found.per_source)} place(s) for "
              f"“{app_ui.e(query)}”:\n\n" + "\n".join(lines) + "\n\n")

    if not found.findings:
        problems = ("\n\n" + "\n".join(f"- {x}" for x in found.errors)
                    if found.errors else "")
        return answered(header + "Nothing came back." + problems)

    if not settings.has_llm:
        body_text = "\n\n".join(
            f"**{f.title}**\n{f.snippet}" for f in found.findings[:10])
        return JSONResponse({"answer": header + body_text})

    try:
        summary = await asyncio.to_thread(
            _read_research, query, found.as_prompt_context())
    except Exception as exc:  # noqa: BLE001
        from lucida.llm import AllModelsBusy, is_rate_limited
        if isinstance(exc, AllModelsBusy) or is_rate_limited(exc):
            return JSONResponse({"error": str(exc)}, status_code=429)
        summary = "Could not read the results this time."

    problems = ("\n\n_Some places did not answer: "
                + "; ".join(found.errors) + "_") if found.errors else ""
    return answered(header + summary + problems)


def _read_research(query: str, context: str) -> str:
    from lucida.llm import get_llm, text_of

    ask = (
        f"A shop owner asked: {query}\n\n"
        f"Here is what the search returned:\n{context}\n\n"
        "Answer their question from this and nothing else. Say plainly what "
        "the results support and what they do not. If the evidence is thin, "
        "say so rather than filling the gap. Short paragraphs, no preamble, "
        "the way you would tell a shopkeeper across a counter."
    )
    reply = get_llm(settings.model or "", 900).invoke(ask)
    return text_of(reply)


async def api_ask(request):
    """Run one turn of the workforce and return the refreshed snapshot."""
    if not settings.has_llm:
        return JSONResponse(
            {"error": "No API key. Add GROQ_API_KEY to .env and restart."},
            status_code=400,
        )
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)
    session_id = _session_for(account["id"])

    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty message"}, status_code=400)

    # A research question gets a question back: which places to look. The
    # sources answer different things and cost different amounts, so it is
    # the owner's call, not a default.
    if _wants_research(text) and not body.get("sources"):
        return JSONResponse({
            "ask_sources": True,
            "query": text,
            "sources": [
                {"key": s2.key, "name": s2.name, "what": s2.what,
                 "available": s2.available, "reason": s2.reason,
                 "default": s2.default}
                for s2 in research.sources()
            ],
        })

    tid = _thread_for(request, account, make=True)
    memory.db.add_message(tid, "user", text)

    quick = _small_talk_reply(text, account)
    if quick is not None:
        memory.db.add_message(tid, "assistant", quick)
        snap = _snapshot(session_id, account)
        snap["answer"] = quick
        return JSONResponse(snap)

    async with _run_lock:
        try:
            # The graph is synchronous; keep the event loop free while it runs.
            answer = await asyncio.to_thread(
                _drain, session_id, text, [], _owner_context(account))
        except Exception as exc:  # noqa: BLE001 — report, never 500 the page
            logger.error("turn failed: %s", exc)
            bus.emit(session_id, "error", "web", f"turn failed: {exc}",
                     level="error")
            from lucida.llm import AllModelsBusy, is_rate_limited
            if isinstance(exc, AllModelsBusy) or is_rate_limited(exc):
                # Not a failure of the app — say so plainly and give the wait,
                # rather than showing the owner a provider traceback.
                return JSONResponse({"error": str(exc)}, status_code=429)
            return JSONResponse({"error": str(exc)}, status_code=500)

    memory.db.add_message(tid, "assistant", answer)
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
        return JSONResponse({"error": "not signed in"}, 401)
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

    tid = _thread_for(request, account, make=True)
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

    memory.db.add_message(tid, "user", f"[photo: {safe}] {text}")

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


async def api_sale(request):
    """Log a sale.

    This is what turns the headline tiles from dashes into figures: sales
    today, order count, how fast stock moves and days of cover are all
    derived from these rows. Nothing else in the system can invent them.
    """
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)

    body = await request.json()
    product = str(body.get("product") or "").strip()
    if not product:
        return JSONResponse({"error": "which product?"}, status_code=400)
    try:
        quantity = int(body.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    if quantity <= 0:
        return JSONResponse({"error": "how many?"}, status_code=400)

    def _price(key):
        try:
            return float(body[key]) if body.get(key) not in (None, "") else None
        except (TypeError, ValueError):
            return None

    order_id = memory.record_order(
        product_name=product,
        quantity=quantity,
        unit_price=_price("unit_price"),
        unit_cost=_price("unit_cost"),
        channel=str(body.get("channel") or "").strip(),
        customer=str(body.get("customer") or "").strip(),
    )
    logger.info("order logged: %s x%d", product, quantity)

    snap = _snapshot(_session_for(account["id"]), account)
    snap["order_id"] = order_id
    return JSONResponse(snap)


async def api_inbox_sync(request):
    """Pull new customer messages in from every connected platform."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)

    result = await asyncio.to_thread(inbox.sync, memory.db)
    snap = _snapshot(_session_for(account["id"]), account)
    snap["sync"] = {
        "fetched": result.fetched,
        "new": result.stored,
        "simulated": result.simulated,
        "per_platform": result.per_platform,
        "errors": result.errors,
        "detail": result.describe(),
    }
    return JSONResponse(snap)


async def api_reply(request):
    """Answer one customer.

    A comment gets a public reply, a DM a private one — decided by what
    arrived, not by the caller. The message is only marked answered if the
    send actually succeeded, so a failure leaves it visibly outstanding.
    """
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)

    body = await request.json()
    try:
        message_id = int(body.get("message_id") or 0)
    except (TypeError, ValueError):
        message_id = 0
    text = str(body.get("text") or "").strip()
    if not message_id:
        return JSONResponse({"error": "which message?"}, status_code=400)
    if not text:
        return JSONResponse({"error": "nothing to send"}, status_code=400)

    result = await asyncio.to_thread(inbox.reply, memory.db, message_id, text)
    if not result.ok:
        return JSONResponse({"error": result.error or "could not send"},
                            status_code=502)

    snap = _snapshot(_session_for(account["id"]), account)
    snap["reply"] = {
        "sent": True, "simulated": result.simulated,
        "detail": result.describe(),
    }
    return JSONResponse(snap)


async def api_decide(request):
    """Answer the human-in-the-loop gate the graph is suspended on."""
    account = current_account(request)
    if account is None:
        return JSONResponse({"error": "not signed in"}, 401)
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
        "email_configured": mailer.configured(),
        "google_configured": google_oauth.enabled(),
        "verified": auth.is_verified(account) if account else False,
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
        Route("/", chat),
        Route("/chat/new", chat_new),
        Route("/chat/{thread_id:int}", chat_open),
        Route("/chat/{thread_id:int}/delete", chat_delete,
              methods=["POST", "GET"]),
        Route("/studio", studio),
        Route("/connect", connect),
        Route("/connect/{platform}", connect_start),
        Route("/connect/{platform}/save", connect_save,
              methods=["POST"]),
        Route("/connect/{platform}/callback", connect_callback),
        Route("/connect/{platform}/disconnect", connect_forget,
              methods=["POST"]),
        Route("/products", products_page),
        Route("/products/save", product_save, methods=["POST"]),
        Route("/products/{product_id:int}/delete", product_delete,
              methods=["POST"]),
        Route("/delivery", delivery_page),
        Route("/api/delivery/quote", api_delivery_quote,
              methods=["POST"]),
        Route("/api/delivery/book", api_delivery_book,
              methods=["POST"]),
        Route("/favicon.ico", favicon),
        Route("/favicon.svg", favicon),
        Route("/board", board),
        Route("/media/{name}", media),
        Route("/api/studio/generate", api_studio_generate,
              methods=["POST"]),
        Route("/api/studio/upload", api_studio_upload,
              methods=["POST"]),
        Route("/login", login, methods=["GET", "POST"]),
        Route("/signup", signup, methods=["GET", "POST"]),
        Route("/logout", logout, methods=["POST", "GET"]),
        Route("/verify", verify, methods=["GET", "POST"]),
        Route("/verify/resend", verify_resend, methods=["POST"]),
        Route("/auth/google", google_start),
        Route("/auth/google/callback", google_callback),
        Route("/account", account_page, methods=["GET", "POST"]),
        Route("/account/avatar", account_avatar, methods=["POST"]),
        Route("/account/password", account_password, methods=["POST"]),
        Route("/avatar/{account_id}", avatar),
        Route("/api/state", api_state),
        Route("/api/ask", api_ask, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/sale", api_sale, methods=["POST"]),
        Route("/api/research/sources", api_research_sources),
        Route("/api/research", api_research, methods=["POST"]),
        Route("/api/inbox/sync", api_inbox_sync, methods=["POST"]),
        Route("/api/reply", api_reply, methods=["POST"]),
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
    print(f"  email     : {mailer.status()}")
    print(f"  google    : {google_oauth.status()}")
    print(f"  accounts  : {auth.count_accounts()} registered")
    if not settings.has_llm:
        print("  (no API key: the page renders, but the workforce can't run)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
