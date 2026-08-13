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

from aiworkforce.memory.vector import VectorStore, embed  # noqa: E402
from aiworkforce.pricing import CallUsage, UsageLedger, estimate_cost  # noqa: E402
from aiworkforce.tools.code_exec import margin_analysis, run_calculation  # noqa: E402
from aiworkforce.tools.courier import courier  # noqa: E402
from aiworkforce.tools.social import social  # noqa: E402


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
    from aiworkforce.graph import AGENT_NAMES, agent_roster, build_graph

    app = build_graph()
    nodes = set(app.get_graph().nodes)

    assert len(AGENT_NAMES) == 8
    assert "supervisor" in nodes and "finalize" in nodes
    assert set(AGENT_NAMES) <= nodes
    assert len(agent_roster()) == 8


def test_approval_gated_agents_are_declared():
    from aiworkforce.agents import build_agents

    agents = build_agents()
    gated = {n for n, a in agents.items() if a.requires_approval}
    assert gated == {"ad_creative", "delivery"}


def test_every_agent_declares_its_identity():
    from aiworkforce.agents import build_agents

    for name, agent in build_agents().items():
        assert agent.name == name
        assert agent.title and agent.description and agent.tools_used


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
