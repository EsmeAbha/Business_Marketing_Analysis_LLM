/* Lucida — connects the design's own controls to the real workforce.
 *
 * The design ships as a self-contained prototype: its Ask button navigates,
 * and its decision buttons only flip local state. This file gives those same
 * controls real effects, without changing the design's markup or styling.
 *
 * Patched into the page by web/patch_design.py, which rewrites two handler
 * bindings to call through here:
 *
 *   goGrow            -> LucidaActions.ask(text)     POST /api/ask
 *   decide(id,choice) -> LucidaActions.decide(...)   POST /api/decide
 *
 * After a call returns, the page reloads. The server injects a fresh snapshot
 * on every render, so a reload is the simplest way to get consistent state
 * everywhere at once — the design's data constants are read at module scope
 * and would otherwise keep showing the values captured at first paint.
 */
(function () {
  'use strict';

  var BUSY_ID = 'lucida-busy';

  function overlay(message) {
    if (document.getElementById(BUSY_ID)) return;
    var el = document.createElement('div');
    el.id = BUSY_ID;
    el.setAttribute('role', 'status');
    el.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:9999',
      'background:rgba(247,245,240,.82)', 'backdrop-filter:blur(2px)',
      'display:flex', 'align-items:center', 'justify-content:center',
      "font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    ].join(';');
    el.innerHTML =
      '<div style="background:#FFFFFF;border:1px solid #E4E4E7;border-radius:14px;' +
      'padding:18px 22px;display:flex;align-items:center;gap:11px;' +
      'box-shadow:0 8px 28px rgba(24,33,29,.10)">' +
      '<span style="width:8px;height:8px;border-radius:50%;background:#7B1E22;' +
      'animation:luPulseA 1.1s infinite"></span>' +
      '<span style="font-size:13.5px;color:#000000">' + message + '</span></div>' +
      '<style>@keyframes luPulseA{0%,100%{opacity:1}50%{opacity:.3}}</style>';
    document.body.appendChild(el);
  }

  function clear() {
    var el = document.getElementById(BUSY_ID);
    if (el) el.remove();
  }

  function toast(message, tone) {
    clear();
    var bad = tone === 'error';
    var el = document.createElement('div');
    el.style.cssText = [
      'position:fixed', 'right:18px', 'bottom:18px', 'z-index:9999',
      'max-width:380px', 'padding:13px 15px', 'border-radius:12px',
      'background:' + (bad ? '#FEE2E2' : '#FBEBEB'),
      'border:1px solid ' + (bad ? '#B91C1C' : '#7B1E22'),
      'color:' + (bad ? '#B91C1C' : '#7B1E22'),
      'font:13px/1.5 Inter, -apple-system, BlinkMacSystemFont, Segoe UI, system-ui, sans-serif',
      'box-shadow:0 8px 28px rgba(24,33,29,.10)'
    ].join(';');
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 7000);
  }

  /* Minimal markdown -> HTML for the workforce's written answer: headings,
     bold, bullets and paragraphs. Everything is escaped first, so model output
     can never inject markup. */
  function render(md) {
    var esc = String(md)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return esc.split(/\n{2,}/).map(function (block) {
      var b = block.trim();
      if (!b) return '';
      b = b.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      var head = b.match(/^(#{1,4})\s+(.*)$/m);
      if (head && b.indexOf('\n') === -1) {
        return '<div style="font-weight:600;font-size:15px;margin:14px 0 4px">'
          + head[2] + '</div>';
      }
      if (/^[-*]\s+/m.test(b)) {
        var items = b.split('\n').filter(Boolean).map(function (l) {
          return '<li style="margin:3px 0">' + l.replace(/^[-*]\s+/, '') + '</li>';
        }).join('');
        return '<ul style="margin:7px 0;padding-left:19px">' + items + '</ul>';
      }
      return '<p style="margin:9px 0;line-height:1.62">'
        + b.replace(/\n/g, '<br>') + '</p>';
    }).join('');
  }

  /* The answer, shown in the design's card idiom. Closing it reloads so every
     section picks up whatever the run just wrote to memory. */
  function answerPanel(text) {
    clear();
    var wrap = document.createElement('div');
    wrap.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:9999', 'display:flex',
      'align-items:center', 'justify-content:center', 'padding:28px',
      'background:rgba(24,33,29,.28)',
      "font-family:'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    ].join(';');
    wrap.innerHTML =
      '<div style="background:#FFFFFF;border:1px solid #E4E4E7;border-radius:14px;' +
      'max-width:760px;width:100%;max-height:82vh;overflow:auto;' +
      'box-shadow:0 18px 50px rgba(24,33,29,.18)">' +
        '<div style="padding:17px 20px;border-bottom:1px solid #F4F4F5;' +
        'display:flex;align-items:center;gap:9px;position:sticky;top:0;background:#FFFFFF">' +
          '<span style="font-size:11px;font-weight:600;letter-spacing:.05em;' +
          'text-transform:uppercase;color:#7B1E22;background:#FBEBEB;' +
          'padding:3px 8px;border-radius:6px">Your team</span>' +
          '<span style="font-size:12px;color:#71717A">what came back</span>' +
          '<button id="lucida-close" style="margin-left:auto;border:1px solid #E4E4E7;' +
          'background:#FFFFFF;color:#3F3F46;font-size:12.5px;padding:6px 12px;' +
          'border-radius:9px;cursor:pointer">Close</button>' +
        '</div>' +
        '<div style="padding:6px 20px 20px;font-size:13.5px;color:#000000">' +
          render(text) +
        '</div>' +
      '</div>';
    document.body.appendChild(wrap);
    wrap.querySelector('#lucida-close').onclick = function () {
      window.location.reload();
    };
  }

  function post(url, body, busyMessage, showAnswer) {
    overlay(busyMessage);
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
        return data;
      });
    }).then(function (data) {
      if (showAnswer && data && data.answer) {
        answerPanel(data.answer);
        return;
      }
      // Fresh data is injected server-side on render.
      window.location.reload();
    }).catch(function (err) {
      toast(String(err.message || err), 'error');
    });
  }

  /* ---- photo upload ------------------------------------------------------
   * The design's "Add stock with a photo" block has an <image-slot> and a
   * "Log it" button with no binding — it was never wired to anything. The
   * slot's shadow root is open, so its file input can be observed directly
   * rather than re-implementing the picker.
   *
   * Sending a photo is what reaches the Product Vision agent, which is
   * otherwise unreachable from this front-end.
   */
  var picked = null;

  function wirePhoto() {
    var slot = document.getElementById('suite-stock-upload');
    if (!slot || slot.__lucidaWired) return;

    var input = slot.shadowRoot && slot.shadowRoot.querySelector('input[type="file"]');
    if (!input) return;
    slot.__lucidaWired = true;

    input.addEventListener('change', function () {
      picked = input.files && input.files[0];
      if (picked) toast('Photo ready — press "Log it" to send it to your team.');
    });

    // The button and the quantity field are the two siblings of the slot's
    // container; both are unbound in the design.
    var block = slot.closest('div').parentElement;
    var btn = block && block.querySelector('button');
    var qty = block && block.querySelector('input');
    if (!btn || btn.__lucidaWired) return;
    btn.__lucidaWired = true;

    btn.addEventListener('click', function () {
      if (!picked) {
        toast('Choose a photo first — click the drop area above.', 'error');
        return;
      }
      if (window.LUCIDA && window.LUCIDA.hasLlm === false) {
        toast('No API key. Add GROQ_API_KEY to .env, then restart.', 'error');
        return;
      }
      var form = new FormData();
      form.append('photo', picked);
      form.append('quantity', (qty && qty.value) || '');
      overlay('Your team is looking at the photo…');
      fetch('/api/upload', { method: 'POST', body: form })
        .then(function (res) {
          return res.json().then(function (d) {
            if (!res.ok) throw new Error(d.error || ('HTTP ' + res.status));
            return d;
          });
        })
        .then(function (d) {
          if (d.answer) answerPanel(d.answer);
          else window.location.reload();
        })
        .catch(function (err) { toast(String(err.message || err), 'error'); });
    });
  }

  /* ---- profile ----------------------------------------------------------
   * The rail's identity block is the shop's monogram and name. It becomes
   * the way into the account: the tile shows the owner's photo when they
   * have one, and clicking anywhere on the block opens /account.
   */
  /* The shop name in the rail and the name in the greeting are dc *props*,
   * not data constants — they carry the demo shop's defaults ("Shomvob
   * Kitchen", "Rifat") and window.LUCIDA never reaches them. The runtime
   * exposes setProps for exactly this, so they are set through the design's
   * own mechanism rather than by rewriting text nodes it will re-render. */
  var propsDone = false;

  function applyIdentity() {
    if (propsDone) return;
    if (typeof window.__dcSetProps !== 'function'
        || typeof window.__dcRootName !== 'function') return;
    var L = window.LUCIDA || {};
    if (!L.account) return;
    try {
      window.__dcSetProps(window.__dcRootName(), {
        businessName: L.businessName || 'Your shop',
        ownerName: L.ownerName || (L.account.email || '').split('@')[0] || '',
      });
      propsDone = true;
    } catch (e) { /* runtime not ready yet; the poller retries */ }
  }

  function wireProfile() {
    var acct = window.LUCIDA && window.LUCIDA.account;
    if (!acct) return;
    var aside = document.querySelector('aside');
    if (!aside) return;
    var block = aside.firstElementChild;
    if (!block || block.__lucidaProfile) return;
    block.__lucidaProfile = true;

    var tile = block.firstElementChild;
    if (tile) {
      if (acct.avatar) {
        tile.style.backgroundImage = 'url("' + acct.avatar + '")';
        tile.style.backgroundSize = 'cover';
        tile.style.backgroundPosition = 'center';
        tile.textContent = '';
      } else if (acct.initials) {
        tile.textContent = acct.initials;
      }
    }

    block.style.cursor = 'pointer';
    block.style.borderRadius = '12px';
    block.style.transition = 'background .15s';
    block.title = 'Your account — ' + (acct.email || '');
    block.setAttribute('role', 'link');
    block.setAttribute('tabindex', '0');
    block.addEventListener('mouseenter', function () {
      block.style.background = '#F4F4F5';
    });
    block.addEventListener('mouseleave', function () {
      block.style.background = 'transparent';
    });
    var open = function () { window.location.href = '/account'; };
    block.addEventListener('click', open);
    block.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
  }

  /* ---- first run ---------------------------------------------------------
   * A new owner lands on a dashboard full of the design's sample figures.
   * Left unexplained that reads as their own trading history. This says what
   * is going on and what to do first, and disappears for good once the shop
   * has anything of its own in it.
   */
  var NOTICE_ID = 'lucida-firstrun';
  var DISMISSED = 'lucida-firstrun-dismissed';

  function firstRunNotice() {
    var L = window.LUCIDA || {};
    if (!L.firstRun || !L.account) return;
    if (document.getElementById(NOTICE_ID)) return;
    try {
      if (window.localStorage.getItem(DISMISSED) === '1') return;
    } catch (e) { /* private mode — just show it */ }

    // Sit above the greeting on the Today page only.
    var h1 = document.querySelector('h1');
    if (!h1) return;
    var host = h1.parentElement && h1.parentElement.parentElement;
    if (!host) return;

    var stage = (L.account.stage === 'running')
      ? ['You said you are already selling.',
         'Tell your team what you sell and what it costs you, and they will '
         + 'price it, watch your stock and write your ads.',
         'What do I sell and am I charging enough?']
      : ['You said you are starting out.',
         'Describe the idea, or add a photo of what you make. Your team will '
         + 'research demand, check what rivals charge and tell you plainly '
         + 'whether it is worth doing.',
         'What food business should I start with 30,000 taka?'];

    var el = document.createElement('div');
    el.id = NOTICE_ID;
    el.style.cssText = 'background:#FFFFFF;border:1px solid #7B1E22;'
      + 'border-radius:14px;padding:16px 18px;margin:0 0 20px;';
    el.innerHTML =
      '<div style="display:flex;align-items:center;gap:9px;margin-bottom:8px">'
      + '<span style="font-size:11px;font-weight:600;letter-spacing:.05em;'
      + 'text-transform:uppercase;color:#7B1E22;background:#FBEBEB;'
      + 'padding:3px 8px;border-radius:6px">Start here</span>'
      + '<span style="font-size:12px;color:#71717A">' + stage[0] + '</span>'
      + '<button id="lucida-firstrun-x" style="margin-left:auto;border:none;'
      + 'background:none;color:#71717A;font-size:12.5px;cursor:pointer">'
      + 'Hide</button></div>'
      + '<div style="font-size:15px;font-weight:600;margin-bottom:5px;'
      + 'color:#000000">The numbers on this page are examples, not yours.</div>'
      + '<div style="font-size:13.5px;color:#3F3F46;line-height:1.6">'
      + stage[1] + ' Everything here fills in with your own as they work — and '
      + 'nothing is published, ordered or paid for without your say-so.</div>'
      + '<div style="margin-top:12px;padding:11px 13px;background:#FFFFFF;'
      + 'border-radius:10px;font-size:13px;color:#3F3F46">'
      + '<strong>Try asking:</strong> &ldquo;' + stage[2] + '&rdquo; '
      + '<span style="color:#71717A">— use the “Ask your team” box on the '
      + 'right.</span></div>';

    host.insertBefore(el, host.firstChild);
    var x = document.getElementById('lucida-firstrun-x');
    if (x) {
      x.onclick = function () {
        try { window.localStorage.setItem(DISMISSED, '1'); } catch (e) {}
        el.remove();
      };
    }
  }

  /* ---- editable reply ----------------------------------------------------
   * The design shows the drafted reply in a read-only div — it assumed the
   * owner either sends it or opens the thread elsewhere to change it. Making
   * that div editable is the smallest change that lets them correct a word
   * before it goes to a customer, which is the whole point of a draft.
   */
  function wireDraft() {
    var label = [...document.querySelectorAll('span')]
      .find(function (s) { return /reply drafted for you/i.test(s.textContent || ''); });
    if (!label) return;
    var card = label.closest('div').parentElement;
    if (!card) return;
    var box = [...card.querySelectorAll('div')].find(function (d) {
      return (d.style || {}).whiteSpace === 'pre-wrap';
    });
    if (!box || box.__lucidaDraft) return;
    box.__lucidaDraft = true;

    box.setAttribute('contenteditable', 'true');
    box.setAttribute('spellcheck', 'true');
    box.style.outline = 'none';
    box.style.borderRadius = '8px';
    box.style.padding = '6px 8px';
    box.style.margin = '-6px -8px';
    box.style.transition = 'background .15s';
    box.title = 'You can edit this before sending';
    box.addEventListener('focus', function () {
      box.style.background = '#FAFAFA';
    });
    box.addEventListener('blur', function () {
      box.style.background = 'transparent';
    });
    // The Send handler reads the live text, so an edit here is what goes.
    box.addEventListener('input', function () {
      window.__lucidaDraftText = box.innerText;
    });
    window.__lucidaDraftText = box.innerText;
  }

  // The design re-renders on every navigation, so re-attach when the Stock
  // page mounts rather than only once at boot.
  function wireAll() {
    applyIdentity();
    wirePhoto();
    wireProfile();
    wireDraft();
    firstRunNotice();
  }
  document.addEventListener('DOMContentLoaded', wireAll);
  setInterval(wireAll, 900);

  window.LucidaActions = {
    wirePhoto: wirePhoto,
    photoReady: function () { return !!picked; },

    /** Send the owner's question to the workforce. */
    ask: function (text) {
      text = (text || '').trim();
      if (!text) {
        toast('Type a question first.', 'error');
        return;
      }
      if (window.LUCIDA && window.LUCIDA.hasLlm === false) {
        toast('No API key. Add GROQ_API_KEY to .env, then restart.', 'error');
        return;
      }
      post('/api/ask', { text: text }, 'Your team is working on it…', true);
    },

    /** Send a reply to one customer message. */
    reply: function (messageId, text) {
      text = (text || '').trim();
      if (!text) {
        toast('Write a reply first.', 'error');
        return;
      }
      // Thread ids are the real social_messages row id; anything else is the
      // design's own sample thread, which has nowhere to send to.
      var id = parseInt(messageId, 10);
      if (!id) {
        toast('This is a sample conversation — nothing to reply to.', 'error');
        return;
      }
      post('/api/reply', { message_id: id, text: text }, 'Sending your reply…');
    },

    /** Pull new customer messages in from the connected platforms. */
    syncInbox: function () {
      post('/api/inbox/sync', {}, 'Checking for new messages…');
    },

    /** Answer the approval gate the graph is suspended on. */
    decide: function (id, choice) {
      // Only the gate the server actually reported is a real suspension; the
      // design's own sample decisions stay local so the prototype still demos.
      var live = window.LUCIDA && window.LUCIDA.decisions
              && window.LUCIDA.decisions.length && id === 'gate';
      if (!live) return false;
      post(
        '/api/decide',
        { decision: choice === 'yes' ? 'approve' : 'reject', feedback: '' },
        choice === 'yes' ? 'Approving…' : 'Holding it back…'
      );
      return true;
    }
  };
})();
