"""sos-service: SOS triggering, simulated media capture, cancel.

Emits: sos.triggered, sos.cancelled

Endpoints:
  POST /sos          Bearer  { lat, lon, mode, media_ref? }   -> { incident_id, status }
  POST /sos/{id}/cancel  Bearer                                -> { status }
  GET  /sos/{id}                                               -> { ... }
"""
from __future__ import annotations
import os
import uuid
import logging

import jwt
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, make_asgi_app

from .db import init, insert_incident, cancel, get
from .events import publish, health, producer, stop_producer

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger("sos-service")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALG = "HS256"
PORT = int(os.getenv("SERVICE_PORT", "8002"))

app = FastAPI(title="helep-sos-service")
app.mount("/metrics", make_asgi_app())
TRIGGERS = Counter("helep_sos_triggers_total", "SOS triggers", ["mode"])
CANCELS = Counter("helep_sos_cancels_total", "SOS cancellations")


class SOSIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    mode: str = Field(pattern="^(online|offline)$")
    media_ref: str | None = None  # simulated: filename of captured mic/cam blob


def auth(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        return jwt.decode(authorization[7:], JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"bad token: {e}")


@app.on_event("startup")
async def startup() -> None:
    init()
    await producer()
    log.info("sos-service.up", port=PORT)


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


@app.post("/sos", status_code=201)
async def trigger(body: SOSIn, claims: dict = Depends(auth)):
    iid = str(uuid.uuid4())
    # Simulated media capture: when device fires SOS the mic+cam blob would be uploaded.
    # Here we just stamp a filename; real upload is out of scope.
    media_ref = body.media_ref or f"sim://incident/{iid}/blob.bin"
    insert_incident(iid, claims["sub"], body.lat, body.lon, body.mode, media_ref)
    await publish(
        "sos.triggered",
        {
            "incident_id": iid,
            "user_id": claims["sub"],
            "lat": body.lat,
            "lon": body.lon,
            "mode": body.mode,
            "media_ref": media_ref,
        },
        key=iid,
    )
    TRIGGERS.labels(mode=body.mode).inc()
    log.info("sos.triggered", id=iid, mode=body.mode)
    return {"incident_id": iid, "status": "ACTIVE"}


@app.post("/sos/{iid}/cancel")
async def cancel_sos(iid: str, claims: dict = Depends(auth)):
    row = cancel(iid, claims["sub"])
    if not row:
        raise HTTPException(404, "incident not found")
    if row["status"] != "CANCELLED":
        raise HTTPException(409, f"current status {row['status']} cannot be cancelled")
    await publish("sos.cancelled", {"incident_id": iid, "user_id": claims["sub"]}, key=iid)
    CANCELS.inc()
    return {"status": "CANCELLED"}


@app.get("/sos/{iid}")
async def get_sos(iid: str):
    row = get(iid)
    if not row:
        raise HTTPException(404, "not found")
    return {k: row[k] for k in row.keys()}
