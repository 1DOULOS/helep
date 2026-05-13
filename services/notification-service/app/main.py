"""notification-service: simulated SMS / push delivery.

Consumes: responder.assigned, safety.zone.entered, sos.triggered (offline mode only)
Produces: notification.sent

Real SMS / push is OUT OF SCOPE — we just log a structured line and persist a row.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, make_asgi_app

from .db import init, record, list_all
from .events import consume, publish, health, producer, stop_producer

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger("notification-service")

PORT = int(os.getenv("SERVICE_PORT", "8004"))
GROUP = "notification-service"

app = FastAPI(title="helep-notification-service")
app.mount("/metrics", make_asgi_app())
SENT = Counter("helep_notifications_sent_total", "Notifications", ["channel", "template"])


TEMPLATES = {
    "responder.assigned": (
        "sms",
        "responder_dispatched",
        "Responder {responder_id} en-route to incident {incident_id}.",
    ),
    "safety.zone.entered": (
        "push",
        "safety_alert",
        "Danger zone {zone_id}: stay clear (incident {incident_id}).",
    ),
    "sos.triggered": (
        "sms",
        "sos_ack",
        "SOS received for incident {incident_id} (offline-fallback).",
    ),
}


async def on_event(p: dict) -> None:
    stream = p.get("_stream", "")
    tmpl = TEMPLATES.get(stream)
    if not tmpl:
        return
    # SRS: offline-mode SOS sends SMS. Online-mode does not fan-out to victim here.
    if stream == "sos.triggered" and p.get("mode") != "offline":
        return
    channel, name, body_fmt = tmpl
    recipient = p.get("user_id") or p.get("victim_user") or "broadcast"
    msg = body_fmt.format(**{k: p.get(k, "?") for k in ("incident_id", "responder_id", "zone_id")})
    record(channel, recipient, name, json.dumps({"text": msg, "src": p}))
    # Simulated delivery — log line stands in for the SMS gateway call.
    log.info("notification.delivered", channel=channel, template=name, recipient=recipient, body=msg)
    SENT.labels(channel=channel, template=name).inc()
    await publish(
        "notification.sent",
        {"channel": channel, "template": name, "recipient": recipient},
        key=p.get("incident_id"),
    )


@app.on_event("startup")
async def startup() -> None:
    init()
    await producer()
    asyncio.create_task(
        consume(
            ["responder.assigned", "safety.zone.entered", "sos.triggered"],
            GROUP, on_event,
        )
    )
    log.info("notification-service.up", port=PORT)


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_producer()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    if not await health():
        raise HTTPException(503, "kafka unreachable")
    return {"status": "ready"}


@app.get("/notifications")
async def latest(limit: int = 50):
    rows = list_all(min(max(limit, 1), 500))
    return [dict(r) for r in rows]
