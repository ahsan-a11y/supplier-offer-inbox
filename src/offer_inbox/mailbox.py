"""IMAP access. Read-only: we never change flags, move or delete mail."""

from __future__ import annotations

import imaplib
import time
from collections.abc import Iterator

from .config import settings


class Mailbox:
    def __init__(self) -> None:
        if not (settings.imap_user and settings.imap_password):
            raise SystemExit("Set IMAP_USER and IMAP_PASSWORD (a Gmail app password) in .env")
        self.conn = imaplib.IMAP4_SSL(settings.imap_host)
        self.conn.login(settings.imap_user, settings.imap_password)

    def __enter__(self) -> "Mailbox":
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.conn.logout()
        except Exception:
            pass

    def select(self, readonly: bool = True) -> int:
        """Selects the folder and returns its UIDVALIDITY."""
        typ, _ = self.conn.select(f'"{settings.imap_folder}"', readonly=readonly)
        if typ != "OK":
            raise RuntimeError(f"cannot open folder {settings.imap_folder}")
        _, data = self.conn.response("UIDVALIDITY")
        return int(data[0])

    def max_uid(self) -> int:
        _, data = self.conn.uid("SEARCH", None, "ALL")
        uids = data[0].split()
        return int(uids[-1]) if uids else 0

    def new_messages(self, after_uid: int) -> Iterator[tuple[int, bytes]]:
        """Yields (uid, raw bytes) for every message with UID greater than after_uid."""
        _, data = self.conn.uid("SEARCH", None, f"UID {after_uid + 1}:*")
        uids = [int(u) for u in data[0].split() if int(u) > after_uid]
        for uid in sorted(uids):
            yield uid, self.fetch(uid)

    def fetch(self, uid: int) -> bytes:
        # BODY.PEEK leaves the \\Seen flag untouched, so buyers' read state is unchanged.
        _, msg = self.conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        return next(part[1] for part in msg if isinstance(part, tuple))

    def append(self, raw: bytes, date=None) -> None:
        """Puts a message into the folder (used to seed test emails with their original From header)."""
        when = imaplib.Time2Internaldate(time.mktime(date.timetuple())) if date else None
        typ, data = self.conn.append(f'"{settings.imap_folder}"', None, when, raw)
        if typ != "OK":
            raise RuntimeError(f"APPEND failed: {data}")

