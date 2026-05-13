"""SQLite repository for sos-service. Pattern: Repository."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

DB_PATH = os.getenv("DB_PATH", "/data/sos.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                lat          REAL NOT NULL,
                lon          REAL NOT NULL,
                mode         TEXT NOT NULL CHECK(mode IN ('online','offline')),
                media_ref    TEXT,
                status       TEXT NOT NULL CHECK(status IN ('ACTIVE','CANCELLED','RESOLVED')),
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def insert_incident(iid: str, uid: str, lat: float, lon: float, mode: str, media_ref: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO incidents (id, user_id, lat, lon, mode, media_ref, status) "
            "VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')",
            (iid, uid, lat, lon, mode, media_ref),
        )


def cancel(iid: str, uid: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        c.execute(
            "UPDATE incidents SET status='CANCELLED' WHERE id=? AND user_id=? AND status='ACTIVE'",
            (iid, uid),
        )
        return c.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()


def get(iid: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM incidents WHERE id=?", (iid,)).fetchone()
