"""SQLite store: one row per email (the processing log) and one row per offered item."""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .llm import FIELDS

NUMERIC = {"quantity_available", "unit_price"}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS emails (
    message_id TEXT PRIMARY KEY,
    content_hash TEXT,
    imap_uid INTEGER,
    from_addr TEXT,
    subject TEXT,
    received_at TEXT,
    link TEXT,
    status TEXT,              -- extracted | not_offer | duplicate | error
    is_offer INTEGER,
    classify_confidence REAL,
    classify_reason TEXT,
    item_count INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    error TEXT,
    processed_at TEXT
);
CREATE INDEX IF NOT EXISTS emails_hash ON emails(content_hash);

CREATE TABLE IF NOT EXISTS offer_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {", ".join(f"{f} {'REAL' if f in NUMERIC else 'TEXT'}" for f in FIELDS)},
    source_email_id TEXT REFERENCES emails(message_id),
    source_attachment TEXT,
    source_link TEXT,          -- Gmail link to the email
    attachment_path TEXT,      -- local copy of the attachment the row came from
    confidence REAL,
    needs_review INTEGER,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def get_state(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute("INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    db.commit()


def email_row(db: sqlite3.Connection, message_id: str) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM emails WHERE message_id=?", (message_id,)).fetchone()


def find_by_hash(db: sqlite3.Connection, content_hash: str, exclude_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM emails WHERE content_hash=? AND message_id<>? AND status IN ('extracted','not_offer')",
        (content_hash, exclude_id),
    ).fetchone()


def upsert_email(db: sqlite3.Connection, **cols) -> None:
    keys = list(cols)
    db.execute(
        f"INSERT INTO emails ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))}) "
        f"ON CONFLICT(message_id) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in keys if k != 'message_id')}",
        [cols[k] for k in keys],
    )


def replace_items(db: sqlite3.Connection, message_id: str, rows: list[dict]) -> None:
    """Re-processing an email replaces its rows, so retries never duplicate items."""
    db.execute("DELETE FROM offer_items WHERE source_email_id=?", (message_id,))
    for r in rows:
        keys = list(r)
        db.execute(
            f"INSERT INTO offer_items ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            [r[k] for k in keys],
        )


ITEM_COLUMNS = FIELDS + [
    "source_email_id", "source_attachment", "source_link", "attachment_path", "confidence", "needs_review",
]


def export_csv(db: sqlite3.Connection, out: Path) -> int:
    rows = db.execute(f"SELECT {', '.join(ITEM_COLUMNS)} FROM offer_items ORDER BY id").fetchall()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(ITEM_COLUMNS)
        for r in rows:
            w.writerow([int(v) if isinstance(v, float) and v.is_integer() else v for v in r])
    return len(rows)
