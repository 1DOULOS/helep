"""SQLite repository for notification-service."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DB_PATH = os.getenv("DB_PATH", "/data/notification.db")
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
            CREATE TABLE IF NOT EXISTS notifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                channel     TEXT NOT NULL CHECK(channel IN ('sms','push','email')),
                recipient   TEXT NOT NULL,
                template    TEXT NOT NULL,
                payload     TEXT NOT NULL,
                created_at  TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def record(channel: str, recipient: str, template: str, payload: str) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO notifications (channel, recipient, template, payload) VALUES (?, ?, ?, ?)",
            (channel, recipient, template, payload),
        )
        return cur.lastrowid


def list_all(limit: int = 100) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
