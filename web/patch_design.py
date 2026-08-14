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

# The palette: white surfaces, pure black type, maroon as the single accent.
#
# Built on shadcn/ui's neutral scale (zinc) rather than invented greys — that
# is what gives the "modern, established" feel of the reference: near-black
# text on white, one hairline grey, and a single saturated accent used
# sparingly.
#
# Applied as a literal colour-for-colour substitution over the whole bundle.
# Replacing at source rather than overriding in CSS means there is no cascade
# to lose against inline styles, and no colour can survive in a code path that
# happens not to be exercised yet.
#
#   white   every surface — ground, cards, rail
#   black   headings and body type
#   zinc    hairlines, muted labels, wells
#   maroon  the accent: brand, actions, active state
PALETTE = {
    # --- brand green -> maroon --------------------------------------------
    "#14603F": "#7B1E22",   # accent
    "#0E4A30": "#5E1519",   # accent, pressed
    "#EAF1EC": "#FBEBEB",   # accent wash
    "#CFE0D5": "#F0D6D6",   # accent edge
    "#9EB3A4": "#A1A1AA",
    "#F4F8F5": "#FAFAFA",

    # --- surfaces -> white -------------------------------------------------
    "#F7F5F0": "#FFFFFF",   # ground
    "#FBFAF7": "#FAFAFA",   # rail, table headers
    "#FFFFFF": "#FFFFFF",   # cards stay white
    "#F1EEE6": "#F4F4F5",   # sunken wells
    "#F5F2EA": "#FAFAFA",

    # --- type -> pure black and zinc ---------------------------------------
    "#18211D": "#000000",   # headings
    "#4A554E": "#3F3F46",   # body copy
    "#7C877F": "#71717A",   # muted labels
    "#A19B8E": "#A1A1AA",   # faint

    # --- hairlines -> zinc --------------------------------------------------
    "#E5E0D6": "#E4E4E7",
    "#EFEBE1": "#F4F4F5",
    "#DCD3BE": "#E4E4E7",
    "#DDD8CC": "#D4D4D8",
    "#C9C3B4": "#D4D4D8",
    "#E1DCD1": "#E4E4E7",
    "#DFDACE": "#E4E4E7",
    "#CFC8B8": "#D4D4D8",
    "#EBDCC2": "#F4F4F5",
    "#F4EFE2": "#FFFFFF",

    # --- attention and failure ----------------------------------------------
    "#B4741B": "#A16207",
    "#FBF1E1": "#FEF9C3",
    "#F0DFC2": "#FDE68A",
    "#A63A2E": "#B91C1C",   # danger, clearly apart from the maroon accent
    "#F8E9E6": "#FEE2E2",
    "#F0DAD6": "#FECACA",

    # --- borrowed brand colours ---------------------------------------------
    "#5B4B9B": "#52525B",
    "#EDEAF6": "#F4F4F5",
    "#1F6470": "#3F3F46",
    "#E8F1F2": "#F4F4F5",
    "#A6377C": "#7B1E22",
    "#2B5C9B": "#52525B",
}

# X (Twitter) sets its type in Chirp, which is proprietary and not
# distributable. Inter is the closest freely-licensed match — same grotesque
# skeleton, same tight default tracking — so it is what the bundle asks for.
FONTS = [
    ("'Plus Jakarta Sans', system-ui, sans-serif",
     "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"),
    ("'Instrument Serif', serif",
     "'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif"),
    ("family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Instrument+Serif:ital@0;1",
     "family=Inter:wght@400;500;600;700;800"),
    ("family=Plus+Jakarta+Sans:wght@200..800&family=Instrument+Serif:ital@0;1",
     "family=Inter:wght@400;500;600;700;800"),
]

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
    # The rail's second line is the demo shop's address, written straight into
    # the markup. Turned into a binding so it can show the owner's own.
    (
        ">Mirpur 11, Dhaka<",
        ">{{ shopLocation }}<",
    ),
    (
        "goSettings: () => this.go('settings'), goActivity: () => this.go('history'),",
        "goSettings: () => this.go('settings'), goActivity: () => this.go('history'),\n"
        "      shopLocation: (window.LUCIDA && window.LUCIDA.location)\n"
        "        || 'Add your area in Settings',",
    ),
    # On an empty shop the figures below are the design's samples. Say so,
    # instead of greeting a new owner with a night's work they never had.
    (
        "      dayLine: open.length",
        "      dayLine: (window.LUCIDA && window.LUCIDA.firstRun)\n"
        "        ? 'Your team is ready, but has not learned anything about your "
        "shop yet. The figures below are examples — ask a question or add a "
        "photo of what you sell, and they fill in with yours.'\n"
        "        : open.length",
    ),
    # The four headline tiles were written as literals — the demo shop's
    # takings, preorders and days of cover. Bound to real figures instead.
    # Each shows an em dash when the shop has no basis for it, rather than a
    # borrowed number.
    (
        ">৳6,480</div>",
        ">{{ salesToday }}</div>",
    ),
    (
        ">24 orders · +12% vs last Tue</div>",
        ">{{ salesTodayNote }}</div>",
    ),
    (
        ">312 pcs</div>",
        ">{{ preorderUnits }}</div>",
    ),
    (
        ">৳5,616 · 9 customers</div>",
        ">{{ preorderNote }}</div>",
    ),
    (
        ">4 days</div>",
        ">{{ coverDays }}</div>",
    ),
    (
        ">Beef shingara running low</div>",
        ">{{ coverNote }}</div>",
    ),
    (
        "      shopLocation: (window.LUCIDA && window.LUCIDA.location)\n"
        "        || 'Add your area in Settings',",
        "      shopLocation: (window.LUCIDA && window.LUCIDA.location)\n"
        "        || 'Add your area in Settings',\n"
        "      salesToday: K().salesToday, salesTodayNote: K().salesTodayNote,\n"
        "      preorderUnits: K().preorderUnits, preorderNote: K().preorderNote,\n"
        "      coverDays: K().coverDays, coverNote: K().coverNote,",
    ),
    # One helper so the six bindings above read from the same place, with a
    # dashed fallback when the server sent nothing.
    #
    # EMPTY_THREAD / EMPTY_RUN exist because the design assumed its own
    # fixtures were always present: `THREADS.find(...) || THREADS[0]` is
    # undefined once a real shop with no customers sends an empty array, and
    # the very next line reads `.name` off it. These give the selection a
    # harmless shape so the page renders empty instead of throwing.
    (
        "\nconst NAV = [",
        "\nfunction K() {\n"
        "  return (window.LUCIDA && window.LUCIDA.kpi) || {\n"
        "    salesToday: '\\u2014', salesTodayNote: 'no sales logged yet',\n"
        "    preorderUnits: '\\u2014', preorderNote: 'none yet',\n"
        "    coverDays: '\\u2014', coverNote: 'needs sales history'\n"
        "  };\n"
        "}\n"
        "const EMPTY_THREAD = { id: '', name: 'No messages yet', initials: '\\u2014',\n"
        "  channel: '', t: '', history: '', preview: '', message: '',\n"
        "  state: 'Your team has not read any customer messages yet.',\n"
        "  stateFg: '#8A7563', mark: '#8A7563', read: '', tags: [],\n"
        "  draft: '', action: '', send: () => {}, sent: false, sentAt: '',\n"
        "  unsent: true };\n"
        "const EMPTY_RUN = { id: '', label: 'No runs yet',\n"
        "  meta: 'Ask your team something and the run appears here.',\n"
        "  gate: { title: '', body: '' }, steps: [] };\n"
        "\nconst NAV = [",
    ),
    (
        "const thread = THREADS.find(t => t.id === s.thread) || THREADS[0];",
        "const thread = THREADS.find(t => t.id === s.thread) || THREADS[0]"
        " || EMPTY_THREAD;",
    ),
    (
        "const run = RUNS.find(r => r.id === s.run) || RUNS[0];\n",
        "const run = RUNS.find(r => r.id === s.run) || RUNS[0] || EMPTY_RUN;\n",
    ),
    # The Stock page's reorder panel is a worked example for the demo shop —
    # a named supplier, a delivery date, a cost, all invented. Bound to what
    # this shop can actually say: which items are at or below their reorder
    # level, and what replacing them is worth at cost.
    (
        "based on 4 weeks of sales + 312 pcs already promised",
        "{{ reorderBasis }}",
    ),
    (
        ">Order 2,000 beef shingara and pilot 600 chicken<",
        ">{{ reorderTitle }}<",
    ),
    (
        'Karwan Bazar Foods delivers in 2 days — that lands before your beef runs out on Saturday. The chicken pilot answers 14 customers who asked for it this month; if it sells at ৳19 you keep ৳6.90 a piece.',
        "{{ reorderBody }}",
    ),
    (
        ">Order sent to Karwan Bazar Foods · ref PO-9931. Delivery expected Thu 14 Aug, and your stock page will update itself when it arrives.<",
        ">{{ reorderSent }}<",
    ),
    (
        "      salesToday: K().salesToday, salesTodayNote: K().salesTodayNote,",
        "      reorderBasis: R().basis, reorderTitle: R().title,\n"
        "      reorderBody: R().body,\n"
        "      salesToday: K().salesToday, salesTodayNote: K().salesTodayNote,",
    ),
    # The Send button only marked the thread answered in local state. It
    # sends the reply now — through LucidaActions so a failure leaves the
    # message visibly unanswered rather than silently ticked off.
    (
        "send: () => { const x = Object.assign({}, s.sent); x[thread.id] = "
        "'just now'; this.setState({ sent: x }); }",
        "send: () => window.LucidaActions.reply(thread.id, "
        "(s.drafts && s.drafts[thread.id]) !== undefined "
        "? s.drafts[thread.id] : thread.draft),\n"
        "        onDraft: e => this.setState({ drafts: Object.assign({}, "
        "s.drafts, { [thread.id]: e.target.value }) })",
    ),
    (
        "const EMPTY_THREAD = {",
        "function R() {\n"
        "  return (window.LUCIDA && window.LUCIDA.reorder) || {\n"
        "    basis: 'nothing to base this on yet',\n"
        "    title: 'Nothing needs reordering',\n"
        "    body: 'Your stock is above the levels you set, or none has been "
        "recorded yet.'\n"
        "  };\n"
        "}\n"
        "const EMPTY_THREAD = {",
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
        # An empty array from the server wins over the design's literal.
        #
        # This used to fall back to the sample data whenever a key was empty,
        # which kept the layout intact but showed a new owner someone else's
        # sales, stock and customers as though they were their own. Presence
        # of the key is the test now: the server sends every key on every
        # render, so an empty one means "this shop genuinely has none", and
        # the design's own empty states handle it.
        replacement = (
            f"const {const} = (window.LUCIDA && window.LUCIDA.{key} !== undefined"
            f" ? window.LUCIDA.{key} : {literal})"
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

    # Every RUNS[0] fallback needs the empty-run shape behind it, and there
    # are four call sites — a single-shot replace would leave three throwing.
    guarded = src.count("|| RUNS[0]") - src.count("|| RUNS[0] || EMPTY_RUN")
    if guarded > 0:
        src = src.replace("|| RUNS[0] || EMPTY_RUN", "|| RUNS[0]")
        src = src.replace("|| RUNS[0]", "|| RUNS[0] || EMPTY_RUN")
        done.append(f"empty-run-guard:{src.count('EMPTY_RUN') - 1}")

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

    fonts = 0
    for old, new in FONTS:
        fonts += src.count(old)
        src = src.replace(old, new)
    if fonts:
        done.append(f"fonts:{fonts}")

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

    # The Windows console is cp1252; hook labels can carry a taka sign.
    summary = ", ".join(done).encode("ascii", "replace").decode("ascii")
    print(f"patched {len(done)} hooks: {summary}")
    if missed:
        print(f"NOT FOUND (left as-is): {', '.join(missed)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
