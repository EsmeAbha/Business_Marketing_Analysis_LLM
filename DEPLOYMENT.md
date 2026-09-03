# Deployment — lucida.aipedia.blog

How this instance is actually deployed, what was changed to get it running,
and what is still worth doing. Written 2026-09-02; updated 2026-09-03.

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

### The provider switch — 2026-09-03

Google is retired. On 2026-09-02 its free tier ran out mid-run and the graph
died with `AllModelsBusy`, which was also the last thing in the log before the
process was found down. A rationed key is not something to demonstrate on.

The app now runs on one paid OpenAI-compatible gateway and nothing else:

| | |
|---|---|
| Text | `openai/gpt-5.4-nano` |
| Vision | `openai/gpt-5.4` |
| Gateway | `OPENAI_GATEWAY_URL`, reaching it via `settings.openai_base_url` |

Three things about this are worth knowing before changing it:

- **The gateway's allow-list is narrower than OpenAI's.** `gpt-4.1-nano` and
  `gpt-5-nano` both return 403. `gpt-5.4-nano` and `gpt-5.4` are served; both
  were checked with a live call rather than assumed.
- **`gpt-5*` models reject `max_tokens`** and require `max_completion_tokens`.
  `_build_openai()` already switches on the `_OPENAI_NO_SAMPLING` prefix
  (`llm.py:73`), so this is handled — but a model named outside that tuple
  would 400 on every call.
- **Vision needs no second provider.** `AIW_VISION_PROVIDER` and
  `AIW_VISION_MODEL` are deliberately blank: `settings.vision_provider` falls
  through to the text provider when it is multimodal, which resolves to
  `openai`/`gpt-5.4` on the same key and the same gateway.

`.env` was also deduplicated in the same pass — it had accumulated four
repeated blocks with two conflicting values for `AIW_GOOGLE_REDIRECT_URI`
(one still pointing at `127.0.0.1:8010`). 19 unique keys now.

---

## Running it

The app is a systemd service, `lucida.service`, enabled at boot:

```bash
systemctl restart lucida      # deploy, after a git pull
systemctl status lucida
journalctl -u lucida -f
```

The unit is at `/etc/systemd/system/lucida.service`. Four of its settings are
load-bearing:

- `Restart=always` with `RestartSec=5` — a SIGKILLed process was back and
  serving in about six seconds when this was tested.
- `EnvironmentFile=` pointing at `.env`, so configuration has one home and no
  secret is copied into the unit. Note that systemd's parser, unlike
  `Environment=`, takes the rest of the line as the value — which is why
  `AIW_DEFAULT_LOCATION=Dhaka, Bangladesh` needs no quoting.
- `KillSignal=SIGINT` with `TimeoutStopSec=120` — a workforce run takes
  60-120 seconds, and uvicorn shuts down gracefully on SIGINT, so a restart
  lets in-flight work finish instead of severing it.
- `Environment=PORT=8010`, because another uvicorn already owns 8000.

It runs as root, which is what it inherited: `data/` is root-owned, so moving
to a dedicated user means chowning a live database and is worth doing as its
own change.

To run it in the foreground instead — for a traceback that has not reached
journald yet:

```bash
systemctl stop lucida
HOST=127.0.0.1 PORT=8010 .venv/bin/python serve.py
```

The startup banner is the fastest check that configuration took effect — it
prints the model chain, the vision chain, and whether Google sign-in is on.

---

## Known issues

The suite is green and hermetic as of 2026-09-03: 87 pass in about 12
seconds, and identically so with every API key removed from the
environment. `tests/test_workforce.py` substitutes `llm.build_client`, so
no test reaches a provider. Two entries that used to live here — a failing
`test_telegram_offset_advances_and_persists` and an 8m20s suite that spent
live quota — are gone because bd20772 and e28de24 fixed them, not because
they were reclassified.

- **A provider switch needs its client library installed, and nothing warns
  you.** `.venv` was carried over from before the move to OpenAI and had no
  `langchain-openai` in it, so every run died with `ProviderError: openai
  support is not installed`. `requirements.txt` had pinned it since 2ad882a;
  only the environment was behind. What makes this worth writing down is that
  three plausible checks all pass while the app is broken: the startup banner
  and `/api/health` report the *configured* chain without building a client,
  and a curl straight at the gateway never touches the app. `_build_openai()`
  imports inside the function, so the failure waits for the first real call.
  After changing `AIW_PROVIDER`, run `pip install -r requirements.txt` and
  then invoke the model through the app's own `get_llm()`.

- **`data/` sits inside the working tree.** Gitignored, but a `git clean -xdf`
  would erase every shop, order and chat thread, and nothing backs it up.

- **Email is unconfigured**, so signup verification codes render on screen
  rather than being mailed. Anyone who reaches the login page can register
  without a working mailbox.

- **One provider, no failover.** Retiring Google bought reliability against
  rate limits and gave it up against outages: `_chain()` now returns a single
  entry, so if the gateway is down the app has nowhere to go. A second key
  from any other provider would restore the fallback the chain is built for.

- **Credentials were shared in plaintext** while configuring this and are due
  for rotation — the gateway key, the Google client secret, the Pathao
  secret, `AIW_SECRET_KEY`, and the Telegram bot token. Rotating
  `AIW_SECRET_KEY` signs every session out, so do it deliberately.

---

## Future direction

Roughly in the order the work should happen.

**1. Move the data out of the repo.** Point `LUCIDA_DATA_DIR` somewhere like
`/var/lib/lucida`, then take nightly SQLite backups with `.backup` (safe
against a live writer, unlike copying the file). Restore should be tested,
not assumed.

**2. Finish the integrations.** Telegram is done — `TELEGRAM_BOT_TOKEN` is
live as @Omygd_bot, answering for the shop named in `AIW_BOT_SHOP`, and one
token is one bot so it can only ever represent one shop.

Pathao is only half-configured, which is easy to miss: `PATHAO_CLIENT_ID`
and `PATHAO_CLIENT_SECRET` are in `.env`, but Pathao's `issue-token` also
wants a username and password, and those live per-shop in Connections
(`connections.credentials()` returns five fields, not two). No shop has them
stored, so a live booking call returns *"The user credentials were
incorrect"*. Delivery **pricing** is unaffected — the three zones are seeded
and `quote()` reads the catalogue — so the quote a customer sees is right
even though the parcel cannot be booked.

Still missing outright: `TAVILY_API_KEY` for real web search (it silently
falls back to `ddgs`, which does work), and `STEADFAST_*` for a second
courier.

**3. Configure SMTP before this is public.** Verification codes shown on
screen mean self-registration needs no working mailbox.

**4. Publish the Google consent screen.** While it is unpublished, only
accounts listed under Test users can sign in.
