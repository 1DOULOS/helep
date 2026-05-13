"""dispatch-service: localize victim, match a responder, enforce no-double-dispatch.

Consumes: sos.triggered, sos.cancelled
Produces: responder.assigned, responder.confirmed, safety.zone.entered

Patterns demonstrated:
  - Strategy   (matching.py)
  - Saga       (this service is the saga coordinator's middle step)
  - Repository (db.py)
  - Outbox-lite (claim row then emit assignment in same handler)
"""
from __future__ import annotations
import asyncio
import logging
import os

import structlog
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, make_asgi_app
from pydantic import BaseModel

from .db import (
    init,
    all_free_responders,
    reserve_responder_for,
    assignment_for,
    release_assignment,
    list_danger_zones,
)
from .events import consume, publish, health, producer, stop_producer
from .matching import matcher, haversine_m

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger("dispatch-service")

PORT = int(os.getenv("SERVICE_PORT", "8003"))
GROUP = "dispatch-service"

app = FastAPI(title="helep-dispatch-service")
app.mount("/metrics", make_asgi_app())
ASSIGNED = Counter("helep_dispatch_assigned_total", "Assignments")
RELEASED = Counter("helep_dispatch_released_total", "Cancellations released")
ZONE_HITS = Counter("helep_dispatch_zone_hits_total", "Danger zone hits")


class ConfirmIn(BaseModel):
    incident_id: str
    responder_id: str


async def on_event(payload: dict) -> None:
    stream = payload.get("_stream")
    if stream == "sos.triggered":
        await handle_sos(payload)
    elif stream == "sos.cancelled":
        await handle_cancel(payload)
    else:
        log.info("ignored", stream=stream)


async def handle_sos(p: dict) -> None:
    iid = p["incident_id"]
    if assignment_for(iid):
        log.info("dispatch.idempotent", incident_id=iid)
        return
    free = all_free_responders()
    if not free:
        log.warning("no responders free", incident_id=iid)
        return
    pick = matcher().pick(p["lat"], p["lon"], free)
    if not pick:
        return
    if not reserve_responder_for(pick["id"], iid):
        log.warning("race lost, retry next event", responder=pick["id"], incident_id=iid)
        return
    await publish(
        "responder.assigned",
        {"incident_id": iid, "responder_id": pick["id"], "victim_user": p["user_id"], "lat": p["lat"], "lon": p["lon"]},
        key=iid,
    )
    ASSIGNED.inc()
    log.info("dispatch.assigned", incident_id=iid, responder=pick["id"])

    # Safety alerts: warn nearby citizens when victim location is inside a danger zone.
    for z in list_danger_zones():
        if haversine_m(p["lat"], p["lon"], z["lat"], z["lon"]) <= z["radius_m"]:
            await publish(
                "safety.zone.entered",
                {"zone_id": z["id"], "incident_id": iid, "user_id": p["user_id"]},
                key=iid,
            )
            ZONE_HITS.inc()


async def handle_cancel(p: dict) -> None:
    iid = p["incident_id"]
    if not assignment_for(iid):
        return
    release_assignment(iid)
    await publish("responder.confirmed", {"incident_id": iid, "status": "RELEASED"}, key=iid)
    RELEASED.inc()


@app.on_event("startup")
async def startup() -> None:
    init()
    await producer()
    asyncio.create_task(consume(["sos.triggered", "sos.cancelled"], GROUP, on_event))
    log.info("dispatch-service.up", port=PORT)


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


@app.post("/responders/confirm")
async def confirm(body: ConfirmIn):
    """Responder acknowledges they're en route. Emits responder.confirmed."""
    a = assignment_for(body.incident_id)
    if not a or a["responder_id"] != body.responder_id:
        raise HTTPException(404, "no matching assignment")
    await publish("responder.confirmed", {"incident_id": body.incident_id, "status": "EN_ROUTE"}, key=body.incident_id)
    return {"ok": True}
