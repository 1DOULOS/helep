"""analytics-service: tally all events, expose stats endpoints (police view).

Consumes: every helep event stream.
Produces: nothing (sink).
"""
from __future__ import annotations
import asyncio
import logging
import os

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, make_asgi_app

from .db import init, bump_event, log_incident, log_zone_hit, zone_summary, crime_map, event_summary
from .events import consume, health, producer, stop_producer

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger("analytics-service")

PORT = int(os.getenv("SERVICE_PORT", "8005"))
GROUP = "analytics-service"

STREAMS = [
    "user.registered",
    "sos.triggered",
    "sos.cancelled",
    "responder.assigned",
    "responder.confirmed",
    "safety.zone.entered",
    "notification.sent",
]

app = FastAPI(title="helep-analytics-service")
app.mount("/metrics", make_asgi_app())
EVENTS = Counter("helep_analytics_events_total", "Events seen", ["stream"])


async def on_event(p: dict) -> None:
    stream = p.get("_stream", "")
    bump_event(stream)
    EVENTS.labels(stream=stream).inc()
    if stream == "sos.triggered":
        log_incident(p["incident_id"], p.get("lat"), p.get("lon"), p.get("mode"))
    elif stream == "safety.zone.entered":
        log_zone_hit(p["zone_id"], p["incident_id"])


@app.on_event("startup")
async def startup() -> None:
    init()
    await producer()
    asyncio.create_task(consume(STREAMS, GROUP, on_event))
    log.info("analytics-service.up", port=PORT)


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


@app.get("/stats/zones")
async def stats_zones():
    return [dict(r) for r in zone_summary()]


@app.get("/stats/crime")
async def stats_crime():
    return [dict(r) for r in crime_map()]


@app.get("/stats/events")
async def stats_events():
    return [dict(r) for r in event_summary()]
