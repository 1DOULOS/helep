"""SQLite repository for user-service. Pattern: Repository."""
from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

DB_PATH = os.getenv("DB_PATH", "/data/user.db")
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
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                phone         TEXT UNIQUE NOT NULL,
                pwd_hash      TEXT NOT NULL,
                role          TEXT NOT NULL CHECK(role IN ('citizen','responder','police')),
                credibility   REAL NOT NULL DEFAULT 1.0,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS contacts (
                user_id   TEXT NOT NULL,
                name      TEXT NOT NULL,
                phone     TEXT NOT NULL,
                PRIMARY KEY (user_id, phone),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            """
        )


def insert_user(uid: str, phone: str, pwd_hash: str, role: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO users (id, phone, pwd_hash, role) VALUES (?, ?, ?, ?)",
            (uid, phone, pwd_hash, role),
        )


def find_by_phone(phone: str) -> Optional[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()


def add_contact(uid: str, name: str, phone: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO contacts (user_id, name, phone) VALUES (?, ?, ?)",
            (uid, name, phone),
        )


def list_contacts(uid: str) -> list[sqlite3.Row]:
    with conn() as c:
        return c.execute("SELECT * FROM contacts WHERE user_id = ?", (uid,)).fetchall()
