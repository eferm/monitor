# monitor

Webhook receiver that turns service events into email alerts.

Endpoints:

- `POST /hooks/tailscale` — Tailscale webhook events, e.g. a node key expiring
  in one day.
- `GET /healthz` — answers `ok` for uptime checks.

**Stack:** Python 3.12, FastAPI, Pydantic, uv, and ruff.

## Setup

```sh
cp .env.example .env    # fill in every value
docker compose up -d --build
```

Compose binds the app to `127.0.0.1:8002`. Put an HTTPS reverse proxy or
Cloudflare Tunnel in front of it, e.g. at `https://monitor.example.com`.

### Outgoing email (Cloudflare Email Service)

1. In the Cloudflare dashboard, open **Email Service → Email Sending** and
   onboard the domain you send from; add the DNS records it lists
   ([domain configuration](https://developers.cloudflare.com/email-service/configuration/domains/)).
2. Create an API token with the **Email Sending: Edit** permission and put it
   in `SMTP_PASSWORD`.
3. Set `MAIL_SENDER` to an address on the onboarded domain.

`SMTP_HOST`, `SMTP_PORT`, and `SMTP_USERNAME` in `.env.example` are already
Cloudflare's values. Any SMTPS (port 465) provider works.

### Tailscale

1. Admin console → **Settings → Webhooks → Add endpoint**.
2. URL: `https://monitor.example.com/hooks/tailscale`.
3. Subscribe to **Node key expiring in one day** and **Node key expired** (or
   any other events you want mailed).
4. Copy the signing secret into `TAILSCALE_WEBHOOK_SECRET` and restart.

## Verify a deployment

In the Tailscale admin console, open the webhook and click **Test endpoint →
Send test event**. An email titled "Tailscale: …" arriving within seconds
confirms the whole path: Tailscale → your proxy → signature check →
Cloudflare → inbox.

No email: `docker compose logs web` shows the cause — `401` is a wrong
`TAILSCALE_WEBHOOK_SECRET`; a `500` with an SMTP error is the mail setup.

## Updates

```sh
git pull
docker compose up -d --build
```

## Development

```sh
uv sync
uv run --env-file .env uvicorn main:app --reload --port 8002
uv run ruff check .
uv run ruff format .
uv run basedpyright
```
