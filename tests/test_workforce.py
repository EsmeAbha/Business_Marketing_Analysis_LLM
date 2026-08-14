"""Component tests that run without an API key.

Everything here exercises the deterministic parts of the system — sandbox,
memory, RAG, adapters, cost accounting and graph wiring — so a reviewer can
verify the machinery works before spending a token.

Run:  python -m pytest tests -v      (or:  python tests/test_workforce.py)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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


def test_simulated_inbox_covers_every_intent():
    messages, simulated = social.fetch_messages(limit=10)
    assert simulated and len(messages) == 10
    assert all({"channel", "customer", "message"} <= set(m) for m in messages)
    assert {m["channel"] for m in messages} == {"messenger", "instagram", "comment"}


def test_simulated_courier_returns_full_consignment():
    booking = courier.book(
        "steadfast", "Rifat", "017xxxxxxxx", "Dhanmondi, Dhaka", "Paratha pack", 450
    )
    assert booking.ok and booking.simulated
    assert booking.consignment_id and booking.tracking_code and booking.eta
    assert booking.cod_amount == 450


def test_unknown_courier_is_rejected():
    booking = courier.book("fedex", "A", "1", "somewhere", "thing", 0)
    assert not booking.ok and "unknown provider" in booking.error


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
