"""Turn attachments into Claude content blocks.

PDFs and images go to the model natively (it reads text, tables and photos).
Spreadsheets are converted to CSV text here, since that is exact and cheaper
than rendering them.
"""

from __future__ import annotations

import base64
import csv
import io
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageOps
from pypdf import PdfReader

from .emails import Attachment

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SHEET_EXT = {".xlsx", ".xlsm"}
TEXT_EXT = {".csv", ".tsv", ".txt"}
MAX_IMAGE_SIDE = 2000  # larger photos are downscaled; text stays legible
MAX_SHEET_CHARS = 200_000


def kind(att: Attachment) -> str:
    ext = Path(att.filename).suffix.lower()
    if att.content_type == "application/pdf" or ext == ".pdf":
        return "pdf"
    if att.content_type in IMAGE_TYPES or ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    if ext in SHEET_EXT:
        return "sheet"
    if ext in TEXT_EXT or att.content_type.startswith("text/"):
        return "text"
    return "other"


def sheet_to_text(data: bytes) -> str:
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in ws.iter_rows(values_only=True):
            if any(v not in (None, "") for v in row):
                writer.writerow(["" if v is None else v for v in row])
        out.append(f"--- sheet: {ws.title} ---\n{buf.getvalue()}")
    return "\n".join(out)[:MAX_SHEET_CHARS]


def _image_block(data: bytes) -> dict:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")  # phone photos carry rotation in EXIF
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()},
    }


def to_blocks(att: Attachment) -> list[dict]:
    """Content blocks for one attachment, each preceded by a label naming the file."""
    label = {"type": "text", "text": f'<attachment filename="{att.filename}">'}
    k = kind(att)
    if k == "pdf":
        doc = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(att.data).decode()},
        }
        return [label, doc]
    if k == "image":
        return [label, _image_block(att.data)]
    if k == "sheet":
        return [label, {"type": "text", "text": sheet_to_text(att.data)}]
    if k == "text":
        return [label, {"type": "text", "text": att.data.decode("utf-8", "replace")[:MAX_SHEET_CHARS]}]
    return [{"type": "text", "text": f'<attachment filename="{att.filename}" skipped="unsupported type {att.content_type}">'}]


def pdf_text(data: bytes, pages: int = 2) -> str:
    """Text layer of the first pages. Empty for scanned PDFs (no text layer)."""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:pages]).strip()
    except Exception:
        return ""


def preview(att: Attachment, chars: int = 1500) -> str:
    """Cheap local text preview for the classifier (it is never sent PDFs or images)."""
    k = kind(att)
    if k == "sheet":
        return sheet_to_text(att.data)[:chars]
    if k == "text":
        return att.data.decode("utf-8", "replace")[:chars]
    if k == "pdf":
        text = pdf_text(att.data)[:chars]
        if text:
            return text
    return f"[{k} attachment, contents not readable as text]"
