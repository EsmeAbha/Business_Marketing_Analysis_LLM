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
    ("/connect", "Connect", "Messenger, Instagram, Facebook, YouTube"),
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
  position:sticky; top:0; height:100vh; }}
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

.main {{ display:flex; flex-direction:column; min-width:0; }}
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
          extra_css: str = "", extra_js: str = "") -> str:
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
        f"{nav}"
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
.msg {{ display:flex; gap:13px; margin-bottom:26px; }}
.who-b {{ width:30px; height:30px; border-radius:9px; flex:none;
  display:grid; place-items:center; font-size:12px; font-weight:600; }}
.you {{ background:{SUNKEN}; color:{INK}; }}
.them {{ background:{ACCENT}; color:#fff; }}
.bubble {{ min-width:0; flex:1; }}
.bubble .name {{ font-size:13px; font-weight:600; margin-bottom:3px; }}
.bubble .text {{ font-size:15px; line-height:1.68; color:{INK};
  white-space:pre-wrap; word-wrap:break-word; }}
.bubble .text h3 {{ font-size:15px; margin:16px 0 5px; font-weight:700; }}
.bubble .text ul {{ margin:8px 0; padding-left:20px; }}
.bubble .text li {{ margin:4px 0; }}
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
  const el = document.createElement('div');
  el.className = 'msg';
  el.innerHTML = '<div class="who-b ' + who + '">' + esc(name[0]) + '</div>'
    + '<div class="bubble"><div class="name">' + esc(name) + '</div>'
    + '<div class="text">' + (raw ? raw : md(text)) + '</div></div>';
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


def chat_page(account: dict, history: list[dict], starters: list[str]) -> str:
    if history:
        msgs = "".join(
            f"<div class='msg'><div class='who-b "
            f"{'you' if m['role'] == 'user' else 'them'}'>"
            f"{e((('You' if m['role'] == 'user' else 'Your team'))[0])}</div>"
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
    return shell("Chat", account, "/", "", body, CHAT_CSS, CHAT_JS)


# ---------------------------------------------------------------------------
# Ad studio
# ---------------------------------------------------------------------------

STUDIO_CSS = f"""
.grid {{ display:grid; grid-template-columns:360px minmax(0,1fr); gap:22px;
  align-items:start; }}
.preview {{ border:1px solid {BORDER}; border-radius:16px; overflow:hidden;
  background:{SUNKEN}; aspect-ratio:1/1; display:grid; place-items:center; }}
.preview img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.ph {{ text-align:center; color:{MUTED}; font-size:13.5px; padding:24px; }}
.sizes {{ display:flex; gap:8px; margin-bottom:14px; }}
.size {{ flex:1; padding:9px; border-radius:10px; border:1px solid {BORDER};
  background:{SURFACE}; font-size:13px; cursor:pointer; text-align:center; }}
.size.on {{ border-color:{ACCENT}; background:{ACCENT_TINT}; color:{ACCENT};
  font-weight:600; }}
.copy {{ white-space:pre-wrap; font-size:14px; line-height:1.65; }}
.tag {{ font-size:11px; font-weight:600; letter-spacing:.05em;
  text-transform:uppercase; padding:3px 8px; border-radius:6px;
  background:{ACCENT_TINT}; color:{ACCENT}; }}
@media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} }}
"""

STUDIO_JS = r"""
let preset = 'square';
document.querySelectorAll('.size').forEach(b => b.onclick = () => {
  document.querySelectorAll('.size').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); preset = b.dataset.preset;
});

const go = document.getElementById('go');
const out = document.getElementById('art');
const copyBox = document.getElementById('copy');

go.onclick = async () => {
  const product = document.getElementById('product').value.trim();
  if (!product) { document.getElementById('product').focus(); return; }
  go.disabled = true; go.textContent = 'Making it…';
  out.innerHTML = '<div class="ph">Drawing your poster…</div>';
  copyBox.innerHTML = '<div class="ph">Writing the words…</div>';
  try {
    const r = await fetch('/api/studio/generate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        product,
        offer: document.getElementById('offer').value.trim(),
        audience: document.getElementById('audience').value.trim(),
        style: document.getElementById('style').value,
        preset
      })
    });
    const d = await r.json();
    if (!r.ok) {
      out.innerHTML = '<div class="ph" style="color:#B91C1C">'
        + (d.error || 'Could not make it') + '</div>';
      copyBox.innerHTML = '';
    } else {
      out.innerHTML = d.image
        ? '<img src="' + d.image + '" alt="Generated poster">'
        : '<div class="ph">' + (d.image_error || 'No image') + '</div>';
      copyBox.innerHTML = '<div class="copy">' + (d.copy_html || '') + '</div>';
      document.getElementById('saved').style.display = d.image ? 'flex' : 'none';
      document.getElementById('dl').href = d.image || '#';
    }
  } catch (err) {
    out.innerHTML = '<div class="ph" style="color:#B91C1C">' + err + '</div>';
  }
  go.disabled = false; go.textContent = 'Make the ad';
};
"""


def studio_page(account: dict, provider: str, channels: dict) -> str:
    head = (
        "<div class='head'><h1>Ad studio</h1>"
        "<p>Describe what you sell. Your team draws the poster and writes the "
        "words for each place you post.</p></div>"
    )
    where = " · ".join(
        f"{k.title()} {'connected' if 'needs' not in v else 'not connected'}"
        for k, v in channels.items()
    )
    body = (
        f"<div class='body'><div class='grid'>"

        f"<div class='card'>"
        f"<div class='field'><label for='product'>What are you advertising?</label>"
        f"<input id='product' placeholder='handmade resin coasters, set of 4'>"
        f"</div>"
        f"<div class='field'><label for='offer'>Any offer? "
        f"<span class='muted'>(optional)</span></label>"
        f"<input id='offer' placeholder='2 for 1 this week'></div>"
        f"<div class='field'><label for='audience'>Who is it for? "
        f"<span class='muted'>(optional)</span></label>"
        f"<input id='audience' placeholder='students in Dhaka'></div>"
        f"<div class='field'><label for='style'>Look</label>"
        f"<select id='style'>"
        f"<option value='clean studio product photography'>Clean studio</option>"
        f"<option value='warm lifestyle scene, natural light'>Warm lifestyle</option>"
        f"<option value='bold flat colour, graphic poster'>Bold graphic</option>"
        f"<option value='rustic wooden surface, cosy'>Rustic</option>"
        f"</select></div>"
        f"<label>Size</label>"
        f"<div class='sizes'>"
        f"<div class='size on' data-preset='square'>Post<br>"
        f"<span class='muted' style='font-size:11px'>1:1</span></div>"
        f"<div class='size' data-preset='story'>Story<br>"
        f"<span class='muted' style='font-size:11px'>9:16</span></div>"
        f"<div class='size' data-preset='wide'>Wide<br>"
        f"<span class='muted' style='font-size:11px'>16:9</span></div>"
        f"</div>"
        f"<button class='btn' id='go' style='width:100%'>Make the ad</button>"
        f"<p class='muted' style='margin:12px 0 0'>Drawn by {e(provider)}. "
        f"Artwork is generated, not a photograph of your stock — say so if a "
        f"customer asks.</p>"
        f"</div>"

        f"<div>"
        f"<div class='preview' id='art'>"
        f"<div class='ph'>Your poster appears here</div></div>"
        f"<div id='saved' style='display:none;gap:9px;margin-top:12px'>"
        f"<a class='btn btn-quiet' id='dl' download>Download the image</a>"
        f"</div>"
        f"<div class='card' style='margin-top:16px'>"
        f"<span class='tag'>Ad copy</span>"
        f"<div id='copy' style='margin-top:12px'>"
        f"<div class='ph'>Words for Facebook, Instagram and YouTube appear "
        f"here.</div></div></div>"
        f"<p class='muted' style='margin-top:12px'>Publishing goes to: "
        f"{e(where)}. <a href='/connect' style='text-decoration:underline'>"
        f"Connect an account</a> to post straight from here.</p>"
        f"</div>"

        f"</div></div>"
    )
    return shell("Ad studio", account, "/studio", head, body,
                 STUDIO_CSS, STUDIO_JS)


# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------

CONNECT_CSS = f"""
.rows {{ display:flex; flex-direction:column; gap:12px; max-width:820px; }}
.row {{ display:flex; align-items:center; gap:14px; padding:18px 20px;
  border:1px solid {BORDER}; border-radius:16px; background:{SURFACE}; }}
.icon {{ width:42px; height:42px; border-radius:11px; display:grid;
  place-items:center; font-size:17px; font-weight:700; color:#fff; flex:none; }}
.row h3 {{ margin:0 0 2px; font-size:15px; font-weight:600;
  letter-spacing:-.01em; }}
.row p {{ margin:0; font-size:13px; color:{MUTED}; line-height:1.5; }}
.steps {{ margin:6px 0 0; padding-left:18px; font-size:12.5px; color:{MUTED};
  line-height:1.65; }}
.steps code {{ background:{SUNKEN}; padding:1px 5px; border-radius:4px;
  font-size:11.5px; }}
"""


def connect_page(account: dict, channels: dict, image_provider: str,
                 db_backend: str, has_llm: bool) -> str:
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
    }
    setup = {
        "messenger": ["Create a Meta app and connect your Page",
                      "Ask for <code>pages_messaging</code> in App Review",
                      "Put the token in <code>META_ACCESS_TOKEN</code> and the "
                      "page id in <code>META_PAGE_ID</code>"],
        "instagram": ["Convert the account to a Business or Creator account",
                      "Link it to your Facebook Page",
                      "Ask for <code>instagram_manage_messages</code> and "
                      "<code>instagram_manage_comments</code> in App Review",
                      "Put the id in <code>META_IG_USER_ID</code>"],
        "facebook": ["Same Meta app and Page as Messenger",
                     "<code>pages_manage_posts</code> covers publishing"],
        "youtube": ["Enable YouTube Data API v3 in Google Cloud",
                    "Create an OAuth client (Desktop app)",
                    "Authorise <code>youtube.upload</code> and exchange the "
                    "code for a refresh token",
                    "An API key alone cannot upload — it only reads"],
    }

    rows = ""
    for key, note in channels.items():
        colour, mark, what = brand.get(key, (ACCENT, "?", ""))
        connected = "needs" not in note
        steps = "" if connected else (
            "<ul class='steps'>"
            + "".join(f"<li>{s}</li>" for s in setup.get(key, []))
            + "</ul>"
        )
        rows += (
            f"<div class='row'>"
            f"<div class='icon' style='background:{colour}'>{mark}</div>"
            f"<div style='flex:1;min-width:0'><h3>{e(key.title())}</h3>"
            f"<p>{e(what)}</p>{steps}</div>"
            f"<span class='pill {'ok' if connected else 'warn'}'>"
            f"{'Connected' if connected else 'Not connected'}</span></div>"
        )

    extras = (
        f"<div class='row'><div class='icon' style='background:{ACCENT}'>AI</div>"
        f"<div style='flex:1'><h3>Ad artwork</h3><p>{e(image_provider)}</p></div>"
        f"<span class='pill ok'>Working</span></div>"
        f"<div class='row'><div class='icon' style='background:#3F3F46'>DB</div>"
        f"<div style='flex:1'><h3>Where your shop is stored</h3>"
        f"<p>{e(db_backend)}</p></div>"
        f"<span class='pill ok'>Working</span></div>"
        f"<div class='row'><div class='icon' style='background:#3F3F46'>AI</div>"
        f"<div style='flex:1'><h3>Your team's model</h3>"
        f"<p>{'Connected and answering' if has_llm else 'No API key set'}</p></div>"
        f"<span class='pill {'ok' if has_llm else 'bad'}'>"
        f"{'Working' if has_llm else 'Missing'}</span></div>"
    )

    body = (f"<div class='body'><div class='rows'>{rows}{extras}</div>"
            f"<p class='muted' style='margin-top:18px;max-width:820px'>"
            f"Until a platform is connected, your team works against a "
            f"stand-in inbox so you can see the flow — every result is "
            f"labelled as such, and nothing is written to your records as "
            f"though a real customer sent it.</p></div>")
    return shell("Connect", account, "/connect", head, body, CONNECT_CSS)
