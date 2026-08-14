"""Sign-in, sign-up and account screens, in the Business Suite design language.

These pages do not exist in the design bundle, so they are written here rather
than patched into it — but they use the same tokens, radii, type and spacing,
so they read as the same product. The workspace itself is still the design's
own markup, untouched.

Everything is plain HTML forms. No React, no runtime: an owner who cannot sign
in should not be depending on a 3 MB bundle to do it.
"""

from __future__ import annotations

import html
from typing import Any

# Tokens, matching web/design and ui/theme.py.
GROUND = "#F7F5F0"
RAIL = "#FBFAF7"
SURFACE = "#FFFFFF"
SUNKEN = "#F1EEE6"
BORDER = "#E5E0D6"
INK = "#18211D"
BODY = "#4A554E"
MUTED = "#7C877F"
GREEN = "#14603F"
GREEN_TINT = "#EAF1EC"
BUTTON = "#7B1E22"
BUTTON_DARK = "#5E1519"
BUTTON_TINT = "#F6E9EA"
DANGER = "#A63A2E"
DANGER_TINT = "#F8E9E6"
SERIF = "'Instrument Serif', Georgia, serif"
SANS = "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Plus+Jakarta+Sans:wght@200..800&'
    'family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">'
)

BASE_CSS = f"""
*,*::before,*::after {{ box-sizing: border-box; }}
html,body {{ margin:0; padding:0; background:{GROUND}; color:{INK};
  font-family:{SANS}; font-size:14px; -webkit-font-smoothing:antialiased; }}
a {{ color:{BUTTON}; text-decoration:none; }}
a:hover {{ color:{BUTTON_DARK}; text-decoration:underline; }}
h1 {{ font-family:{SERIF}; font-weight:400; letter-spacing:-0.01em; margin:0; }}
label {{ display:block; font-size:12.5px; color:{MUTED}; margin:0 0 5px;
  font-weight:500; }}
input, select, textarea {{
  width:100%; padding:10px 12px; border-radius:10px; border:1px solid {BORDER};
  background:{RAIL}; color:{INK}; font-size:13.5px; font-family:inherit; }}
input:focus, select:focus, textarea:focus {{
  outline:none; border-color:{BUTTON}; box-shadow:0 0 0 3px {BUTTON_TINT}; }}
.field {{ margin-bottom:14px; }}
.row {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.btn {{ width:100%; padding:11px 15px; border-radius:9px; border:none;
  background:{BUTTON}; color:{GROUND}; font-size:13.5px; font-weight:600;
  cursor:pointer; font-family:inherit; }}
.btn:hover {{ background:{BUTTON_DARK}; }}
.btn-quiet {{ background:{SURFACE}; color:{BODY}; border:1px solid {BORDER};
  font-weight:500; }}
.btn-quiet:hover {{ background:{SURFACE}; border-color:{BUTTON}; color:{BUTTON}; }}
.card {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:14px;
  padding:22px 24px; }}
.note {{ font-size:12.5px; color:{MUTED}; line-height:1.55; }}
.alert {{ background:{DANGER_TINT}; border:1px solid {DANGER}; color:{DANGER};
  border-radius:10px; padding:10px 13px; font-size:13px; margin-bottom:16px; }}
.ok {{ background:{GREEN_TINT}; border:1px solid {GREEN}; color:{GREEN};
  border-radius:10px; padding:10px 13px; font-size:13px; margin-bottom:16px; }}
.mark {{ width:38px; height:38px; border-radius:12px; background:{GREEN};
  color:#F4EFE2; display:grid; place-items:center; font-family:{SERIF};
  font-size:21px; }}
"""


def _e(v: Any) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def _page(title: str, body: str, extra_css: str = "") -> str:
    return (
        f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(title)} · Lucida</title>{FONTS}"
        f"<style>{BASE_CSS}{extra_css}</style></head><body>{body}</body></html>"
    )


def _brand(sub: str) -> str:
    return (
        f"<div style='display:flex;align-items:center;gap:11px;margin-bottom:22px;'>"
        f"<div class='mark'>L</div><div style='line-height:1.25;'>"
        f"<div style='font-weight:600;font-size:15px;'>Lucida</div>"
        f"<div style='font-size:12px;color:{MUTED};'>{_e(sub)}</div>"
        f"</div></div>"
    )


def _alert(message: str, kind: str = "alert") -> str:
    return f"<div class='{kind}'>{_e(message)}</div>" if message else ""


# ---------------------------------------------------------------------------
# Sign in
# ---------------------------------------------------------------------------


SPLIT_CSS = f"""
.split {{ min-height:100vh; display:grid; grid-template-columns:1fr 1fr; }}
.pitch {{ background:{RAIL}; border-right:1px solid {BORDER};
  padding:56px 52px; display:flex; flex-direction:column; justify-content:center; }}
.form-side {{ padding:56px 52px; display:flex; flex-direction:column;
  justify-content:center; }}
.form-wrap {{ width:100%; max-width:430px; margin:0 auto; }}
.bullet {{ display:flex; gap:11px; margin-bottom:15px; }}
.bullet .dot {{ width:7px;height:7px;border-radius:50%;background:{GREEN};
  margin-top:7px;flex:none; }}
@media (max-width: 900px) {{
  .split {{ grid-template-columns:1fr; }}
  .pitch {{ display:none; }}
}}
"""


def _pitch() -> str:
    points = [
        ("Starting out?",
         "Tell it what you're thinking and it researches the market, prices "
         "the product and tells you plainly whether it's worth doing."),
        ("Already trading?",
         "It reads your messages, tracks stock, writes your ads and warns you "
         "before you run out — and asks before it spends anything."),
        ("You stay in charge",
         "Nothing is published, ordered or delivered until you approve it."),
    ]
    body = "".join(
        f"<div class='bullet'><span class='dot'></span><div>"
        f"<div style='font-weight:600;font-size:14px;margin-bottom:3px;'>{_e(t)}</div>"
        f"<div class='note'>{_e(d)}</div></div></div>"
        for t, d in points
    )
    return (
        f"<div class='pitch'><div style='max-width:420px;'>"
        f"{_brand('a supervisor and eight specialists')}"
        f"<h1 style='font-size:34px;margin-bottom:10px;'>"
        f"A whole team for your shop.</h1>"
        f"<p class='note' style='font-size:14px;margin:0 0 26px;'>"
        f"One supervisor routes work to eight specialists — research, pricing, "
        f"stock, marketing, customers, delivery — and stops at your gates.</p>"
        f"{body}</div></div>"
    )


def login_page(error: str = "", email: str = "", notice: str = "") -> str:
    body = (
        f"<div class='split'>{_pitch()}"
        f"<div class='form-side'><div class='form-wrap'>"
        f"<h1 style='font-size:27px;margin-bottom:6px;'>Welcome back.</h1>"
        f"<p class='note' style='margin:0 0 22px;'>Sign in to your shop.</p>"
        f"{_alert(notice, 'ok')}{_alert(error)}"
        f"<form method='post' action='/login'>"
        f"<div class='field'><label for='email'>Email</label>"
        f"<input id='email' name='email' type='email' required "
        f"autocomplete='email' value='{_e(email)}'></div>"
        f"<div class='field'><label for='password'>Password</label>"
        f"<input id='password' name='password' type='password' required "
        f"autocomplete='current-password'></div>"
        f"<button class='btn' type='submit'>Sign in</button></form>"
        f"<p class='note' style='margin-top:18px;text-align:center;'>"
        f"New here? <a href='/signup'>Create an account</a></p>"
        f"</div></div></div>"
    )
    return _page("Sign in", body, SPLIT_CSS)


# ---------------------------------------------------------------------------
# Sign up
# ---------------------------------------------------------------------------


SIGNUP_CSS = SPLIT_CSS + f"""
.choice {{ display:grid; grid-template-columns:1fr 1fr; gap:10px;
  margin-bottom:18px; }}
.choice input {{ position:absolute; opacity:0; pointer-events:none; }}
.choice label {{ display:block; margin:0; cursor:pointer; padding:13px 14px;
  border:1px solid {BORDER}; border-radius:12px; background:{SURFACE};
  color:{BODY}; font-size:13px; font-weight:500; line-height:1.4; }}
.choice input:checked + label {{ border-color:{BUTTON};
  background:{BUTTON_TINT}; color:{BUTTON}; font-weight:600; }}
.choice label .sub {{ display:block; font-size:11.5px; color:{MUTED};
  font-weight:400; margin-top:3px; }}
.choice input:checked + label .sub {{ color:{BUTTON}; }}
"""


def signup_page(error: str = "", values: dict[str, Any] | None = None) -> str:
    v = values or {}
    stage = v.get("business_stage") or "starting"
    body = (
        f"<div class='split'>{_pitch()}"
        f"<div class='form-side'><div class='form-wrap'>"
        f"<h1 style='font-size:27px;margin-bottom:6px;'>Set up your shop.</h1>"
        f"<p class='note' style='margin:0 0 20px;'>Two minutes. You can change "
        f"any of this later.</p>"
        f"{_alert(error)}"
        f"<form method='post' action='/signup'>"

        f"<label>Where are you today?</label>"
        f"<div class='choice'>"
        f"<div><input type='radio' id='st-starting' name='business_stage' "
        f"value='starting'{' checked' if stage == 'starting' else ''}>"
        f"<label for='st-starting'>I'm starting out"
        f"<span class='sub'>No business yet — help me work out what to sell"
        f"</span></label></div>"
        f"<div><input type='radio' id='st-running' name='business_stage' "
        f"value='running'{' checked' if stage == 'running' else ''}>"
        f"<label for='st-running'>I already sell"
        f"<span class='sub'>I have a business — help me run it</span></label>"
        f"</div></div>"

        f"<div class='row'>"
        f"<div class='field'><label for='owner_name'>Your name</label>"
        f"<input id='owner_name' name='owner_name' value='{_e(v.get('owner_name'))}'>"
        f"</div>"
        f"<div class='field'><label for='business_name'>Shop name "
        f"<span style='color:{MUTED};font-weight:400;'>(optional)</span></label>"
        f"<input id='business_name' name='business_name' "
        f"value='{_e(v.get('business_name'))}'></div></div>"

        f"<div class='row'>"
        f"<div class='field'><label for='location'>Where you sell</label>"
        f"<input id='location' name='location' placeholder='Mirpur 11, Dhaka' "
        f"value='{_e(v.get('location'))}'></div>"
        f"<div class='field'><label for='what_you_sell'>What you sell "
        f"<span style='color:{MUTED};font-weight:400;'>(or hope to)</span></label>"
        f"<input id='what_you_sell' name='what_you_sell' "
        f"placeholder='shingara, samosa' value='{_e(v.get('what_you_sell'))}'>"
        f"</div></div>"

        f"<div class='field'><label for='email'>Email</label>"
        f"<input id='email' name='email' type='email' required "
        f"autocomplete='email' value='{_e(v.get('email'))}'></div>"
        f"<div class='field'><label for='password'>Password</label>"
        f"<input id='password' name='password' type='password' required "
        f"minlength='8' autocomplete='new-password'>"
        f"<div class='note' style='margin-top:5px;'>At least 8 characters.</div>"
        f"</div>"

        f"<button class='btn' type='submit'>Create my shop</button></form>"
        f"<p class='note' style='margin-top:18px;text-align:center;'>"
        f"Already have an account? <a href='/login'>Sign in</a></p>"
        f"</div></div></div>"
    )
    return _page("Create your shop", body, SIGNUP_CSS)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


ACCOUNT_CSS = f"""
.wrap {{ max-width:760px; margin:0 auto; padding:34px 24px 70px; }}
.top {{ display:flex; align-items:center; gap:14px; margin-bottom:26px; }}
.avatar {{ width:64px; height:64px; border-radius:20px; object-fit:cover;
  border:1px solid {BORDER}; background:{GREEN}; color:#F4EFE2;
  display:grid; place-items:center; font-family:{SERIF}; font-size:26px; }}
.sec {{ font-size:16px; font-weight:600; margin:26px 0 12px; }}
.pill {{ display:inline-flex; align-items:center; font-size:11.5px;
  font-weight:500; padding:3px 9px; border-radius:999px;
  background:{GREEN_TINT}; color:{GREEN}; }}
.back {{ font-size:13px; color:{BODY}; }}
.actions {{ display:flex; gap:10px; margin-top:16px; }}
.actions .btn {{ width:auto; }}
"""


def account_page(
    account: dict[str, Any],
    error: str = "",
    notice: str = "",
    shop_stats: dict[str, int] | None = None,
) -> str:
    stage = account.get("business_stage") or "starting"
    avatar = account.get("avatar_path")
    face = (
        f"<img class='avatar' src='/avatar/{_e(account['id'])}' alt='Your photo'>"
        if avatar else
        f"<div class='avatar'>{_e(_initials(account))}</div>"
    )
    stats = shop_stats or {}
    stat_line = " · ".join(
        f"{v} {k}" for k, v in stats.items() if v
    ) or "nothing recorded yet"

    body = (
        f"<div class='wrap'>"
        f"<p class='back'><a href='/'>&larr; Back to your shop</a></p>"
        f"<div class='top'>{face}<div>"
        f"<h1 style='font-size:27px;'>{_e(account.get('owner_name') or 'Your account')}</h1>"
        f"<div class='note' style='margin-top:4px;'>{_e(account.get('email'))} · "
        f"<span class='pill'>{'Already selling' if stage == 'running' else 'Starting out'}"
        f"</span></div></div></div>"
        f"{_alert(notice, 'ok')}{_alert(error)}"

        f"<div class='card'>"
        f"<div class='sec' style='margin-top:0;'>Your details</div>"
        f"<form method='post' action='/account'>"
        f"<div class='row'>"
        f"<div class='field'><label for='owner_name'>Your name</label>"
        f"<input id='owner_name' name='owner_name' "
        f"value='{_e(account.get('owner_name'))}'></div>"
        f"<div class='field'><label for='business_name'>Shop name</label>"
        f"<input id='business_name' name='business_name' "
        f"value='{_e(account.get('business_name'))}'></div></div>"
        f"<div class='row'>"
        f"<div class='field'><label for='location'>Where you sell</label>"
        f"<input id='location' name='location' "
        f"value='{_e(account.get('location'))}'></div>"
        f"<div class='field'><label for='currency'>Currency</label>"
        f"<input id='currency' name='currency' "
        f"value='{_e(account.get('currency') or 'BDT')}'></div></div>"
        f"<div class='field'><label for='what_you_sell'>What you sell</label>"
        f"<input id='what_you_sell' name='what_you_sell' "
        f"value='{_e(account.get('what_you_sell'))}'></div>"
        f"<div class='field'><label for='business_stage'>Where you are</label>"
        f"<select id='business_stage' name='business_stage'>"
        f"<option value='starting'{' selected' if stage == 'starting' else ''}>"
        f"Starting out — help me work out what to sell</option>"
        f"<option value='running'{' selected' if stage == 'running' else ''}>"
        f"Already selling — help me run it</option></select>"
        f"<div class='note' style='margin-top:5px;'>This changes where your "
        f"team starts: research and validation, or day-to-day management.</div>"
        f"</div>"
        f"<div class='actions'><button class='btn' type='submit'>Save changes</button>"
        f"</div></form></div>"

        f"<div class='card' style='margin-top:16px;'>"
        f"<div class='sec' style='margin-top:0;'>Your photo</div>"
        f"<p class='note' style='margin:0 0 12px;'>Shown in the corner of your "
        f"workspace. Click it any time to come back here.</p>"
        f"<form method='post' action='/account/avatar' enctype='multipart/form-data'>"
        f"<div class='field'><input type='file' name='avatar' accept='image/*' required>"
        f"</div>"
        f"<div class='actions'><button class='btn btn-quiet' type='submit'>"
        f"Upload photo</button></div></form></div>"

        f"<div class='card' style='margin-top:16px;'>"
        f"<div class='sec' style='margin-top:0;'>Password</div>"
        f"<form method='post' action='/account/password'>"
        f"<div class='row'>"
        f"<div class='field'><label for='current'>Current password</label>"
        f"<input id='current' name='current' type='password' required "
        f"autocomplete='current-password'></div>"
        f"<div class='field'><label for='new'>New password</label>"
        f"<input id='new' name='new' type='password' required minlength='8' "
        f"autocomplete='new-password'></div></div>"
        f"<div class='actions'><button class='btn btn-quiet' type='submit'>"
        f"Change password</button></div></form></div>"

        f"<div class='card' style='margin-top:16px;'>"
        f"<div class='sec' style='margin-top:0;'>Your shop's memory</div>"
        f"<p class='note' style='margin:0 0 12px;'>Everything your team has "
        f"learned lives in a database of its own, separate from every other "
        f"account: {_e(stat_line)}.</p>"
        f"<form method='post' action='/logout'>"
        f"<div class='actions'><button class='btn btn-quiet' type='submit'>"
        f"Sign out</button></div></form></div>"
        f"</div>"
    )
    return _page("Your account", body, ACCOUNT_CSS)


def _initials(account: dict[str, Any]) -> str:
    source = (account.get("owner_name") or account.get("business_name")
              or account.get("email") or "?")
    parts = [p for p in str(source).replace("@", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "?"
