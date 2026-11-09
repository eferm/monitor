# monitor

## Philosophy

- One file, `main.py`. Stateless: no database, no files written, no background
  jobs, no state machines.
- No JavaScript, no CSS, no HTML pages. The app only receives webhooks and
  sends email.
- Happy path only. Malformed input fails loudly; the sender's retry is the
  recovery mechanism.
- Generic and public: no instance-specific domains, addresses, or tailnet names
  in the repo. Instance values live in `.env` (git-ignored); examples use
  `example.com`.
- Configuration is the `Config` Pydantic model, validated from `os.environ` at
  import, so a missing or malformed variable fails at startup with one error
  listing every bad field. `hide_input_in_errors` keeps secrets out of that
  error.

## Invariants

- `GET /healthz` is the one unauthenticated route; it answers `ok` and touches
  nothing else.
- Every `/hooks/*` endpoint verifies its sender's signature over the raw request body
  before parsing it. The signature check is the only access control.
- Payloads are validated with Pydantic models declaring only the fields the
  email uses; extra fields are ignored. The subject is `[Tailscale] ` plus the
  events' messages.
  Each event renders as `Event: <type>`, `Tailnet: <tailnet>`, and
  `timestamp` on one line each, then `data` as indented JSON, so every event
  type works without code changes.
- Event selection belongs to the sending service's subscription settings, not
  to code here. Each request produces one email.

## Tailscale

- Docs: https://tailscale.com/kb/1213/webhooks
- Body is a JSON array of events (`timestamp`, `version`, `type`, `tailnet`,
  `message`, optional `data`).
- Header `Tailscale-Webhook-Signature: t=<epoch>,v1=<sig>`; `sig` is hex
  HMAC-SHA256 of `"<t>.<body>"` keyed by the webhook secret. Timestamps older
  than 5 minutes are rejected as replays.

## Adding an endpoint

Add a `POST /hooks/<source>` route, a Pydantic model for its payload, a
`verify_<source>` function for its signature scheme, and its secret as a `Config`
field in `main.py` and `.env.example`. Reuse `send`. Document the
service-side setup in `README.md`.

## Deployment

Docker Compose, bound to `127.0.0.1:8002`, behind an HTTPS proxy or tunnel.
Uvicorn trusts `X-Forwarded-*` from `FORWARDED_ALLOW_IPS` (compose default:
the Docker network ranges); the client IP is used only for access logs.
Cloudflare Email Service SMTP (`smtp.mx.cloudflare.net:465`, implicit TLS,
username `api_token`) for outgoing mail.
