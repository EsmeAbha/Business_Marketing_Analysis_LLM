"""Patch the design bundle so it can be served by Lucida, without redrawing it.

Two edits, both additive — the design's own markup, styling and view-model
logic are left exactly as authored:

1. `window.__resources` maps the runtime's CDN URLs onto vendored copies, so
   React/ReactDOM/Babel load from disk and the page works offline. This is the
   runtime's own documented override hook (`cdnScriptFor`), not a hack.

2. Each data constant the backend can fill is wrapped so it prefers
   `window.LUCIDA.<key>` when the server injected a non-empty value, and keeps
   the design's original literal otherwise. That way an empty database still
   renders the design exactly as drawn, and real data replaces it in place.

Run:  python web/patch_design.py
"""

from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
INDEX = HERE / "design" / "index.html"

# design constant -> key on window.LUCIDA
OVERRIDES = {
    "DECISIONS": "decisions",
    "OVERNIGHT": "overnight",
    "THREADS": "threads",
    "STOCK": "stock",
    "CAMPAIGNS": "campaigns",
    # CREATIVES is intentionally absent: each entry drives an <image-slot>
    # keyed to a design asset id, and Lucida's ad copy carries no imagery.
    # Overriding it would leave empty picture frames where the design shows
    # finished creative.
    # COST_ROWS is intentionally absent: it is the design's per-ingredient
    # cost breakdown, which this backend does not record. It keeps the
    # design's own example rather than being filled with unrelated data.
    "COST_BARS": "costBars",
    "PNL": "pnl",
    "DEMANDS": "demands",
    "HISTORY": "history",
    "CHANNELS": "channels",
    "ROSTER": "roster",
    "RUNS": "runs",
    "MEM_RECORDS": "memRecords",
    "FAILURES": "failures",
}

RESOURCES = """<script>
/* Injected by Lucida — map the dc-runtime's CDN URLs onto vendored copies.
   `cdnScriptFor()` in support.js consults window.__resources first, so this
   keeps the page fully offline without touching the runtime. */
window.__resources = {
  "https://unpkg.com/react@18.3.1/umd/react.production.min.js":
      "./vendor/react.production.min.js",
  "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js":
      "./vendor/react-dom.production.min.js",
  "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js":
      "./vendor/babel.min.js"
};
window.LUCIDA = window.LUCIDA || {};
</script>
<script src="./lucida-actions.js"></script>
<style id="lucida-layout">
/* The design caps each section panel with `max-width` but leaves it
   left-aligned, which was fine at its authored 1180px but strands a wide
   empty gutter on a larger monitor. Centring the capped panels inside the
   content column fixes that without altering any of the design's own
   measurements — the panel keeps its exact width, it is just no longer
   pinned to the left edge. */
[style*="max-width: 1120px"],
[style*="max-width: 1180px"],
[style*="max-width: 1060px"],
[style*="max-width: 1000px"] {
  margin-left: auto !important;
  margin-right: auto !important;
}

</style>
"""

# The palette. The design was drawn in deep green on warm paper; this recasts
# it as coffee and cream with maroon red as the one accent, black for type and
# white used sparingly.
#
# Applied to the whole bundle — markup and view model alike — as a literal
# colour-for-colour substitution. Replacing at source rather than overriding in
# CSS means there is no cascade to lose against inline styles, and no colour
# can survive in a code path that happens not to be exercised yet.
#
#   cream   dominant surface and ground
#   coffee  body copy, muted labels, borders, dividers
#   black   headings
#   maroon  the accent — brand, actions, active state
#   white   used only where a card must lift off the cream
#
# Green is gone entirely: every one of its shades maps onto maroon.
PALETTE = {
    # --- brand green -> maroon red -------------------------------------
    "#14603F": "#7B1E22",   # accent
    "#0E4A30": "#5E1519",   # accent, pressed
    "#EAF1EC": "#F3E2E1",   # accent wash
    "#CFE0D5": "#E4C9C8",   # accent edge
    "#9EB3A4": "#B79E86",   # muted accent -> coffee
    "#F4F8F5": "#FAF3E7",   # palest accent -> cream

    # --- greys with a green cast -> coffee ------------------------------
    "#7C877F": "#8A7563",   # muted labels
    "#4A554E": "#4A3728",   # body copy
    "#18211D": "#17120F",   # headings -> black
    "#A19B8E": "#A89680",   # faint

    # --- paper -> cream --------------------------------------------------
    "#F7F5F0": "#F4EADA",   # ground
    "#FBFAF7": "#FAF3E7",   # rail, table headers
    "#F1EEE6": "#EFE2CE",   # sunken wells
    "#F5F2EA": "#F2E6D4",
    "#FFFFFF": "#FDFAF4",   # card surface — near-white, so white stays rare

    # --- hairlines -> coffee ---------------------------------------------
    "#E5E0D6": "#DDCDB4",
    "#EFEBE1": "#E7DAC4",
    "#DCD3BE": "#D6C4A8",
    "#DDD8CC": "#D2BFA4",
    "#C9C3B4": "#CBB99E",
    "#E1DCD1": "#DCCBB2",
    "#DFDACE": "#DACAB0",
    "#CFC8B8": "#C7B499",

    # --- accents borrowed from other brands -> palette --------------------
    "#5B4B9B": "#6B4F3A",   # store label (purple)
    "#EDEAF6": "#EFE2CE",
    "#1F6470": "#4A3728",   # store label (teal)
    "#E8F1F2": "#EFE2CE",
    "#A6377C": "#7B1E22",   # Instagram magenta
    "#2B5C9B": "#6B4F3A",   # Facebook blue

    # Amber and the danger reds already sit in the coffee family, so they
    # stay: #B4741B, #FBF1E1, #F0DFC2, #A63A2E, #F8E9E6, #F0DAD6, #EBDCC2,
    # #F4EFE2.
}

# Handler rebinds: give the design's own controls real effects. Each entry is
# (exact source fragment, replacement). The markup is never touched — only what
# the existing bindings do when clicked.
HANDLERS = [
    (
        # The Ask button navigates to Grow in the prototype; make it put the
        # question to the actual workforce instead.
        "goGrow: () => this.go('grow')",
        "goGrow: () => window.LucidaActions.ask(this.state.ask)",
    ),
    (
        # Route a real suspended gate to the server. LucidaActions.decide()
        # returns false for the design's sample decisions, which then keep
        # their original local behaviour so the prototype still demonstrates.
        "  decide(id, choice) {\n",
        "  decide(id, choice) {\n"
        "    if (window.LucidaActions && window.LucidaActions.decide(id, choice)) return;\n",
    ),
    # Real runs are keyed by session id, not the design's 'r1'. Three
    # RUNS.find() calls have no fallback and would throw on a stale id; the
    # design already guards the fourth this exact way.
    (
        "const run = RUNS.find(r => r.id === s.run);",
        "const run = RUNS.find(r => r.id === s.run) || RUNS[0];",
    ),
    (
        "const run = RUNS.find(r => r.id === this.state.run);",
        "const run = RUNS.find(r => r.id === this.state.run) || RUNS[0];",
    ),
    (
        "const s = this.state, run = RUNS.find(r => r.id === s.run);",
        "const s = this.state, run = RUNS.find(r => r.id === s.run) || RUNS[0];",
    ),
    # With no runs at all, RUNS[0] is undefined too — bail out rather than
    # dereference it while the player ticks.
    (
        "  schedule() {\n    clearTimeout(this.timer);\n",
        "  schedule() {\n    clearTimeout(this.timer);\n"
        "    if (!RUNS.length) return;\n",
    ),
]


def _match_bracket(text: str, start: int) -> int:
    """Index just past the bracket group that opens at `start`.

    Walks the source tracking strings and escapes, because the design's data
    literals contain both brackets and apostrophes inside quoted Bangla text.
    """
    opener = text[start]
    closer = {"[": "]", "{": "}"}[opener]
    depth = 0
    quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "'\"`":
            quote = ch
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError(f"unbalanced bracket from offset {start}")


def patch(src: str) -> tuple[str, list[str], list[str]]:
    done: list[str] = []
    missed: list[str] = []

    for const, key in OVERRIDES.items():
        if f"window.LUCIDA.{key}" in src:
            done.append(f"{const} (already)")
            continue
        m = re.search(rf"^const {const} = (?=[\[{{])", src, re.M)
        if not m:
            missed.append(const)
            continue
        open_at = m.end()
        close_at = _match_bracket(src, open_at)
        literal = src[open_at:close_at]
        replacement = (
            f"const {const} = (window.LUCIDA && window.LUCIDA.{key} "
            f"&& window.LUCIDA.{key}.length ? window.LUCIDA.{key} : {literal})"
        )
        src = src[: m.start()] + replacement + src[close_at:]
        done.append(const)

    # Presence of the needle is the only test. Checking for the replacement
    # instead silently skips a needed edit whenever the design already
    # contains that exact text somewhere else — which it does: the guarded
    # `RUNS.find(...) || RUNS[0]` form appears verbatim in renderVals, so a
    # replacement-based check made the identical fix look already-applied.
    # Idempotency comes from always patching the pristine backup, not from
    # this loop.
    for needle, replacement in HANDLERS:
        if needle not in src:
            missed.append(f"handler:{needle.strip()[:40]}")
            continue
        src = src.replace(needle, replacement, 1)
        done.append(f"handler:{needle.strip().split('(')[0].split(':')[0][:30]}")

    # Case-insensitively, because the bundle mixes #14603F and #14603f.
    recoloured = 0
    def _swap(match):
        nonlocal recoloured
        hit = PALETTE.get(match.group(0).upper())
        if hit is None:
            return match.group(0)
        recoloured += 1
        return hit
    src = re.sub(r"#[0-9A-Fa-f]{6}", _swap, src)
    if recoloured:
        done.append(f"palette:{recoloured}")

    if "window.__resources" not in src:
        src = src.replace(
            '<script src="./support.js"></script>',
            RESOURCES + '<script src="./support.js"></script>',
            1,
        )
        done.append("__resources")

    return src, done, missed


def main() -> int:
    if not INDEX.exists():
        print(f"missing {INDEX}", file=sys.stderr)
        return 1

    original = INDEX.read_text(encoding="utf-8")
    backup = INDEX.with_suffix(".orig.html")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
        print(f"backed up pristine design -> {backup.name}")

    # Always patch from the pristine copy so re-runs stay idempotent.
    patched, done, missed = patch(backup.read_text(encoding="utf-8"))
    INDEX.write_text(patched, encoding="utf-8")

    print(f"patched {len(done)} hooks: {', '.join(done)}")
    if missed:
        print(f"NOT FOUND (left as-is): {', '.join(missed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
