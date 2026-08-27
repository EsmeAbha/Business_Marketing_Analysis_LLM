"""The product surfaces: chat, ad studio, integrations.

The Business Suite bundle is a dashboard — it reports what happened. These are
the screens where the owner actually does something, and they did not exist in
it, so they are written here in the same design language: white, pure black
type, maroon accent, Inter, shadcn's neutrals and radii.

Server-rendered HTML with small islands of JavaScript. No build step, no
bundle: the chat has to work on a cheap phone on a Dhaka connection, and 3 MB
of React before a shop owner can type a message is not a trade worth making.
"""

from __future__ import annotations

import html
import json
from typing import Any

INK = "#000000"
BODY = "#3F3F46"
MUTED = "#71717A"
FAINT = "#A1A1AA"
DASHED = "—"
SURFACE = "#FFFFFF"
RAIL = "#FAFAFA"
SUNKEN = "#F4F4F5"
BORDER = "#E4E4E7"
ACCENT = "#7B1E22"
ACCENT_DARK = "#5E1519"
ACCENT_TINT = "#FBEBEB"
AMBER = "#A16207"
AMBER_TINT = "#FEF9C3"
DANGER = "#B91C1C"
DANGER_TINT = "#FEE2E2"
SANS = ("'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', "
        "system-ui, sans-serif")

FONT_LINK = (
    '<link rel="icon" href="/favicon.svg" type="image/svg+xml">'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

# Five places, named for what the owner came to do. Everything else is
# reached from inside the one that owns it: the ad studio from Chat, the
# workforce from Home, delivery from Products. A rail with nine entries made
# the owner choose before they had read anything, and most of those choices
# led to the same screen.
NAV = [
    ("/", "Home", "What needs you today"),
    ("/chat", "Chat", "Ask your team anything"),
    ("/products", "Products", "What you sell, stock and delivery"),
    ("/customers", "Customers", "Messages and reviews"),
    ("/workforce", "Workforce", "Watch your agents work"),
    ("/settings", "Settings", "Channels, couriers, your account"),
]


def e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


SHELL_CSS = f"""
*,*::before,*::after {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; height:100%; background:{SURFACE};
  color:{INK}; font-family:{SANS}; font-size:15px;
  -webkit-font-smoothing:antialiased; }}
a {{ color:inherit; text-decoration:none; }}
button, input, textarea, select {{ font-family:inherit; }}

.app {{ display:grid; grid-template-columns:248px minmax(0,1fr);
  min-height:100vh; }}
.rail {{ background:{RAIL}; border-right:1px solid {BORDER};
  padding:18px 14px; display:flex; flex-direction:column; gap:4px;
  position:sticky; top:0; height:100vh; overflow:hidden; }}
.brand {{ display:flex; align-items:center; gap:10px; padding:4px 8px 18px; }}
.logo {{ width:34px; height:34px; border-radius:10px; background:{ACCENT};
  color:#fff; display:grid; place-items:center; font-weight:700;
  font-size:15px; letter-spacing:-.02em; }}
.brand b {{ font-size:15px; font-weight:600; letter-spacing:-.01em; }}
.brand span {{ display:block; font-size:12px; color:{MUTED}; font-weight:400; }}
.nav {{ display:flex; align-items:center; gap:10px; padding:9px 11px;
  border-radius:9px; font-size:14px; font-weight:500; color:{BODY};
  letter-spacing:-.006em; }}
.nav:hover {{ background:{SUNKEN}; color:{INK}; }}
.nav.on {{ background:{ACCENT_TINT}; color:{ACCENT}; font-weight:600; }}
.nav small {{ display:block; font-size:11.5px; color:{MUTED};
  font-weight:400; }}
.nav.on small {{ color:{ACCENT}; opacity:.8; }}
.railfoot {{ margin-top:auto; border-top:1px solid {BORDER}; padding-top:12px; }}
.who {{ display:flex; align-items:center; gap:9px; padding:8px;
  border-radius:9px; cursor:pointer; }}
.who:hover {{ background:{SUNKEN}; }}
.avatar {{ width:30px; height:30px; border-radius:9px; background:{ACCENT};
  color:#fff; display:grid; place-items:center; font-size:12px;
  font-weight:600; object-fit:cover; }}

/* `clip` rather than `hidden`: hidden on one axis forces the other to auto,
   which would turn the chat's own scrolling container into a second one.
   This is the backstop that stops any single wide child — a long token, an
   unbreakable URL — from dragging the whole page sideways. */
.main {{ display:flex; flex-direction:column; min-width:0; overflow-x:clip; }}
.head {{ padding:26px 32px 0; }}
.head h1 {{ margin:0; font-size:28px; font-weight:800; letter-spacing:-.032em; }}
.head p {{ margin:6px 0 0; font-size:14.5px; color:{MUTED}; }}
.body {{ padding:22px 32px 32px; }}

.card {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:16px;
  padding:20px 22px; box-shadow:0 1px 2px rgba(0,0,0,.04); min-width:0; }}
/* A redirect URI or an access token has no spaces in it, and on a phone an
   unbreakable string is what pushes a card past its own edge. */
.card code, .card pre {{ overflow-wrap:anywhere; word-break:break-word; }}
.btn {{ padding:11px 18px; border-radius:11px; border:none; background:{ACCENT};
  color:#fff; font-size:14.5px; font-weight:600; letter-spacing:-.01em;
  cursor:pointer; transition:background .15s, transform .06s; }}
.btn:hover {{ background:{ACCENT_DARK}; }}
.btn:active {{ transform:scale(.99); }}
.btn[disabled] {{ opacity:.55; cursor:not-allowed; }}
.btn-quiet {{ background:{SURFACE}; color:{INK}; border:1px solid {BORDER};
  font-weight:500; }}
.btn-quiet:hover {{ background:{SUNKEN}; }}
.field {{ margin-bottom:14px; }}
label {{ display:block; font-size:13px; font-weight:500; margin-bottom:6px; }}
input,select,textarea {{ width:100%; padding:11px 13px; border-radius:10px;
  border:1px solid {BORDER}; background:{SURFACE}; font-size:14px;
  color:{INK}; }}
input:focus,select:focus,textarea:focus {{ outline:none; border-color:{INK};
  box-shadow:0 0 0 3px rgba(0,0,0,.08); }}
.muted {{ color:{MUTED}; font-size:13.5px; line-height:1.6; }}
.pill {{ display:inline-flex; align-items:center; gap:5px; font-size:12px;
  font-weight:500; padding:3px 9px; border-radius:999px; }}
.ok {{ background:{ACCENT_TINT}; color:{ACCENT}; }}
.warn {{ background:{AMBER_TINT}; color:{AMBER}; }}
.bad {{ background:{DANGER_TINT}; color:{DANGER}; }}
@media (max-width: 860px) {{
  .app {{ grid-template-columns:1fr; }}
  .rail {{ position:static; height:auto; flex-direction:row; overflow-x:auto; }}
  .nav small, .brand span, .railfoot {{ display:none; }}
}}
"""


def shell(title: str, account: dict, active: str, head: str, body: str,
          extra_css: str = "", extra_js: str = "", aside: str = "") -> str:
    initials = (account or {}).get("initials") or "?"
    avatar = (account or {}).get("avatar") or ""
    face = (f"<img class='avatar' src='{e(avatar)}' alt=''>" if avatar
            else f"<div class='avatar'>{e(initials)}</div>")
    items = list(NAV)
    if (account or {}).get("is_admin"):
        items.append(("/admin", "Service admin",
                      "Every shop on this installation"))
    nav = "".join(
        f"<a class='nav{' on' if href == active else ''}' href='{href}'>"
        f"<div>{e(label)}<small>{e(sub)}</small></div></a>"
        for href, label, sub in items
    )
    return (
        f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{e(title)} · Lucida</title>{FONT_LINK}"
        f"<style>{SHELL_CSS}{extra_css}</style></head><body>"
        f"<div class='app'><aside class='rail'>"
        f"<div class='brand'><div class='logo'>L</div><div>"
        f"<b>{e((account or {}).get('business') or 'Lucida')}</b>"
        f"<span>{e((account or {}).get('location') or '')}</span></div></div>"
        f"{nav}{aside}"
        f"<div class='railfoot'><a class='who' href='/account'>{face}"
        f"<div style='min-width:0'><div style='font-size:13px;font-weight:500'>"
        f"{e((account or {}).get('name') or 'Your account')}</div>"
        f"<div style='font-size:11.5px;color:{MUTED};overflow:hidden;"
        f"text-overflow:ellipsis'>{e((account or {}).get('email') or '')}</div>"
        f"</div></a></div></aside>"
        f"<main class='main'>{head}{body}</main></div>"
        f"<script>{extra_js}</script></body></html>"
    )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

CHAT_CSS = f"""
.main {{ height:100vh; }}
.thread {{ flex:1; overflow-y:auto; padding:28px 0 24px; }}
.wrap {{ max-width:780px; margin:0 auto; padding:0 24px; }}
/* Two sides, the way a messaging app does it: what the owner said sits
   right in a tinted bubble, what the team said sits left with its mark.
   The team's side is wider because its answers are long — a report squeezed
   into a chat bubble is harder to read, not friendlier. */
.msg {{ display:flex; gap:11px; margin-bottom:22px; align-items:flex-start; }}
.msg.mine {{ flex-direction:row-reverse; }}
.who-b {{ width:28px; height:28px; border-radius:8px; flex:none;
  display:grid; place-items:center; font-size:11.5px; font-weight:600;
  margin-top:2px; }}
.you {{ background:{SUNKEN}; color:{BODY}; }}
.them {{ background:{ACCENT}; color:#fff; }}
.bubble {{ min-width:0; }}
.msg.mine .bubble {{ max-width:72%; }}
.msg.theirs .bubble {{ max-width:88%; }}
.bubble .name {{ font-size:12px; font-weight:600; margin-bottom:4px;
  color:{MUTED}; letter-spacing:-.005em; }}
.msg.mine .name {{ text-align:right; }}
.bubble .text {{ font-size:15px; line-height:1.65; color:{INK};
  word-wrap:break-word; overflow-wrap:anywhere; }}
/* The owner's own words read as a said-thing; the team's as a written one. */
.msg.mine .text {{ background:{ACCENT_TINT}; padding:11px 15px;
  border-radius:16px 4px 16px 16px; }}
.msg.theirs .text {{ padding-top:1px; }}
.bubble .text h3 {{ font-size:15px; margin:15px 0 5px; font-weight:700; }}
.bubble .text ul {{ margin:8px 0; padding-left:20px; }}
.bubble .text li {{ margin:4px 0; }}
.bubble .text p:first-child {{ margin-top:0; }}
.bubble .text p:last-child {{ margin-bottom:0; }}
.picker {{ border:1px solid {BORDER}; border-radius:14px; padding:14px 16px;
  background:{SURFACE}; }}
.picker h4 {{ margin:0 0 3px; font-size:14.5px; font-weight:600; }}
.picker .sub {{ font-size:13px; color:{MUTED}; margin-bottom:11px; }}
.src {{ display:flex; gap:10px; padding:9px 10px; border-radius:10px;
  cursor:pointer; align-items:flex-start; }}
.src:hover {{ background:{SUNKEN}; }}
.src.off {{ opacity:.55; cursor:not-allowed; }}
.src input {{ width:auto; margin:3px 0 0; accent-color:{ACCENT}; flex:none; }}
.src b {{ font-size:13.5px; font-weight:600; display:block; }}
.src span {{ font-size:12.5px; color:{MUTED}; }}
.empty {{ text-align:center; padding:60px 20px; }}
.empty h2 {{ font-size:30px; font-weight:800; letter-spacing:-.032em;
  margin:0 0 8px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center;
  margin-top:22px; }}
.chip {{ padding:9px 14px; border-radius:999px; border:1px solid {BORDER};
  background:{SURFACE}; font-size:13.5px; cursor:pointer; color:{BODY}; }}
.chip:hover {{ border-color:{INK}; color:{INK}; }}

/* The composer: pinned bottom, centred on the column, the way a chat app
   puts it — this is the main thing an owner does, so it is the main thing
   on the screen. */
.composer {{ position:sticky; bottom:0; background:{SURFACE};
  border-top:1px solid {BORDER}; padding:14px 0 18px; }}
.cbox {{ max-width:780px; margin:0 auto; padding:0 24px; }}
.cinner {{ display:flex; align-items:flex-end; gap:9px; border:1px solid
  {BORDER}; border-radius:16px; padding:9px 9px 9px 15px;
  background:{SURFACE}; transition:border-color .15s, box-shadow .15s; }}
.cinner:focus-within {{ border-color:{INK};
  box-shadow:0 0 0 3px rgba(0,0,0,.07); }}
#msg {{ flex:1; border:none; outline:none; resize:none; font-size:15px;
  line-height:1.55; max-height:190px; padding:6px 0; background:transparent; }}
#msg:focus {{ box-shadow:none; }}
.send {{ width:38px; height:38px; border-radius:11px; border:none;
  background:{ACCENT}; color:#fff; cursor:pointer; flex:none;
  display:grid; place-items:center; font-size:16px; }}
.send:hover {{ background:{ACCENT_DARK}; }}
.send[disabled] {{ opacity:.4; cursor:not-allowed; }}
.clip {{ width:38px; height:38px; border-radius:11px; border:1px solid
  {BORDER}; background:{SURFACE}; cursor:pointer; flex:none; display:grid;
  place-items:center; color:{MUTED}; font-size:15px; }}
.clip:hover {{ border-color:{INK}; color:{INK}; }}
.hint {{ text-align:center; font-size:11.5px; color:{FAINT}; margin-top:8px; }}
.typing span {{ display:inline-block; width:6px; height:6px; margin-right:3px;
  border-radius:50%; background:{FAINT}; animation:b 1.2s infinite; }}
.typing span:nth-child(2) {{ animation-delay:.15s; }}
.typing span:nth-child(3) {{ animation-delay:.3s; }}
@keyframes b {{ 0%,60%,100% {{ opacity:.25 }} 30% {{ opacity:1 }} }}
"""

CHAT_JS = r"""
const thread = document.getElementById('thread');
const box = document.getElementById('msg');
const send = document.getElementById('send');
const file = document.getElementById('file');
let busy = false;

const esc = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;');

function md(t) {
  return esc(t).split(/\n{2,}/).map(b => {
    b = b.trim();
    if (!b) return '';
    b = b.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (/^#{1,4}\s/.test(b)) return '<h3>' + b.replace(/^#{1,4}\s/,'') + '</h3>';
    if (/^[-*]\s/m.test(b)) return '<ul>' + b.split('\n').filter(Boolean)
      .map(l => '<li>' + l.replace(/^[-*]\s/,'') + '</li>').join('') + '</ul>';
    return '<p style="margin:9px 0">' + b.replace(/\n/g,'<br>') + '</p>';
  }).join('');
}

function bubble(who, name, text, raw) {
  const mine = who === 'you';
  const el = document.createElement('div');
  el.className = 'msg ' + (mine ? 'mine' : 'theirs');
  const mark = mine ? (window.__ME || 'Y') : 'L';
  el.innerHTML = '<div class="who-b ' + who + '">' + esc(mark) + '</div>'
    + '<div class="bubble"><div class="name">' + esc(name) + '</div>'
    + '<div class="text">' + (raw ? raw : (mine ? esc(text) : md(text)))
    + '</div></div>';
  const empty = document.getElementById('empty');
  if (empty) empty.remove();
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

function grow() {
  box.style.height = 'auto';
  box.style.height = Math.min(box.scrollHeight, 190) + 'px';
  send.disabled = !box.value.trim();
}
box.addEventListener('input', grow);
box.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); }
});
document.querySelectorAll('.chip').forEach(c => {
  c.onclick = () => { box.value = c.dataset.q || c.textContent.trim();
    grow(); box.focus(); };
});

// A research question comes back as a question: which places to look. The
// sources answer different things and cost different amounts, so the choice
// is the owner's rather than a default nobody sees.
function askSources(query, list) {
  const rows = list.map(s => `
    <label class="src ${s.available ? '' : 'off'}">
      <input type="checkbox" value="${s.key}"
        ${s.default && s.available ? 'checked' : ''}
        ${s.available ? '' : 'disabled'}>
      <span><b>${esc(s.name)}</b>
      <span>${esc(s.available ? s.what : s.reason)}</span></span>
    </label>`).join('');
  const el = bubble('them', 'Your team', '', `
    <div class="picker">
      <h4>Where should I look?</h4>
      <div class="sub">Each one answers something different.</div>
      ${rows}
      <button class="btn" style="margin-top:11px;width:100%">Search these</button>
    </div>`);
  const btn = el.querySelector('button');
  btn.onclick = async () => {
    const chosen = [...el.querySelectorAll('input:checked')].map(i => i.value);
    if (!chosen.length) { btn.textContent = 'Pick at least one'; return; }
    const names = [...el.querySelectorAll('input:checked')]
      .map(i => i.closest('.src').querySelector('b').textContent);
    el.querySelector('.picker').outerHTML =
      '<div class="muted">Looking in: ' + esc(names.join(', ')) + '</div>';
    const wait = bubble('them', 'Your team', '',
      '<span class="typing"><span></span><span></span><span></span></span>');
    try {
      const r = await fetch('/api/research', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ query, sources: chosen })
      });
      const d = await r.json();
      wait.querySelector('.text').innerHTML = r.ok
        ? md(d.answer || 'Nothing came back.')
        : '<span style="color:#B91C1C">' + esc(d.error || 'Search failed') + '</span>';
    } catch (err) {
      wait.querySelector('.text').innerHTML =
        '<span style="color:#B91C1C">' + esc(String(err)) + '</span>';
    }
    busy = false;
  };
}

async function ask() {
  const text = box.value.trim();
  if (!text || busy) return;
  busy = true; send.disabled = true;
  bubble('you', 'You', text);
  box.value = ''; grow();

  const wait = bubble('them', 'Your team', '',
    '<span class="typing"><span></span><span></span><span></span></span>');
  try {
    const r = await fetch('/api/ask', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text })
    });
    const d = await r.json();
    const out = wait.querySelector('.text');
    if (d.ask_sources) {
      wait.remove();
      askSources(d.query, d.sources || []);
      return;                       // busy is cleared when they choose
    }
    if (!r.ok) {
      out.innerHTML = '<span style="color:#B91C1C">'
        + esc(d.error || 'That did not work.') + '</span>';
    } else {
      out.innerHTML = md(d.answer || 'Nothing came back.');
    }
  } catch (err) {
    wait.querySelector('.text').innerHTML =
      '<span style="color:#B91C1C">' + esc(String(err)) + '</span>';
  }
  busy = false; grow(); thread.scrollTop = thread.scrollHeight;
}
send.onclick = ask;

file.onchange = async () => {
  const f = file.files && file.files[0];
  if (!f || busy) return;
  busy = true;
  bubble('you', 'You', 'Sent a photo: ' + f.name);
  const wait = bubble('them', 'Your team', '',
    '<span class="typing"><span></span><span></span><span></span></span>');
  const form = new FormData();
  form.append('photo', f);
  try {
    const r = await fetch('/api/upload', { method: 'POST', body: form });
    const d = await r.json();
    wait.querySelector('.text').innerHTML = r.ok
      ? md(d.answer || 'Looked at it.')
      : '<span style="color:#B91C1C">' + esc(d.error || 'Upload failed') + '</span>';
  } catch (err) {
    wait.querySelector('.text').innerHTML =
      '<span style="color:#B91C1C">' + esc(String(err)) + '</span>';
  }
  file.value = ''; busy = false;
};
grow();
"""


HISTORY_CSS = f"""
.hist {{ margin-top:14px; border-top:1px solid {BORDER}; padding-top:12px;
  overflow-y:auto; min-height:0; }}
.hist h5 {{ margin:0 0 7px; font-size:11px; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase; color:{FAINT};
  padding:0 11px; display:flex; align-items:center; }}
.hist h5 a {{ margin-left:auto; font-size:11px; color:{ACCENT};
  font-weight:600; text-transform:none; letter-spacing:0; }}
.thr {{ display:flex; align-items:center; gap:6px; padding:7px 11px;
  border-radius:8px; font-size:13px; color:{BODY}; }}
.thr:hover {{ background:{SUNKEN}; color:{INK}; }}
.thr.on {{ background:{ACCENT_TINT}; color:{ACCENT}; font-weight:600; }}
.thr span {{ overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  flex:1; min-width:0; }}
.thr b {{ font-size:11px; font-weight:500; color:{FAINT}; }}
.thr.on b {{ color:{ACCENT}; }}
.hist .none {{ font-size:12px; color:{FAINT}; padding:2px 11px; }}
"""


def history_rail(threads: list[dict], current: int | None) -> str:
    """Past conversations, newest first — the owner's own words as the label."""
    if not threads:
        rows = "<div class='none'>Nothing yet. Ask something.</div>"
    else:
        rows = "".join(
            f"<a class='thr{' on' if t['id'] == current else ''}' "
            f"href='/chat/{t['id']}'>"
            f"<span>{e(t.get('title') or 'Untitled')}</span>"
            f"<b>{t.get('turns', 0)}</b></a>"
            for t in threads
        )
    # The ad studio sits here rather than in the rail: making a poster is
    # something you decide to do part-way through a conversation about what
    # to sell, not a place you set out for.
    return (
        f"<div class='hist'><h5>Conversations"
        f"<a href='/chat/new'>+ New</a></h5>{rows}"
        f"<h5 style='margin-top:16px'>Make something"
        f"<a href='/studio'>Open</a></h5>"
        f"<div class='none'>Turn a photo into a poster and ad copy.</div>"
        f"</div>"
    )


def chat_page(account: dict, history: list[dict], starters: list[str],
              threads: list[dict] | None = None,
              current: int | None = None) -> str:
    initials = (account or {}).get("initials") or "Y"
    if history:
        msgs = "".join(
            f"<div class='msg "
            f"{'mine' if m['role'] == 'user' else 'theirs'}'>"
            f"<div class='who-b "
            f"{'you' if m['role'] == 'user' else 'them'}'>"
            f"{e(initials if m['role'] == 'user' else 'L')}</div>"
            f"<div class='bubble'><div class='name'>"
            f"{'You' if m['role'] == 'user' else 'Your team'}</div>"
            f"<div class='text'>{e(m['text'])}</div></div></div>"
            for m in history
        )
    else:
        chips = "".join(
            f"<button class='chip' data-q='{e(s)}'>{e(s)}</button>"
            for s in starters
        )
        msgs = (
            f"<div class='empty' id='empty'>"
            f"<h2>What can your team do for you?</h2>"
            f"<p class='muted' style='max-width:460px;margin:0 auto'>"
            f"Ask anything about your shop, or send a photo of a product. "
            f"Nine specialists pick it up between them.</p>"
            f"<div class='chips'>{chips}</div></div>"
        )

    body = (
        f"<div class='thread' id='thread'><div class='wrap'>{msgs}</div></div>"
        f"<div class='composer'><div class='cbox'>"
        f"<div class='cinner'>"
        f"<textarea id='msg' rows='1' placeholder='Message your team…'>"
        f"</textarea>"
        f"<label class='clip' for='file' title='Send a product photo'>+"
        f"<input id='file' type='file' accept='image/*' hidden></label>"
        f"<button class='send' id='send' disabled title='Send'>&uarr;</button>"
        f"</div>"
        f"<div class='hint'>Enter to send · Shift+Enter for a new line · "
        f"nothing is published or paid for without your approval</div>"
        f"</div></div>"
    )
    # The owner's own mark, so the two speakers are told apart by initial
    # rather than by both being a "Y".
    js = f"window.__ME = {json.dumps(initials)};\n" + CHAT_JS
    return shell("Chat", account, "/", "", body, CHAT_CSS + HISTORY_CSS, js,
                 aside=history_rail(threads or [], current))


# ---------------------------------------------------------------------------
# Ad studio
# ---------------------------------------------------------------------------

STUDIO_CSS = f"""
.studio {{ display:grid; grid-template-columns:300px minmax(0,1fr) 250px;
  gap:18px; align-items:start; }}
.panel {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:16px;
  padding:16px 17px; }}
.panel h3 {{ margin:0 0 12px; font-size:13px; font-weight:600;
  letter-spacing:.02em; text-transform:uppercase; color:{MUTED}; }}
.stage {{ background:{SUNKEN}; border:1px solid {BORDER}; border-radius:16px;
  padding:16px; display:grid; place-items:center; min-height:460px; }}
#canvas {{ max-width:100%; max-height:70vh; border-radius:10px;
  box-shadow:0 2px 14px rgba(0,0,0,.10); background:#fff; cursor:default; }}
.ph {{ text-align:center; color:{MUTED}; font-size:13.5px; padding:40px 20px; }}
.tools {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:14px; }}
.tool {{ padding:8px 11px; border-radius:9px; border:1px solid {BORDER};
  background:{SURFACE}; font-size:12.5px; cursor:pointer; color:{BODY};
  display:inline-flex; align-items:center; gap:5px; }}
.tool:hover {{ border-color:{INK}; color:{INK}; }}
.tool.on {{ border-color:{ACCENT}; background:{ACCENT_TINT}; color:{ACCENT};
  font-weight:600; }}
.slider {{ margin-bottom:11px; }}
.slider label {{ display:flex; justify-content:space-between; font-size:12.5px;
  margin-bottom:5px; color:{BODY}; }}
.slider label b {{ font-weight:600; color:{INK}; font-variant-numeric:tabular-nums; }}
input[type=range] {{ width:100%; padding:0; accent-color:{ACCENT};
  height:4px; }}
.sizes {{ display:flex; gap:7px; margin-bottom:12px; }}
.size {{ flex:1; padding:8px 4px; border-radius:9px; border:1px solid {BORDER};
  background:{SURFACE}; font-size:12px; cursor:pointer; text-align:center; }}
.size.on {{ border-color:{ACCENT}; background:{ACCENT_TINT}; color:{ACCENT};
  font-weight:600; }}
.swatches {{ display:flex; flex-wrap:wrap; gap:6px; }}
.sw {{ width:24px; height:24px; border-radius:7px; cursor:pointer;
  border:2px solid transparent; }}
.sw.on {{ border-color:{INK}; }}
.copy {{ white-space:pre-wrap; font-size:13.5px; line-height:1.65; }}
.gauge {{ margin-top:7px; font-size:11.5px; color:{MUTED}; line-height:1.5; }}
.bar {{ height:3px; border-radius:2px; background:{SUNKEN}; overflow:hidden;
  margin-bottom:5px; }}
.bar span {{ display:block; height:100%; width:0; border-radius:2px;
  background:{MUTED}; transition:width .18s, background .18s; }}
.tag {{ font-size:11px; font-weight:600; letter-spacing:.05em;
  text-transform:uppercase; padding:3px 8px; border-radius:6px;
  background:{ACCENT_TINT}; color:{ACCENT}; }}
.layer {{ display:flex; align-items:center; gap:8px; padding:7px 9px;
  border-radius:8px; font-size:12.5px; cursor:pointer; }}
.layer:hover {{ background:{SUNKEN}; }}
.layer.on {{ background:{ACCENT_TINT}; color:{ACCENT}; }}
.layer button {{ margin-left:auto; border:none; background:none; cursor:pointer;
  color:{MUTED}; font-size:14px; }}
.row2 {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
@media (max-width:1200px) {{ .studio {{ grid-template-columns:1fr; }} }}
"""

STUDIO_JS = r"""
// ---- state ---------------------------------------------------------------
// One object describing the whole picture. Every tool mutates it and calls
// draw(); nothing is baked into the pixels until the owner downloads, so any
// edit can be undone by changing the number back.
const S = {
  img: null, preset: 'square', seed: null, prompt: '',
  rotate: 0, flipH: false, flipV: false,
  crop: 1,                       // 1 = full frame, 0.5 = centre half
  filters: { brightness:100, contrast:100, saturate:100, sepia:0, grayscale:0, blur:0 },
  shapes: [], sel: -1, tool: 'select', colour: '#7B1E22'
};
const cv = document.getElementById('canvas');
const ctx = cv.getContext('2d');
const stage = document.getElementById('stage');

function filterString() {
  const f = S.filters;
  return `brightness(${f.brightness}%) contrast(${f.contrast}%) ` +
         `saturate(${f.saturate}%) sepia(${f.sepia}%) ` +
         `grayscale(${f.grayscale}%) blur(${f.blur}px)`;
}

function draw() {
  if (!S.img) return;
  const iw = S.img.naturalWidth, ih = S.img.naturalHeight;
  // Crop is a centred box; rotation of 90/270 swaps which side is which.
  const cw = iw * S.crop, ch = ih * S.crop;
  const sx = (iw - cw) / 2, sy = (ih - ch) / 2;
  const turned = S.rotate === 90 || S.rotate === 270;
  cv.width = turned ? ch : cw;
  cv.height = turned ? cw : ch;

  ctx.save();
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.translate(cv.width / 2, cv.height / 2);
  ctx.rotate(S.rotate * Math.PI / 180);
  ctx.scale(S.flipH ? -1 : 1, S.flipV ? -1 : 1);
  ctx.filter = filterString();
  ctx.drawImage(S.img, sx, sy, cw, ch, -cw / 2, -ch / 2, cw, ch);
  ctx.restore();

  // Shapes sit above the photo, so they are never filtered with it.
  ctx.save();
  ctx.filter = 'none';
  S.shapes.forEach((s, i) => {
    ctx.globalAlpha = s.alpha === undefined ? 1 : s.alpha;
    ctx.fillStyle = s.colour;
    ctx.strokeStyle = s.colour;
    if (s.type === 'rect') {
      ctx.fillRect(s.x * cv.width, s.y * cv.height,
                   s.w * cv.width, s.h * cv.height);
    } else if (s.type === 'circle') {
      ctx.beginPath();
      ctx.ellipse(s.x * cv.width, s.y * cv.height,
                  s.w * cv.width / 2, s.h * cv.height / 2, 0, 0, Math.PI * 2);
      ctx.fill();
    } else if (s.type === 'bar') {
      ctx.fillRect(0, s.y * cv.height, cv.width, s.h * cv.height);
    } else if (s.type === 'text') {
      const px = Math.round((s.size || 0.07) * cv.height);
      ctx.font = `800 ${px}px Inter, system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(s.text || '', s.x * cv.width, s.y * cv.height);
    }
    if (i === S.sel) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#000';
      ctx.setLineDash([6, 4]);
      ctx.lineWidth = 2;
      const w = (s.type === 'bar' ? 1 : s.w) * cv.width;
      const x = (s.type === 'bar' ? 0.5 : s.x) * cv.width;
      ctx.strokeRect(x - w / 2, s.y * cv.height - (s.h * cv.height) / 2,
                     w, s.h * cv.height);
      ctx.setLineDash([]);
    }
  });
  ctx.restore();
  renderLayers();
}

// ---- loading a picture ---------------------------------------------------
function load(src) {
  const im = new Image();
  im.crossOrigin = 'anonymous';
  im.onload = () => {
    S.img = im;
    document.getElementById('ph').style.display = 'none';
    cv.style.display = 'block';
    document.getElementById('exportRow').style.display = 'flex';
    draw();
  };
  im.onerror = () => msg('That image could not be loaded.', true);
  im.src = src;
}

function msg(t, bad) {
  const el = document.getElementById('note');
  el.textContent = t;
  el.style.color = bad ? '#B91C1C' : '#71717A';
}

// ---- generate / regenerate ----------------------------------------------
async function generate(newSeed) {
  const product = document.getElementById('product').value.trim();
  if (!product) { document.getElementById('product').focus(); return; }
  const btn = document.getElementById('go');
  const again = document.getElementById('again');
  btn.disabled = true; again.disabled = true;
  btn.textContent = 'Drawing…';
  msg('Drawing your picture — a few seconds.');
  if (newSeed) S.seed = Math.floor(Math.random() * 1e9);

  try {
    const r = await fetch('/api/studio/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        product,
        detail: document.getElementById('detail').value.trim(),
        offer: document.getElementById('offer').value.trim(),
        audience: document.getElementById('audience').value.trim(),
        style: document.getElementById('style').value,
        preset: S.preset, seed: S.seed
      })
    });
    const d = await r.json();
    if (!r.ok || !d.image) {
      msg(d.error || d.image_error || 'Could not draw it.', true);
    } else {
      load(d.image);
      again.style.display = 'inline-block';
      msg('Drawn by ' + (d.provider || 'AI') + '. Edit it on the right.');
      if (d.copy_html) {
        document.getElementById('copy').innerHTML =
          '<div class="copy">' + d.copy_html + '</div>';
      }
    }
  } catch (err) { msg(String(err), true); }
  btn.disabled = false; again.disabled = false; btn.textContent = 'Draw it';
}
// How long a description should be, in words. Below the floor the model
// fills the gaps with whatever is generic; above the ceiling the later words
// stop getting attention, so the setting you cared about is the part dropped.
const WORDS_MIN = 8, WORDS_GOOD = 14, WORDS_MAX = 25;
const detail = document.getElementById('detail');
const gfill = document.getElementById('gfill');
const gtext = document.getElementById('gtext');

function gauge() {
  const words = detail.value.trim().split(/\s+/).filter(Boolean).length;
  const pct = Math.min(100, (words / WORDS_MAX) * 100);
  gfill.style.width = pct + '%';
  if (!words) {
    gfill.style.background = '#71717A';
    gtext.textContent = 'Add 8-25 words. Too few and it invents the rest; ' +
      'too many and the end gets ignored.';
  } else if (words < WORDS_MIN) {
    gfill.style.background = '#A16207';
    gtext.textContent = words + ' words — a bit thin. Say the colour, the ' +
      'material and what it sits on.';
  } else if (words <= WORDS_MAX) {
    gfill.style.background = '#7B1E22';
    gtext.textContent = words + ' words — good length for a clear picture.';
  } else {
    gfill.style.background = '#A16207';
    gtext.textContent = words + ' words — past 25 the last ones stop ' +
      'counting. Trim it to the details that matter most.';
  }
}
detail.addEventListener('input', gauge);
gauge();

document.getElementById('go').onclick = () => generate(true);
document.getElementById('again').onclick = () => generate(true);

// ---- uploading your own photo -------------------------------------------
document.getElementById('up').onchange = async (ev) => {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  msg('Loading your photo…');
  const form = new FormData();
  form.append('photo', f);
  try {
    const r = await fetch('/api/studio/upload', { method: 'POST', body: form });
    const d = await r.json();
    if (!r.ok) { msg(d.error || 'Upload failed', true); return; }
    load(d.image);
    document.getElementById('again').style.display = 'none';
    msg('Your own photo — edit it on the right.');
  } catch (err) { msg(String(err), true); }
  ev.target.value = '';
};

// ---- tools ---------------------------------------------------------------
document.querySelectorAll('[data-rot]').forEach(b => b.onclick = () => {
  S.rotate = (S.rotate + Number(b.dataset.rot) + 360) % 360; draw();
});
document.getElementById('flipH').onclick = () => { S.flipH = !S.flipH; draw(); };
document.getElementById('flipV').onclick = () => { S.flipV = !S.flipV; draw(); };

document.querySelectorAll('[data-filter]').forEach(inp => {
  inp.oninput = () => {
    S.filters[inp.dataset.filter] = Number(inp.value);
    inp.parentElement.querySelector('b').textContent =
      inp.value + (inp.dataset.filter === 'blur' ? 'px' : '%');
    draw();
  };
});
document.getElementById('crop').oninput = (e) => {
  S.crop = Number(e.target.value) / 100;
  e.target.parentElement.querySelector('b').textContent = e.target.value + '%';
  draw();
};

document.querySelectorAll('[data-preset]').forEach(b => b.onclick = () => {
  document.querySelectorAll('[data-preset]').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); S.preset = b.dataset.preset;
});
document.querySelectorAll('.sw').forEach(b => b.onclick = () => {
  document.querySelectorAll('.sw').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); S.colour = b.dataset.c;
  if (S.sel >= 0) { S.shapes[S.sel].colour = S.colour; draw(); }
});

// ---- shapes and text -----------------------------------------------------
document.querySelectorAll('[data-shape]').forEach(b => b.onclick = () => {
  if (!S.img) { msg('Make or upload a picture first.', true); return; }
  const kind = b.dataset.shape;
  if (kind === 'text') {
    const t = prompt('What should it say?', 'Fresh today');
    if (!t) return;
    S.shapes.push({ type:'text', text:t, x:.5, y:.15, w:.8, h:.12,
                    size:.075, colour:S.colour, alpha:1 });
  } else if (kind === 'bar') {
    S.shapes.push({ type:'bar', x:.5, y:.88, w:1, h:.14,
                    colour:S.colour, alpha:.88 });
  } else {
    S.shapes.push({ type:kind, x:.5, y:.5, w:.3, h:.3,
                    colour:S.colour, alpha:.85 });
  }
  S.sel = S.shapes.length - 1;
  draw();
});

function renderLayers() {
  const box = document.getElementById('layers');
  if (!S.shapes.length) {
    box.innerHTML = '<p class="muted" style="font-size:12.5px;margin:0">' +
      'Nothing added yet.</p>';
    return;
  }
  box.innerHTML = S.shapes.map((s, i) =>
    '<div class="layer' + (i === S.sel ? ' on' : '') + '" data-i="' + i + '">' +
    '<span style="width:12px;height:12px;border-radius:4px;background:' +
    s.colour + '"></span>' +
    (s.type === 'text' ? ('“' + (s.text || '').slice(0, 14) + '”') : s.type) +
    '<button data-del="' + i + '" title="Remove">&times;</button></div>').join('');
  box.querySelectorAll('.layer').forEach(l => l.onclick = (ev) => {
    if (ev.target.dataset.del !== undefined) {
      S.shapes.splice(Number(ev.target.dataset.del), 1); S.sel = -1;
    } else { S.sel = Number(l.dataset.i); }
    draw();
  });
}

// Drag the selected shape around the canvas.
let drag = false;
cv.addEventListener('pointerdown', (ev) => {
  if (S.sel < 0) return;
  drag = true; cv.setPointerCapture(ev.pointerId);
});
cv.addEventListener('pointermove', (ev) => {
  if (!drag || S.sel < 0) return;
  const r = cv.getBoundingClientRect();
  S.shapes[S.sel].x = (ev.clientX - r.left) / r.width;
  S.shapes[S.sel].y = (ev.clientY - r.top) / r.height;
  draw();
});
cv.addEventListener('pointerup', () => { drag = false; });

document.getElementById('reset').onclick = () => {
  S.rotate = 0; S.flipH = S.flipV = false; S.crop = 1; S.shapes = []; S.sel = -1;
  S.filters = { brightness:100, contrast:100, saturate:100, sepia:0,
                grayscale:0, blur:0 };
  document.querySelectorAll('[data-filter]').forEach(i => {
    i.value = i.dataset.filter === 'brightness' || i.dataset.filter === 'contrast'
      || i.dataset.filter === 'saturate' ? 100 : 0;
    i.parentElement.querySelector('b').textContent = i.value +
      (i.dataset.filter === 'blur' ? 'px' : '%');
  });
  const c = document.getElementById('crop');
  c.value = 100; c.parentElement.querySelector('b').textContent = '100%';
  draw();
};

document.getElementById('dl').onclick = () => {
  if (!S.img) return;
  const a = document.createElement('a');
  a.download = 'lucida-ad.png';
  a.href = cv.toDataURL('image/png');
  a.click();
};
"""


def studio_page(account: dict, provider: str, channels: dict,
                note: str = "") -> str:
    head = (
        "<div class='head'><h1>Ad studio</h1>"
        "<p>Draw a picture or upload your own, then crop it, colour it and "
        "put your words on it.</p></div>"
    )
    where = " · ".join(
        f"{k.title()} {'connected' if 'needs' not in v else 'not connected'}"
        for k, v in channels.items()
    )

    def slider(key, label, lo, hi, val, unit="%"):
        return (
            f"<div class='slider'><label>{e(label)}<b>{val}{unit}</b></label>"
            f"<input type='range' data-filter='{key}' min='{lo}' max='{hi}' "
            f"value='{val}'></div>"
        )

    swatches = "".join(
        f"<div class='sw{' on' if c == '#7B1E22' else ''}' data-c='{c}' "
        f"style='background:{c}'></div>"
        for c in ("#7B1E22", "#000000", "#FFFFFF", "#A16207", "#B91C1C",
                  "#1D4ED8", "#15803D", "#71717A")
    )

    body = (
        f"<div class='body'><div class='studio'>"

        # ---- left: what to draw -------------------------------------
        f"<div class='panel'><h3>What to draw</h3>"
        f"<div class='field'><label for='product'>Product</label>"
        f"<input id='product' placeholder='handmade resin coasters'></div>"
        f"<div class='field'><label for='detail'>Describe it"
        f"<span class='muted' style='font-weight:400'> — colour, material, "
        f"shape, what it sits on</span></label>"
        f"<textarea id='detail' rows='3' maxlength='200' "
        f"placeholder='deep teal with gold flecks, square, on a light oak "
        f"table'></textarea>"
        f"<div class='gauge'><div class='bar'><span id='gfill'></span></div>"
        f"<span id='gtext'>Add 8-25 words. Too few and it invents the rest; "
        f"too many and the end gets ignored.</span></div></div>"
        f"<div class='field'><label for='style'>Look</label><select id='style'>"
        f"<option value='clean studio lighting, soft shadow, plain background'>"
        f"Clean studio</option>"
        f"<option value='warm natural window light, lifestyle scene'>"
        f"Warm lifestyle</option>"
        f"<option value='bold flat colour background, graphic poster'>"
        f"Bold graphic</option>"
        f"<option value='rustic wooden surface, cosy, warm tones'>Rustic</option>"
        f"<option value='dark moody background, dramatic side light'>"
        f"Dark and moody</option></select></div>"
        f"<label>Size</label><div class='sizes'>"
        f"<div class='size on' data-preset='square'>Post<br>"
        f"<span class='muted' style='font-size:10.5px'>1:1</span></div>"
        f"<div class='size' data-preset='story'>Story<br>"
        f"<span class='muted' style='font-size:10.5px'>9:16</span></div>"
        f"<div class='size' data-preset='wide'>Wide<br>"
        f"<span class='muted' style='font-size:10.5px'>16:9</span></div></div>"
        f"<div class='row2'>"
        f"<button class='btn' id='go'>Draw it</button>"
        f"<button class='btn btn-quiet' id='again' style='display:none'>"
        f"Try again</button></div>"
        f"<div style='margin-top:10px'>"
        f"<label class='btn btn-quiet' for='up' style='display:block;"
        f"text-align:center;cursor:pointer'>Upload my own photo"
        f"<input id='up' type='file' accept='image/*' hidden></label></div>"
        f"<p class='muted' id='note' style='margin:12px 0 0;font-size:12.5px'>"
        f"Drawn by {e(provider)}.</p>"
        + (f"<div style='margin-top:10px;padding:11px 12px;border-radius:11px;"
           f"background:{AMBER_TINT};color:{AMBER};font-size:12.5px;"
           f"line-height:1.55'>{e(note)}</div>" if note else "")
        + f"<div class='field' style='margin-top:14px'>"
        f"<label for='offer'>Offer <span class='muted'>(for the words)</span>"
        f"</label><input id='offer' placeholder='2 for 1 this week'></div>"
        f"<div class='field' style='margin-bottom:0'><label for='audience'>"
        f"Who it's for</label>"
        f"<input id='audience' placeholder='students in Dhaka'></div>"
        f"</div>"

        # ---- middle: the picture -------------------------------------
        f"<div><div class='stage' id='stage'>"
        f"<div class='ph' id='ph'>Your picture appears here.<br>"
        f"Draw one on the left, or upload your own.</div>"
        f"<canvas id='canvas' style='display:none'></canvas></div>"
        f"<div id='exportRow' style='display:none;gap:9px;margin-top:12px'>"
        f"<button class='btn' id='dl'>Download</button>"
        f"<button class='btn btn-quiet' id='reset'>Undo all edits</button>"
        f"</div>"
        f"<div class='card' style='margin-top:16px'><span class='tag'>"
        f"Ad copy</span><div id='copy' style='margin-top:12px'>"
        f"<p class='muted' style='margin:0'>Words for Facebook, Instagram and "
        f"YouTube appear here once you draw something.</p></div></div>"
        f"<p class='muted' style='margin-top:12px;font-size:12.5px'>"
        f"Posting goes to: {e(where)} · "
        f"<a href='/connect' style='text-decoration:underline'>connect an "
        f"account</a>. Generated artwork is not a photograph of your stock — "
        f"say so if a customer asks.</p></div>"

        # ---- right: the tools ----------------------------------------
        f"<div class='panel'><h3>Edit</h3>"
        f"<div class='tools'>"
        f"<button class='tool' data-rot='-90'>&#8630; Left</button>"
        f"<button class='tool' data-rot='90'>&#8631; Right</button>"
        f"<button class='tool' id='flipH'>&#8646; Flip</button>"
        f"<button class='tool' id='flipV'>&#8645; Flip</button></div>"

        f"<div class='slider'><label>Crop in<b>100%</b></label>"
        f"<input type='range' id='crop' min='30' max='100' value='100'></div>"

        f"<h3 style='margin-top:16px'>Filters</h3>"
        + slider("brightness", "Brightness", 40, 180, 100)
        + slider("contrast", "Contrast", 40, 200, 100)
        + slider("saturate", "Colour", 0, 250, 100)
        + slider("sepia", "Warmth", 0, 100, 0)
        + slider("grayscale", "Black and white", 0, 100, 0)
        + slider("blur", "Blur", 0, 12, 0, "px")
        +
        f"<h3 style='margin-top:16px'>Add</h3><div class='tools'>"
        f"<button class='tool' data-shape='text'>Text</button>"
        f"<button class='tool' data-shape='bar'>Banner</button>"
        f"<button class='tool' data-shape='rect'>Box</button>"
        f"<button class='tool' data-shape='circle'>Circle</button></div>"
        f"<label style='margin-top:6px'>Colour</label>"
        f"<div class='swatches'>{swatches}</div>"
        f"<h3 style='margin-top:16px'>Layers</h3>"
        f"<div id='layers'><p class='muted' style='font-size:12.5px;margin:0'>"
        f"Nothing added yet.</p></div>"
        f"<p class='muted' style='margin:12px 0 0;font-size:12px'>"
        f"Pick a layer, then drag on the picture to move it.</p>"
        f"</div>"

        f"</div></div>"
    )
    return shell("Ad studio", account, "/studio", head, body,
                 STUDIO_CSS, STUDIO_JS)







# ---------------------------------------------------------------------------
# Admin — the operator's view of the whole service
# ---------------------------------------------------------------------------

ADMIN_CSS = f"""
.kpis {{ display:grid; gap:12px; margin-bottom:18px;
  grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); }}
.kpi {{ border:1px solid {BORDER}; border-radius:14px; padding:15px 17px;
  background:{SURFACE}; }}
.kpi small {{ display:block; font-size:11.5px; color:{MUTED};
  letter-spacing:.03em; text-transform:uppercase; }}
.kpi b {{ display:block; font-size:25px; font-weight:700; margin-top:5px;
  letter-spacing:-.03em; }}
.kpi span {{ display:block; font-size:12px; color:{MUTED}; margin-top:2px; }}

.spark {{ display:flex; align-items:flex-end; gap:4px; height:52px;
  margin-top:10px; }}
.spark i {{ flex:1; background:{ACCENT_TINT}; border-radius:3px 3px 0 0;
  min-height:2px; position:relative; }}
.spark i.has {{ background:{ACCENT}; }}

.utable {{ width:100%; border-collapse:collapse; font-size:13px; }}
.utable th {{ text-align:left; font-size:11px; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase; color:{FAINT};
  padding:0 12px 9px 0; white-space:nowrap; }}
.utable td {{ padding:11px 12px 11px 0; border-top:1px solid {BORDER};
  vertical-align:top; }}
.utable td:last-child, .utable th:last-child {{ padding-right:0;
  text-align:right; }}
.biz {{ font-weight:600; }}
.biz small {{ display:block; font-weight:400; color:{MUTED}; font-size:12px;
  margin-top:2px; overflow-wrap:anywhere; }}
.num {{ font-variant-numeric:tabular-nums; }}
.quiet {{ color:{FAINT}; }}
.privacy {{ border:1px solid {BORDER}; border-left:3px solid {ACCENT};
  border-radius:12px; padding:13px 16px; background:{RAIL};
  font-size:13px; color:{BODY}; line-height:1.6; margin-bottom:18px;
  max-width:900px; }}
.scroller {{ overflow-x:auto; border:1px solid {BORDER}; border-radius:16px;
  padding:16px 18px; background:{SURFACE}; }}
"""


def _bytes(n: int) -> str:
    if n > 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{max(0, n) // 1024} KB"


def admin_page(account: dict, data: dict) -> str:
    """Who is on the service, and how much of it they are using."""
    t = data["totals"]
    peak = max([s["n"] for s in data["signups"]] + [1])

    spark = "".join(
        f"<i class='{'has' if s['n'] else ''}' "
        f"style='height:{max(4, round(s['n'] / peak * 100))}%' "
        f"title='{e(s['day'])}: {s['n']} signup(s)'></i>"
        for s in data["signups"]
    )

    kpis = (
        f"<div class='kpi'><small>Accounts</small><b>{t['accounts']}</b>"
        f"<span>{t['verified']} verified · {t['dormant']} never started</span>"
        f"</div>"
        f"<div class='kpi'><small>Active this week</small><b>{t['active7']}</b>"
        f"<span>{t['active30']} in the last 30 days</span></div>"
        f"<div class='kpi'><small>Sales recorded</small>"
        f"<b>{t['sales']:,.0f}</b><span>across {t['orders']} order(s)</span>"
        f"</div>"
        f"<div class='kpi'><small>Products</small><b>{t['products']}</b>"
        f"<span>{t['connections']} channel(s) connected</span></div>"
        f"<div class='kpi'><small>Customer messages</small>"
        f"<b>{t['messages']}</b><span>{t['conversations']} chat thread(s)"
        f"</span></div>"
        f"<div class='kpi'><small>Storage</small><b>{_bytes(t['bytes'])}</b>"
        f"<span>all shops together</span></div>"
    )

    rows = ""
    for a in data["accounts"]:
        marks = []
        if not a["verified"]:
            marks.append("<span class='pill warn'>unverified</span>")
        if a["dormant"]:
            marks.append("<span class='pill warn'>never started</span>")
        if a.get("auth_provider") == "google":
            marks.append("<span class='pill ok'>google</span>")
        rows += (
            f"<tr>"
            f"<td><div class='biz'>{e(a.get('business_name') or 'No name yet')}"
            f"<small>{e(a.get('email'))}</small></div></td>"
            f"<td>{e(a.get('owner_name') or '—')}<br>"
            f"<span class='quiet' style='font-size:12px'>"
            f"{e(a.get('location') or '—')}</span></td>"
            f"<td>{e(a.get('business_stage') or '—')}<br>"
            f"<span class='quiet' style='font-size:12px'>"
            f"joined {e(a['joined'])}</span></td>"
            f"<td>{e(a['last_seen'])}</td>"
            f"<td class='num'>{a['products']}</td>"
            f"<td class='num'>{a['orders']}</td>"
            f"<td class='num'>{a['sales']:,.0f}</td>"
            f"<td class='num'>{a['messages']}</td>"
            f"<td class='num'>{a['connections']}</td>"
            f"<td class='num'>{_bytes(a['bytes'])}</td>"
            f"<td>{' '.join(marks)}</td>"
            f"</tr>"
        )

    head = (
        "<div class='head'><h1>Service admin</h1>"
        "<p>Every shop on this installation, what it is using, and whether "
        "it came back after signing up.</p></div>"
    )
    body = (
        f"<div class='body'>"
        f"<div class='privacy'><b>What this page deliberately does not "
        f"show.</b> Counts only — never the contents of a shop's business. "
        f"No customer message, no drafted reply, no product description, no "
        f"access token is read to build this. You can see that a shop has "
        f"{t['messages']} messages; you cannot read one.</div>"
        f"<div class='kpis'>{kpis}</div>"
        f"<div class='scroller' style='margin-bottom:18px'>"
        f"<b style='font-size:14px'>Signups, last 14 days</b>"
        f"<div class='spark'>{spark}</div></div>"
        f"<div class='scroller'>"
        f"<table class='utable'>"
        f"<tr><th>Business</th><th>Owner</th><th>Stage</th><th>Last seen</th>"
        f"<th>Products</th><th>Orders</th><th>Sales</th><th>Msgs</th>"
        f"<th>Channels</th><th>Data</th><th></th></tr>"
        f"{rows}</table></div>"
        f"</div>"
    )
    return shell("Admin", account, "/admin", head, body, ADMIN_CSS)

# ---------------------------------------------------------------------------
# Workforce — the graph, live, and a way to hand out work
# ---------------------------------------------------------------------------

# Where each specialist sits. A star: the supervisor routes everything, so it
# belongs in the middle and the eight sit around it at even angles.
# A card is about 11% of the stage tall, so nothing sits closer than 13% to
# an edge — at 96% the Customers card was cut off by the frame.
TEAM = [
    ("supervisor", "Supervisor", "Routes the work and holds your gates", 50, 50),
    ("vision", "Product Vision", "Reads photos of what you sell", 50, 14),
    ("market", "Market Research", "What sells, and what rivals charge", 17, 27),
    ("pricing", "Pricing", "What to charge and what you keep", 83, 27),
    ("inventory", "Stock", "What you have and when it runs out", 85, 57),
    ("ads", "Ad Creative", "Writes and publishes the ads", 71, 84),
    ("engage", "Customers", "Reads messages, drafts the replies", 50, 87),
    ("delivery", "Delivery", "Quotes and books the courier", 29, 84),
    ("report", "Reporting", "Writes the day up for you", 15, 57),
]

WORKFORCE_CSS = f"""
.wf {{ display:grid; grid-template-columns:minmax(0,1.55fr) minmax(300px,1fr);
  gap:18px; align-items:start; max-width:1280px; }}
.stage {{ position:relative; width:100%; aspect-ratio:10/7; background:{RAIL};
  border:1px solid {BORDER}; border-radius:18px; overflow:hidden; }}
/* Above the wires. They are appended to the same box after the nodes, so
   without this the lines sit on top and swallow the click that is meant to
   pick a specialist. */
.node {{ position:absolute; transform:translate(-50%,-50%); width:20%;
  min-width:124px; padding:9px 11px; border-radius:12px; background:{SURFACE};
  border:1px solid {BORDER}; box-shadow:0 1px 2px rgba(0,0,0,.05);
  cursor:pointer; z-index:2; transition:border-color .18s, box-shadow .18s,
  transform .18s; }}
.node:hover {{ border-color:{INK}; transform:translate(-50%,-50%) scale(1.03); }}
.node.on {{ border-color:{ACCENT}; background:{ACCENT_TINT};
  box-shadow:0 3px 14px rgba(123,30,34,.18); }}
.node.used {{ border-color:#F0D6D6; }}
.node.picked {{ border-color:{INK}; box-shadow:0 0 0 3px rgba(0,0,0,.08); }}
.node b {{ display:flex; align-items:center; gap:6px; font-size:12.5px;
  font-weight:600; letter-spacing:-.01em; }}
.node small {{ display:block; font-size:11px; color:{MUTED}; margin-top:3px;
  line-height:1.35; }}
.dot {{ width:7px; height:7px; border-radius:50%; background:#D4D4D8;
  flex:none; }}
.node.used .dot {{ background:{FAINT}; }}
.node.on .dot {{ background:{ACCENT}; animation:pulse 1.1s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:.25 }} }}
.wire {{ position:absolute; height:1px; background:#E7E7EA;
  transform-origin:0 50%; z-index:0; pointer-events:none; }}
.wire.live {{ height:2px; background:{ACCENT}; border-radius:2px; }}
.hop {{ position:absolute; z-index:1; pointer-events:none;
  transform:translate(-50%,-50%); width:20px;
  height:20px; border-radius:50%; display:grid; place-items:center;
  font-size:11px; font-weight:700; background:{SURFACE}; color:{ACCENT};
  border:1px solid #C4879A; }}
.hop.live {{ background:{ACCENT}; color:#fff; border-color:{ACCENT}; }}

.wfbar {{ display:flex; align-items:center; gap:10px; margin-bottom:12px;
  flex-wrap:wrap; }}
.state {{ display:inline-flex; align-items:center; gap:7px; font-size:13px;
  font-weight:500; padding:5px 11px; border-radius:999px;
  background:{SUNKEN}; color:{BODY}; }}
.state .dot {{ width:8px; height:8px; }}
.state.busy {{ background:{ACCENT_TINT}; color:{ACCENT}; }}
.state.busy .dot {{ background:{ACCENT}; animation:pulse 1.1s infinite; }}

.feed {{ border:1px solid {BORDER}; border-radius:16px; background:{SURFACE};
  overflow:hidden; }}
.feed h3 {{ margin:0; padding:14px 16px; font-size:14px; font-weight:600;
  border-bottom:1px solid {BORDER}; display:flex; align-items:center;
  gap:8px; }}
.feed .rows {{ max-height:340px; overflow-y:auto; }}
.ev {{ display:grid; grid-template-columns:52px minmax(0,1fr); gap:10px;
  padding:10px 16px; border-bottom:1px solid {SUNKEN}; font-size:12.5px; }}
.ev:last-child {{ border-bottom:none; }}
.ev time {{ color:{FAINT}; font-variant-numeric:tabular-nums; }}
.ev b {{ display:block; font-weight:600; font-size:12px; }}
.ev span {{ color:{MUTED}; line-height:1.5; overflow-wrap:anywhere; }}
.ev.warn b {{ color:{AMBER}; }}
.ev.error b {{ color:{DANGER}; }}
.ev .none {{ color:{MUTED}; }}

.assign {{ border:1px solid {BORDER}; border-radius:16px; padding:18px;
  background:{SURFACE}; margin-bottom:16px; }}
.assign h3 {{ margin:0 0 3px; font-size:14px; font-weight:600; }}
.assign p {{ margin:0 0 12px; font-size:12.5px; color:{MUTED};
  line-height:1.55; }}
.who-pill {{ display:inline-flex; align-items:center; gap:6px;
  background:{ACCENT_TINT}; color:{ACCENT}; font-size:12px; font-weight:600;
  padding:4px 10px; border-radius:999px; margin-bottom:10px; }}
/* The cards are a percentage of the frame, but a minimum width in pixels —
   so on a narrow screen that minimum is a third of the frame and the ring
   spills out of it. Below these widths the cards shrink instead, and the
   frame grows taller to keep them apart. */
@media (max-width: 1100px) {{
  .wf {{ grid-template-columns:minmax(0,1fr); }}
  .stage {{ aspect-ratio:10/8; }}
  .node {{ min-width:106px; width:22%; padding:8px 9px; }}
  .node small {{ font-size:10px; }}
}}
@media (max-width: 620px) {{
  .stage {{ aspect-ratio:10/11; }}
  .node {{ min-width:0; width:30%; padding:7px 8px; }}
  .node b {{ font-size:11px; }}
  .node small {{ display:none; }}
}}
"""

WORKFORCE_JS = """
const NODES = window.__TEAM;
const $ = (id) => document.getElementById(id);
let picked = null;
const used = new Set();
const hops = [];

/* The fixed topology behind everything: the supervisor reaches all eight.
   Drawn once, in CSS rather than SVG, so an unbound template is never a
   console error and the whole thing scales with the box. */
function wires() {
  const stage = $('stage');
  const hub = NODES[0];
  NODES.slice(1).forEach((n) => {
    const el = document.createElement('div');
    el.className = 'wire';
    place(el, hub, n);
    stage.appendChild(el);
  });
}

function place(el, a, b, thick) {
  const box = $('stage').getBoundingClientRect();
  const dx = (b.x - a.x) / 100 * box.width;
  const dy = (b.y - a.y) / 100 * box.height;
  el.style.left = a.x + '%';
  el.style.top = a.y + '%';
  el.style.width = Math.sqrt(dx * dx + dy * dy) + 'px';
  el.style.transform = 'rotate(' + (Math.atan2(dy, dx) * 180 / Math.PI) + 'deg)';
}

function nodeById(id) { return NODES.find((n) => n.id === id); }

/* A handoff arrives: draw it, number it, and mark both ends as used. */
function addHop(fromId, toId) {
  const a = nodeById(fromId), b = nodeById(toId);
  if (!a || !b) return;
  document.querySelectorAll('.wire.live').forEach((w) => w.classList.remove('live'));
  const wire = document.createElement('div');
  wire.className = 'wire live';
  place(wire, a, b);
  $('stage').appendChild(wire);

  const badge = document.createElement('div');
  badge.className = 'hop live';
  badge.textContent = String(hops.length + 1);
  badge.style.left = ((a.x + b.x) / 2) + '%';
  badge.style.top = ((a.y + b.y) / 2) + '%';
  $('stage').appendChild(badge);
  document.querySelectorAll('.hop').forEach((h, i, all) => {
    if (i < all.length - 1) h.classList.remove('live');
  });
  hops.push([fromId, toId]);
}

function markBusy(id) {
  document.querySelectorAll('.node.on').forEach((n) => n.classList.remove('on'));
  const el = $('n-' + id);
  if (el) { el.classList.add('on'); el.classList.add('used'); used.add(id); }
}

function setState(busy, text) {
  const s = $('runstate');
  s.className = 'state' + (busy ? ' busy' : '');
  s.innerHTML = '<span class="dot"></span>' + text;
}

function logEvent(e) {
  const rows = $('rows');
  const none = rows.querySelector('.none');
  if (none) none.remove();
  const div = document.createElement('div');
  div.className = 'ev' + (e.level === 'error' ? ' error'
    : e.level === 'warning' ? ' warn' : '');
  div.innerHTML = '<time>' + (e.at || '') + '</time><div><b>'
    + (e.actor || 'workforce').replace(/_/g, ' ') + '</b><span>'
    + (e.summary || e.kind) + '</span></div>';
  rows.insertBefore(div, rows.firstChild);
  while (rows.children.length > 60) rows.removeChild(rows.lastChild);
}

/* One connection, held open, pushing each step as it is recorded. */
function listen() {
  const src = new EventSource('/api/events');
  src.onmessage = (m) => {
    const e = JSON.parse(m.data);
    logEvent(e);
    if (e.node) markBusy(e.node);
    if (e.kind === 'handoff' && e.to) addHop(e.node || 'supervisor', e.to);
    if (e.kind === 'session_start') setState(true, 'Working');
    if (e.kind === 'agent_start') setState(true, (e.actor || '').replace(/_/g, ' ') + ' is working');
    if (e.kind === 'approval') setState(false, 'Waiting for your decision');
    if (e.kind === 'report' || e.summary === 'run complete') setState(false, 'Idle');
  };
  src.onerror = () => setState(false, 'Reconnecting…');
}

function pick(id) {
  picked = id;
  document.querySelectorAll('.node').forEach((n) => n.classList.remove('picked'));
  $('n-' + id).classList.add('picked');
  const n = nodeById(id);
  $('who').innerHTML = '<span class="who-pill">' + n.name + '</span>';
  $('task').placeholder = 'What should ' + n.name + ' do?';
  $('task').focus();
  $('send').disabled = !$('task').value.trim();
}

async function assign() {
  const task = $('task').value.trim();
  if (!picked || !task) return;
  const btn = $('send');
  btn.disabled = true; btn.textContent = 'Working…';
  setState(true, 'Starting');
  $('out').textContent = '';
  try {
    const r = await fetch('/api/assign', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent: picked, task: task }) });
    const d = await r.json();
    $('out').innerHTML = d.error
      ? '<div class="note bad">' + d.error + '</div>'
      : '<div class="note">' + (d.answer || 'Done.').slice(0, 900) + '</div>';
  } catch (err) {
    $('out').innerHTML = '<div class="note bad">' + err.message + '</div>';
  }
  btn.textContent = 'Assign the job'; btn.disabled = false;
  setState(false, 'Idle');
}

document.addEventListener('DOMContentLoaded', () => {
  wires();
  window.addEventListener('resize', () => {
    document.querySelectorAll('.wire').forEach((w) => w.remove());
    wires();
    const done = hops.slice(); hops.length = 0;
    document.querySelectorAll('.hop').forEach((h) => h.remove());
    done.forEach(([a, b]) => addHop(a, b));
  });
  NODES.forEach((n) => {
    const el = $('n-' + n.id);
    if (el && n.id !== 'supervisor') el.onclick = () => pick(n.id);
  });
  $('task').addEventListener('input', () => {
    $('send').disabled = !picked || !$('task').value.trim();
  });
  $('send').addEventListener('click', assign);
  listen();
});
"""


def workforce_page(account: dict, busy: bool = False,
                   ops: dict | None = None) -> str:
    """The team at work: the graph moves as they move, and you can hand out a job.

    `ops` carries the read-only operator panels - runs, memory and spend.
    They are optional so the page still renders without a snapshot.
    """
    nodes = "".join(
        f"<div class='node' id='n-{n[0]}' style='left:{n[3]}%;top:{n[4]}%'>"
        f"<b><span class='dot'></span>{e(n[1])}</b>"
        f"<small>{e(n[2])}</small></div>"
        for n in TEAM
    )
    team_json = json.dumps([
        {"id": n[0], "name": n[1], "x": n[3], "y": n[4]} for n in TEAM
    ])

    head = (
        "<div class='head'><h1>Workforce</h1>"
        "<p>One supervisor and eight specialists. Watch the work move between "
        "them as it happens, or pick one and hand it a job yourself.</p></div>"
    )
    body = (
        f"<div class='body'><div class='wf'>"

        f"<div>"
        f"<div class='wfbar'>"
        f"<span class='state' id='runstate'><span class='dot'></span>"
        f"{'Working' if busy else 'Idle'}</span>"
        f"<span class='muted' style='font-size:12.5px'>"
        f"Click a specialist to give it a job.</span></div>"
        f"<div class='stage' id='stage'>{nodes}</div>"
        f"</div>"

        f"<div>"
        f"<div class='assign'>"
        f"<h3>Hand out a job</h3>"
        f"<p>The supervisor normally decides who does what. This goes over its "
        f"head and puts the work straight in front of the specialist you "
        f"choose — useful when you already know who you need.</p>"
        f"<div id='who'><span class='muted' style='font-size:12.5px'>"
        f"Nobody picked yet.</span></div>"
        f"<div class='field' style='margin-top:10px'>"
        f"<textarea id='task' rows='3' "
        f"placeholder='Pick a specialist on the left first'></textarea></div>"
        f"<button class='btn' id='send' disabled>Assign the job</button>"
        f"<div id='out' style='margin-top:12px'></div>"
        f"</div>"

        f"<div class='feed'><h3>Live activity</h3>"
        f"<div class='rows' id='rows'>"
        f"<div class='ev'><time></time><div><span class='none'>"
        f"Nothing running. Ask a question in the chat, or hand a job to a "
        f"specialist, and every step appears here as it happens.</span>"
        f"</div></div></div></div>"
        f"</div>"

        f"</div>"
        + operator_panels((ops or {}).get("runs") or [],
                          (ops or {}).get("memRecords") or [],
                          (ops or {}).get("costBars") or [])
        + "</div>"
    )
    js = f"window.__TEAM = {team_json};\n" + WORKFORCE_JS
    return shell("Workforce", account, "/workforce", head, body,
                 WORKFORCE_CSS + NOTE_CSS + OPERATOR_CSS, js)


NOTE_CSS = f"""
.note {{ padding:12px 14px; border-radius:12px; background:{ACCENT_TINT};
  color:{ACCENT}; font-size:13px; line-height:1.6; border:1px solid #F3D4D6;
  white-space:pre-wrap; max-height:280px; overflow-y:auto; }}
.note.bad {{ background:{DANGER_TINT}; color:{DANGER}; border-color:#FBC5C5; }}
"""

# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

PRODUCTS_CSS = f"""
.plist {{ max-width:1000px; width:100%; }}
.prow {{ display:grid;
  grid-template-columns:minmax(0,2fr) 110px 110px 110px 100px 160px;
  gap:12px; align-items:center; padding:14px 16px; border:1px solid {BORDER};
  border-radius:14px; background:{SURFACE}; margin-bottom:10px; }}
.phead {{ display:grid;
  grid-template-columns:minmax(0,2fr) 110px 110px 110px 100px 160px;
  gap:12px; padding:0 16px 8px; font-size:11.5px; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase; color:{FAINT}; }}
.pname {{ font-size:14.5px; font-weight:600; min-width:0;
  overflow-wrap:anywhere; }}
.pname small {{ display:block; font-size:12px; color:{MUTED};
  font-weight:400; margin-top:2px; }}
.pnum {{ font-size:14px; }}
.pnum.missing {{ color:{AMBER}; font-weight:600; }}
.pacts {{ display:flex; gap:8px; justify-content:flex-end; }}
.pacts .btn {{ padding:8px 13px; font-size:13px; }}
.pacts form {{ margin:0; }}
.pform {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:0 14px; }}
.pform .wide {{ grid-column:1 / -1; }}
@media (max-width: 900px) {{
  .phead {{ display:none; }}
  .prow {{ grid-template-columns:minmax(0,1fr); }}
  .pacts {{ justify-content:flex-start; }}
}}
"""


def products_page(account: dict, products: list[dict], editing: str = "",
                  note: str = "") -> str:
    """The catalogue, and the only place a weight can be set.

    Weight gets its own column and its own warning because until now nothing
    in the app could record one, and every delivery quote depends on it: a
    product without a weight simply cannot be priced.
    """
    cur = account.get("currency") or "BDT"
    unweighed = [p for p in products if not (p.get("weight_g") or 0)]

    banner = f"<div class='note'>{e(note)}</div>" if note else ""
    if unweighed:
        banner += (
            f"<div class='note bad'>{len(unweighed)} product(s) have no "
            f"weight, so a delivery for them cannot be priced. Put in what "
            f"one piece weighs — that is what the courier charges on.</div>")

    current = next((p for p in products if str(p["id"]) == str(editing)), None)

    def money(v):
        return f"{cur} {float(v):,.0f}" if v else DASHED

    rows = ""
    for p in products:
        grams = int(p.get("weight_g") or 0)
        # Double quotes inside, single quotes around the attribute: that
        # way the markup needs no backslash escapes at all.
        confirm = ('return confirm("Remove this product from your '
                   'catalogue?")')
        rows += (
            f"<div class='prow'>"
            f"<div class='pname'>{e(p['name'])}"
            f"<small>{e(p.get('category') or 'no category')}</small></div>"
            f"<div class='pnum{'' if grams else ' missing'}'>"
            f"{str(grams) + ' g' if grams else 'not set'}</div>"
            f"<div class='pnum'>{money(p.get('unit_cost'))}</div>"
            f"<div class='pnum'>{money(p.get('sell_price'))}</div>"
            f"<div class='pnum'>{int(p.get('quantity') or 0)}</div>"
            f"<div class='pacts'>"
            f"<a class='btn btn-quiet' href='/products?edit={p['id']}'>Edit</a>"
            f"<form method='post' action='/products/{p['id']}/delete' "
            f"onsubmit='{confirm}'>"
            f"<button class='btn btn-quiet' type='submit'>Remove</button>"
            f"</form></div></div>"
        )
    if not rows:
        rows = (f"<div class='prow'><div class='pname' "
                f"style='grid-column:1/-1;font-weight:400;color:{MUTED}'>"
                f"Nothing in your catalogue yet. Add the first thing you sell "
                f"below, or send your team a photo of it in the chat.</div>"
                f"</div>")

    def val(field, fallback=""):
        if current and current.get(field) is not None:
            return e(current.get(field))
        return e(fallback)

    hidden = (f"<input type='hidden' name='id' value='{current['id']}'>"
              if current else "")
    cancel = ("<a class='btn btn-quiet' href='/products' "
              "style='margin-left:8px;display:inline-block'>Cancel</a>"
              if current else "")
    title = f"Edit {e(current['name'])}" if current else "Add a product"

    photo_now = ""
    if current and current.get("photo_path"):
        from pathlib import Path as _P
        photo_now = (
            f"<div style='margin-top:8px;display:flex;align-items:center;gap:10px'>"
            f"<img src='/media/{e(_P(str(current['photo_path'])).name)}' alt='' "
            f"style='width:64px;height:64px;object-fit:cover;border-radius:8px;"
            f"border:1px solid rgba(140,150,175,.3)'>"
            f"<span class='muted' style='font-size:12px'>Current photo. "
            f"Choosing a new file replaces it.</span></div>")

    form = (
        f"<div class='card' style='max-width:1000px'>"
        f"<h3 style='margin:0 0 4px;font-size:15px'>{title}</h3>"
        f"<p class='muted' style='margin:0 0 16px'>Weight is the one your "
        f"courier bills on: one piece, in grams, packed as you send it.</p>"
        f"<form method='post' action='/products/save' class='pform' "
        f"enctype='multipart/form-data'>{hidden}"
        f"<div class='field wide'><label for='pn'>Name</label>"
        f"<input id='pn' name='name' required value='{val('name')}'></div>"
        f"<div class='field'><label for='pc'>Category</label>"
        f"<input id='pc' name='category' value='{val('category')}'></div>"
        f"<div class='field'><label for='pw'>Weight of one piece (g)</label>"
        f"<input id='pw' name='weight_g' type='number' min='0' "
        f"value='{val('weight_g', 0)}'></div>"
        f"<div class='field'><label for='pu'>Costs you ({e(cur)})</label>"
        f"<input id='pu' name='unit_cost' type='number' step='0.01' min='0' "
        f"value='{val('unit_cost')}'></div>"
        f"<div class='field'><label for='ps'>Sells for ({e(cur)})</label>"
        f"<input id='ps' name='sell_price' type='number' step='0.01' min='0' "
        f"value='{val('sell_price')}'></div>"
        f"<div class='field'><label for='pq'>In stock now</label>"
        f"<input id='pq' name='quantity' type='number' min='0' "
        f"value='{val('quantity', 0)}'></div>"
        f"<div class='field'><label for='pr'>Warn me below</label>"
        f"<input id='pr' name='reorder_level' type='number' min='0' "
        f"value='{val('reorder_level', 5)}'></div>"
        f"<div class='field wide'><label for='pp'>Photo of this product</label>"
        f"<input id='pp' name='photo' type='file' accept='image/*'>"
        f"{photo_now}</div>"
        f"<div class='wide' style='margin-top:4px'>"
        f"<button class='btn' type='submit'>"
        f"{'Save changes' if current else 'Add it'}</button>{cancel}"
        f"</div></form></div>"
    )

    head = (
        "<div class='head'><h1>Products</h1>"
        "<p>What you sell, what each piece costs you, and what it weighs. "
        "Your team fills this in as it learns; you can correct any of it.</p>"
        "<p style='margin-top:10px'>"
        "<a class='btn btn-quiet' style='text-decoration:none;"
        "display:inline-block' href='/delivery'>Price a delivery &rarr;</a>"
        "</p></div>"
    )
    # What the stock on hand is actually worth. Recomputed on every render from
    # the rows themselves, so editing a quantity or a price updates it — the
    # owner asked to change stock and see profit move, and this is that.
    stock_value = sum((p.get("quantity") or 0) * (p.get("unit_cost") or 0)
                      for p in products)
    revenue = sum((p.get("quantity") or 0) * (p.get("sell_price") or 0)
                  for p in products)
    profit = revenue - stock_value
    margin = (profit / revenue * 100) if revenue else 0.0
    priced = [p for p in products if (p.get("sell_price") or 0) > 0]
    out_now = [p for p in priced if not (p.get("quantity") or 0)]

    def _tile(label, value, tone=""):
        return (f"<div style='flex:1;min-width:150px'>"
                f"<div class='muted' style='font-size:11px;text-transform:uppercase;"
                f"letter-spacing:.05em'>{e(label)}</div>"
                f"<div style='font-size:20px;font-weight:700;{tone}'>{e(value)}</div></div>")

    totals = (
        f"<div class='card' style='max-width:1000px;display:flex;flex-wrap:wrap;"
        f"gap:18px;margin-bottom:14px'>"
        + _tile("Stock at cost", f"{stock_value:,.0f} {cur}")
        + _tile("If it all sells", f"{revenue:,.0f} {cur}")
        + _tile("Profit in that", f"{profit:,.0f} {cur}",
                "color:#16a34a" if profit > 0 else "")
        + _tile("Blended margin", f"{margin:.1f}%")
        + _tile("Out of stock", f"{len(out_now)} of {len(priced)}",
                "color:#b45309" if out_now else "")
        + f"</div>")

    body = (
        f"<div class='body'>{banner}{totals}"
        f"<div class='plist'>"
        f"<div class='phead'><span>Product</span><span>Weight</span>"
        f"<span>Costs</span><span>Sells for</span><span>In stock</span>"
        f"<span></span></div>{rows}</div>"
        f"<div style='margin-top:18px'>{form}</div></div>"
    )
    return shell("Products", account, "/products", head, body, PRODUCTS_CSS)

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

DELIVERY_CSS = f"""
.dgrid {{ display:grid; gap:16px; max-width:980px;
  grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); align-items:start; }}
.two {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(140px,1fr));
  gap:12px; }}
.quote {{ border:1px solid {BORDER}; border-radius:16px; padding:20px;
  background:{RAIL}; }}
.qline {{ display:flex; justify-content:space-between; align-items:baseline;
  padding:9px 0; border-bottom:1px solid {BORDER}; font-size:14px; gap:12px; }}
.qline:last-of-type {{ border-bottom:none; }}
.qline b {{ font-weight:600; }}
.qtotal {{ display:flex; justify-content:space-between; align-items:baseline;
  margin-top:12px; padding-top:14px; border-top:2px solid {INK};
  font-size:17px; font-weight:700; gap:12px; }}
.qwait {{ color:{MUTED}; font-size:13.5px; line-height:1.6; }}
.warnbox {{ background:{AMBER_TINT}; color:{AMBER}; border:1px solid #FDE68A;
  border-radius:12px; padding:11px 14px; font-size:13px; margin-bottom:14px; }}
.zones {{ width:100%; border-collapse:collapse; font-size:13px;
  margin-top:8px; }}
.zones th {{ text-align:left; font-weight:500; color:{MUTED};
  font-size:11.5px; text-transform:uppercase; letter-spacing:.04em;
  padding:0 10px 7px 0; }}
.zones td {{ padding:7px 10px 7px 0; border-top:1px solid {BORDER}; }}
.zones td:last-child, .zones th:last-child {{ text-align:right; padding-right:0; }}
"""

DELIVERY_JS = """
const $ = (id) => document.getElementById(id);
const money = (n, cur) => cur + ' ' + Number(n).toLocaleString(undefined,
  { maximumFractionDigits: 0 });

async function priceIt() {
  const body = {
    product: $('dproduct').value, quantity: +$('dqty').value || 1,
    area: $('darea').value, city: $('dcity').value,
    from_city: $('fcity').value, from_area: $('farea').value,
    zone: $('dzone').value,
    cod: $('dcod').checked,
  };
  $('qbox').innerHTML = '<div class="qwait">Working it out…</div>';
  const r = await fetch('/api/delivery/quote', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const q = await r.json();
  if (!q.known) {
    $('qbox').innerHTML = '<div class="qwait"><b>Cannot price this yet.</b><br>'
      + (q.problems || []).map((p) => '· ' + p).join('<br>')
      + '<br><br>Weight comes from your catalogue. Tell your team what a piece '
      + 'weighs and this fills in.</div>';
    $('bookbtn').disabled = true;
    return;
  }
  const c = q.currency;
  $('qbox').innerHTML =
    '<div class="qline"><span>Parcel weight</span><b>' + q.weight_g + ' g'
      + (q.billable_kg ? ' · ' + q.billable_kg + ' extra kg billed' : '') + '</b></div>'
    + '<div class="qline"><span>Zone</span><b>' + q.zone + '</b></div>'
    + '<div class="qline"><span>Priced by</span><b>' + (q.pricedBy || '') + '</b></div>'
    + '<div class="qline"><span>Goods</span><b>' + money(q.goods, c) + '</b></div>'
    + '<div class="qline"><span>Delivery</span><b>' + money(q.delivery, c) + '</b></div>'
    + (q.cod_fee ? '<div class="qline"><span>Cash-on-delivery fee</span><b>'
        + money(q.cod_fee, c) + '</b></div>' : '')
    + '<div class="qtotal"><span>Customer pays</span><span>'
      + money(q.total, c) + '</span></div>';
  $('bookbtn').disabled = false;
  window.__cod = q.total;
}

async function bookIt() {
  const btn = $('bookbtn');
  btn.disabled = true; btn.textContent = 'Booking…';
  const r = await fetch('/api/delivery/book', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      customer: $('dcustomer').value, phone: $('dphone').value,
      address: $('daddress').value, product: $('dproduct').value,
      cod_amount: $('dcod').checked ? (window.__cod || 0) : 0,
      note: $('dnote').value,
    }) });
  const out = await r.json();
  btn.textContent = 'Book the courier';
  btn.disabled = false;
  $('bookout').innerHTML = out.ok
    ? '<div class="warnbox" style="background:#FBEBEB;color:#7B1E22;'
      + 'border-color:#F0D6D6">Booked with ' + out.provider
      + (out.consignment ? ' · consignment ' + out.consignment : '')
      + (out.simulated ? ' — simulated, because no courier is connected yet.' : '.')
      + '</div>'
    : '<div class="warnbox">' + (out.error || 'The courier refused the booking.')
      + '</div>';
}

document.addEventListener('DOMContentLoaded', () => {
  $('pricebtn').addEventListener('click', priceIt);
  $('bookbtn').addEventListener('click', bookIt);
});
"""


def delivery_page(account: dict, products: list[dict], zones: list[dict],
                  courier: str = "", dispatch: tuple = ("", ""),
                  note: str = "") -> str:
    """Weigh a parcel, price it honestly, and hand it to a real courier."""
    head = (
        "<div class='head'><h1>Delivery</h1>"
        "<p>What a parcel weighs decides what it costs. Pick what is going, "
        "say where, and the charge comes from your courier's own rates.</p>"
        "</div>"
    )

    unweighed = [p for p in products if not (p.get("weight_g") or 0)]
    warn = ""
    if unweighed:
        warn = (f"<div class='warnbox'>{len(unweighed)} of your "
                f"{len(products)} products have no weight recorded, so they "
                f"cannot be priced. Tell your team what they weigh.</div>")
    if not courier:
        warn += ("<div class='warnbox'>No courier connected, so a booking is "
                 "simulated and nothing is really collected. Connect "
                 "Steadfast or Pathao to make it real.</div>")

    def _option(p: dict) -> str:
        grams = int(p.get("weight_g") or 0)
        # The weight is in the label because it is the thing that decides the
        # price, and because a zero is how the owner learns which product
        # still needs weighing.
        weight = f" — {grams} g" if grams else " — no weight recorded"
        return (f"<option value='{e(p['name'])}'>"
                f"{e(p['name'])}{weight}</option>")

    options = "".join(_option(p) for p in products) or (
        "<option value=''>Nothing in your catalogue yet</option>")

    rows = "".join(
        f"<tr><td>{e(z.get('name'))}</td>"
        f"<td>{int(z.get('base_weight_g') or 0)} g</td>"
        f"<td>{e(account.get('currency') or 'BDT')} "
        f"{float(z.get('base_charge') or 0):,.0f}</td>"
        f"<td>+{float(z.get('per_kg_extra') or 0):,.0f}/kg</td></tr>"
        for z in zones
    )

    body = (
        f"<div class='body'>{warn}"
        f"<div class='dgrid'>"

        f"<div class='card'>"
        f"<h3 style='margin:0 0 4px;font-size:15px'>Where you send from</h3>"
        f"<p class='muted' style='margin:0 0 12px'>The zone is the distance "
        f"from here to the customer. An online shop still packs the parcel "
        f"somewhere — put that place in.</p>"
        f"<div class='two'>"
        f"<div class='field'><label for='fcity'>City</label>"
        f"<input id='fcity' value='{e(dispatch[0])}' placeholder='Dhaka'></div>"
        f"<div class='field'><label for='farea'>Area</label>"
        f"<input id='farea' value='{e(dispatch[1])}' placeholder='Mirpur'></div>"
        f"</div>"
        f"<h3 style='margin:16px 0 14px;font-size:15px'>What is going where"
        f"</h3>"
        f"<div class='field'><label for='dproduct'>Product</label>"
        f"<select id='dproduct'>{options}</select></div>"
        f"<div class='two'>"
        f"<div class='field'><label for='dqty'>How many</label>"
        f"<input id='dqty' type='number' min='1' value='1'></div>"
        f"<div class='field'><label for='dcity'>City</label>"
        f"<input id='dcity' placeholder='Dhaka'></div>"
        f"</div>"
        f"<div class='field'><label for='darea'>Area</label>"
        f"<input id='darea' placeholder='Gulshan'></div>"
        f"<div class='field'><label for='dzone'>Which rate applies</label>"
        f"<select id='dzone'>"
        f"<option value=''>Work it out from the address</option>"
        f"<option value='same_area'>Same area as you</option>"
        f"<option value='inside_city'>Inside your city</option>"
        f"<option value='outside_city'>Outside your city</option>"
        f"</select></div>"
        f"<label style='display:flex;align-items:center;gap:8px;font-weight:400'>"
        f"<input id='dcod' type='checkbox' checked style='width:auto'>"
        f"Cash on delivery</label>"
        f"<button class='btn' id='pricebtn' style='margin-top:14px'>"
        f"Work out the charge</button>"
        f"</div>"

        f"<div class='quote' id='qbox'>"
        f"<div class='qwait'>Pick a product and a destination, and the charge "
        f"appears here — weight, zone, delivery and the cash-on-delivery fee, "
        f"each shown separately so you can see where it comes from.</div>"
        f"</div>"

        f"<div class='card'>"
        f"<h3 style='margin:0 0 4px;font-size:15px'>Who is receiving it</h3>"
        f"<p class='muted' style='margin:0 0 14px'>Only needed when you book.</p>"
        f"<div class='field'><label for='dcustomer'>Name</label>"
        f"<input id='dcustomer' placeholder='Customer name'></div>"
        f"<div class='field'><label for='dphone'>Phone</label>"
        f"<input id='dphone' placeholder='01XXXXXXXXX'></div>"
        f"<div class='field'><label for='daddress'>Full address</label>"
        f"<textarea id='daddress' rows='2' placeholder='House, road, area'>"
        f"</textarea></div>"
        f"<div class='field'><label for='dnote'>Note for the rider</label>"
        f"<input id='dnote' placeholder='Optional'></div>"
        f"<button class='btn' id='bookbtn' disabled>Book the courier</button>"
        f"<div id='bookout' style='margin-top:12px'></div>"
        f"</div>"

        f"<div class='card'>"
        f"<h3 style='margin:0 0 4px;font-size:15px'>Your courier rates</h3>"
        f"<p class='muted' style='margin:0 0 6px'>These are what the charge is "
        f"worked out from. Part of a kilo over the base bills as a whole "
        f"kilo — that is how couriers charge, not a rounding choice.</p>"
        f"<table class='zones'><tr><th>Zone</th><th>Base weight</th>"
        f"<th>Base</th><th>Each extra kg</th></tr>{rows}</table>"
        f"</div>"

        f"</div></div>"
    )
    return shell("Delivery", account, "/delivery", head, body,
                 DELIVERY_CSS, DELIVERY_JS)

# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------

CONNECT_CSS = f"""
/* The four platforms as tiles. auto-fit with a minimum means the column count
   follows the window instead of being declared: two up on a laptop, one on a
   phone, three on a wide monitor, with no breakpoint to maintain. */
.tiles {{ display:grid; gap:14px; max-width:980px; width:100%;
  grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); }}
.tile {{ display:flex; flex-direction:column; min-width:0; padding:20px;
  border:1px solid {BORDER}; border-radius:16px; background:{SURFACE}; }}
.tile .top {{ display:grid; grid-template-columns:42px minmax(0,1fr);
  gap:12px; align-items:start; }}
.icon {{ width:42px; height:42px; border-radius:11px; display:grid;
  place-items:center; font-size:17px; font-weight:700; color:#fff; }}
.tile h3 {{ margin:0 0 2px; font-size:15px; font-weight:600;
  letter-spacing:-.01em; }}
.tile p {{ margin:0; font-size:13px; color:{MUTED}; line-height:1.5; }}
.steps {{ margin:12px 0 0; padding-left:18px; font-size:12.5px; color:{MUTED};
  line-height:1.65; }}
.steps code {{ background:{SUNKEN}; padding:1px 5px; border-radius:4px;
  font-size:11.5px; overflow-wrap:anywhere; }}
/* Pushed to the bottom, so the status and the button sit on one line across
   every tile in the row however much setup text is above them. */
.foot {{ margin-top:auto; padding-top:16px; display:flex; align-items:center;
  justify-content:space-between; gap:12px; }}
.foot form {{ margin:0; }}
.foot .btn {{ font-size:13.5px; padding:10px 16px; white-space:nowrap; }}

/* The three that need no connecting are half-height and sit below, three up:
   they are a readout, not a decision. */
.facts {{ display:grid; gap:14px; max-width:980px; width:100%; margin-top:14px;
  grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); }}
.fact {{ display:grid; grid-template-columns:36px minmax(0,1fr); gap:11px;
  align-items:start; padding:16px 18px; border:1px solid {BORDER};
  border-radius:16px; background:{RAIL}; }}
.fact .icon {{ width:36px; height:36px; border-radius:10px; font-size:13px; }}
.fact h3 {{ margin:0 0 2px; font-size:13.5px; font-weight:600; }}
.fact p {{ margin:0 0 7px; font-size:12.5px; color:{MUTED}; line-height:1.5; }}

.note {{ max-width:980px; margin:0 0 16px; padding:12px 16px;
  border-radius:12px; background:{ACCENT_TINT}; color:{ACCENT};
  font-size:13.5px; font-weight:500; border:1px solid #F3D4D6; }}
.note.bad {{ background:{DANGER_TINT}; color:{DANGER}; border-color:#FBC5C5; }}
@media (max-width: 420px) {{
  .foot {{ flex-direction:column; align-items:stretch; }}
  .foot .btn {{ width:100%; }}
}}
"""


# What each platform is called, and what the owner has to have in hand. The
# id is asked for separately from the token because Meta's tokens do not say
# which Page they are for, and a token without one cannot be checked.
# What each platform asks for. A list rather than a fixed pair because
# Pathao needs four things — the client pair identifies the integration, the
# login identifies the merchant, and it will not issue a token without both.
# `name` is the form field; `token` and `ident` are the two the storage layer
# already understands, and anything else travels alongside them.
NEEDS = {
    "messenger": {
        "why": "Both come from the same Meta app. A Page token is what reads "
               "the messages; a user token cannot.",
        "fields": [("token", "Page access token", "textarea"),
                   ("ident", "Facebook Page id", "text")],
    },
    "facebook": {
        "why": "The same token and Page as Messenger — Meta treats them as "
               "one thing, so connecting either connects both.",
        "fields": [("token", "Page access token", "textarea"),
                   ("ident", "Facebook Page id", "text")],
    },
    "instagram": {
        "why": "The token is the Facebook Page's. The id is the Instagram "
               "Business account linked to that Page, not the handle.",
        "fields": [("token", "Page access token", "textarea"),
                   ("ident", "Instagram Business account id", "text")],
    },
    "youtube": {
        "why": "An API key cannot upload — the upload happens as you, not as "
               "the app, so it has to be a refresh token.",
        "fields": [("token", "OAuth refresh token", "textarea")],
    },
    "steadfast": {
        "why": "Both come from the API page of your Steadfast merchant "
               "portal. They are checked against your account balance before "
               "they are saved.",
        "fields": [("token", "API key", "text"),
                   ("ident", "Secret key", "text")],
    },
    "pathao": {
        "why": "Pathao issues a token from your client pair *and* your "
               "Merchant panel login together — the pair alone returns \u201cthe "
               "user credentials were incorrect\u201d. Your store is read back "
               "automatically; a parcel needs somewhere to be collected from.",
        "fields": [("token", "Client id", "text"),
                   ("ident", "Client secret", "text"),
                   ("username", "Merchant panel email", "text"),
                   ("password", "Merchant panel password", "password"),
                   ("sandbox", "Use Pathao's sandbox (books nothing real)",
                    "checkbox")],
    },
}


def connect_form(account: dict, platform: str, has_oauth: bool,
                 redirect_uri: str, error: str = "") -> str:
    """Paste a credential. Checked against the live API before it is saved."""
    spec = NEEDS.get(platform, {"why": "", "fields": [("token", "Token", "text")]})
    warn = f"<div class='note bad'>{e(error)}</div>" if error else ""

    fields = ""
    for name, label, kind in spec["fields"]:
        if kind == "checkbox":
            fields += (
                f"<label style='display:flex;align-items:center;gap:8px;"
                f"font-weight:400;margin-bottom:14px'>"
                f"<input type='checkbox' name='{e(name)}' value='1' "
                f"style='width:auto'>{e(label)}</label>")
        elif kind == "textarea":
            fields += (
                f"<div class='field'><label for='{e(name)}'>{e(label)}</label>"
                f"<textarea id='{e(name)}' name='{e(name)}' rows='3' required "
                f"placeholder='paste it here'></textarea></div>")
        else:
            fields += (
                f"<div class='field'><label for='{e(name)}'>{e(label)}</label>"
                f"<input id='{e(name)}' name='{e(name)}' type='{e(kind)}' "
                f"required></div>")

    if has_oauth:
        alt = (f"<p class='muted' style='margin-top:14px'>Or "
               f"<a href='/connect/{e(platform)}' style='color:{ACCENT};"
               f"font-weight:600'>sign in with {e(platform.title())}</a> "
               f"instead and never handle a token.</p>")
    else:
        alt = (f"<p class='muted' style='margin-top:14px'>One-click sign-in is "
               f"off because this machine has no app registered with the "
               f"platform. To turn it on, register one and set its id and "
               f"secret, with <code>{e(redirect_uri)}</code> as the redirect."
               f"</p>")

    body = (
        f"<div class='body'><div class='card' style='max-width:560px'>"
        f"{warn}"
        f"<p class='muted' style='margin-top:0'>{e(spec['why'])}</p>"
        f"<form method='post' action='/connect/{e(platform)}/save'>"
        f"{fields}"
        f"<button class='btn' type='submit'>Check and connect</button>"
        f"<a class='btn btn-quiet' href='/connect' "
        f"style='margin-left:8px;display:inline-block'>Cancel</a>"
        f"</form>{alt}"
        f"<p class='muted' style='margin-top:14px'>Nothing is saved unless the "
        f"platform confirms the credential works. It is stored in your shop's "
        f"own database, not in a file shared with anyone else.</p>"
        f"</div></div>"
    )
    head = (
        f"<div class='head'><h1>Connect {e(platform.title())}</h1>"
        f"<p>Give it a credential and it will be checked straight away.</p>"
        f"</div>"
    )
    return shell(f"Connect {platform}", account, "/connect", head, body,
                 CONNECT_CSS)


def settings_page(account: dict, channels: dict, image_provider: str,
                  db_backend: str, has_llm: bool,
                  oauth: dict | None = None, note: str = "",
                  shop_stats: dict | None = None,
                  telegram_on: bool = False) -> str:
    """Everything the owner configures, on one page.

    Channels and the account used to be two screens in two different
    chromes - the account one had no rail at all, so opening it felt like
    leaving the app.
    """
    oauth = oauth or {}
    head = (
        "<div class='head'><h1>Settings</h1>"
        "<p>Your channels, your couriers and your account. Everything works "
        "without a channel connected - your team just cannot read or post to "
        "a platform it has no key for.</p></div>"
    )

    brand = {
        "messenger": ("#0084FF", "M", "Read what customers send your page."),
        "instagram": ("#7B1E22", "IG", "Read DMs, post ads, reply to comments."),
        "facebook": ("#1877F2", "f", "Post ads and reply to comments."),
        "youtube": ("#FF0000", "▶", "Publish videos you supply."),
        "steadfast": ("#0F766E", "SF", "Book parcels and collect cash on delivery."),
        "pathao": ("#E11D48", "P", "Book parcels across Bangladesh."),
    }
    setup = {
        "messenger": ["Create a Meta app and add your Facebook Page to it",
                      "Ask for <code>pages_messaging</code> in App Review — "
                      "reading customer DMs is Meta's most reviewed permission",
                      "Then press Connect and paste the Page token"],
        "instagram": ["Convert the account to a Business or Creator account",
                      "Link it to your Facebook Page",
                      "Ask for <code>instagram_manage_messages</code> and "
                      "<code>instagram_manage_comments</code> in App Review",
                      "Then press Connect — the token is the Page's, the id "
                      "is the linked Instagram Business account"],
        "facebook": ["Same Meta app and Page as Messenger",
                     "<code>pages_manage_posts</code> covers publishing",
                     "Connecting either one connects both"],
        "steadfast": ["Sign in to the Steadfast merchant portal",
                      "Open <code>API</code> and copy the key and secret",
                      "Press Connect — the keys are checked against your "
                      "account balance before anything is saved"],
        "pathao": ["Open the Pathao Merchant panel",
                   "Under <code>Developer API</code>, copy the client id and "
                   "client secret",
                   "Press Connect — a token is issued to prove they work"],
        "youtube": ["Enable YouTube Data API v3 in Google Cloud",
                    "Create an OAuth client and authorise "
                    "<code>youtube.upload</code>",
                    "An API key alone cannot upload — it only reads, so "
                    "Connect asks for a refresh token"],
    }

    banner = f"<div class='note'>{e(note)}</div>" if note else ""

    rows = ""
    for key, state in channels.items():
        colour, mark, what = brand.get(key, (ACCENT, "?", ""))
        connected = state.startswith("connected")
        steps = "" if connected else (
            "<ul class='steps'>"
            + "".join(f"<li>{s}</li>" for s in setup.get(key, []))
            + "</ul>"
        )
        # The button is the point of the screen, so it sits where the badge
        # used to and the badge shrinks to a line of status under it.
        if connected:
            action = (
                f"<form method='post' action='/connect/{key}/disconnect'>"
                f"<button class='btn btn-quiet' type='submit'>Disconnect"
                f"</button></form>"
            )
        else:
            label = ("Sign in with " + key.title() if oauth.get(key)
                     else "Connect")
            action = (f"<a class='btn' href='/connect/{key}'>{e(label)}</a>")
        rows += (
            f"<div class='tile'>"
            f"<div class='top'>"
            f"<div class='icon' style='background:{colour}'>{mark}</div>"
            f"<div><h3>{e(key.title())}</h3><p>{e(what)}</p></div>"
            f"</div>{steps}"
            f"<div class='foot'>"
            f"<span class='pill {'ok' if connected else 'warn'}'>"
            f"{e(state)}</span>{action}</div></div>"
        )

    tg_note = ("Your bot is live and answering customers" if telegram_on
               else "Set a bot token from @BotFather to go live")
    extras = (
        f"<div class='fact'><div class='icon' style='background:#229ED9'>TG"
        f"</div>"
        f"<div><h3>Telegram</h3><p>{e(tg_note)}</p>"
        f"<span class='pill {'ok' if telegram_on else 'warn'}'>"
        f"{'Working' if telegram_on else 'Not set up'}</span></div></div>"
        f"<div class='fact'><div class='icon' style='background:{ACCENT}'>AI</div>"
        f"<div><h3>Ad artwork</h3><p>{e(image_provider)}</p>"
        f"<span class='pill ok'>Working</span></div></div>"
        f"<div class='fact'><div class='icon' style='background:#3F3F46'>DB</div>"
        f"<div><h3>Where your shop is stored</h3><p>{e(db_backend)}</p>"
        f"<span class='pill ok'>Working</span></div></div>"
        f"<div class='fact'><div class='icon' style='background:#3F3F46'>AI</div>"
        f"<div><h3>Your team's model</h3>"
        f"<p>{'Connected and answering' if has_llm else 'No API key set'}</p>"
        f"<span class='pill {'ok' if has_llm else 'bad'}'>"
        f"{'Working' if has_llm else 'Missing'}</span></div></div>"
    )

    body = (f"<div class='body'>{banner}"
            f"<div class='tiles'>{rows}</div>"
            f"<div class='facts'>{extras}</div>"
            f"<p class='muted' style='margin-top:18px;max-width:980px'>"
            f"Until a platform is connected, your team works against a "
            f"stand-in inbox so you can see the flow — every result is "
            f"labelled as such, and nothing is written to your records as "
            f"though a real customer sent it.</p></div>")
    body = (body.removesuffix("</div>")
            + _account_section(account, shop_stats) + "</div>")
    return shell("Settings", account, "/settings", head, body,
                 CONNECT_CSS + SETTINGS_CSS)


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------
#
# What the owner sees first, and the only screen allowed to interrupt them.
# The approval gate lives here because it is the one thing that stops the
# workforce dead: until it is answered, nothing else the team does matters.
# It had no home in this UI at all before — the only card that could answer a
# gate was in a design mockup whose buttons were never wired to anything.

HOME_CSS = """
.ktiles { display:grid; grid-template-columns:repeat(3,minmax(0,1fr));
  gap:14px; }
.ktile { background:%(surface)s; border:1px solid %(border)s;
  border-radius:16px; padding:18px 20px; min-width:0; }
.ktile span { display:block; font-size:12px; color:%(muted)s;
  font-weight:600; letter-spacing:.04em; text-transform:uppercase; }
.ktile b { display:block; font-size:27px; font-weight:800;
  letter-spacing:-.03em; margin:7px 0 4px; }
.ktile small { color:%(muted)s; font-size:12.5px; }

.gate { border:1px solid %(accent)s; background:%(accentTint)s;
  border-radius:16px; padding:20px 22px; margin-top:16px; }
.gate .from { font-size:12px; color:%(accent)s; font-weight:700;
  letter-spacing:.04em; text-transform:uppercase; }
.gate h2 { margin:6px 0 0; font-size:18px; letter-spacing:-.02em; }
.gate p { margin:8px 0 0; font-size:14px; color:%(body)s; line-height:1.6; }
.gate .acts { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; }

.two { display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
  gap:16px; margin-top:16px; }
.two h3 { margin:0 0 12px; font-size:15px; letter-spacing:-.015em; }
.line { display:flex; align-items:center; gap:11px; padding:10px 0;
  border-top:1px solid %(sunken)s; min-width:0; }
.line.first { border-top:none; }
.line .dot { width:30px; height:30px; border-radius:9px; flex:none;
  display:grid; place-items:center; font-size:12px; font-weight:600; }
.line .who { min-width:0; flex:1; }
.line b { display:block; font-size:13.5px; font-weight:600;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.line small { color:%(muted)s; font-size:12.5px; display:block;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.none { color:%(muted)s; font-size:13.5px; line-height:1.6; margin:0; }
.more { display:inline-block; margin-top:12px; font-size:13px;
  color:%(accent)s; font-weight:600; }
.quick { display:flex; gap:10px; margin-top:18px; flex-wrap:wrap; }
.quick a { text-decoration:none; display:inline-block; }
@media (max-width: 860px) {
  .ktiles, .two { grid-template-columns:1fr; }
}
""" % {"surface": SURFACE, "border": BORDER, "muted": MUTED, "body": BODY,
       "accent": ACCENT, "accentTint": ACCENT_TINT, "sunken": SUNKEN}

HOME_JS = """
document.querySelectorAll('[data-decide]').forEach(function (b) {
  b.addEventListener('click', function () {
    var was = b.textContent;
    b.disabled = true;
    b.textContent = 'Sending...';
    fetch('/api/decide', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({decision: b.dataset.decide})
    }).then(function (r) {
      if (!r.ok) { throw new Error('failed'); }
      location.reload();
    }).catch(function () {
      b.disabled = false;
      b.textContent = was;
      var n = document.getElementById('gatenote');
      if (n) { n.textContent = 'That did not go through. Try again.'; }
    });
  });
});
"""


def home_page(account: dict, day: dict, kpi: dict, gates: list,
              threads: list, stock: list) -> str:
    """Where the shop stands, and the one thing that might be waiting."""
    tiles = "".join(
        f"<div class='ktile'><span>{e(label)}</span><b>{e(value)}</b>"
        f"<small>{e(note)}</small></div>"
        for label, value, note in (
            ("Sales today", kpi.get("salesToday") or DASHED,
             kpi.get("salesTodayNote") or ""),
            ("Promised", kpi.get("preorderUnits") or DASHED,
             kpi.get("preorderNote") or ""),
            ("Stock cover", kpi.get("coverDays") or DASHED,
             kpi.get("coverNote") or ""),
        )
    )

    gate = ""
    for g in gates:
        who = e(g.get("by") or "")
        gate += (
            f"<div class='gate'>"
            f"<div class='from'>{e(g.get('tag') or 'Decision')}"
            f"{' &middot; ' + who if who else ''}</div>"
            f"<h2>{e(g.get('title'))}</h2>"
            f"<p>{e(g.get('body'))}</p>"
            f"<div class='acts'>"
            f"<button class='btn' data-decide='approve'>"
            f"{e(g.get('yes') or 'Go ahead')}</button>"
            f"<button class='btn btn-quiet' data-decide='reject'>Not now"
            f"</button></div>"
            f"<p class='none' id='gatenote' style='margin-top:10px'>"
            f"{e(g.get('hint') or '')}</p>"
            f"</div>"
        )

    low = [r for r in stock if str(r.get("todo") or "").strip()][:4]
    stock_rows = "".join(
        f"<div class='line{' first' if i == 0 else ''}'>"
        f"<div class='dot' style='background:{r.get('thumbBg') or SUNKEN};"
        f"color:{r.get('thumbFg') or INK}'>{e(r.get('initial') or '?')}</div>"
        f"<div class='who'><b>{e(r.get('name'))}</b>"
        f"<small>{e(r.get('qty'))} &middot; {e(r.get('cover'))}</small></div>"
        f"</div>"
        for i, r in enumerate(low)
    ) or ("<p class='none'>Nothing is running low. Your team says so here "
          "before anything sells out.</p>")

    unanswered = [t for t in threads
                  if "answer" not in str(t.get("state") or "").lower()]
    shown = (unanswered or threads)[:4]
    msg_rows = "".join(
        f"<div class='line{' first' if i == 0 else ''}'>"
        f"<div class='dot' style='background:{SUNKEN};color:{BODY}'>"
        f"{e(t.get('initials') or '?')}</div>"
        f"<div class='who'><b>{e(t.get('name'))}</b>"
        f"<small>{e(t.get('preview'))}</small></div>"
        f"</div>"
        for i, t in enumerate(shown)
    ) or ("<p class='none'>No customer messages yet. Connect a channel in "
          "Settings and your team starts answering them.</p>")

    head = (f"<div class='head'><h1>Home</h1>"
            f"<p>{e(day.get('line') or '')}</p></div>")
    body = (
        f"<div class='body'>"
        f"<div class='ktiles'>{tiles}</div>"
        f"{gate}"
        f"<div class='two'>"
        f"<div class='card'><h3>Running low</h3>{stock_rows}"
        f"<a class='more' href='/products'>Open products &rarr;</a></div>"
        f"<div class='card'><h3>Latest from customers</h3>{msg_rows}"
        f"<a class='more' href='/customers'>Open customers &rarr;</a></div>"
        f"</div>"
        f"<div class='quick'>"
        f"<a class='btn' href='/chat'>Ask your team</a>"
        f"<a class='btn btn-quiet' href='/studio'>Make a poster</a>"
        f"<a class='btn btn-quiet' href='/workforce'>Watch your team work</a>"
        f"</div>"
        f"</div>"
    )
    return shell("Home", account, "/", head, body, HOME_CSS, HOME_JS)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
#
# Both halves of what a customer leaves behind: the conversation the bot held
# on the shop's behalf, and the review it asked for afterwards. Reviews were
# being recorded and displayed nowhere at all, which made asking for them
# pointless — the owner could not read a single one.

CUSTOMERS_CSS = """
.tabs { display:flex; gap:8px; margin-bottom:16px; }
.tab { padding:8px 15px; border-radius:999px; border:1px solid %(border)s;
  background:%(surface)s; font-size:13.5px; color:%(body)s; cursor:pointer; }
.tab.on { background:%(accentTint)s; border-color:%(accent)s;
  color:%(accent)s; font-weight:600; }

/* The list on the left, one conversation window on the right. The window is
   a fixed height on purpose: every customer gets the same one, so switching
   between them does not move the reply box or resize the page. A long thread
   scrolls inside it rather than stretching it. */
.inbox { display:grid; grid-template-columns:296px minmax(0,1fr); gap:16px;
  height:%(windowH)s; }
.people { border:1px solid %(border)s; border-radius:16px;
  background:%(surface)s; overflow-y:auto; }
.person { display:flex; align-items:center; gap:11px; width:100%%;
  padding:13px 15px; border:none; border-bottom:1px solid %(sunken)s;
  background:none; text-align:left; cursor:pointer; }
.person:last-child { border-bottom:none; }
.person:hover { background:%(rail)s; }
.person.on { background:%(accentTint)s; }
.person .face { width:34px; height:34px; border-radius:10px; flex:none;
  background:%(sunken)s; color:%(body)s; display:grid; place-items:center;
  font-size:13px; font-weight:600; }
.person.on .face { background:%(accent)s; color:#fff; }
.person .who { min-width:0; flex:1; }
.person b { display:block; font-size:13.5px; font-weight:600;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.person small { display:block; font-size:12px; color:%(muted)s;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.person .flag { width:7px; height:7px; border-radius:999px; flex:none;
  background:%(amber)s; }

.window { border:1px solid %(border)s; border-radius:16px;
  background:%(surface)s; display:flex; flex-direction:column;
  min-width:0; overflow:hidden; }
.pane { display:none; flex-direction:column; height:100%%; min-height:0; }
.pane.on { display:flex; }
.pane .bar { display:flex; align-items:center; gap:10px; padding:14px 18px;
  border-bottom:1px solid %(sunken)s; flex:none; }
.pane .bar h3 { margin:0; font-size:14.5px; letter-spacing:-.01em; }
.meta { font-size:12.5px; color:%(muted)s; }
.talk { flex:1; min-height:0; overflow-y:auto; padding:16px 18px;
  font-size:13.5px; line-height:1.7; color:%(body)s;
  white-space:pre-wrap; overflow-wrap:anywhere; }
.reply { display:flex; gap:9px; padding:14px 18px; flex:none;
  border-top:1px solid %(sunken)s; }
.reply input { flex:1; }
.blank { display:grid; place-items:center; height:100%%; padding:30px;
  text-align:center; }

.stars { color:%(amber)s; font-size:14px; letter-spacing:2px; }
.rev { border-top:1px solid %(sunken)s; padding:14px 0; }
.rev.first { border-top:none; padding-top:0; }
.rev p { margin:6px 0 0; font-size:13.5px; color:%(body)s; line-height:1.6; }
.none { color:%(muted)s; font-size:13.5px; line-height:1.6; margin:0; }
.hide { display:none; }

@media (max-width: 860px) {
  .inbox { grid-template-columns:1fr; height:auto; }
  .people { max-height:230px; }
  .window { height:%(windowH)s; }
}
""" % {"border": BORDER, "surface": SURFACE, "body": BODY, "muted": MUTED,
       "accent": ACCENT, "accentTint": ACCENT_TINT, "sunken": SUNKEN,
       "rail": RAIL, "amber": AMBER, "windowH": "620px"}

CUSTOMERS_JS = """
document.querySelectorAll('.tab').forEach(function (t) {
  t.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (o) {
      o.classList.toggle('on', o === t);
    });
    document.querySelectorAll('[data-panel]').forEach(function (p) {
      p.classList.toggle('hide', p.dataset.panel !== t.dataset.tab);
    });
  });
});

// Switching customer swaps what is inside the one window; it never changes
// the window. The transcript starts at the newest line, which is the part
// you are replying to.
function showPerson(id) {
  document.querySelectorAll('.person').forEach(function (p) {
    p.classList.toggle('on', p.dataset.person === id);
  });
  document.querySelectorAll('.pane').forEach(function (p) {
    var on = p.dataset.pane === id;
    p.classList.toggle('on', on);
    if (on) {
      var talk = p.querySelector('.talk');
      if (talk) { talk.scrollTop = talk.scrollHeight; }
    }
  });
}
document.querySelectorAll('.person').forEach(function (p) {
  p.addEventListener('click', function () { showPerson(p.dataset.person); });
});
var first = document.querySelector('.person');
if (first) { showPerson(first.dataset.person); }

document.querySelectorAll('[data-reply]').forEach(function (b) {
  b.addEventListener('click', function () {
    var box = document.getElementById('r-' + b.dataset.reply);
    var text = ((box && box.value) || '').trim();
    if (!text) { if (box) { box.focus(); } return; }
    b.disabled = true;
    b.textContent = 'Sending...';
    fetch('/api/reply', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message_id: b.dataset.reply, text: text})
    }).then(function (r) {
      if (!r.ok) { throw new Error('failed'); }
      location.reload();
    }).catch(function () {
      b.disabled = false;
      b.textContent = 'Send';
      box.value = '';
      box.placeholder = 'That did not send. Try again.';
    });
  });
});
"""


def customers_page(account: dict, threads: list, reviews: list) -> str:
    """A list of customers, and one conversation window they all share.

    Every customer's window is the same size and in the same place, so moving
    down the list does not move the page under you. Whoever is still waiting
    on a reply is listed first, because they are the reason to open this
    screen at all.
    """
    def waiting(t: dict) -> bool:
        return "answer" not in str(t.get("state") or "").lower()

    ordered = sorted(threads, key=lambda t: (not waiting(t)))

    people, panes = "", ""
    for t in ordered:
        # Only a real inbox message can be answered from here; a comment
        # carries a "c" prefix and is replied to where it was left.
        rid = str(t.get("id") or "")
        state = str(t.get("state") or "New")
        people += (
            f"<button class='person' data-person='{e(rid)}'>"
            f"<div class='face'>{e(t.get('initials') or '?')}</div>"
            f"<div class='who'><b>{e(t.get('name'))}</b>"
            f"<small>{e(t.get('preview'))}</small></div>"
            f"{'' if not waiting(t) else '<span class=flag></span>'}"
            f"</button>"
        )
        box = (
            f"<div class='reply'>"
            f"<input id='r-{e(rid)}' placeholder='Write a reply...'>"
            f"<button class='btn' data-reply='{e(rid)}'>Send</button></div>"
            if rid.isdigit() else
            f"<div class='reply'><span class='meta'>Reply to this one on "
            f"{e(t.get('channel'))}, where it was left.</span></div>"
        )
        panes += (
            f"<div class='pane' data-pane='{e(rid)}'>"
            f"<div class='bar'>"
            f"<div style='flex:1;min-width:0'><h3>{e(t.get('name'))}</h3>"
            f"<div class='meta'>{e(t.get('channel'))} &middot; "
            f"{e(t.get('t'))}</div></div>"
            f"<span class='pill {'ok' if not waiting(t) else 'warn'}'>"
            f"{e(state)}</span></div>"
            f"<div class='talk'>{e(t.get('message') or t.get('preview'))}</div>"
            f"{box}</div>"
        )

    if ordered:
        n = len(ordered)
        wait_n = sum(1 for t in ordered if waiting(t))
        count = (f"<p class='meta' style='margin:0 0 12px'>"
                 f"{n} customer{'' if n == 1 else 's'}"
                 f"{f' &middot; {wait_n} waiting on you' if wait_n else ''}"
                 f"</p>")
        inbox_html = (f"{count}<div class='inbox'>"
                      f"<div class='people'>{people}</div>"
                      f"<div class='window'>{panes}</div></div>")
    else:
        inbox_html = (
            "<div class='inbox'><div class='people'></div>"
            "<div class='window'><div class='blank'><p class='none'>"
            "No messages yet. Your team answers customers on Telegram by "
            "itself, and both sides of every conversation appear here. "
            "Settings shows whether the bot is live.</p></div></div></div>"
        )

    revs = ""
    for i, r in enumerate(reviews):
        rating = int(r.get("rating") or 0)
        stars = ("★" * rating + "☆" * (5 - rating)) if rating else ""
        product = e(r.get("product_name") or "")
        revs += (
            f"<div class='rev{' first' if i == 0 else ''}'>"
            f"<b>{e(r.get('customer') or 'A customer')}</b> "
            f"<span class='stars'>{stars}</span>"
            f"{f'<span class=meta> &middot; {product}</span>' if product else ''}"
            f"<p>{e(r.get('comment') or '')}</p></div>"
        )
    if not revs:
        revs = ("<p class='none'>No reviews yet. Your team asks for one "
                "after an order, and whatever the customer sends back "
                "appears here.</p>")

    head = ("<div class='head'><h1>Customers</h1>"
            "<p>What they asked, what your team answered, and what they "
            "thought of it afterwards.</p></div>")
    body = (
        f"<div class='body'>"
        f"<div class='tabs'>"
        f"<button class='tab on' data-tab='talk'>Messages</button>"
        f"<button class='tab' data-tab='revs'>Reviews</button></div>"
        f"<div data-panel='talk'>{inbox_html}</div>"
        f"<div data-panel='revs' class='hide'><div class='card'>{revs}</div>"
        f"</div></div>"
    )
    return shell("Customers", account, "/customers", head, body,
                 CUSTOMERS_CSS, CUSTOMERS_JS)




# ---------------------------------------------------------------------------
# The operator's view
# ---------------------------------------------------------------------------
#
# What the agents did, what they wrote down, and what it cost. These three
# panels used to exist only inside the design mockup, which rendered real
# figures behind dead buttons. They belong with the live graph on Workforce,
# which is the screen an operator actually opens.

OPERATOR_CSS = """
.ops { margin-top:22px; display:grid; gap:16px;
  grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }
.ops h3 { margin:0 0 4px; font-size:15px; letter-spacing:-.015em; }
.ops .lede { margin:0 0 12px; font-size:12.5px; color:%(muted)s; }
.op { padding:10px 0; border-top:1px solid %(sunken)s; min-width:0; }
.op.first { border-top:none; }
.op b { display:block; font-size:13.5px; font-weight:600; }
.op small { display:block; font-size:12.5px; color:%(muted)s;
  overflow-wrap:anywhere; }
.bar { height:6px; border-radius:999px; background:%(sunken)s;
  margin-top:6px; overflow:hidden; }
.bar i { display:block; height:100%%; border-radius:999px; }
.opfoot { margin:12px 0 0; font-size:12.5px; color:%(muted)s; }
""" % {"muted": MUTED, "sunken": SUNKEN}


def operator_panels(runs: list, records: list, costs: list) -> str:
    """Runs, memory and spend — read-only, and honest when empty."""
    run_rows = "".join(
        f"<div class='op{' first' if i == 0 else ''}'>"
        f"<b>{e(r.get('label'))}</b><small>{e(r.get('meta'))}</small></div>"
        for i, r in enumerate(runs[:6])
    ) or ("<p class='none'>Nothing has run yet. Ask your team a question and "
          "the run appears here.</p>")

    mem_rows = "".join(
        f"<div class='op{' first' if i == 0 else ''}'>"
        f"<b>{e(m.get('key'))}</b><small>{e(m.get('value'))}</small>"
        f"<small>{e(m.get('store'))} &middot; {e(m.get('by'))}</small></div>"
        for i, m in enumerate(records[:6])
    ) or ("<p class='none'>Your team has not written anything down yet. What "
          "it learns about your shop is listed here.</p>")

    cost_rows = "".join(
        f"<div class='op{' first' if i == 0 else ''}'>"
        f"<b>{e(c.get('name'))}</b>"
        f"<small>{e(c.get('tok'))} tokens &middot; {e(c.get('cost'))}</small>"
        f"<div class='bar'><i style='width:{int(c.get('pct') or 2)}%;"
        f"background:{c.get('color') or ACCENT}'></i></div></div>"
        for i, c in enumerate(costs[:6])
    ) or ("<p class='none'>No model calls billed yet.</p>")

    return (
        f"<div class='ops'>"
        f"<div class='card'><h3>Recent runs</h3>"
        f"<p class='lede'>Every question, and how far it got.</p>"
        f"{run_rows}</div>"
        f"<div class='card'><h3>What it remembers</h3>"
        f"<p class='lede'>The shared memory every agent reads and writes.</p>"
        f"{mem_rows}</div>"
        f"<div class='card'><h3>What it cost</h3>"
        f"<p class='lede'>Model spend this session, per agent.</p>"
        f"{cost_rows}</div>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# The account, inside Settings
# ---------------------------------------------------------------------------
#
# These forms post to the same endpoints the standalone account screen used.
# Only their surroundings changed: they sit in the rail now, so changing your
# password no longer means leaving the workspace and coming back.

SETTINGS_CSS = """
.sec { margin:26px 0 12px; font-size:15px; font-weight:700;
  letter-spacing:-.015em; }
.pair { display:grid; grid-template-columns:repeat(2,minmax(0,1fr));
  gap:0 14px; }
.acct { max-width:980px; }
.acct .card { margin-bottom:14px; }
.acct h3 { margin:0 0 4px; font-size:15px; letter-spacing:-.015em; }
.acct .lede { margin:0 0 14px; font-size:12.5px; color:%(muted)s; }
.acct .go { margin-top:4px; }
@media (max-width: 860px) { .pair { grid-template-columns:1fr; } }
""" % {"muted": MUTED}


def _account_section(account: dict, shop_stats: dict | None = None) -> str:
    """Who you are, what your shop is called, and how to sign out."""
    account = account or {}
    stage = account.get("business_stage") or "starting"
    stats = shop_stats or {}
    learned = " · ".join(f"{v} {k}" for k, v in stats.items() if v) \
        or "nothing recorded yet"

    def field(name: str, label: str, value: str = "") -> str:
        return (f"<div class='field'><label for='{name}'>{e(label)}</label>"
                f"<input id='{name}' name='{name}' value='{e(value)}'></div>")

    return (
        f"<div class='acct'>"
        f"<div class='sec'>Your shop and your account</div>"

        f"<div class='card'>"
        f"<h3>Your details</h3>"
        f"<p class='lede'>Your team uses these as facts about the business, "
        f"not as guesses.</p>"
        f"<form method='post' action='/account'>"
        f"<div class='pair'>"
        f"{field('owner_name', 'Your name', account.get('owner_name') or '')}"
        f"{field('business_name', 'Shop name', account.get('business_name') or '')}"
        f"</div><div class='pair'>"
        f"{field('location', 'Where you sell', account.get('location') or '')}"
        f"{field('currency', 'Currency', account.get('currency') or 'BDT')}"
        f"</div>"
        f"{field('what_you_sell', 'What you sell', account.get('what_you_sell') or '')}"
        f"<div class='field'><label for='business_stage'>Where you are</label>"
        f"<select id='business_stage' name='business_stage'>"
        f"<option value='starting'{' selected' if stage == 'starting' else ''}>"
        f"Starting out - help me work out what to sell</option>"
        f"<option value='running'{' selected' if stage == 'running' else ''}>"
        f"Already selling - help me run it</option></select></div>"
        f"<button class='btn go' type='submit'>Save changes</button>"
        f"</form></div>"

        f"<div class='card'>"
        f"<h3>Your photo</h3>"
        f"<p class='lede'>Shown at the bottom of the rail.</p>"
        f"<form method='post' action='/account/avatar' "
        f"enctype='multipart/form-data'>"
        f"<div class='field'><input type='file' name='avatar' "
        f"accept='image/*' required></div>"
        f"<button class='btn btn-quiet go' type='submit'>Upload photo</button>"
        f"</form></div>"

        f"<div class='card'>"
        f"<h3>Password</h3>"
        f"<form method='post' action='/account/password'>"
        f"<div class='pair'>"
        f"<div class='field'><label for='current'>Current password</label>"
        f"<input id='current' name='current' type='password' required "
        f"autocomplete='current-password'></div>"
        f"<div class='field'><label for='new'>New password</label>"
        f"<input id='new' name='new' type='password' required minlength='8' "
        f"autocomplete='new-password'></div></div>"
        f"<button class='btn btn-quiet go' type='submit'>Change password"
        f"</button></form></div>"

        f"<div class='card'>"
        f"<h3>Your shop's memory</h3>"
        f"<p class='lede'>Everything your team has learned lives in a "
        f"database of its own, separate from every other account: "
        f"{e(learned)}.</p>"
        f"<form method='post' action='/logout'>"
        f"<button class='btn btn-quiet go' type='submit'>Sign out</button>"
        f"</form></div>"
        f"</div>"
    )
