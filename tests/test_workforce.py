"""Component tests that run without an API key.

Everything here exercises the deterministic parts of the system — sandbox,
memory, RAG, adapters, cost accounting and graph wiring — so a reviewer can
verify the machinery works before spending a token.

Run:  python -m pytest tests -v      (or:  python tests/test_workforce.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))  # `web` lives at the project root

# Before any lucida import: `config` resolves every data path at import time,
# so setting this afterwards has no effect and the suite would read and write
# the developer's own shop.
os.environ.setdefault("LUCIDA_DATA_DIR", tempfile.mkdtemp())

from lucida.memory.vector import VectorStore, embed  # noqa: E402
from lucida.pricing import CallUsage, UsageLedger, estimate_cost  # noqa: E402
from lucida.tools.code_exec import margin_analysis, run_calculation  # noqa: E402
from lucida.tools.courier import courier  # noqa: E402
from lucida.tools.social import social  # noqa: E402


# --- Code execution sandbox ------------------------------------------------


def test_sandbox_runs_pricing_maths():
    result = run_calculation("price = 250\nmargin = price - 100\nprint(margin)")
    assert result.ok
    assert result.variables["margin"] == 150
    assert "150" in result.stdout


def test_sandbox_blocks_imports_and_io():
    for hostile in (
        "import os\nprint(os.getcwd())",
        "open('/etc/passwd').read()",
        "__import__('os').system('dir')",
        "eval('1+1')",
    ):
        result = run_calculation(hostile)
        assert not result.ok, f"sandbox failed to block: {hostile!r}"
        assert "sandbox policy" in result.error


def test_sandbox_contains_runtime_errors():
    result = run_calculation("x = 1 / 0")
    assert not result.ok
    assert "ZeroDivisionError" in result.error


def test_margin_analysis_is_correct():
    m = margin_analysis(unit_cost=100, sell_price=250, fixed_costs=5000,
                        expected_monthly_units=200)
    assert m["unit_margin"] == 150.0
    assert m["margin_pct"] == 60.0
    assert m["breakeven_units"] == 33.3          # 5000 / 150
    assert m["projected_monthly_profit"] == 25000.0  # 150*200 - 5000


def test_margin_analysis_handles_zero_margin():
    m = margin_analysis(unit_cost=100, sell_price=100, fixed_costs=500)
    assert m["unit_margin"] == 0.0
    assert m["breakeven_units"] == -1.0  # sentinel for "never breaks even"


# --- Semantic memory / RAG -------------------------------------------------


def _seeded_store() -> VectorStore:
    store = VectorStore(Path(tempfile.mkdtemp()) / "kb.jsonl")
    store.add(
        "Market research: frozen paratha for working families in Dhaka. "
        "Competitor prices 180-260 BDT. Low competition.",
        {"agent": "market_research", "kind": "market_research"},
    )
    store.add(
        "Pricing decision: sell paratha pack at 220 BDT on 95 BDT cost. "
        "Margin 56.8 percent. Break-even 120 units.",
        {"agent": "pricing", "kind": "pricing"},
    )
    store.add(
        "Customers keep asking for a sugar-free version we do not currently sell.",
        {"agent": "engagement", "kind": "customer_engagement"},
    )
    store.add(
        "Inventory update: 40 paratha packs in stock, reorder level 15.",
        {"agent": "inventory", "kind": "inventory"},
    )
    return store


def test_retrieval_bridges_morphology():
    """The query says 'price'/'decide'; the document says 'Pricing'/'decision'."""
    store = _seeded_store()
    hits = store.search("what price did we decide and why", k=2)
    assert hits, "retrieval returned nothing"
    assert hits[0][0].metadata["agent"] == "pricing"


def test_retrieval_ranks_by_topic():
    store = _seeded_store()
    cases = {
        "which products are running low on stock": "inventory",
        "what are customers asking for that we do not sell": "engagement",
        "is there much competition in this niche": "market_research",
    }
    for query, expected in cases.items():
        hits = store.search(query, k=2)
        assert hits, f"no hits for {query!r}"
        assert hits[0][0].metadata["agent"] == expected, (
            f"{query!r} -> {hits[0][0].metadata['agent']}, expected {expected}"
        )


def test_metadata_filter_scopes_retrieval():
    store = _seeded_store()
    hits = store.search("paratha", k=5, where={"kind": "inventory"})
    assert hits
    assert all(d.metadata["kind"] == "inventory" for d, _ in hits)


def test_embeddings_are_stable_across_processes():
    """CRC32, not Python's per-process randomised hash()."""
    a, b = embed("frozen paratha pack"), embed("frozen paratha pack")
    assert (a == b).all()
    assert abs(float((a * a).sum()) - 1.0) < 1e-5  # L2 normalised


def test_store_survives_reload():
    path = Path(tempfile.mkdtemp()) / "kb.jsonl"
    VectorStore(path).add("Pricing decision: 220 BDT", {"agent": "pricing"})
    reloaded = VectorStore(path)
    assert reloaded.count() == 1
    assert reloaded.search("what price", k=1)


# --- Simulated adapters ----------------------------------------------------


def test_simulated_publish_is_labelled():
    result = social.publish_facebook("Test ad copy")
    assert result.ok and result.simulated
    assert result.external_id
    assert "SIMULATED" in result.describe()


def test_unconnected_channel_invents_no_customers():
    """An unconnected channel must report nothing, not sample people.

    `social_messages` is the shop's real record. Fabricated customers there
    skew the sentiment breakdown, create phantom pre-orders, and end up quoted
    as fact in the owner's report — so "no connection" has to mean "no
    messages", never "here are some plausible ones".
    """
    messages, simulated = social.fetch_messages(limit=10)
    assert messages == []
    assert simulated is True

    from lucida.tools import channels

    for reader in (channels.read_messenger, channels.read_instagram):
        box = reader(10)
        assert box.messages == [], "an unconnected channel fabricated messages"

def test_simulated_courier_returns_full_consignment():
    booking = courier.book(
        "steadfast", "Rifat", "017xxxxxxxx", "Dhanmondi, Dhaka", "Paratha pack", 450
    )
    assert booking.ok and booking.simulated
    assert booking.consignment_id and booking.tracking_code and booking.eta
    assert booking.cod_amount == 450


def test_telegram_offset_advances_and_persists(monkeypatch):
    from lucida.tools import channels

    class DummyDB:
        def __init__(self):
            self._state = {"last_update_id": 10}

        def query(self, sql, params=()):
            if "SELECT last_update_id FROM telegram_sync_state" in sql:
                return [{"last_update_id": self._state["last_update_id"]}]
            return []

        def execute(self, sql, params=()):
            if "INSERT INTO telegram_sync_state" in sql or "UPDATE telegram_sync_state" in sql:
                self._state["last_update_id"] = params[0]
                return 1
            return 0

    db = DummyDB()
    monkeypatch.setattr(channels, "_shop_db", lambda: db)

    calls = {}

    def fake_get(method, params):
        calls[method] = params.copy()
        return {
            "ok": True,
            "result": [{
                "update_id": 11,
                "message": {
                    "message_id": 77,
                    "date": 1720000000,
                    "chat": {"id": 123},
                    "from": {"id": 123, "first_name": "A"},
                    "text": "hello",
                },
            }, {
                "update_id": 12,
                "message": {
                    "message_id": 78,
                    "date": 1720000001,
                    "chat": {"id": 123},
                    "from": {"id": 123, "first_name": "A"},
                    "text": "second message",
                },
            }],
        }, ""

    monkeypatch.setattr(channels, "_telegram_get", fake_get)

    box = channels.read_telegram(25)

    assert box.messages
    assert calls["getUpdates"]["offset"] == 11
    assert db._state["last_update_id"] == 12


def test_unknown_courier_is_rejected():
    booking = courier.book("fedex", "A", "1", "somewhere", "thing", 0)
    assert not booking.ok and "unknown provider" in booking.error


def test_admin_password_comes_from_the_environment(monkeypatch):
    """The admin password is configured, never baked into this source tree.

    It used to be the constant "admin1234", which on a public deploy meant
    anyone who could read the repo had the admin account — and because the
    seeding ran at import, changing it in the UI lasted until the next
    restart and no longer.
    """
    from web import auth

    monkeypatch.setenv("AIW_ADMIN_PASSWORD", "a-configured-admin-password")
    auth.ensure_default_admin()

    admin = auth.authenticate("admin", "a-configured-admin-password")
    assert admin["email"] == "admin"
    assert auth.is_verified(admin)

    with pytest.raises(auth.AuthError):
        auth.authenticate("admin", "admin1234")


def test_no_admin_is_seeded_when_none_is_configured(monkeypatch):
    """A fresh install with nothing declared gets no default way in."""
    from web import auth

    monkeypatch.delenv("AIW_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "DEFAULT_ADMIN_EMAIL", "admin-probe-unseeded")
    auth.ensure_default_admin()

    with pytest.raises(auth.AuthError):
        auth.authenticate("admin-probe-unseeded", "anything at all")


def test_name_is_a_valid_login():
    """Signing in takes a name, not necessarily an email address.

    Nothing is posted to an address any more, so demanding one was a chore
    that bought no safety.
    """
    from web import auth

    for good in ("abha", "abha.shop", "abha_2026", "someone@example.com"):
        assert auth._validate(good, "longenough1") == (good, "longenough1")

    for bad in ("ab", "has space", "no!punct", ""):
        try:
            auth._validate(bad, "longenough1")
        except auth.AuthError:
            pass
        else:
            raise AssertionError(f"{bad!r} should not be a valid login")

    # Password rules are unchanged.
    try:
        auth._validate("abha", "short")
    except auth.AuthError:
        pass
    else:
        raise AssertionError("a short password should still be refused")


def test_new_accounts_need_no_email_verification():
    from web import auth

    assert auth.is_verified({"email_verified": 1})
    assert not auth.is_verified({"email_verified": 0})


def test_the_text_provider_defaults_to_google():
    # The *default*, not whatever this machine's .env happens to say. Reading
    # the live `settings` made this a test of the developer's own config: it
    # passed only while AIW_PROVIDER was google, and failed the moment the
    # provider was legitimately changed.
    import os

    from lucida.config import Settings

    previous = os.environ.pop("AIW_PROVIDER", None)
    try:
        assert Settings().provider == "google"
        os.environ["AIW_PROVIDER"] = "GroQ"
        assert Settings().provider == "groq", "the name is normalised"
    finally:
        os.environ.pop("AIW_PROVIDER", None)
        if previous is not None:
            os.environ["AIW_PROVIDER"] = previous


# --- Cost accounting -------------------------------------------------------


def test_cost_uses_published_rates():
    # Opus 5: $5/1M input, $25/1M output.
    assert abs(estimate_cost("claude-opus-5", 1_000_000, 0) - 5.00) < 1e-9
    assert abs(estimate_cost("claude-opus-5", 0, 1_000_000) - 25.00) < 1e-9
    assert abs(estimate_cost("claude-haiku-4-5", 1_000_000, 0) - 1.00) < 1e-9


def test_cached_tokens_bill_at_reduced_rate():
    full = estimate_cost("claude-opus-5", input_tokens=1_000_000)
    cached = estimate_cost("claude-opus-5", cache_read_tokens=1_000_000)
    assert abs(cached - full * 0.1) < 1e-9


def test_ledger_aggregates_per_agent():
    ledger = UsageLedger()
    ledger.record(CallUsage("pricing", "claude-opus-5", 12_000, 1_500, 8_000))
    ledger.record(CallUsage("pricing", "claude-opus-5", 4_000, 500))
    ledger.record(CallUsage("reporting", "claude-opus-5", 20_000, 3_000))

    by_agent = ledger.by_agent()
    assert by_agent["pricing"]["calls"] == 2
    assert by_agent["pricing"]["input"] == 16_000
    assert ledger.total_tokens == 49_000
    assert ledger.total_cost_usd > 0


# --- Graph wiring ----------------------------------------------------------


def test_graph_has_supervisor_and_eight_specialists():
    from lucida.graph import AGENT_NAMES, agent_roster, build_graph

    app = build_graph()
    nodes = set(app.get_graph().nodes)

    assert len(AGENT_NAMES) == 8
    assert "supervisor" in nodes and "finalize" in nodes
    assert set(AGENT_NAMES) <= nodes
    assert len(agent_roster()) == 8


def test_approval_gated_agents_are_declared():
    from lucida.agents import build_agents

    agents = build_agents()
    gated = {n for n, a in agents.items() if a.requires_approval}
    assert gated == {"ad_creative", "delivery"}


def test_every_agent_declares_its_identity():
    from lucida.agents import build_agents

    for name, agent in build_agents().items():
        assert agent.name == name
        assert agent.title and agent.description and agent.tools_used


# --- Supervisor routing guard (regression) ---------------------------------
#
# A router that re-picks an agent which already succeeded produced an infinite
# loop that only the step limit broke: 20 supervisor calls and 334s for a run
# that should take 25s. The constraint is enforced in code, not just the prompt.


def _state(**over):
    from lucida.state import new_state

    s = new_state("t", "what should I sell?")
    s.update(over)
    return s


def test_completed_agents_are_removed_from_the_allowed_set():
    from lucida.supervisor import supervisor

    state = _state(
        agent_outputs={
            "market_research": {"ok": True, "summary": "done"},
            "pricing": {"ok": True, "summary": "done"},
        },
        completed_agents=["market_research", "pricing"],
    )
    allowed = supervisor._allowed_agents(state)
    assert "market_research" not in allowed
    assert "pricing" not in allowed
    assert "reporting" in allowed


def test_failed_agent_gets_one_retry_then_is_dropped():
    from lucida.supervisor import supervisor

    failed_once = _state(
        agent_outputs={"delivery": {"ok": False, "error": "no address"}},
        completed_agents=["delivery"],
    )
    assert "delivery" in supervisor._allowed_agents(failed_once)

    failed_twice = _state(
        agent_outputs={"delivery": {"ok": False, "error": "no address"}},
        completed_agents=["delivery", "delivery"],
    )
    assert "delivery" not in supervisor._allowed_agents(failed_twice)


def test_product_vision_is_unroutable_without_an_image():
    from lucida.supervisor import supervisor

    assert "product_vision" not in supervisor._allowed_agents(_state(image_paths=[]))
    assert "product_vision" in supervisor._allowed_agents(_state(image_paths=["a.jpg"]))


def test_rerouting_a_completed_agent_falls_forward_to_the_plan():
    from lucida.agents.schemas import RoutingDecision
    from lucida.supervisor import supervisor

    state = _state(
        agent_outputs={"market_research": {"ok": True, "summary": "done"}},
        completed_agents=["market_research"],
        plan=["market_research finds a niche", "reporting writes the summary"],
    )
    bad = RoutingDecision(
        next_agent="market_research", task="again", reason="loop", stage="idea_research"
    )
    fixed = supervisor._enforce(bad, state)
    assert fixed.next_agent == "reporting"


def test_router_finishes_when_every_agent_is_done():
    from lucida.agents.schemas import RoutingDecision
    from lucida.supervisor import supervisor

    state = _state(
        agent_outputs={a: {"ok": True, "summary": "d"} for a in supervisor.ALL_AGENTS},
        completed_agents=list(supervisor.ALL_AGENTS),
    )
    bad = RoutingDecision(
        next_agent="pricing", task="again", reason="loop", stage="reporting"
    )
    assert supervisor._enforce(bad, state).next_agent == "FINISH"


# --- Human-in-the-loop control flow (regression) ---------------------------
#
# `interrupt()` raises GraphInterrupt to suspend the graph. The agent error
# boundary caught it as a failure, silently disabling every approval gate.


def test_graph_interrupt_is_not_swallowed_by_the_error_boundary():
    from lucida.agents.base import _CONTROL_FLOW, AgentResult, BaseAgent

    class Suspending(BaseAgent):
        name = "suspending_test_agent"
        title = "Suspender"
        description = "raises LangGraph control flow"

        def execute(self, state):
            raise _CONTROL_FLOW("suspend")

    class Failing(BaseAgent):
        name = "failing_test_agent"
        title = "Failer"
        description = "raises a real error"

        def execute(self, state):
            raise ValueError("boom")

    # Control flow must propagate so LangGraph can checkpoint and suspend.
    try:
        Suspending()(_state())
    except _CONTROL_FLOW:
        pass
    else:
        raise AssertionError("GraphInterrupt was swallowed — approval gates are dead")

    # A genuine error must still be contained, not crash the run.
    update = Failing()(_state())
    assert update["agent_outputs"]["failing_test_agent"]["ok"] is False
    assert "boom" in update["errors"][0]


def test_approval_writes_are_idempotent_across_interrupt_replay():
    from lucida.memory import memory

    for _ in range(3):
        memory.db.add_approval("replay-test", "publish_ads", "request_changes", "shorter")
    rows = [
        a for a in memory.approvals("replay-test") if a["decision"] == "request_changes"
    ]
    assert len(rows) == 1, f"interrupt replay duplicated the approval row: {len(rows)}"


# --- Provider configuration ------------------------------------------------


def test_provider_defaults_and_vision_gating():
    from lucida.config import PROVIDER_LIMITS, TEXT_DEFAULTS, VISION_DEFAULTS

    for provider, (main, fast) in TEXT_DEFAULTS.items():
        assert main and fast, f"{provider} is missing a model default"
        assert provider in PROVIDER_LIMITS

    # Groq serves no multimodal model — photo understanding must not claim to work.
    assert VISION_DEFAULTS["groq"] == ""
    # Its output budget must stay under the measured 12k tokens/minute cap.
    assert PROVIDER_LIMITS["groq"]["max_tokens"] <= 4000


def test_unknown_provider_fails_loudly():
    from lucida.llm import ProviderError, build_client

    try:
        build_client("not-a-provider", "some-model", 100)
    except ProviderError as exc:
        assert "unknown provider" in str(exc)
    else:
        raise AssertionError("an unknown provider should raise ProviderError")


# --- The shop bot holds a conversation -------------------------------------
#
# Each of these is a thread that used to break. The bot answers one message at
# a time, so the only thing keeping "how much for 2?" and "ok I want it"
# meaningful is what it remembers about the chat they arrived in.


def _shop():
    """A shop with one candle in stock and a courier rate to price against."""
    from lucida.memory.db import Database

    db = Database(Path(tempfile.mkdtemp()) / "shop.db")
    db.upsert_profile(business_name="Noor Candles", location="Dhaka",
                      currency="BDT")
    pid = db.upsert_product("Coconut Soy Candle", sell_price=450,
                            unit_cost=200, weight_g=400)
    db.set_stock(pid, 12)
    db.execute(
        "INSERT INTO delivery_zones (name, kind, provider, base_charge,"
        " per_kg_extra, cod_percent, active) VALUES (?,?,?,?,?,?,1)",
        ("Inside Dhaka", "inside_city", "pathao", 70, 20, 1.0))
    return db


def _say(db, chat, *lines):
    from lucida.tools import shopbot

    replies = [shopbot.answer(db, line, "Rina", chat_id=chat) for line in lines]
    return replies[-1] if len(replies) == 1 else replies


def test_bot_prices_the_quantity_asked_for():
    db = _shop()
    _, reply = _say(db, "c1", "do you have coconut candles?", "how much for 2?")
    assert "900" in reply.text, reply.text
    assert "450" in reply.text  # the unit price is still shown


def test_bot_keeps_the_product_when_the_address_arrives():
    # The bot asked for an address; the reply names no product, but the
    # customer has already said which one. Asking again reads as not listening.
    db = _shop()
    *_, reply = _say(db, "c2", "I want a coconut candle", "ok",
                     "House 7, Road 3, Dhanmondi")
    assert "Coconut Soy Candle" in reply.text, reply.text
    assert "Which one" not in reply.text


def test_a_house_number_is_not_a_quantity():
    # "7 Road 3" is a house, not seven candles: the total must stay at two.
    db = _shop()
    *_, reply = _say(db, "c3", "how much for 2 coconut candles?",
                     "7 Road 3, Dhanmondi")
    assert "900" in reply.text, reply.text
    assert "3,150" not in reply.text  # 7 x 450, the misreading


def test_half_an_address_is_finished_on_the_next_line():
    # The area comes first, the road second. Demanding both on one line asks
    # the same question forever.
    db = _shop()
    *_, reply = _say(db, "c4", "I want a coconut candle", "Dhanmondi",
                     "House 12, Road 5")
    assert "Total" in reply.text, reply.text
    assert "full address" not in reply.text.lower()  # it must not ask again


def test_one_chat_does_not_leak_into_another():
    db = _shop()
    _say(db, "c5", "how much for 2 coconut candles?")
    reply = _say(db, "c6", "how much?")
    assert "900" not in reply.text, reply.text


def test_bot_never_offers_what_is_out_of_stock():
    from lucida.tools import shopbot

    db = _shop()
    pid = db.upsert_product("Lavender Candle", sell_price=520, weight_g=400)
    db.set_stock(pid, 0)
    reply = shopbot.answer(db, "do you have lavender candles?", "Rina",
                           chat_id="c7")
    assert "sold out" in reply.text.lower(), reply.text


# --- Leaving a review ------------------------------------------------------
#
# "/review" is a request to leave one, not the review itself. Filing the
# command as the opinion stored a rating of 0 and a comment of "/review", and
# the words the customer sent next were answered with a price.


def test_review_command_alone_stores_nothing():
    from lucida.tools import shopbot

    db = _shop()
    reply = shopbot.answer(db, "/review", "Rina", chat_id="v1")
    assert "how did we do" in reply.text.lower(), reply.text
    assert shopbot.reviews(db) == []


def test_rating_then_words_make_one_review():
    db = _shop()
    _say(db, "v2", "/review", "5", "great candle, loved the smell")
    stored = _shop_reviews(db)
    assert len(stored) == 1, stored
    assert stored[0]["rating"] == 5
    assert "loved the smell" in stored[0]["comment"]


def test_a_review_on_one_line_is_taken_whole():
    db = _shop()
    _say(db, "v3", "/review 5 stars, lovely candle")
    stored = _shop_reviews(db)
    assert len(stored) == 1, stored
    assert stored[0]["rating"] == 5
    assert "lovely candle" in stored[0]["comment"]
    assert "/review" not in stored[0]["comment"]


def test_a_question_during_a_review_is_still_answered():
    # Waiting for a review must not swallow a real question.
    db = _shop()
    *_, reply = _say(db, "v4", "/review", "how much for 2 coconut candles?")
    assert "900" in reply.text, reply.text
    assert _shop_reviews(db) == []


def _shop_reviews(db):
    from lucida.tools import shopbot

    return shopbot.reviews(db)



# --- One interface, six places ---------------------------------------------
#
# The app used to carry four overlapping UIs. Two were design mockups whose
# buttons were unwired placeholders, and one of those was the first entry in
# the rail — so the most likely first click in the whole app landed on a
# screen where nothing happened. These tests pin the shape that replaced it.


_SIGNUPS = [0]


def _client():
    """The real server, signed in as a shop of this test's own.

    A fresh email per call: two tests sharing one would have the second
    signup rejected, leaving a client that is quietly signed out — and an
    assertion about the rail would then pass against the login page.
    """
    from starlette.testclient import TestClient

    import serve

    _SIGNUPS[0] += 1
    client = TestClient(serve.app)
    landed = client.post("/signup", data={
        "email": f"nav{_SIGNUPS[0]}@example.com", "password": "hunter2hunter2",
        "owner_name": "Rina", "business_name": "Noor Candles",
        "business_stage": "running", "location": "Dhaka",
        "what_you_sell": "candles"}, follow_redirects=True)
    assert landed.url.path == "/", f"signup failed: {landed.url.path}"
    return client


def _nav(html: str) -> list:
    import re

    return re.findall(r"class='nav(?: on)?' href='([^']+)'", html)


def test_every_screen_shows_the_same_six_places():
    client = _client()
    want = ["/", "/chat", "/products", "/customers", "/workforce", "/settings"]
    for path in want:
        page = client.get(path)
        assert page.status_code == 200, (path, page.status_code)
        assert _nav(page.text) == want, (path, _nav(page.text))


def test_no_two_nav_entries_lead_to_the_same_screen():
    # The complaint that started this: several buttons, one destination.
    client = _client()
    seen = {}
    hrefs = _nav(client.get("/").text)
    assert len(hrefs) == 6, hrefs
    for href in hrefs:
        body = client.get(href).text
        title = body.split("<title>")[1].split("</title>")[0]
        assert title not in seen, (title, href, seen.get(title))
        seen[title] = href


def test_the_old_addresses_still_land_somewhere():
    client = _client()
    for old, new in (("/board", "/"), ("/connect", "/settings"),
                     ("/account", "/settings")):
        r = client.get(old, follow_redirects=False)
        assert r.status_code in (301, 302, 303, 307, 308), (old, r.status_code)
        assert r.headers.get("location") == new, (old, r.headers.get("location"))


def test_the_approval_gate_can_actually_be_answered():
    # It could not before: the only card that rendered a gate lived in a
    # mockup, and its buttons were placeholder strings.
    from web import app_ui

    account = {"initials": "R", "business": "Noor Candles"}
    gate = [{"tag": "Delivery", "by": "From your delivery assistant",
             "title": "Send this parcel?", "body": "One candle to Dhanmondi.",
             "yes": "Go ahead", "hint": "Nothing happens until you tap."}]
    html = app_ui.home_page(account, {"line": "One thing needs you."},
                            {}, gate, [], [])
    assert "Send this parcel?" in html
    assert "data-decide='approve'" in html
    assert "data-decide='reject'" in html
    assert "/api/decide" in html


def test_reviews_are_visible_to_the_owner():
    # The bot has always recorded these; nothing ever displayed one.
    from web import app_ui

    html = app_ui.customers_page(
        {"initials": "R"}, [],
        [{"customer": "Rina", "rating": 5, "product_name": "Coconut Soy Candle",
          "comment": "lovely, smells great"}])
    assert "lovely, smells great" in html
    assert "Coconut Soy Candle" in html
    assert "★" in html


def _threads():
    return [
        {"id": "1", "name": "Abha", "initials": "A", "channel": "Telegram",
         "t": "06:47", "state": "Answered", "preview": "coconut candle?",
         "message": "Abha: coconut candle? " * 300},
        {"id": "2", "name": "Rina", "initials": "R", "channel": "Telegram",
         "t": "09:12", "state": "Waiting", "preview": "koto taka?",
         "message": "Rina: koto taka?"},
        {"id": "c9", "name": "Karim", "initials": "K", "channel": "Facebook",
         "t": "10:03", "state": "Answered", "preview": "nice!",
         "message": "nice!"},
    ]


def test_customers_are_listed_one_by_one():
    # Every transcript used to render open, one after another, so finding a
    # person meant scrolling past everybody else's conversation.
    from web import app_ui

    html = app_ui.customers_page({"initials": "E"}, _threads(), [])
    assert html.count("<button class='person'") == 3, "one row per customer"
    assert "3 customers" in html and "1 waiting on you" in html
    for name in ("Abha", "Rina", "Karim"):
        assert name in html


def test_every_customer_shares_one_fixed_conversation_window():
    # The window must not resize or move between customers, however long the
    # thread is — one window, a fixed height, and the transcript scrolls
    # inside it.
    import re

    from web import app_ui

    html = app_ui.customers_page({"initials": "E"}, _threads(), [])
    assert html.count("<div class='window'>") == 1, "exactly one window"
    assert html.count("<div class='pane'") == 3, "one pane per customer"
    height = re.search(r"\.inbox \{[^}]*height:(\S+);", html, re.S)
    assert height and height.group(1).endswith("px"), "the window is fixed"
    assert ".talk { flex:1; min-height:0; overflow-y:auto;" in html


def test_only_a_reply_that_can_be_sent_gets_a_box():
    # A Facebook comment carries a "c" prefix and is answered on the
    # platform; offering a send box that cannot send would be a lie.
    from web import app_ui

    html = app_ui.customers_page({"initials": "E"}, _threads(), [])
    assert html.count("data-reply=") == 2
    assert "r-c9" not in html


def test_the_operator_view_survived_the_merge():
    # Runs, memory and spend used to render only inside the deleted mockup.
    from web import app_ui

    html = app_ui.workforce_page(
        {"initials": "R"}, busy=False,
        ops={"runs": [{"label": "Price the candles", "meta": "3 steps"}],
             "memRecords": [{"key": "Coconut Soy Candle", "value": "450 BDT",
                             "store": "catalog", "by": "Inventory"}],
             "costBars": [{"name": "Pricing", "tok": "1,200",
                           "cost": "$0.0031", "pct": 40}]})
    for marker in ("Recent runs", "What it remembers", "What it cost",
                   "Price the candles", "Coconut Soy Candle", "$0.0031"):
        assert marker in html, marker


def test_only_one_interface_is_left_in_the_tree():
    root = _ROOT
    assert not (root / "app.py").exists(), "the Streamlit app should be gone"
    assert not (root / "ui").exists(), "the Streamlit pages should be gone"
    assert not (root / "web" / "design").exists(), "the mockups should be gone"



# --- The model chain -------------------------------------------------------
#
# Chat stopped answering when one provider ran out of quota, even though the
# owner had a working key for another. Two faults compounded: failover only
# existed for Groq, and only a 429 moved the chain along — a 503 "high demand"
# raised after the SDK had retried it internally for four minutes.


class _Boom(Exception):
    pass


def _fake_client(script):
    """A stand-in whose calls follow `script`: an exception raises, else returns.

    `calls` records the model each attempt was made against, which is what
    separates "retried the same model" from "gave up and used the next one".
    """
    calls = []

    class _C:
        def __init__(self, model=""):
            self.model = model

        def invoke(self, *a, **kw):
            calls.append(self.model)
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step

        def with_structured_output(self, *a, **kw):
            return self

    return _C, calls


def test_a_busy_model_moves_the_chain_along():
    # 503 is not a rate limit and not a retired model, so nothing used to
    # treat it as a reason to try anything else.
    from lucida import llm

    busy = Exception("503 UNAVAILABLE: this model is experiencing high demand")
    assert llm.is_overloaded(busy)
    assert llm.should_try_next(busy)
    assert llm._why(busy) == "is busy"


class _Settings:
    """Just the parts of `settings` the chain reads. `provider` is a computed
    property on the real object, so it cannot simply be assigned."""

    def __init__(self, provider, keys):
        self.provider = provider
        self._keys = keys

    def key_for(self, name):
        return self._keys.get(name, "")


def test_the_chain_leaves_the_provider_it_started_on():
    from lucida import llm

    real = llm.settings
    try:
        llm.settings = _Settings("google", {"google": "g", "groq": "q"})
        chain = llm._chain("gemini-flash-latest")
    finally:
        llm.settings = real
    assert chain[0] == ("google", "gemini-flash-latest"), chain
    assert any(p == "groq" for p, _ in chain), chain
    # Every Groq model is worth trying: the caps are per-model.
    assert sum(1 for p, _ in chain if p == "groq") > 1, chain
    assert not any(p == "anthropic" for p, _ in chain), "no key, no attempt"


def test_one_key_still_gives_the_behaviour_it_always_had():
    from lucida import llm

    real = llm.settings
    try:
        llm.settings = _Settings("google", {"google": "g"})
        chain = llm._chain("gemini-flash-latest")
    finally:
        llm.settings = real
    assert chain == [("google", "gemini-flash-latest")], chain


def test_a_rejected_tool_call_is_retried_on_the_same_model():
    # Groq rejects its own reply when the model writes the JSON as text
    # instead of a tool call. It is intermittent, so it should cost one
    # retry — not the model, and on a short chain not the whole run.
    from lucida import llm

    flaky = Exception("tool_use_failed: model did not call a tool")
    make, calls = _fake_client([flaky, "second time lucky"])
    real = llm.build_client
    try:
        llm.build_client = lambda provider, model, budget: make(model)
        out = llm._Failover([("groq", "m1"), ("groq", "m2")], 100).invoke("hi")
    finally:
        llm.build_client = real
    assert out == "second time lucky"
    assert calls == ["m1", "m1"], f"the retry must stay on m1, got {calls}"


def test_a_capped_model_is_not_retried_but_handed_on():
    from lucida import llm

    capped = Exception("429 rate_limit exceeded")
    make, calls = _fake_client([capped, "from the next model"])
    real = llm.build_client
    try:
        llm.build_client = lambda provider, model, budget: make(model)
        out = llm._Failover([("groq", "m1"), ("groq", "m2")], 100).invoke("hi")
    finally:
        llm.build_client = real
    assert out == "from the next model"
    assert calls == ["m1", "m2"], f"a cap is not retried, got {calls}"


def test_structured_calls_fail_over_the_same_way():
    # This is the path that was actually breaking: every agent asks for
    # structured output, so a chain that only protected plain calls left
    # the whole workforce unprotected.
    from lucida import llm

    make, calls = _fake_client([
        Exception("429 rate_limit exceeded"), {"ok": True}])
    real = llm.build_client
    try:
        llm.build_client = lambda provider, model, budget: make(model)
        got = (llm._Failover([("google", "g"), ("groq", "q")], 100)
               .with_structured_output(dict).invoke("hi"))
    finally:
        llm.build_client = real
    assert got == {"ok": True}
    assert calls == ["g", "q"], f"it must cross providers, got {calls}"


def test_a_real_error_is_raised_rather_than_hidden():
    # A bad key or a malformed request is not a reason to try four more
    # models and then report that everything is rationed.
    from lucida import llm

    make, calls = _fake_client([_Boom("invalid api key")])
    real = llm.build_client
    try:
        llm.build_client = lambda provider, model, budget: make(model)
        try:
            llm._Failover([("groq", "m1"), ("groq", "m2")], 100).invoke("hi")
        except _Boom:
            pass
        else:
            raise AssertionError("the real error should surface")
    finally:
        llm.build_client = real
    assert len(calls) == 1, "it should not have walked the chain"



# --- What the bot promises the shelf can keep ------------------------------


def test_the_bot_hears_how_many_they_asked_for():
    # "i want 5" read as one. A bare number mid-sentence is usually a house
    # number, so it takes a verb to mark it as a count — and those verbs
    # were missing.
    from lucida.tools import shopbot

    for line, want in (("i want 5", 5), ("give me 3", 3), ("i need 2", 2),
                       ("amar 4 ta lagbe", 4), ("send me 6", 6),
                       ("how much for 2", 2), ("3 pcs", 3), ("x2", 2)):
        assert shopbot._qty_in(line) == want, (line, shopbot._qty_in(line))


def test_a_house_number_is_still_not_a_count():
    from lucida.tools import shopbot

    for line in ("House 12, Road 5, Dhanmondi", "flat 9 block c"):
        assert shopbot._qty_in(line) == 1, line


def test_the_bot_will_not_promise_more_than_it_has():
    # The one mistake a customer travels for.
    db = _shop()
    reply = _say(db, "s1", "i want 50 coconut soy candles")
    assert "only have 12" in reply.text, reply.text
    assert "Would you like 12" in reply.text
    assert reply.intent == "availability"
    # And it must not have gone on to ask for an address.
    assert "address" not in reply.text.lower()


def test_accepting_the_amount_it_does_have_carries_through():
    db = _shop()
    *_, reply = _say(db, "s2", "i want 50 coconut soy candles", "yes")
    assert "12 x Coconut Soy Candle" in reply.text, reply.text
    assert "address" in reply.text.lower()


def test_a_sold_out_item_is_not_taken_as_an_order():
    from lucida.memory.db import Database

    db = _shop()
    pid = db.upsert_product("Lavender Candle", sell_price=520, weight_g=400)
    db.set_stock(pid, 0)
    reply = _say(db, "s3", "i want 2 lavender candles")
    assert "sold out" in reply.text.lower(), reply.text


def test_the_total_uses_the_amount_the_shelf_allowed():
    db = _shop()
    *_, reply = _say(db, "s4", "i want 50 coconut soy candles", "yes",
                     "House 12, Road 5, Dhanmondi")
    # 12 at 450, not 50 at 450.
    assert "5,400" in reply.text, reply.text
    assert "22,500" not in reply.text


# --- Two messages inside one poll ------------------------------------------


def _telegram_shop(monkey):
    """A shop whose bot can 'send', so auto_answer runs end to end."""
    from lucida.tools import channels

    sent = []

    class _Result:
        ok, error, simulated = True, "", False

        def describe(self):
            return "ok"

    monkey.append((channels, "telegram_ready", channels.telegram_ready))
    monkey.append((channels, "send_telegram", channels.send_telegram))
    channels.telegram_ready = lambda: True
    channels.send_telegram = lambda cid, text, buttons=None: (
        sent.append((cid, text, buttons)) or _Result())
    return _shop(), sent


def test_a_review_split_over_two_messages_survives_one_poll():
    # The poll runs every ten seconds. "/review" and the rating land in the
    # same batch, and the older message used to be discarded unread — so the
    # shop never started waiting for a review and the rating was answered
    # with a price.
    from lucida.tools import inbox, shopbot

    undo = []
    try:
        db, sent = _telegram_shop(undo)
        for text in ("/review", "5 lovely candle, smells great"):
            db.execute(
                "INSERT INTO social_messages (platform, kind, thread_id,"
                " sender_id, sender_name, message, received_at, replied)"
                " VALUES (?,?,?,?,?,?,?,0)",
                ("telegram", "dm", "77", "77", "Abha", text,
                 "2026-08-27T10:00:00"))
        inbox.auto_answer(db)

        stored = shopbot.reviews(db)
        assert len(stored) == 1, stored
        assert stored[0]["rating"] == 5, stored
        assert "lovely candle" in stored[0]["comment"], stored
        # One person, one reply — reading both did not mean answering twice.
        assert len(sent) == 1, sent
        assert "thank you" in sent[0][1].lower(), sent
    finally:
        for obj, name, original in undo:
            setattr(obj, name, original)


def test_every_message_in_a_batch_is_settled():
    # Nothing may be left looking unanswered in the owner's inbox.
    from lucida.tools import inbox

    undo = []
    try:
        db, _ = _telegram_shop(undo)
        for text in ("hi", "hello", "you there?"):
            db.execute(
                "INSERT INTO social_messages (platform, kind, thread_id,"
                " sender_id, sender_name, message, received_at, replied)"
                " VALUES (?,?,?,?,?,?,?,0)",
                ("telegram", "dm", "78", "78", "Abha", text,
                 "2026-08-27T10:00:00"))
        inbox.auto_answer(db)
        left = db.query("SELECT COUNT(*) AS n FROM social_messages"
                        " WHERE replied=0")
        assert left[0]["n"] == 0, left
    finally:
        for obj, name, original in undo:
            setattr(obj, name, original)



class _VisionSettings:
    """The parts of `settings` the vision and fast chains read."""

    provider = "groq"
    model = "openai/gpt-oss-120b"
    fast_model = "openai/gpt-oss-20b"
    vision_provider = "google"
    vision_model = "gemini-flash-latest"
    max_tokens = 1000
    has_vision = True
    vision_help = ""

    def __init__(self, keys):
        self._keys = keys

    def key_for(self, name):
        return self._keys.get(name, "")


def test_photo_understanding_can_move_to_a_second_provider():
    # Groq serves no multimodal model, so photos land on Google — whose free
    # tier is twenty requests a day. This was the last call in the app that
    # could not move to a second model, so running that quota out handed the
    # owner the provider's own 429 traceback.
    from lucida import llm

    real = llm.settings
    try:
        llm.settings = _VisionSettings({"google": "g", "groq": "q"})
        assert llm._vision_chain() == [("google", "gemini-flash-latest")]

        llm.settings = _VisionSettings({"google": "g", "anthropic": "a"})
        chain = llm._vision_chain()
        assert chain[0] == ("google", "gemini-flash-latest"), chain
        assert any(p == "anthropic" for p, _ in chain), chain

        # And the client the vision agent is handed must actually use it.
        client = llm.get_vision_llm(200)
        assert isinstance(client, llm._Failover), type(client)
        assert client._models == chain, client._models
    finally:
        llm.settings = real


def test_the_routing_client_fails_over_too():
    from lucida import llm

    real = llm.settings
    try:
        llm.settings = _VisionSettings({"groq": "q", "google": "g"})
        client = llm.get_fast_llm(200)
    finally:
        llm.settings = real
    # Not a bare provider client: it has somewhere to go.
    assert isinstance(client, llm._Failover)
    assert len(client._models) > 1


def test_an_exhausted_quota_reads_as_english_not_a_traceback():
    from lucida import llm

    make, calls = _fake_client([
        Exception("429 RESOURCE_EXHAUSTED quota exceeded"),
        Exception("429 RESOURCE_EXHAUSTED quota exceeded")])
    real = llm.build_client
    try:
        llm.build_client = lambda provider, model, budget: make(model)
        try:
            llm._Failover([("google", "gemini-flash-latest"),
                           ("anthropic", "claude-opus-5")], 100).invoke("hi")
        except llm.AllModelsBusy as exc:
            assert "over its cap" in str(exc), exc
            assert "Nothing is broken" in str(exc), exc
        else:
            raise AssertionError("it should report every model as busy")
    finally:
        llm.build_client = real
    assert calls == ["gemini-flash-latest", "claude-opus-5"], calls



# --- Busy, paused, and wrecked are three different things ------------------
#
# `is_running` used to ask the checkpoint whether it had a next node. A run
# suspended for an approval keeps one, and so does a run that died mid-flight
# — so after a crash the session read as "working" for ever, the owner was
# told "your team is already working", and nothing on the screen could clear
# it. That is a lock-out, not a status.


def _runtime():
    from lucida.graph import WorkforceRuntime

    return WorkforceRuntime()


def test_a_session_nobody_is_working_on_is_not_running():
    rt = _runtime()
    assert not rt.is_running(rt.new_session_id())


def test_a_crashed_run_releases_the_session():
    # The exact shape of the lock-out: the graph blows up mid-run, and the
    # owner must still be able to hand out the next job.
    rt = _runtime()
    session = "sess-crash-test"

    def explode(*args, **kwargs):
        raise RuntimeError("the provider ran out of quota mid-run")

    class _Wreckage:
        # What LangGraph leaves behind: the node it never got to run.
        next = ("supervisor",)

    rt.app.stream = explode
    out = list(rt._stream({}, session))
    rt.snapshot = lambda sid: _Wreckage()

    assert any(o.get("node") == "__error__" for o in out), out
    assert rt.is_suspended(session), "the checkpoint keeps the pending node"
    assert not rt.is_running(session), "a dead run must not hold the session"
    assert not rt.pending_approval(session), "and it is not a gate either"


def test_a_finished_run_releases_the_session():
    rt = _runtime()
    session = "sess-done-test"

    rt.app.stream = lambda *a, **k: iter(())
    list(rt._stream({}, session))
    assert not rt.is_running(session)


def test_a_run_holds_the_session_only_while_it_streams():
    rt = _runtime()
    session = "sess-live-test"
    seen = []

    def one_chunk(*args, **kwargs):
        yield {"supervisor": {"ok": True}}

    rt.app.stream = one_chunk
    for _ in rt._stream({}, session):
        seen.append(rt.is_running(session))

    assert seen and all(seen), "it should read as running while it streams"
    assert not rt.is_running(session), "and stop the moment it is done"


def test_suspended_is_asked_of_the_checkpoint_not_the_marker():
    # The two answers must be able to disagree: that disagreement is what
    # separates a paused graph from a busy one.
    rt = _runtime()
    session = "sess-suspend-test"

    class _Snap:
        next = ("supervisor",)

    rt.snapshot = lambda sid: _Snap()
    assert rt.is_suspended(session), "the checkpoint still holds work"
    assert not rt.is_running(session), "but nobody is working on it"



# --- Leaving a review by tapping a star ------------------------------------
#
# "/review doesn't work" survived two fixes to the bot, because the bot was
# never the problem: read_telegram dropped every message beginning with "/"
# as Telegram protocol chatter, so the command was thrown away before the
# shop ever saw it.


def _telegram_updates(updates, answered=None):
    """Point channels at a fixed set of updates instead of the network."""
    from lucida.tools import channels

    def fake_get(method, params):
        if method == "answerCallbackQuery":
            if answered is not None:
                answered.append(params.get("callback_query_id"))
            return {"ok": True, "result": True}, ""
        return {"ok": True, "result": updates}, ""

    return fake_get


def _message(uid, text, chat=551):
    return {"update_id": uid, "message": {
        "message_id": uid, "date": 1756000000, "text": text,
        "from": {"id": chat, "first_name": "Karim", "is_bot": False},
        "chat": {"id": chat}}}


def test_the_commands_the_shop_answers_are_not_thrown_away():
    from lucida.tools import channels

    ready, get = channels.telegram_ready, channels._telegram_get
    try:
        channels.telegram_ready = lambda: True
        channels._telegram_get = _telegram_updates([
            _message(1, "hello"),
            _message(2, "/review"),
            _message(3, "/start"),
            _message(4, "/settings"),   # Telegram's own, not the customer's
        ])
        read = channels.read_telegram(db=_shop())
    finally:
        channels.telegram_ready, channels._telegram_get = ready, get

    said = [m["message"] for m in read.messages]
    assert "/review" in said, said
    assert "/start" in said, said
    assert "/settings" not in said, "protocol chatter should still be dropped"


def test_a_tapped_button_arrives_as_what_it_meant():
    from lucida.tools import channels

    answered = []
    ready, get = channels.telegram_ready, channels._telegram_get
    try:
        channels.telegram_ready = lambda: True
        channels._telegram_get = _telegram_updates([{
            "update_id": 9, "callback_query": {
                "id": "cb-99", "data": "/rate 4",
                "from": {"id": 551, "first_name": "Karim"},
                "message": {"chat": {"id": 551}}}}], answered)
        read = channels.read_telegram(db=_shop())
    finally:
        channels.telegram_ready, channels._telegram_get = ready, get

    assert [m["message"] for m in read.messages] == ["/rate 4"]
    assert read.messages[0]["sender_id"] == "551"
    # A button that keeps spinning reads as a shop that missed the tap.
    assert answered == ["cb-99"], answered


def test_review_offers_stars_to_tap():
    from lucida.tools import shopbot

    db = _shop()
    reply = shopbot.answer(db, "/review", "Karim", chat_id="rv1")
    assert reply.buttons, "a rating is a thing to pick, not to spell"
    labels = [label for label, _ in reply.buttons[0]]
    payloads = [data for _, data in reply.buttons[0]]
    assert len(labels) == 5, labels
    assert payloads == [f"/rate {n}" for n in range(1, 6)], payloads


def test_a_tapped_star_and_the_words_make_one_review():
    from lucida.tools import shopbot

    db = _shop()
    _say(db, "rv2", "do you have coconut soy candles?", "/review", "/rate 4",
         "lovely smell, delivery was quick")

    stored = shopbot.reviews(db)
    assert len(stored) == 1, stored
    assert stored[0]["rating"] == 4, stored
    assert "lovely smell" in stored[0]["comment"], stored
    # The product under discussion is recorded with it.
    assert stored[0]["product_name"] == "Coconut Soy Candle", stored


def test_the_answer_to_our_own_question_is_not_reread_as_a_question():
    # "delivery was quick" is a review that mentions delivery, not a delivery
    # enquiry — and the shop had just asked what made it that score.
    from lucida.tools import shopbot

    db = _shop()
    *_, reply = _say(db, "rv3", "/review", "/rate 5",
                     "delivery was quick and the price is good")
    assert "thank you" in reply.text.lower(), reply.text
    assert shopbot.reviews(db)[0]["comment"].startswith("delivery was quick")


def test_a_typed_rating_still_works():
    # Not everyone taps. The old path must survive.
    from lucida.tools import shopbot

    db = _shop()
    _say(db, "rv4", "/review", "5 khub bhalo")
    stored = shopbot.reviews(db)
    assert len(stored) == 1 and stored[0]["rating"] == 5, stored
    assert "khub bhalo" in stored[0]["comment"], stored


def test_the_stars_reach_the_customer():
    # The buttons are useless unless auto_answer hands them to the sender.
    from lucida.tools import channels, inbox

    sent = []
    ready, send = channels.telegram_ready, channels.send_telegram
    try:
        channels.telegram_ready = lambda: True

        class _Ok:
            ok, error, simulated = True, "", False

            def describe(self):
                return "ok"

        def fake_send(chat_id, text, buttons=None):
            sent.append((text, buttons))
            return _Ok()

        channels.send_telegram = fake_send
        db = _shop()
        db.execute(
            "INSERT INTO social_messages (platform, kind, thread_id, sender_id,"
            " sender_name, message, received_at, replied)"
            " VALUES (?,?,?,?,?,?,?,0)",
            ("telegram", "dm", "808", "808", "Karim", "/review",
             "2026-08-27T10:00:00"))
        inbox.auto_answer(db)
    finally:
        channels.telegram_ready, channels.send_telegram = ready, send

    assert sent, "the shop should have replied"
    text, buttons = sent[-1]
    assert buttons, "the star keyboard must travel with the reply"
    assert len(buttons[0]) == 5, buttons


def test_a_quota_error_never_reaches_the_owner_raw():
    # The exact error that kept coming back, with google as the primary
    # provider. It must be absorbed by the chain, whatever the provider is.
    from lucida import llm

    quota = Exception(
        "Error calling model 'gemini-flash-latest' (RESOURCE_EXHAUSTED): "
        "429 RESOURCE_EXHAUSTED quota exceeded")

    class _Primary:
        provider = "google"
        model = "gemini-flash-latest"
        fast_model = "gemini-flash-lite-latest"
        vision_provider = "google"
        vision_model = "gemini-flash-latest"
        max_tokens = 1000
        has_vision = True
        vision_help = ""

        def key_for(self, name):
            return {"google": "g", "groq": "q"}.get(name, "")

    def fake(provider, model, budget):
        class _C:
            def invoke(self, *a, **k):
                if provider == "google":
                    raise quota
                return type("R", (), {"content": "answered by " + model})()

            def with_structured_output(self, *a, **k):
                return self

        return _C()

    settings_was, build_was = llm.settings, llm.build_client
    try:
        llm.settings = _Primary()
        llm.build_client = fake
        out = llm.get_llm().invoke("hi")
    finally:
        llm.settings, llm.build_client = settings_was, build_was

    assert "answered by" in out.content, out.content


def test_health_reports_the_models_this_process_will_use():
    # Config is read once at import, so a server started before an .env edit
    # keeps the old answer. Without this, the only way to find out what a
    # running process was calling was to make it fail and read the traceback.
    client = _client()
    body = client.get("/api/health").json()

    assert body["text_chain"], body
    assert body["vision_chain"], body
    assert all("/" in entry for entry in body["text_chain"]), body


if __name__ == "__main__":
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
