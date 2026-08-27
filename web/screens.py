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
GROUND = "#FFFFFF"
RAIL = "#FAFAFA"
SURFACE = "#FFFFFF"
SUNKEN = "#F4F4F5"
BORDER = "#E4E4E7"
INK = "#000000"
BODY = "#3F3F46"
MUTED = "#71717A"
ACCENT = "#7B1E22"
ACCENT_TINT = "#FBEBEB"
BUTTON = "#7B1E22"
BUTTON_DARK = "#5E1519"
BUTTON_TINT = "#FBEBEB"
DANGER = "#B91C1C"
DANGER_TINT = "#FEE2E2"
RING = "rgba(0,0,0,.10)"
SERIF = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

# Built on shadcn/ui's conventions: its zinc neutrals, its radius scale, its
# ring-on-focus, and its habit of one solid primary against otherwise white
# surfaces. Written as plain CSS rather than pulled in as the library —
# shadcn ships React components compiled by Tailwind, and adding that build
# step to reach four form screens would cost more than it returns.
#
# The reference's DNA is in the specifics: a generous 16px card radius, a
# full-width pill action, and a headline set tight and heavy rather than
# large — that is what reads as "established" instead of "template".
BASE_CSS = f"""
*,*::before,*::after {{ box-sizing: border-box; }}
html,body {{ margin:0; padding:0; background:{GROUND}; color:{INK};
  font-family:{SANS}; font-size:14px; -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility; }}
a {{ color:{INK}; text-decoration:none; font-weight:500; }}
a:hover {{ text-decoration:underline; text-underline-offset:3px; }}
h1 {{ font-weight:800; letter-spacing:-0.033em; line-height:1.12; margin:0; }}
label {{ display:block; font-size:13px; color:{INK}; margin:0 0 6px;
  font-weight:500; letter-spacing:-0.006em; }}
input, select, textarea {{
  width:100%; padding:11px 13px; border-radius:10px;
  border:1px solid {BORDER}; background:{SURFACE}; color:{INK};
  font-size:14px; font-family:inherit; transition:border-color .15s,
  box-shadow .15s; }}
input::placeholder {{ color:{MUTED}; }}
input:focus, select:focus, textarea:focus {{
  outline:none; border-color:{INK}; box-shadow:0 0 0 3px {RING}; }}
.field {{ margin-bottom:16px; }}
.row {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}

/* The reference's action: full width, deeply rounded, solid, confident. */
.btn {{ width:100%; padding:13px 18px; border-radius:12px; border:none;
  background:{BUTTON}; color:#FFFFFF; font-size:15px; font-weight:600;
  letter-spacing:-0.011em; cursor:pointer; font-family:inherit;
  transition:background .15s, transform .06s; }}
.btn:hover {{ background:{BUTTON_DARK}; }}
.btn:active {{ transform:scale(.99); }}
.btn:focus-visible {{ outline:none; box-shadow:0 0 0 3px {RING}; }}
.btn-quiet {{ background:{SURFACE}; color:{INK}; border:1px solid {BORDER};
  font-weight:500; }}
.btn-quiet:hover {{ background:{SUNKEN}; }}

.card {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:16px;
  padding:26px 28px; box-shadow:0 1px 2px rgba(0,0,0,.04); }}
.note {{ font-size:14px; color:{MUTED}; line-height:1.6; }}
.alert {{ background:{DANGER_TINT}; border:1px solid {DANGER}; color:{DANGER};
  border-radius:10px; padding:11px 14px; font-size:13.5px; margin-bottom:16px;
  font-weight:500; }}
.ok {{ background:{ACCENT_TINT}; border:1px solid {ACCENT}; color:{ACCENT};
  border-radius:10px; padding:11px 14px; font-size:13.5px; margin-bottom:16px;
  font-weight:500; }}
.mark {{ width:40px; height:40px; border-radius:12px; background:{ACCENT};
  color:#FFFFFF; display:grid; place-items:center; font-weight:700;
  font-size:18px; letter-spacing:-0.02em; }}
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
.bullet .dot {{ width:7px;height:7px;border-radius:50%;background:{ACCENT};
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
        f"<h1 style='font-size:40px;margin-bottom:12px;'>"
        f"A whole team for your shop.</h1>"
        f"<p class='note' style='font-size:14px;margin:0 0 26px;'>"
        f"One supervisor routes work to eight specialists — research, pricing, "
        f"stock, marketing, customers, delivery — and stops at your gates.</p>"
        f"{body}</div></div>"
    )


GOOGLE_MARK = (
    "<svg width='17' height='17' viewBox='0 0 48 48' aria-hidden='true'>"
    "<path fill='#4285F4' d='M45.1 24.5c0-1.6-.1-2.7-.4-3.9H24v7.1h12.1c-.2 1.8-1.6 "
    "4.4-4.5 6.2l-.1.3 6.6 5 .5.1c4.2-3.9 6.5-9.5 6.5-14.8'/>"
    "<path fill='#34A853' d='M24 46c6 0 11-2 14.6-5.4l-7-5.4c-1.9 1.3-4.4 2.2-7.6 "
    "2.2-5.8 0-10.7-3.8-12.5-9l-.3.1-6.8 5.3-.1.3C8 40.3 15.4 46 24 46'/>"
    "<path fill='#FBBC05' d='M11.5 28.4c-.5-1.4-.8-2.9-.8-4.4s.3-3 .7-4.4v-.3l-6.9-5.4"
    "-.2.1C2.8 17 2 20.4 2 24s.8 7 2.3 10z'/>"
    "<path fill='#EA4335' d='M24 9.5c4.1 0 6.9 1.8 8.5 3.3l6.2-6C34.9 3.3 30 1 24 "
    "1 15.4 1 8 6.7 4.3 15l7.2 5.6C13.3 15.3 18.2 9.5 24 9.5'/></svg>"
)

GOOGLE_CSS = f"""
.gbtn {{ display:flex; align-items:center; justify-content:center; gap:9px;
  width:100%; padding:11px 15px; border-radius:9px; border:1px solid {BORDER};
  background:{SURFACE}; color:{INK}; font-size:13.5px; font-weight:500;
  cursor:pointer; font-family:inherit; text-decoration:none; }}
.gbtn:hover {{ border-color:{BUTTON}; color:{BUTTON}; text-decoration:none; }}
.or {{ display:flex; align-items:center; gap:11px; margin:16px 0;
  color:{MUTED}; font-size:12px; }}
.or::before, .or::after {{ content:''; flex:1; height:1px; background:{BORDER}; }}
.code-in {{ font-size:26px; letter-spacing:.5em; text-align:center;
  font-family:{SERIF}; padding:14px 12px; }}
"""


# ---------------------------------------------------------------------------
# Password reveal
# ---------------------------------------------------------------------------


# Icons are inline for the same reason GOOGLE_MARK is: the pages carry no
# script or icon bundle, and one <svg> costs less than a dependency.
EYE_ON = (
    "<svg class='on' width='17' height='17' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='2' stroke-linecap='round' "
    "stroke-linejoin='round' aria-hidden='true'>"
    "<path d='M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z'/>"
    "<circle cx='12' cy='12' r='3'/></svg>"
)
EYE_OFF = (
    "<svg class='off' width='17' height='17' viewBox='0 0 24 24' fill='none' "
    "stroke='currentColor' stroke-width='2' stroke-linecap='round' "
    "stroke-linejoin='round' aria-hidden='true'>"
    "<path d='M9.88 9.88a3 3 0 1 0 4.24 4.24'/>"
    "<path d='M10.73 5.08A10.4 10.4 0 0 1 12 5c7 0 10 7 10 7a13.2 13.2 0 0 1-1.67 2.68'/>"
    "<path d='M6.61 6.61A13.5 13.5 0 0 0 2 12s3 7 10 7a9.7 9.7 0 0 0 5.39-1.61'/>"
    "<path d='M2 2l20 20'/></svg>"
)

PASSWORD_CSS = f"""
.pw {{ position:relative; }}
/* Room for the button, so a long password never runs under it. */
.pw input {{ padding-right:42px; }}
.pw button {{ position:absolute; top:1px; right:1px; bottom:1px; width:40px;
  display:flex; align-items:center; justify-content:center; padding:0;
  border:none; background:none; color:{MUTED}; cursor:pointer;
  border-radius:0 9px 9px 0; }}
.pw button:hover {{ color:{INK}; }}
.pw button:focus-visible {{ outline:none; color:{INK};
  box-shadow:0 0 0 3px {RING}; }}
/* Without script the toggle does nothing, so it is not shown until the
   script removes the attribute. */
.pw button[hidden] {{ display:none; }}
.pw .off {{ display:none; }}
.pw.shown .on {{ display:none; }}
.pw.shown .off {{ display:block; }}
"""

# Not an f-string: the braces below are JavaScript's, not format fields.
PASSWORD_JS = """<script>
document.querySelectorAll('.pw > button').forEach(function (btn) {
  btn.hidden = false;
  btn.addEventListener('click', function () {
    var wrap = btn.parentNode, input = wrap.querySelector('input');
    var show = input.type === 'password';
    // Switching type resets the caret in most browsers; put it back.
    var start = input.selectionStart, end = input.selectionEnd;
    input.type = show ? 'text' : 'password';
    wrap.classList.toggle('shown', show);
    btn.setAttribute('aria-pressed', show ? 'true' : 'false');
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    input.focus();
    try { input.setSelectionRange(start, end); } catch (e) {}
  });
});
</script>"""


def _password_field(autocomplete: str, label: str = "Password",
                    extra: str = "") -> str:
    return (
        f"<div class='field'><label for='password'>{_e(label)}</label>"
        f"<div class='pw'>"
        f"<input id='password' name='password' type='password' required "
        f"autocomplete='{autocomplete}'{extra}>"
        f"<button type='button' hidden aria-pressed='false' "
        f"aria-controls='password' aria-label='Show password'>"
        f"{EYE_ON}{EYE_OFF}</button></div></div>"
    )


def _google_block(enabled: bool) -> str:
    if not enabled:
        return ""
    return (
        f"<a class='gbtn' href='/auth/google'>{GOOGLE_MARK}"
        f"<span>Continue with Google</span></a>"
        f"<div class='or'>or</div>"
    )


def login_page(error: str = "", email: str = "", notice: str = "",
               google: bool = False) -> str:
    body = (
        f"<div class='split'>{_pitch()}"
        f"<div class='form-side'><div class='form-wrap'>"
        f"<h1 style='font-size:30px;margin-bottom:8px;'>Welcome back.</h1>"
        f"<p class='note' style='margin:0 0 22px;'>Sign in to your shop.</p>"
        f"{_alert(notice, 'ok')}{_alert(error)}"
        f"{_google_block(google)}"
        f"<form method='post' action='/login'>"
        f"<div class='field'><label for='email'>Name</label>"
        # Deliberately type='text': type='email' makes the browser reject a
        # plain name before the form is even submitted.
        f"<input id='email' name='email' type='text' required "
        f"autocomplete='username' value='{_e(email)}'></div>"
        f"{_password_field('current-password')}"
        f"<button class='btn' type='submit'>Sign in</button></form>"
        f"<p class='note' style='margin-top:18px;text-align:center;'>"
        f"New here? <a href='/signup'>Create an account</a></p>"
        f"</div></div></div>"
    )
    return _page("Sign in", body + PASSWORD_JS,
                 SPLIT_CSS + GOOGLE_CSS + PASSWORD_CSS)


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


def signup_page(error: str = "", values: dict[str, Any] | None = None,
                google: bool = False) -> str:
    v = values or {}
    stage = v.get("business_stage") or "starting"
    body = (
        f"<div class='split'>{_pitch()}"
        f"<div class='form-side'><div class='form-wrap'>"
        f"<h1 style='font-size:30px;margin-bottom:8px;'>Set up your shop.</h1>"
        f"<p class='note' style='margin:0 0 20px;'>Two minutes. You can change "
        f"any of this later.</p>"
        f"{_alert(error)}"
        f"{_google_block(google)}"
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

        f"<div class='field'><label for='email'>Name</label>"
        f"<input id='email' name='email' type='text' required "
        f"autocomplete='username' value='{_e(v.get('email'))}'>"
        f"<div class='note' style='margin-top:5px;'>"
        f"What you will sign in with. An email address works too.</div></div>"
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
    return _page("Create your shop", body, SIGNUP_CSS + GOOGLE_CSS)


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------


def verify_page(
    email: str,
    error: str = "",
    notice: str = "",
    dev_code: str = "",
    delivery_problem: str = "",
    resend_in: int = 0,
) -> str:
    """Enter the six-digit code.

    `dev_code` is only ever populated when no mail server is configured. It is
    labelled as such on the page — showing a code and implying an email went
    out would be worse than not sending one.
    """
    dev = ""
    if dev_code:
        dev = (
            f"<div class='ok' style='text-align:left;'>"
            f"<strong>No mail server is set up</strong>, so nothing was "
            f"emailed. Your code is <strong style='font-size:16px;"
            f"letter-spacing:.12em;'>{_e(dev_code)}</strong>."
            f"<div style='margin-top:6px;font-size:12px;'>Set AIW_SMTP_* in "
            f".env to send these by email instead.</div></div>"
        )
    # When no mail server is configured, the block above already explains that
    # and shows the code. Repeating "Email is not set up on this server" under
    # it says the same thing twice, in a red box that reads like a failure —
    # so the delivery problem is only shown when it is a *different* problem,
    # i.e. sending was attempted and went wrong.
    problem = (
        f"<div class='alert'>{_e(delivery_problem)}</div>"
        if delivery_problem and not dev_code else ""
    )
    wait = (
        f"<span class='note'>You can ask for another in {resend_in}s.</span>"
        if resend_in else
        "<button class='btn btn-quiet' type='submit' form='resend' "
        "style='width:auto;padding:8px 13px;'>Send a new code</button>"
    )

    body = (
        f"<div style='min-height:100vh;display:flex;align-items:center;"
        f"justify-content:center;padding:28px;'>"
        f"<div style='width:100%;max-width:420px;'>"
        f"{_brand('confirm your email')}"
        f"<div class='card'>"
        f"<h1 style='font-size:27px;margin-bottom:8px;'>Check your email.</h1>"
        f"<p class='note' style='margin:0 0 18px;'>We sent a six-digit code to "
        f"<strong style='color:{INK};'>{_e(email)}</strong>. It expires in 15 "
        f"minutes.</p>"
        f"{dev}{problem}{_alert(notice, 'ok')}{_alert(error)}"
        f"<form method='post' action='/verify'>"
        f"<div class='field'><label for='code'>Your code</label>"
        f"<input class='code-in' id='code' name='code' inputmode='numeric' "
        f"pattern='[0-9]*' maxlength='6' autocomplete='one-time-code' "
        f"required autofocus></div>"
        f"<button class='btn' type='submit'>Confirm my email</button></form>"
        f"<form id='resend' method='post' action='/verify/resend'></form>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"gap:10px;margin-top:14px;'>{wait}"
        f"<a class='note' href='/logout'>Use a different account</a></div>"
        f"</div></div></div>"
    )
    return _page("Confirm your email", body, GOOGLE_CSS)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------








def not_found() -> str:
    """A plain 404. Used where saying "forbidden" would itself be a leak."""
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Not found · Lucida</title>"
        "<style>body{font-family:'Inter',system-ui,sans-serif;background:#fff;"
        "color:#000;display:grid;place-items:center;height:100vh;margin:0}"
        "div{text-align:center}h1{font-size:22px;margin:0 0 6px}"
        "p{color:#71717A;font-size:14px;margin:0 0 18px}"
        "a{color:#7B1E22;font-weight:600;text-decoration:none}</style>"
        "</head><body><div><h1>Not found</h1>"
        "<p>There is nothing at that address.</p>"
        "<a href='/'>Back to your team</a></div></body></html>"
    )
