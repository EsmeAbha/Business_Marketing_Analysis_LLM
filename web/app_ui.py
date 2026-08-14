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
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

NAV = [
    ("/", "Chat", "Ask your team anything"),
    ("/studio", "Ad studio", "Make posters and ad copy"),
    ("/delivery", "Delivery", "Weigh it, price it, book the courier"),
    ("/connect", "Connect", "Channels and couriers"),
    ("/board", "Dashboard", "Stock, money, customers, runs"),
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
  padding:20px 22px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
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
    nav = "".join(
        f"<a class='nav{' on' if href == active else ''}' href='{href}'>"
        f"<div>{e(label)}<small>{e(sub)}</small></div></a>"
        for href, label, sub in NAV
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
    return (
        f"<div class='hist'><h5>Conversations"
        f"<a href='/chat/new'>+ New</a></h5>{rows}</div>"
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
                  courier: str = "", note: str = "") -> str:
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
        f"<h3 style='margin:0 0 14px;font-size:15px'>What is going where</h3>"
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
NEEDS = {
    "messenger": ("Page access token", "Facebook Page id",
                  "Both come from the same Meta app. A Page token is what "
                  "reads the messages; a user token cannot."),
    "facebook": ("Page access token", "Facebook Page id",
                 "The same token and Page as Messenger — Meta treats them "
                 "as one thing, so connecting either connects both."),
    "instagram": ("Page access token", "Instagram Business account id",
                  "The token is the Facebook Page's. The id is the Instagram "
                  "Business account linked to that Page, not the handle."),
    "steadfast": ("API key", "Secret key",
                  "Both come from the API page of your Steadfast merchant "
                  "portal. They are checked against your account balance "
                  "before they are saved."),
    "pathao": ("Client id", "Client secret",
               "Both come from Developer API in the Pathao Merchant panel. "
               "A token is issued to prove they work before they are saved."),
    "youtube": ("OAuth refresh token", "",
                "An API key cannot upload — the upload happens as you, not "
                "as the app, so it has to be a refresh token."),
}


def connect_form(account: dict, platform: str, has_oauth: bool,
                 redirect_uri: str, error: str = "") -> str:
    """Paste a credential. Checked against the live API before it is saved."""
    token_label, ident_label, why = NEEDS.get(platform, ("Token", "Id", ""))
    warn = (f"<div class='note bad'>{e(error)}</div>" if error else "")
    ident_field = (
        f"<div class='field'><label for='ident'>{e(ident_label)}</label>"
        f"<input id='ident' name='ident' required "
        f"placeholder='numbers only'></div>"
    ) if ident_label else ""
    alt = (
        f"<p class='muted' style='margin-top:14px'>Or "
        f"<a href='/connect/{e(platform)}' style='color:{ACCENT};"
        f"font-weight:600'>sign in with {e(platform.title())}</a> instead and "
        f"never handle a token.</p>"
    ) if has_oauth else (
        f"<p class='muted' style='margin-top:14px'>One-click sign-in is off "
        f"because this machine has no app registered with the platform. To "
        f"turn it on, register one and set its id and secret, with "
        f"<code>{e(redirect_uri)}</code> as the redirect.</p>"
    )

    body = (
        f"<div class='body'><div class='card' style='max-width:560px'>"
        f"{warn}"
        f"<p class='muted' style='margin-top:0'>{e(why)}</p>"
        f"<form method='post' action='/connect/{e(platform)}/save'>"
        f"<div class='field'><label for='token'>{e(token_label)}</label>"
        f"<textarea id='token' name='token' rows='3' required "
        f"placeholder='paste it here'></textarea></div>"
        f"{ident_field}"
        f"<button class='btn' type='submit'>Check and connect</button>"
        f"<a class='btn btn-quiet' href='/connect' "
        f"style='margin-left:8px;display:inline-block'>Cancel</a>"
        f"</form>{alt}"
        f"<p class='muted' style='margin-top:14px'>Nothing is saved unless "
        f"the platform confirms the credential works. It is stored in your "
        f"shop's own database, not in a file shared with anyone else.</p>"
        f"</div></div>"
    )
    head = (
        f"<div class='head'><h1>Connect {e(platform.title())}</h1>"
        f"<p>Give it a credential and it will be checked straight away.</p>"
        f"</div>"
    )
    return shell(f"Connect {platform}", account, "/connect", head, body,
                 CONNECT_CSS)


def connect_page(account: dict, channels: dict, image_provider: str,
                 db_backend: str, has_llm: bool,
                 oauth: dict | None = None, note: str = "") -> str:
    oauth = oauth or {}
    head = (
        "<div class='head'><h1>Connect your accounts</h1>"
        "<p>Everything works without these — your team just cannot read or "
        "post to a platform it has no key for.</p></div>"
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

    extras = (
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
    return shell("Connect", account, "/connect", head, body, CONNECT_CSS)
