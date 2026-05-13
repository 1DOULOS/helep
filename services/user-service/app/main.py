"""user-service: identity, JWT auth, credibility, emergency contacts.

Emits: user.registered
Endpoints:
  POST /signup    { phone, password, role }                -> { id, token }
  POST /login     { phone, password }                      -> { id, token }
  GET  /me                                                 -> { id, phone, role, credibility }
  POST /contacts  { name, phone }                          -> 201
  GET  /contacts                                           -> [ { name, phone } ]
"""
from __future__ import annotations
import os
import time
import uuid
import logging

import bcrypt
import jwt
import structlog
from fastapi import Depends, FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from prometheus_client import Counter, make_asgi_app

from .db import init, insert_user, find_by_phone, add_contact, list_contacts
from .events import publish, health, producer, stop_producer

logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
log = structlog.get_logger("user-service")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALG = "HS256"
PORT = int(os.getenv("SERVICE_PORT", "8001"))

app = FastAPI(title="helep-user-service")
app.mount("/metrics", make_asgi_app())
SIGNUPS = Counter("helep_user_signups_total", "Signups")
LOGINS = Counter("helep_user_logins_total", "Logins")


class SignupIn(BaseModel):
    phone: str = Field(min_length=6)
    password: str = Field(min_length=6)
    role: str = Field(pattern="^(citizen|responder|police)$")


class LoginIn(BaseModel):
    phone: str
    password: str


class ContactIn(BaseModel):
    name: str
    phone: str


def make_token(uid: str, role: str) -> str:
    payload = {"sub": uid, "role": role, "iat": int(time.time()), "exp": int(time.time()) + 86400}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


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
    await producer()  # warm up Kafka producer
    log.info("user-service.up", port=PORT)


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


@app.post("/signup", status_code=201)
async def signup(body: SignupIn):
    if find_by_phone(body.phone):
        raise HTTPException(409, "phone already registered")
    uid = str(uuid.uuid4())
    pwd_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    insert_user(uid, body.phone, pwd_hash, body.role)
    await publish("user.registered", {"id": uid, "phone": body.phone, "role": body.role}, key=uid)
    SIGNUPS.inc()
    return {"id": uid, "token": make_token(uid, body.role)}


@app.post("/login")
async def login(body: LoginIn):
    row = find_by_phone(body.phone)
    if not row or not bcrypt.checkpw(body.password.encode(), row["pwd_hash"].encode()):
        raise HTTPException(401, "invalid credentials")
    LOGINS.inc()
    return {"id": row["id"], "token": make_token(row["id"], row["role"])}


@app.get("/me")
async def me(claims: dict = Depends(auth)):
    row = find_by_phone_by_id(claims["sub"])
    if not row:
        raise HTTPException(404, "user gone")
    return {"id": row["id"], "phone": row["phone"], "role": row["role"], "credibility": row["credibility"]}


@app.post("/contacts", status_code=201)
async def post_contact(body: ContactIn, claims: dict = Depends(auth)):
    add_contact(claims["sub"], body.name, body.phone)
    return {"ok": True}


@app.get("/contacts")
async def get_contacts(claims: dict = Depends(auth)):
    rows = list_contacts(claims["sub"])
    return [{"name": r["name"], "phone": r["phone"]} for r in rows]


def find_by_phone_by_id(uid: str):
    import sqlite3
    from .db import DB_PATH
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        return c.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        c.close()
