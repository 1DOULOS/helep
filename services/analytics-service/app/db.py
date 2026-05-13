"""SQLite repository for analytics-service. Tally tables, append-only."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.getenv("DB_PATH", "/data/analytics.db")
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
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS incident_log (
                incident_id TEXT PRIMARY KEY,
                lat         REAL,
                lon         REAL,
                mode        TEXT,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS zone_hits (
                zone_id    TEXT NOT NULL,
                incident_id TEXT NOT NULL,
                at         TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (zone_id, incident_id)
            );
            CREATE TABLE IF NOT EXISTS event_counts (
                stream  TEXT PRIMARY KEY,
                n       INTEGER NOT NULL DEFAULT 0
            );
            """
        )


def bump_event(stream: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO event_counts (stream, n) VALUES (?, 1) "
            "ON CONFLICT(stream) DO UPDATE SET n = n + 1",
            (stream,),
        )


def log_incident(iid: str, lat: float | None, lon: float | None, mode: str | None) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO incident_log (incident_id, lat, lon, mode) VALUES (?, ?, ?, ?)",
            (iid, lat, lon, mode),
        )


def log_zone_hit(zone_id: str, iid: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO zone_hits (zone_id, incident_id) VALUES (?, ?)",
            (zone_id, iid),
        )


def zone_summary() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT zone_id, COUNT(*) AS hits FROM zone_hits GROUP BY zone_id ORDER BY hits DESC"
        ).fetchall()


def crime_map() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT lat, lon, mode, created_at FROM incident_log ORDER BY created_at DESC LIMIT 500"
        ).fetchall()


def event_summary() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT stream, n FROM event_counts ORDER BY n DESC").fetchall()
