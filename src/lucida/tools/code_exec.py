"""Restricted Python execution for pricing, margin and break-even maths.

The Pricing & Cost agent writes real Python rather than doing arithmetic in
prose, so the numbers in a business plan are computed and reproducible. The
sandbox is deliberately narrow: no imports beyond a maths whitelist, no
filesystem, no network, no dunder access, and a wall-clock timeout.

This is a defence-in-depth measure for *our own* agent's generated code, not a
general-purpose sandbox for untrusted third-party input.
"""

from __future__ import annotations

import io
import math
import re
import statistics
import threading
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any

from ..observability import get_logger

logger = get_logger("tools.code_exec")

_TIMEOUT_SECONDS = 10.0

# Patterns that indicate the generated code is reaching outside the sandbox.
_FORBIDDEN = re.compile(
    r"(^|\W)(import\s+(?!math|statistics)|__\w+__|open\s*\(|exec\s*\(|eval\s*\("
    r"|compile\s*\(|globals\s*\(|locals\s*\(|getattr\s*\(|setattr\s*\("
    r"|subprocess|socket|shutil|pathlib|requests|os\.)",
)

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict,
    "divmod": divmod, "enumerate": enumerate, "filter": filter, "float": float,
    "int": int, "len": len, "list": list, "map": map, "max": max, "min": min,
    "pow": pow, "print": print, "range": range, "round": round, "sorted": sorted,
    "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "True": True, "False": False, "None": None,
}


@dataclass
class ExecResult:
    ok: bool
    stdout: str
    variables: dict[str, Any]
    error: str = ""

    def summary(self) -> str:
        if not self.ok:
            return f"Calculation failed: {self.error}"
        body = self.stdout.strip()
        if self.variables:
            kv = ", ".join(f"{k}={v}" for k, v in list(self.variables.items())[:12])
            body = f"{body}\n[computed: {kv}]" if body else f"[computed: {kv}]"
        return body or "(no output)"


def _looks_unsafe(code: str) -> str:
    match = _FORBIDDEN.search(code)
    return match.group(0).strip() if match else ""


def run_calculation(code: str, inputs: dict[str, Any] | None = None) -> ExecResult:
    """Execute a short pricing/margin script and return its output and results.

    Any variable the script assigns whose name doesn't start with `_` is
    returned, so the agent can pull out `margin_pct`, `breakeven_units`, etc.
    """
    code = (code or "").strip()
    if not code:
        return ExecResult(False, "", {}, "empty code block")

    offender = _looks_unsafe(code)
    if offender:
        logger.warning("rejected sandboxed code containing %r", offender)
        return ExecResult(
            False, "", {}, f"blocked by sandbox policy: {offender!r} is not permitted"
        )

    namespace: dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "math": math,
        "statistics": statistics,
        **(inputs or {}),
    }
    buffer = io.StringIO()
    outcome: dict[str, Any] = {"error": None}

    def _target() -> None:
        try:
            with redirect_stdout(buffer):
                exec(code, namespace)  # noqa: S102 — restricted namespace, see module docstring
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(_TIMEOUT_SECONDS)

    if thread.is_alive():
        # The thread is daemonised, so it dies with the process; we just stop waiting.
        return ExecResult(
            False, buffer.getvalue(), {}, f"timed out after {_TIMEOUT_SECONDS:.0f}s"
        )

    if outcome["error"]:
        return ExecResult(False, buffer.getvalue(), {}, str(outcome["error"]))

    results = {
        k: v
        for k, v in namespace.items()
        if not k.startswith("_")
        and k not in {"math", "statistics"}
        and isinstance(v, (int, float, str, bool, list, dict, tuple))
    }
    logger.info("sandbox run ok, %d result variables", len(results))
    return ExecResult(True, buffer.getvalue(), results)


def margin_analysis(
    unit_cost: float,
    sell_price: float,
    fixed_costs: float = 0.0,
    expected_monthly_units: int = 0,
) -> dict[str, float]:
    """Deterministic core metrics, computed in Python rather than by the model."""
    unit_cost = max(0.0, float(unit_cost))
    sell_price = max(0.0, float(sell_price))
    unit_margin = sell_price - unit_cost
    margin_pct = (unit_margin / sell_price * 100) if sell_price else 0.0
    markup_pct = (unit_margin / unit_cost * 100) if unit_cost else 0.0
    breakeven_units = (fixed_costs / unit_margin) if unit_margin > 0 else float("inf")
    monthly_profit = unit_margin * expected_monthly_units - fixed_costs
    return {
        "unit_cost": round(unit_cost, 2),
        "sell_price": round(sell_price, 2),
        "unit_margin": round(unit_margin, 2),
        "margin_pct": round(margin_pct, 2),
        "markup_pct": round(markup_pct, 2),
        "breakeven_units": (
            round(breakeven_units, 1) if breakeven_units != float("inf") else -1.0
        ),
        "projected_monthly_profit": round(monthly_profit, 2),
    }
