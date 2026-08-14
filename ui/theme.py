"""Lucida's visual design system.

Ported from the `Business Suite` design: a warm paper ground, deep-green accent,
Instrument Serif for headlines and figures, Plus Jakarta Sans for everything
else, on a 244px rail + content grid.

The design leads here, not Streamlit. The stylesheet below removes Streamlit's
own chrome (toolbar, header, footer, decoration bar, element gaps) and rebuilds
the page to the design's measurements, so what you see is the design rather
than a Streamlit app wearing its colours.

Two halves, and the split matters:

  * `CSS` restyles what Streamlit still paints — buttons, inputs, chat bubbles.
    Anything the owner clicks has to stay a real widget, because that is what
    triggers a rerun; an HTML button cannot approve an ad spend.
  * The helpers below emit the design's own markup for display content — KPI
    cards, decision cards, tables, pills — where there is nothing to click.
"""

from __future__ import annotations

import html as _html

import streamlit as st

# ---------------------------------------------------------------------------
# Tokens — sampled from the design by frequency, not by eye.
# ---------------------------------------------------------------------------

GROUND = "#F7F5F0"     # page background — warm paper
RAIL = "#FBFAF7"       # sidebar + table header rows
SURFACE = "#FFFFFF"    # cards
SUNKEN = "#F1EEE6"     # inset wells, segmented controls
BORDER = "#E5E0D6"     # hairlines
BORDER_SOFT = "#EFEBE1"  # row dividers inside a card
DIVIDER = "#F5F2EA"

INK = "#18211D"        # headings
BODY = "#4A554E"       # body copy
MUTED = "#7C877F"      # labels, captions, metadata
FAINT = "#A19B8E"

ACCENT = "#14603F"     # deep green — the brand
ACCENT_DARK = "#0E4A30"
ACCENT_TINT = "#EAF1EC"
ACCENT_EDGE = "#CFE0D5"

# Buttons are maroon red rather than the brand green. Kept as its own token
# instead of changing ACCENT, so pills, links and status colours stay green
# and only the things you press change.
BUTTON = "#7B1E22"
BUTTON_DARK = "#5E1519"
BUTTON_TINT = "#F6E9EA"

WARN = "#B4741B"       # amber — attention, not failure
WARN_TINT = "#FBF1E1"
WARN_BORDER = "#F0DFC2"

DANGER = "#A63A2E"
DANGER_TINT = "#F8E9E6"

SANS = "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif"
SERIF = "'Instrument Serif', Georgia, serif"
MONO = "ui-monospace, 'Cascadia Code', Menlo, monospace"

RADIUS_CARD = "14px"
RADIUS_CTRL = "10px"
RADIUS_BTN = "9px"

RAIL_W = "244px"
CONTENT_MAX = "1120px"

STATUS = {
    "live": (ACCENT, ACCENT_TINT),
    "ok": (ACCENT, ACCENT_TINT),
    "published": (ACCENT, ACCENT_TINT),
    "simulated": (WARN, WARN_TINT),
    "warn": (WARN, WARN_TINT),
    "drafted": (WARN, WARN_TINT),
    "missing": (DANGER, DANGER_TINT),
    "error": (DANGER, DANGER_TINT),
    "failed": (DANGER, DANGER_TINT),
    "idle": (MUTED, SUNKEN),
}


# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@200..800&family=Instrument+Serif:ital@0;1&display=swap');

/* ---- strip Streamlit's chrome ---------------------------------------- */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
#MainMenu, footer, header {{
    display: none !important;
    height: 0 !important;
}}
[data-testid="stAppViewContainer"] > .main {{ padding-top: 0; }}

/* ---- ground ---------------------------------------------------------- */
[data-testid="stAppViewContainer"] {{
    background: {GROUND};
    color: {INK};
    font-size: 14px;
}}
html, body, [data-testid="stAppViewContainer"] * {{
    font-family: {SANS};
    -webkit-font-smoothing: antialiased;
}}
/* The design's content column: 30px/36px padding, capped at 1120px. */
.block-container {{
    padding: 30px 36px 90px !important;
    max-width: {CONTENT_MAX} !important;
}}
/* Streamlit's default 1rem gap between every element is far looser than the
   design's rhythm; the components below carry their own spacing. */
[data-testid="stVerticalBlock"] {{ gap: 0.55rem; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: transparent; }}

h1 {{
    font-family: {SERIF} !important; font-weight: 400 !important;
    font-size: 30px !important; letter-spacing: -0.01em;
    color: {INK}; margin: 0 0 5px !important; padding: 0 !important;
}}
h2 {{ font-size: 16px !important; font-weight: 600 !important; color: {INK}; }}
h3 {{ font-size: 15px !important; font-weight: 600 !important; color: {INK}; }}
p, li {{ color: {BODY}; line-height: 1.6; font-size: 14px; }}
a {{ color: {ACCENT}; text-decoration: none; }}
a:hover {{ color: {ACCENT_DARK}; }}
code {{
    font-family: {MONO}; font-size: 0.85em;
    background: {SUNKEN}; color: {BODY};
    padding: 1px 5px; border-radius: 5px;
}}
hr {{ border-color: {BORDER}; margin: 18px 0; }}

/* ---- rail ------------------------------------------------------------ */
[data-testid="stSidebar"] {{
    background: {RAIL};
    border-right: 1px solid {BORDER};
    width: {RAIL_W} !important;
    min-width: {RAIL_W} !important;
}}
[data-testid="stSidebar"] > div {{ padding-top: 18px; }}
[data-testid="stSidebar"] .block-container {{ padding: 18px 14px 24px !important; }}
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"] {{
    display: none !important;
}}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: 0.15rem; }}

/* Rail nav rows: full-width, left-aligned, quiet until active. */
.st-key-nav .stButton > button {{
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    padding: 9px 11px;
    font-size: 13.5px;
    font-weight: 500;
    border-radius: {RADIUS_CTRL};
    border: none;
    background: transparent;
    color: {BODY};
}}
.st-key-nav .stButton > button:hover {{
    background: {SUNKEN};
    color: {ACCENT};
}}
/* Active row — tinted, not solid; the design never fills a nav row. */
.st-key-nav .stButton > button[kind="primary"] {{
    background: {ACCENT_TINT};
    color: {ACCENT};
    font-weight: 600;
}}
.st-key-nav .stButton > button[kind="primary"]:hover {{
    background: {ACCENT_TINT};
    color: {ACCENT_DARK};
}}

/* ---- buttons --------------------------------------------------------- */
.stButton > button {{
    border-radius: {RADIUS_BTN};
    font-size: 13px;
    font-weight: 500;
    padding: 9px 15px;
    transition: background .15s, border-color .15s, color .15s;
    box-shadow: none;
}}
.stButton > button[kind="secondary"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    color: {BODY};
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: {BUTTON}; color: {BUTTON}; background: {SURFACE};
}}
.stButton > button[kind="primary"] {{
    background: {BUTTON}; border: 1px solid {BUTTON};
    color: {GROUND}; font-weight: 600;
}}
.stButton > button[kind="primary"]:hover {{
    background: {BUTTON_DARK}; border-color: {BUTTON_DARK}; color: {GROUND};
}}
.stButton > button:focus {{ box-shadow: 0 0 0 3px {BUTTON_TINT} !important; }}

/* Opener buttons read as quiet suggestion cards. */
.st-key-openers .stButton > button {{
    text-align: left; justify-content: flex-start;
    padding: 13px 15px; font-size: 13.5px; line-height: 1.45;
    border-radius: {RADIUS_CARD}; height: 100%; white-space: normal;
}}
.st-key-railfoot {{
    margin-top: 16px; border-top: 1px solid {BORDER}; padding-top: 14px;
}}

/* ---- inputs ---------------------------------------------------------- */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div {{
    background: {SURFACE} !important;
    border: 1px solid {BORDER} !important;
    border-radius: {RADIUS_CTRL} !important;
    color: {INK} !important;
    font-size: 13.5px !important;
}}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {{
    border-color: {ACCENT} !important;
    box-shadow: 0 0 0 3px {ACCENT_TINT} !important;
}}
[data-testid="stWidgetLabel"] label p {{
    font-size: 12.5px !important; color: {MUTED} !important; font-weight: 500;
}}

/* ---- chat ------------------------------------------------------------ */
[data-testid="stChatMessage"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD};
    padding: 15px 17px;
    margin-bottom: 10px;
    animation: luFadeUp .25s ease both;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
    background: {SUNKEN}; border-color: transparent;
}}
[data-testid="stChatMessageContent"] p {{ line-height: 1.65; font-size: 14px; }}
[data-testid="stChatInput"] {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD};
}}
[data-testid="stChatInput"]:focus-within {{ border-color: {ACCENT}; }}
[data-testid="stBottomBlockContainer"] {{
    background: {GROUND}; padding-bottom: 18px; max-width: {CONTENT_MAX};
}}

/* ---- containers ------------------------------------------------------ */
[data-testid="stExpander"] {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD};
}}
[data-testid="stExpander"] summary {{
    font-size: 13px; font-weight: 500; color: {BODY};
}}
[data-testid="stExpander"] summary:hover {{ color: {ACCENT}; }}
[data-testid="stStatus"] {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD};
}}

/* ---- tabs ------------------------------------------------------------ */
[data-baseweb="tab-list"] {{
    gap: 3px; background: {SUNKEN}; padding: 3px;
    border-radius: {RADIUS_CTRL}; border-bottom: none;
}}
[data-baseweb="tab"] {{
    border-radius: 8px; padding: 7px 13px !important;
    font-size: 12.5px; color: {MUTED}; background: transparent;
}}
[data-baseweb="tab"]:hover {{ color: {ACCENT}; background: transparent; }}
[data-baseweb="tab"][aria-selected="true"] {{
    background: {SURFACE}; color: {ACCENT}; font-weight: 600;
    box-shadow: 0 1px 2px rgba(24,33,29,.06);
}}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{ display: none; }}

/* ---- metrics & data -------------------------------------------------- */
[data-testid="stMetric"] {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}; padding: 15px 16px;
}}
[data-testid="stMetricLabel"] p {{ font-size: 12px !important; color: {MUTED} !important; }}
[data-testid="stMetricValue"] {{
    font-family: {SERIF}; font-size: 27px !important; font-weight: 400 !important;
    color: {INK};
}}
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border: 1px solid {BORDER}; border-radius: {RADIUS_CARD}; overflow: hidden;
}}
[data-testid="stAlert"] {{ border-radius: {RADIUS_CTRL}; font-size: 13.5px; }}

/* ---- scrollbar & motion ---------------------------------------------- */
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-thumb {{ background: #DDD8CC; border-radius: 6px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
@keyframes luFadeUp {{
    from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: none; }}
}}
@keyframes luPulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .35; }} }}

/* ---- design components ----------------------------------------------- */
.lu-lede {{ margin: 0 0 22px; font-size: 14px; color: {BODY}; max-width: 760px; }}

.lu-kpis {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px; margin: 4px 0 22px;
}}
.lu-kpi {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}; padding: 15px 16px;
}}
.lu-kpi-label {{ font-size: 12px; color: {MUTED}; }}
.lu-kpi-value {{ font-family: {SERIF}; font-size: 27px; margin-top: 4px; line-height: 1.15; }}
.lu-kpi-note {{ font-size: 12px; margin-top: 2px; color: {MUTED}; }}

.lu-card {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}; padding: 16px 17px; margin-bottom: 12px;
    animation: luFadeUp .25s ease both;
}}
.lu-card-head {{ display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }}
.lu-card-title {{ font-size: 15.5px; font-weight: 600; line-height: 1.4; margin-bottom: 6px; }}
.lu-card-body {{ font-size: 13.5px; color: {BODY}; line-height: 1.6; }}

.lu-tag {{
    font-size: 11px; font-weight: 600; letter-spacing: .05em;
    text-transform: uppercase; padding: 3px 8px; border-radius: 6px;
}}
.lu-pill {{
    display: inline-flex; align-items: center; gap: 5px;
    font-size: 11.5px; font-weight: 500; padding: 3px 9px; border-radius: 999px;
}}
.lu-meta {{ font-size: 12px; color: {MUTED}; }}

.lu-facts {{
    display: flex; gap: 18px; flex-wrap: wrap;
    margin: 12px 0 2px; padding: 11px 13px;
    background: {GROUND}; border-radius: {RADIUS_CTRL};
}}
.lu-fact-k {{ font-size: 11.5px; color: {MUTED}; }}
.lu-fact-v {{ font-size: 14px; font-weight: 600; margin-top: 2px; }}

.lu-section {{ display: flex; align-items: baseline; gap: 10px; margin: 24px 0 12px; }}
.lu-section h2 {{ margin: 0; font-size: 16px; font-weight: 600; }}
.lu-section span {{ font-size: 12.5px; color: {MUTED}; }}

/* Tables are CSS grids, exactly as the design builds them. */
.lu-table {{
    background: {SURFACE}; border: 1px solid {BORDER};
    border-radius: {RADIUS_CARD}; overflow: hidden; margin-bottom: 18px;
}}
.lu-thead {{
    background: {RAIL}; padding: 11px 16px;
    font-size: 11.5px; letter-spacing: .04em; text-transform: uppercase;
    color: {MUTED};
}}
.lu-trow {{
    padding: 13px 16px; border-top: 1px solid {BORDER_SOFT};
    align-items: center; font-size: 13.5px;
}}
.lu-thead, .lu-trow {{ display: grid; gap: 14px; }}
.lu-trow strong {{ font-weight: 600; }}

.lu-list-row {{
    display: flex; gap: 10px; padding: 11px 0;
    border-top: 1px solid {SUNKEN};
}}
.lu-list-row:first-child {{ border-top: none; }}
.lu-bullet {{
    width: 6px; height: 6px; border-radius: 50%; background: {ACCENT};
    margin-top: 7px; flex: none;
}}

.lu-dot {{
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: {ACCENT}; animation: luPulse 2.4s infinite; margin-right: 6px;
}}
.lu-empty {{
    background: {SURFACE}; border: 1px dashed {BORDER};
    border-radius: {RADIUS_CARD}; padding: 26px; text-align: center;
    color: {MUTED}; font-size: 13px; margin-bottom: 16px;
}}
</style>
"""


def inject() -> None:
    """Install the stylesheet. Call once, first thing in the page body."""
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Display components
#
# These render HTML directly because they hold nothing clickable. Every string
# that could carry user or model text is escaped on the way in.
# ---------------------------------------------------------------------------


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


def page_header(title: str, lede: str = "") -> None:
    """Serif page title over the design's one-line explanation."""
    sub = f"<p class='lu-lede'>{_esc(lede)}</p>" if lede else ""
    st.markdown(
        f"<h1 style=\"font-family:{SERIF};font-size:30px;font-weight:400;"
        f"letter-spacing:-0.01em;color:{INK};margin:0 0 5px;\">{_esc(title)}</h1>"
        f"{sub}",
        unsafe_allow_html=True,
    )


def section(title: str, note: str = "") -> None:
    extra = f"<span>{_esc(note)}</span>" if note else ""
    st.markdown(
        f"<div class='lu-section'><h2>{_esc(title)}</h2>{extra}</div>",
        unsafe_allow_html=True,
    )


def kpis(cards: list[dict]) -> None:
    """A responsive row of KPI cards.

    Each card is ``{"label", "value", "note", "tone"}``; tone colours the value
    and warms the border so an amber card reads as "look at this".
    """
    if not cards:
        return
    out = []
    for c in cards:
        tone = c.get("tone", "")
        fg = STATUS.get(tone, (INK, ""))[0]
        value_color = fg if tone and tone != "idle" else INK
        note_color = fg if tone and tone != "idle" else MUTED
        border = WARN_BORDER if tone in ("warn", "simulated") else BORDER
        note = (
            f"<div class='lu-kpi-note' style='color:{note_color};'>{_esc(c['note'])}</div>"
            if c.get("note") else ""
        )
        out.append(
            f"<div class='lu-kpi' style='border-color:{border};'>"
            f"<div class='lu-kpi-label'>{_esc(c['label'])}</div>"
            f"<div class='lu-kpi-value' style='color:{value_color};'>{_esc(c['value'])}</div>"
            f"{note}</div>"
        )
    st.markdown(f"<div class='lu-kpis'>{''.join(out)}</div>", unsafe_allow_html=True)


def tag(text: str, tone: str = "ok") -> str:
    fg, bg = STATUS.get(tone, (MUTED, SUNKEN))
    return f"<span class='lu-tag' style='color:{fg};background:{bg};'>{_esc(text)}</span>"


def pill(text: str, tone: str = "idle") -> str:
    fg, bg = STATUS.get(tone, (MUTED, SUNKEN))
    return f"<span class='lu-pill' style='color:{fg};background:{bg};'>{_esc(text)}</span>"


def facts(items: list[tuple[str, str]], tones: list[str] | None = None) -> str:
    if not items:
        return ""
    tones = tones or []
    cells = []
    for i, (k, v) in enumerate(items):
        tone = tones[i] if i < len(tones) else ""
        color = STATUS.get(tone, (INK, ""))[0] if tone else INK
        cells.append(
            f"<div><div class='lu-fact-k'>{_esc(k)}</div>"
            f"<div class='lu-fact-v' style='color:{color};'>{_esc(v)}</div></div>"
        )
    return f"<div class='lu-facts'>{''.join(cells)}</div>"


def card(
    title: str,
    body: str = "",
    tag_text: str = "",
    tone: str = "ok",
    by: str = "",
    when: str = "",
    fact_items: list[tuple[str, str]] | None = None,
) -> None:
    """The design's card anatomy: tag row, title, body, inset fact strip.

    Interactive cards render this for the content and put real Streamlit
    buttons directly beneath.
    """
    border = WARN_BORDER if tone in ("warn", "simulated") else BORDER
    head_bits = []
    if tag_text:
        head_bits.append(tag(tag_text, tone))
    if by:
        head_bits.append(f"<span class='lu-meta'>{_esc(by)}</span>")
    if when:
        head_bits.append(f"<span class='lu-meta' style='margin-left:auto;'>{_esc(when)}</span>")
    head = f"<div class='lu-card-head'>{''.join(head_bits)}</div>" if head_bits else ""
    body_html = f"<div class='lu-card-body'>{_esc(body)}</div>" if body else ""
    st.markdown(
        f"<div class='lu-card' style='border-color:{border};'>{head}"
        f"<div class='lu-card-title'>{_esc(title)}</div>{body_html}"
        f"{facts(fact_items or [])}</div>",
        unsafe_allow_html=True,
    )


def table(columns: list[str], widths: str, rows: list[list[str]]) -> None:
    """A grid table in the design's idiom.

    ``widths`` is a raw ``grid-template-columns`` value so callers control
    column sizing exactly as the design does. Cells are pre-rendered HTML —
    callers use `pill()` / `tag()` inside them — so cell *text* must be
    escaped by the caller via `esc()`.
    """
    head = "".join(f"<span>{_esc(c)}</span>" for c in columns)
    body = "".join(
        f"<div class='lu-trow' style='grid-template-columns:{widths};'>"
        + "".join(f"<div>{c}</div>" for c in row)
        + "</div>"
        for row in rows
    )
    st.markdown(
        f"<div class='lu-table'>"
        f"<div class='lu-thead' style='grid-template-columns:{widths};'>{head}</div>"
        f"{body}</div>",
        unsafe_allow_html=True,
    )


def bullets(items: list[tuple[str, str]]) -> None:
    """The design's dotted activity list: (text, meta) pairs."""
    rows = "".join(
        f"<div class='lu-list-row'><span class='lu-bullet'></span><div>"
        f"<div style='font-size:13.5px;line-height:1.45;'>{_esc(t)}</div>"
        f"<div class='lu-meta' style='margin-top:2px;'>{_esc(m)}</div>"
        f"</div></div>"
        for t, m in items
    )
    st.markdown(f"<div class='lu-card'>{rows}</div>", unsafe_allow_html=True)


def empty(message: str) -> None:
    st.markdown(f"<div class='lu-empty'>{_esc(message)}</div>", unsafe_allow_html=True)


def live_dot(label: str) -> None:
    st.markdown(
        f"<div style='font-size:11.5px;font-weight:600;color:{BODY};'>"
        f"<span class='lu-dot'></span>{_esc(label)}</div>",
        unsafe_allow_html=True,
    )


def esc(value: object) -> str:
    """Public escape helper for callers building table cells."""
    return _esc(value)
