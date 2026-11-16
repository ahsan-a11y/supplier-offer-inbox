"""Classify -> extract -> normalize -> store, for one email at a time."""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import llm, store
from .config import settings
from .emails import Email

log = logging.getLogger("offer_inbox")


@dataclass
class Result:
    is_offer: bool
    classify_confidence: float
    classify_reason: str
    items: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0


def _clean_str(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def normalize(raw_item: dict, supplier_name: str | None, e: Email) -> dict:
    """Deterministic clean-up after the model: types, ISO codes, dates, review flag."""
    it = {k: _clean_str(v) if isinstance(v, str) else v for k, v in raw_item.items()}
    it["supplier_name"] = _clean_str(supplier_name) or _clean_str(e.sender_name)
    it["supplier_email"] = e.sender_addr
    if it.get("currency"):
        cur = it["currency"].upper()
        it["currency"] = {"$": "USD", "€": "EUR", "£": "GBP", "US$": "USD"}.get(cur, cur)
    if it.get("valid_until"):
        try:
            it["valid_until"] = date.fromisoformat(it["valid_until"][:10]).isoformat()
        except ValueError:
            it["notes"] = "; ".join(filter(None, [it.get("notes"), f"validity: {it['valid_until']}"]))
            it["valid_until"] = None
    for num in ("quantity_available", "unit_price"):
        v = it.get(num)
        if isinstance(v, float) and v.is_integer():
            it[num] = int(v)

    conf = float(it.get("confidence") or 0)
    missing_core = not it.get("product_name") or it.get("unit_price") is None
    it["confidence"] = round(conf, 2)
    it["needs_review"] = int(conf < settings.review_threshold or missing_core)
    return it


def run_models(e: Email) -> Result:
    """The model part of the pipeline, with no side effects. The eval calls this directly."""
    cls, u1 = llm.classify(e)
    res = Result(bool(cls["is_offer"]), float(cls["confidence"]), cls["reason"], cost_usd=u1.cost)
    if not res.is_offer:
        return res
    out, u2 = llm.extract(e)
    res.cost_usd += u2.cost
    res.items = [normalize(i, out.get("supplier_name"), e) for i in out["items"]]
    return res


def _save_attachments(e: Email) -> dict[str, str]:
    folder = settings.attachments_dir / hashlib.sha1(e.message_id.encode()).hexdigest()[:16]
    paths = {}
    for a in e.attachments:
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.\- ]", "_", a.filename)
        p = folder / safe
        p.write_bytes(a.data)
        paths[a.filename] = str(p)
    return paths


def process(e: Email, db: sqlite3.Connection, uid: int | None = None) -> str:
    """Processes one email idempotently. Returns the final status."""
    prev = store.email_row(db, e.message_id)
    if prev and prev["status"] in ("extracted", "not_offer", "duplicate"):
        return "already_done"
    attempts = (prev["attempts"] if prev else 0) + 1
    if prev and prev["status"] == "error" and attempts > settings.max_attempts:
        return "gave_up"

    base = dict(
        message_id=e.message_id, content_hash=e.content_hash, imap_uid=uid, from_addr=e.sender_addr,
        subject=e.subject, received_at=e.date.isoformat() if e.date else None, link=e.gmail_link,
        attempts=attempts, processed_at=store.now(),
    )

    dup = store.find_by_hash(db, e.content_hash, e.message_id)
    if dup:
        store.upsert_email(db, **base, status="duplicate", error=f"same content as {dup['message_id']}")
        db.commit()
        log.info("duplicate of %s: %s", dup["message_id"], e.subject)
        return "duplicate"

    try:
        res = run_models(e)
    except Exception as exc:  # recorded and retried on the next poll
        store.upsert_email(db, **base, status="error", error=f"{type(exc).__name__}: {exc}")
        db.commit()
        log.exception("failed: %s", e.subject)
        return "error"

    status = "extracted" if res.is_offer else "not_offer"
    store.upsert_email(
        db, **base, status=status, is_offer=int(res.is_offer), classify_confidence=res.classify_confidence,
        classify_reason=res.classify_reason, item_count=len(res.items), cost_usd=round(res.cost_usd, 5), error=None,
    )
    if res.is_offer:
        paths = _save_attachments(e)
        rows = []
        for it in res.items:
            src = it.pop("source_attachment", None)
            rows.append({
                **{f: it.get(f) for f in llm.FIELDS},
                "source_email_id": e.message_id,
                "source_attachment": src,
                "source_link": e.gmail_link,
                "attachment_path": paths.get(src) if src else None,
                "confidence": it["confidence"],
                "needs_review": it["needs_review"],
                "extracted_at": store.now(),
            })
        store.replace_items(db, e.message_id, rows)
    db.commit()
    log.info("%s (%d items, $%.4f): %s", status, len(res.items), res.cost_usd, e.subject)
    return status


def start_cursor(db: sqlite3.Connection, mb) -> None:
    """Sets where polling starts. First run: at the newest message, so mail that was already
    in the inbox is never processed (no cost, and no old private mail sent to the model).
    If UIDVALIDITY changes, the server renumbered the folder, so we restart at the newest
    message too and log it."""
    validity = str(mb.select())
    known = store.get_state(db, "uidvalidity")
    if known == validity and store.get_state(db, "last_uid") is not None:
        return
    newest = mb.max_uid()
    if known and known != validity:
        log.warning("UIDVALIDITY changed (%s -> %s); restarting at newest message", known, validity)
    else:
        log.info("first run: ignoring the %s messages already in the folder", newest)
    store.set_state(db, "uidvalidity", validity)
    store.set_state(db, "last_uid", str(newest))


def poll_once(db: sqlite3.Connection) -> dict[str, int]:
    """Fetches messages newer than the last seen UID, then retries earlier errors."""
    from .emails import parse_email
    from .mailbox import Mailbox

    counts: dict[str, int] = {}
    with Mailbox() as mb:
        start_cursor(db, mb)
        last = int(store.get_state(db, "last_uid") or 0)
        retry_uids = [r["imap_uid"] for r in db.execute(
            "SELECT imap_uid FROM emails WHERE status='error' AND attempts<? AND imap_uid IS NOT NULL",
            (settings.max_attempts,),
        )]
        for uid, raw in mb.new_messages(last):
            status = process(parse_email(raw), db, uid)
            counts[status] = counts.get(status, 0) + 1
            store.set_state(db, "last_uid", str(uid))
        for uid in retry_uids:
            status = process(parse_email(mb.fetch(uid)), db, uid)
            counts[f"retry_{status}"] = counts.get(f"retry_{status}", 0) + 1
    return counts


def process_file(path: Path, db: sqlite3.Connection) -> str:
    from .emails import parse_email

    return process(parse_email(path.read_bytes()), db)
