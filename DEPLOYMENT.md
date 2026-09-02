# Deployment — lucida.aipedia.blog

How this instance is actually deployed, what was changed to get it running,
and what is still worth doing. Written 2026-09-02.

The application's own documentation — architecture, the eight agents, the
screens — is in [README.md](README.md). This file only covers the
deployment.

---

## Where it runs

| | |
|---|---|
| Host | Ubuntu VPS (address not published here — see the DNS records) |
| App | `serve.py` under `.venv`, bound to `127.0.0.1:8010` |
| Public URL | https://lucida.aipedia.blog |
| Front door | nginx 1.24, TLS from Let's Encrypt |
| Data | `data/` inside the repo (SQLite, gitignored) |

Port 8010 rather than the default 8000: another uvicorn process already owns
8000 on this host. `serve.py` reads `$PORT` and `$HOST`, so nothing is
hard-coded.

The domain `aipedia.blog` is registered at Spaceship. The apex and `www`
serve a placeholder page from `/var/www/aipedia.blog`; the `lucida`
subdomain is this app.

### nginx

`/etc/nginx/sites-available/lucida.aipedia.blog` proxies to `127.0.0.1:8010`.
Three settings are load-bearing and should not be trimmed:

- `client_max_body_size 25m` — the Product Vision agent takes photo uploads,
  and nginx's 1 MB default rejects them before they reach the app.
- `proxy_read_timeout 600s` on `/` — a graph run that suspends at an approval
  gate can outlive nginx's 60 second default, which would sever the request
  mid-run.
- A separate `location = /api/events` with `proxy_buffering off`. The UI opens
  an `EventSource` there (`web/app_ui.py:1354`); with buffering on, nginx holds
  each event until its buffer fills, which defeats the live agent view.

### TLS

Certificates are issued by certbot and renewed automatically by
`certbot.timer`:

- `aipedia.blog` + `www.aipedia.blog`
- `lucida.aipedia.blog`

Issuance for the subdomain initially failed. The cause was **not** DNSSEC
validation — the registry DS record matched the live DNSKEY exactly. The
zone's authoritative servers were returning `SERVFAIL` for CAA queries, and
the failure persisted with `+cd` (validation disabled), which places the fault
in the servers rather than the chain of trust. With no CAA record present,
answering required a signed proof of non-existence that the signer was not
producing, and Let's Encrypt will not issue without reading CAA.

Adding an explicit CAA record at the apex resolved it immediately, by turning
the query into a positive signed answer:

```
CAA  @  0  issue  "letsencrypt.org"
```

Worth keeping regardless — it now restricts certificate issuance for the
domain to Let's Encrypt.

---

## Configuration

`.env` is gitignored and holds live credentials. `.env.example` documents
every key. Local backups match `.env.bak-*` and are gitignored too — that
pattern is the only change in this commit.

The file had drifted badly from the running configuration. What was wrong:

- **`GROQ_API_KEY` still held the `gsk_...` placeholder.** A non-empty value
  makes `llm._chain()` treat Groq as configured, so the model chain read
  `gemini-flash-latest -> openai/gpt-oss-120b -> qwen3.6-27b ->
  openai/gpt-oss-20b` and every fallback would have returned 401 the moment
  Gemini rate-limited. Cleared; the chain is now `gemini-flash-latest` alone.

- **Google sign-in was configured but inert, in three ways at once.** The
  credentials were commented out; they used invented key names
  (`GOOGLE_AUTH_CLIENT` / `GOOGLE_AUTH_SECRET`, where `web/google_oauth.py`
  reads `AIW_GOOGLE_CLIENT_ID` / `AIW_GOOGLE_CLIENT_SECRET`); and the client
  ID carried a spurious `http://` prefix. None of these raise an error —
  `enabled()` simply returns False and the button stays hidden.

- 22 keys were present but empty, and two were defined twice. An empty key and
  an absent key are identical to the app, so the empties are gone.

`AIW_HTTPS=1` is set now that the app is behind TLS, so session cookies carry
the `Secure` flag (`serve.py:1965`).

No code changes were needed for Google sign-in. It was already implemented in
full — `web/google_oauth.py`, the routes at `serve.py:2009-2010`, and
`auth.upsert_google_account()`.

---

## Running it

```bash
HOST=127.0.0.1 PORT=8010 .venv/bin/python serve.py
```

The startup banner is the fastest check that configuration took effect — it
prints the model chain, the vision chain, and whether Google sign-in is on.

---

## Known issues

- **The app is not supervised.** It runs as a detached process, so a reboot
  or a crash leaves it down with nothing to restart it. This is the most
  important gap.

- **`test_telegram_offset_advances_and_persists` fails.** `tests/test_workforce.py:238`
  asserts a simulated inbox has messages and gets `Inbox(messages=[],
  simulated=True)`. Pre-existing and independent of configuration — it fails
  with `.env` removed entirely.

- **The test suite makes live API calls.** 9 seconds without a key, 8m20s
  with one. Tests burn Gemini quota and will fail whenever the key is
  rate-limited. They should mock the provider.

- **`data/` sits inside the working tree.** Gitignored, but a `git clean -xdf`
  would erase every shop, order and chat thread, and nothing backs it up.

- **`OPENAI_API_KEY`, `OPENAI_MODEL` and `OPENAI_GATEWAY_URL` are read by
  nothing.** `build_client()` supports google, groq and anthropic only; the
  `openai/gpt-oss-*` names in `llm.py` are Groq-hosted models, which makes
  this an easy mistake to make. Kept in `.env` pending a decision.

- **Email is unconfigured**, so signup verification codes render on screen
  rather than being mailed. Anyone who reaches the login page can register
  without a working mailbox.

---

## Future direction

Roughly in the order the work should happen.

**1. Supervise the process.** A systemd unit with `Restart=always`, an
`EnvironmentFile` pointing at `.env`, and journald for logs. Small change,
and it closes the largest gap between this and a real deployment.

**2. Move the data out of the repo.** Point `LUCIDA_DATA_DIR` somewhere like
`/var/lib/lucida`, then take nightly SQLite backups with `.backup` (safe
against a live writer, unlike copying the file). Restore should be tested,
not assumed.

**3. Make the tests offline again.** Mock the provider so the suite runs in
seconds without a key, and fix the simulated-inbox bug rather than leaving one
red test as the normal state — a suite people expect to fail stops being read.

**4. Decide on the OpenAI-compatible gateway.** Either add a fourth provider
to `build_client()` alongside google/groq/anthropic — a contained change,
roughly one `_build_openai()` plus a `config.py` entry — or drop the three
dead keys. Leaving them looks like configuration that works.

**5. Finish the integrations.** `TELEGRAM_BOT_TOKEN` for the customer
channel, `TAVILY_API_KEY` for real web search (it silently falls back to
`ddgs`), `STEADFAST_*` for a second courier — only Pathao is configured, so
there is no fallback if it is down.

**6. Configure SMTP before this is public.** Verification codes shown on
screen mean self-registration needs no working mailbox.

**7. Publish the Google consent screen.** While it is unpublished, only
accounts listed under Test users can sign in.
