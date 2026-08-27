# Deploying Lucida

## What this app needs from a host

Four things, and they rule out most of the fashionable places:

1. **A persistent disk.** Every shop's data is a SQLite file under
   `LUCIDA_DATA_DIR`, along with uploads and generated artwork. A container's
   own filesystem is wiped on each deploy; without a mounted volume, a deploy
   erases the business.
2. **One instance.** The approval gates and the run lock live in the
   process's memory. A second copy would hand one owner two different
   sessions and let two graph runs write over each other. Scale up, not out —
   and turn autoscaling **off**.
3. **Long requests.** A workforce run takes 60–120 seconds. Anything that
   cuts requests off at 10 or 30 seconds will kill runs halfway.
4. **Outbound HTTPS**, to Groq, Google, Pathao and Meta.

This is why Vercel, Netlify and Cloudflare Workers are the wrong shape: they
are serverless, have no persistent disk, and time requests out early.

## Environment

| Variable | What it does |
|---|---|
| `PORT` | Set by the host. Its presence is what makes the app bind `0.0.0.0`. |
| `LUCIDA_DATA_DIR` | Where the volume is mounted, e.g. `/data`. |
| `AIW_HTTPS=1` | Marks session cookies Secure. Set it once TLS is on. |
| `AIW_PUBLIC_URL` | Your real address, e.g. `https://app.example.com`. OAuth redirects are built from it. |
| `GROQ_API_KEY`, `GOOGLE_API_KEY` | The models. |
| `AIW_SMTP_*` | Verification emails. Without them, codes print on screen. |

Never commit `.env`. Set these as the host's own secrets.

## Fly.io

Cheapest of the managed options, and Singapore is the closest region to
Dhaka.

```bash
fly launch --no-deploy            # answer no to Postgres and Redis
fly volumes create lucida_data --size 3 --region sin
```

In `fly.toml`:

```toml
[env]
  LUCIDA_DATA_DIR = "/data"
  AIW_HTTPS = "1"

[mounts]
  source = "lucida_data"
  destination = "/data"

[http_service]
  internal_port = 8000
  auto_stop_machines = false      # a stopped machine loses in-flight runs
  min_machines_running = 1
  max_machines_running = 1        # one instance, see above
```

```bash
fly secrets set GROQ_API_KEY=... GOOGLE_API_KEY=...
fly deploy
```

Updates are `fly deploy` — about a minute.

## Railway

The least to learn. Connect the GitHub repo, and every push to `main`
deploys itself.

1. New Project → Deploy from GitHub repo
2. Add a **Volume**, mount path `/data`
3. Variables: `LUCIDA_DATA_DIR=/data`, `AIW_HTTPS=1`, plus your keys
4. Settings → make sure replicas stay at **1**

`railway.json` in the repo root already pins the parts that are easy to get
wrong by clicking: the Dockerfile as the builder rather than an inferred
buildpack, one replica, and `/api/health` as the health check with five
minutes to come up — the image installs the whole model stack before it can
answer. The volume and the secrets are the two things it cannot declare for
you, because neither belongs in a committed file.

## A plain VPS (Hetzner, DigitalOcean, Vultr)

Cheapest overall and nothing is hidden, but TLS, restarts and backups are
yours to run. Singapore or India for latency to Dhaka.

```bash
docker build -t lucida .
docker run -d --name lucida --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v /srv/lucida-data:/data \
  --env-file /srv/lucida.env \
  lucida
```

Put Caddy in front for automatic HTTPS — a two-line Caddyfile:

```
app.example.com {
  reverse_proxy 127.0.0.1:8000
}
```

Updating is `git pull && docker build -t lucida . && docker restart lucida`,
or a GitHub Action that does it on push.

## Back the data up

`LUCIDA_DATA_DIR` **is** the business: accounts, every shop's database, the
photos. Nothing reconstructs it.

```bash
sqlite3 /data/accounts.db ".backup '/backup/accounts.db'"
tar czf /backup/shops-$(date +%F).tgz /data/shops /data/uploads
```

Fly volumes take daily snapshots by default; on a VPS, run the above from
cron and copy it off the machine.

## After it is live

- Point `AIW_PUBLIC_URL` at the real address and redeploy, or OAuth
  redirects will still be aimed at `127.0.0.1`
- Register the new callback URLs with Meta and Google:
  `https://your-domain/connect/facebook/callback`,
  `https://your-domain/connect/youtube/callback`
- Meta webhooks, when you get to them, need a public HTTPS URL — which is
  exactly what any of the above gives you
