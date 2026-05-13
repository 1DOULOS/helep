"""SQLite repository for dispatch-service. Pattern: Repository."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

DB_PATH = os.getenv("DB_PATH", "/data/dispatch.db")
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
            CREATE TABLE IF NOT EXISTS responders (
                id           TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                lat          REAL NOT NULL,
                lon          REAL NOT NULL,
                credibility  REAL NOT NULL DEFAULT 1.0,
                busy         INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS assignments (
                incident_id  TEXT PRIMARY KEY,
                responder_id TEXT NOT NULL,
                status       TEXT NOT NULL CHECK(status IN ('ASSIGNED','CONFIRMED','RELEASED')),
                created_at   TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS danger_zones (
                id        TEXT PRIMARY KEY,
                lat       REAL NOT NULL,
                lon       REAL NOT NULL,
                radius_m  REAL NOT NULL
            );
            """
        )
        # Seed a few responders and zones for the demo (student can replace).
        seed = c.execute("SELECT COUNT(*) FROM responders").fetchone()[0]
        if seed == 0:
            c.executemany(
                "INSERT INTO responders (id, name, lat, lon, credibility) VALUES (?, ?, ?, ?, ?)",
                [
                    ("r1", "Unit Alpha", 4.0511, 9.7679, 0.9),
                    ("r2", "Unit Bravo", 4.0611, 9.7779, 0.8),
                    ("r3", "Unit Charlie", 4.0411, 9.7579, 0.7),
                ],
            )
            c.execute(
                "INSERT INTO danger_zones (id, lat, lon, radius_m) VALUES (?, ?, ?, ?)",
                ("z1", 4.0500, 9.7700, 500.0),
            )


def all_free_responders() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM responders WHERE busy = 0").fetchall()


def reserve_responder_for(rid: str, incident_id: str) -> bool:
    """Atomic claim: returns True if responder was free and is now busy."""
    with conn() as c:
        cur = c.execute(
            "UPDATE responders SET busy = 1 WHERE id = ? AND busy = 0", (rid,)
        )
        if cur.rowcount == 0:
            return False
        # Idempotency: only insert assignment if none exists for this incident
        try:
            c.execute(
                "INSERT INTO assignments (incident_id, responder_id, status) VALUES (?, ?, 'ASSIGNED')",
                (incident_id, rid),
            )
        except sqlite3.IntegrityError:
            # already assigned → roll back responder claim
            c.execute("UPDATE responders SET busy = 0 WHERE id = ?", (rid,))
            return False
        return True


def assignment_for(incident_id: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM assignments WHERE incident_id = ?", (incident_id,)).fetchone()


def release_assignment(incident_id: str) -> None:
    with conn() as c:
        row = c.execute("SELECT responder_id FROM assignments WHERE incident_id = ?", (incident_id,)).fetchone()
        if not row:
            return
        c.execute("UPDATE assignments SET status='RELEASED' WHERE incident_id = ?", (incident_id,))
        c.execute("UPDATE responders SET busy = 0 WHERE id = ?", (row["responder_id"],))


def list_danger_zones() -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM danger_zones").fetchall()
