"""Renders spec.py into evalset/emails/*.eml and evalset/labels/*.json.

    uv run python evalset/build.py
"""

from __future__ import annotations

import csv
import io
import json
import random
import sys
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from spec import EMAILS  # noqa: E402

# ---------------------------------------------------------------- attachment renderers


def pdf_table(a: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=a["title"], leftMargin=40, rightMargin=40)
    styles = getSampleStyleSheet()
    table = Table([a["columns"]] + [[str(c) for c in r] for r in a["rows"]], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f7")]),
    ]))
    doc.build([Paragraph(a["title"], styles["Title"]), Paragraph(a["subtitle"], styles["Normal"]),
               Spacer(1, 12), table])
    return buf.getvalue()


def _render_sheet(a: dict, scale: int = 2) -> Image.Image:
    """Draws a printed-looking table on white paper."""
    font = ImageFont.load_default(size=15 * scale)
    bold = ImageFont.load_default(size=20 * scale)
    small = ImageFont.load_default(size=12 * scale)
    cells = [a["columns"]] + [[str(c) for c in r] for r in a["rows"]]
    widths = [max(font.getlength(r[i]) for r in cells) + 24 * scale for i in range(len(a["columns"]))]
    row_h = 30 * scale
    w = int(sum(widths) + 80 * scale)
    h = int(150 * scale + row_h * len(cells))
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    x0, y = 40 * scale, 30 * scale
    d.text((x0, y), a["title"], fill="black", font=bold)
    d.text((x0, y + 36 * scale), a["subtitle"], fill="black", font=small)
    y += 80 * scale
    for ri, row in enumerate(cells):
        x = x0
        for ci, cell in enumerate(row):
            d.rectangle([x, y, x + widths[ci], y + row_h], outline="black", width=scale)
            d.text((x + 10 * scale, y + 7 * scale), cell, fill="black", font=font)
            x += widths[ci]
        y += row_h
    return img


def photo_table(a: dict) -> bytes:
    """A phone photo: rotated sheet on a desk, uneven light, blur, JPEG artifacts."""
    rnd = random.Random(2)
    sheet = _render_sheet(a)
    sheet = sheet.rotate(-4.5, expand=True, fillcolor=(120, 96, 70), resample=Image.BICUBIC)
    bg = Image.new("RGB", (sheet.width + 260, sheet.height + 220), (120, 96, 70))
    bg.paste(sheet, (140, 90), mask=None)
    # warm, uneven lighting
    shade = Image.linear_gradient("L").resize(bg.size).rotate(30)
    bg = Image.composite(bg, Image.new("RGB", bg.size, (60, 50, 40)), shade.point(lambda v: 150 + v // 3))
    bg = bg.filter(ImageFilter.GaussianBlur(1.6))
    px = bg.load()
    for _ in range(bg.width * bg.height // 40):
        x, y = rnd.randrange(bg.width), rnd.randrange(bg.height)
        r, g, b = px[x, y]
        n = rnd.randint(-25, 25)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    bg.thumbnail((2400, 2400))
    out = io.BytesIO()
    bg.save(out, format="JPEG", quality=62)
    return out.getvalue()


def scan_table(a: dict) -> bytes:
    """A cheap office scan: grayscale, slight skew, speckle noise, low resolution."""
    rnd = random.Random(10)
    img = _render_sheet(a, scale=1).convert("L")
    img = img.rotate(1.8, expand=True, fillcolor=255, resample=Image.BICUBIC)
    px = img.load()
    for _ in range(img.width * img.height // 60):
        x, y = rnd.randrange(img.width), rnd.randrange(img.height)
        px[x, y] = rnd.choice([0, 60, 200])
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def xlsx(a: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Offer"
    for line in a.get("preamble", []):
        ws.append([line])
    ws.append(a["columns"])
    for r in a["rows"]:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def csv_file(a: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(a["columns"])
    w.writerows(a["rows"])
    return buf.getvalue().encode()


RENDERERS = {
    "pdf_table": (pdf_table, "application", "pdf"),
    "photo_table": (photo_table, "image", "jpeg"),
    "scan_table": (scan_table, "image", "png"),
    "xlsx": (xlsx, "application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "csv": (csv_file, "text", "csv"),
}

# ---------------------------------------------------------------- email assembly


def html_table(columns, rows) -> str:
    head = "".join(f"<th style='border:1px solid #999;padding:4px'>{c}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td style='border:1px solid #999;padding:4px'>{c}</td>" for c in r) + "</tr>" for r in rows
    )
    return f"<table style='border-collapse:collapse'><tr>{head}</tr>{body}</table>"


def build_message(e: dict) -> EmailMessage:
    m = EmailMessage()
    m["From"] = formataddr(e["from_"])
    m["To"] = "purchasing@inbox.example"
    m["Subject"] = e["subject"]
    m["Date"] = format_datetime(datetime.fromisoformat(e["date"]))
    m["Message-ID"] = f"<eval-{e['id']}@offer-inbox.test>"
    if e.get("html"):
        html = e["body_intro"] + html_table(e["columns"], e["rows"]) + e["body_outro"]
        text = html.replace("<br>", "\n")
        m.set_content("(HTML message)\n" + text)
        m.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    else:
        m.set_content(e["body"])
    for a in e["attachments"]:
        fn, maintype, subtype = RENDERERS[a["type"]]
        m.add_attachment(fn(a), maintype=maintype, subtype=subtype, filename=a["filename"])
    return m


def label(e: dict) -> dict:
    sender = e["from_"][1]
    return {
        "id": e["id"],
        "kind": e["kind"],
        "message_id": f"<eval-{e['id']}@offer-inbox.test>",
        "is_offer": e["is_offer"],
        "items": [{**it, "supplier_email": sender} for it in e["items"]],
    }


def main() -> None:
    (HERE / "emails").mkdir(exist_ok=True)
    (HERE / "labels").mkdir(exist_ok=True)
    for e in EMAILS:
        (HERE / "emails" / f"{e['id']}.eml").write_bytes(bytes(build_message(e)))
        (HERE / "labels" / f"{e['id']}.json").write_text(json.dumps(label(e), indent=2, ensure_ascii=False) + "\n")
    n_items = sum(len(e["items"]) for e in EMAILS)
    n_offers = sum(e["is_offer"] for e in EMAILS)
    print(f"wrote {len(EMAILS)} emails ({n_offers} offers, {len(EMAILS) - n_offers} non-offers, {n_items} labelled items)")


if __name__ == "__main__":
    main()
