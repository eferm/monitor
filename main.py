"""Webhook receiver that turns service events into email alerts."""

import asyncio
import hmac
import json
import os
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from hashlib import sha256
from typing import Annotated, ClassVar

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, JsonValue, NameEmail, TypeAdapter


class Config(BaseModel):
    """Environment variables, validated at import; other variables are ignored."""

    # Errors would otherwise echo the whole environment, secrets included.
    model_config: ClassVar[ConfigDict] = ConfigDict(hide_input_in_errors=True)

    TAILSCALE_WEBHOOK_SECRET: str
    MAIL_TO: NameEmail
    MAIL_SENDER: NameEmail
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str


config = Config.model_validate(os.environ)

# Tailscale's recommended replay window for signed webhook timestamps.
REPLAY_WINDOW_SECONDS = 300


class TailscaleEvent(BaseModel):
    timestamp: datetime
    type: str
    tailnet: str
    message: str
    # Event-specific details (actor, device, policy, ...); absent on some events.
    data: dict[str, JsonValue] = {}

    def render(self) -> str:
        fields = [self.type, self.message, self.tailnet, str(self.timestamp)]
        return "\n".join([*fields, json.dumps(self.data)])


tailscale_events = TypeAdapter(list[TailscaleEvent])

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/healthz")
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok\n")


def send(subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = str(config.MAIL_SENDER)
    message["To"] = str(config.MAIL_TO)
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP_SSL(
        config.SMTP_HOST,
        config.SMTP_PORT,
        timeout=10,
        context=ssl.create_default_context(),
    ) as smtp:
        _ = smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        _ = smtp.send_message(message)


def verify_tailscale(signature: str, body: bytes) -> None:
    """Header format `t=<epoch>,v1=<hex HMAC-SHA256 of "<epoch>.<body>">`."""
    parts = dict(part.split("=", 1) for part in signature.split(","))
    expected = hmac.new(
        config.TAILSCALE_WEBHOOK_SECRET.encode(),
        f"{parts['t']}.".encode() + body,
        sha256,
    ).hexdigest()
    fresh = time.time() - int(parts["t"]) < REPLAY_WINDOW_SECONDS
    if not (hmac.compare_digest(expected, parts["v1"]) and fresh):
        raise HTTPException(401)


@app.post("/hooks/tailscale")
async def tailscale(
    request: Request, tailscale_webhook_signature: Annotated[str, Header()]
) -> None:
    # The signature covers the exact request bytes, so verify before parsing.
    body = await request.body()
    verify_tailscale(tailscale_webhook_signature, body)
    events = tailscale_events.validate_json(body)
    # smtplib blocks; a worker thread keeps it off the event loop.
    # dict.fromkeys dedupes event types while keeping first-seen order.
    await asyncio.to_thread(
        send,
        "Tailscale: " + ", ".join(dict.fromkeys(event.type for event in events)),
        "\n\n".join(event.render() for event in events),
    )
