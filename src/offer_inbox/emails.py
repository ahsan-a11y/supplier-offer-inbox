"""Parse raw RFC 822 messages into a simple Email object."""

from __future__ import annotations

import email
import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import quote


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class Email:
    message_id: str
    from_name: str
    from_addr: str
    subject: str
    date: datetime | None
    body: str
    attachments: list[Attachment] = field(default_factory=list)
    raw: bytes = b""
    reply_name: str = ""
    reply_addr: str = ""

    @property
    def sender_name(self) -> str:
        return self.reply_name or self.from_name

    @property
    def sender_addr(self) -> str:
        """The supplier's address. Mail sent through sales platforms (and our demo, sent via Gmail)
        often comes from a generic address with the person's real address in Reply-To."""
        return self.reply_addr or self.from_addr

    @property
    def content_hash(self) -> str:
        """Catches the same offer re-sent with a new Message-ID."""
        h = hashlib.sha256()
        h.update(self.from_addr.lower().encode())
        h.update(self.subject.strip().lower().encode())
        h.update(self.body.strip().encode())
        for a in self.attachments:
            h.update(hashlib.sha256(a.data).digest())
        return h.hexdigest()

    @property
    def gmail_link(self) -> str:
        mid = self.message_id.strip("<>")
        return f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{quote(mid, safe='')}"


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)</(td|th)>", " | ", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", "", markup))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def parse_email(raw: bytes) -> Email:
    msg = email.message_from_bytes(raw, policy=policy.default)
    name, addr = parseaddr(str(msg.get("From", "")))
    reply_name, reply_addr = parseaddr(str(msg.get("Reply-To", "")))

    plain, rich = None, None
    attachments: list[Attachment] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        ctype = part.get_content_type()
        if filename or disposition == "attachment" or ctype.startswith("image/"):
            payload = part.get_payload(decode=True) or b""
            attachments.append(Attachment(filename or f"inline.{ctype.split('/')[-1]}", ctype, payload))
        elif ctype == "text/plain" and plain is None:
            plain = part.get_content()
        elif ctype == "text/html" and rich is None:
            rich = part.get_content()

    # HTML usually keeps tables intact, so prefer it when both exist.
    body = _html_to_text(rich) if rich else (plain or "")

    try:
        date = parsedate_to_datetime(msg["Date"]) if msg["Date"] else None
    except (TypeError, ValueError):
        date = None

    message_id = str(msg.get("Message-ID", "")).strip()
    if not message_id:
        message_id = "<sha256-" + hashlib.sha256(raw).hexdigest()[:24] + "@local>"

    return Email(
        message_id=message_id,
        from_name=name,
        from_addr=addr.lower(),
        subject=str(msg.get("Subject", "")),
        date=date,
        body=body.strip(),
        attachments=attachments,
        raw=raw,
        reply_name=reply_name,
        reply_addr=reply_addr.lower(),
    )
