"""Command line entry point: `offer-inbox <command>`."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import pipeline, store
from .config import settings

console = Console()


def cmd_poll(args) -> None:
    db = store.connect()
    while True:
        try:
            counts = pipeline.poll_once(db)
            console.print(f"[dim]{time.strftime('%H:%M:%S')}[/] poll done: {counts or 'no new mail'}")
        except Exception as exc:  # a bad poll (network, auth) must not kill the loop
            logging.exception("poll failed: %s", exc)
        if args.once:
            break
        time.sleep(args.interval)


def cmd_process(args) -> None:
    db = store.connect()
    for p in args.files:
        console.print(f"{p}: {pipeline.process_file(Path(p), db)}")


def _num(v) -> str:
    if v is None:
        return ""
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def cmd_show(args) -> None:
    db = store.connect()
    t = Table(title="Emails (newest first)", show_lines=False)
    t.add_column("received", no_wrap=True)
    t.add_column("from", max_width=24, no_wrap=True, overflow="ellipsis")
    t.add_column("subject", max_width=34, no_wrap=True, overflow="ellipsis")
    t.add_column("status", no_wrap=True)
    t.add_column("items", justify="right")
    t.add_column("cost $", justify="right")
    # rowid = order the emails were stored in, so the email just processed is on top.
    for r in db.execute("SELECT * FROM emails ORDER BY rowid DESC LIMIT ?", (args.emails,)):
        color = {"extracted": "green", "not_offer": "dim", "error": "red"}.get(r["status"], "yellow")
        t.add_row((r["received_at"] or "")[5:16].replace("T", " "), r["from_addr"], r["subject"],
                  f"[{color}]{r['status']}[/]", str(r["item_count"]), f"{r['cost_usd'] or 0:.4f}")
    console.print(t)

    t = Table(title="Offer items (newest first)")
    t.add_column("supplier", max_width=18, no_wrap=True, overflow="ellipsis")
    t.add_column("product", max_width=30, no_wrap=True, overflow="ellipsis")
    t.add_column("qty", justify="right", no_wrap=True)
    t.add_column("price", justify="right", no_wrap=True)
    t.add_column("ship from", max_width=16, no_wrap=True, overflow="ellipsis")
    t.add_column("valid until", no_wrap=True)
    t.add_column("from file", max_width=16, no_wrap=True, overflow="ellipsis")
    t.add_column("conf", justify="right")
    q = "SELECT * FROM offer_items" + (" WHERE needs_review=1" if args.review else "") + " ORDER BY id DESC LIMIT ?"
    for r in db.execute(q, (args.limit,)):
        qty = f"{_num(r['quantity_available'])} {r['quantity_unit'] or ''}".strip()
        price = f"{r['unit_price']:,.2f} {r['currency'] or ''}".strip() if r["unit_price"] is not None else "-"
        t.add_row(r["supplier_name"] or "", r["product_name"] or "", qty, price, r["ship_from"] or "",
                  r["valid_until"] or "", r["source_attachment"] or "(email body)", f"{r['confidence'] or 0:.2f}",
                  style="yellow" if r["needs_review"] else None)
    console.print(t)
    console.print("[yellow]yellow[/] = flagged for review (low confidence or missing price). "
                  "Full details: [bold]uv run offer-inbox export[/] then open data/offer_items.csv")


def cmd_export(args) -> None:
    n = store.export_csv(store.connect(), Path(args.out))
    console.print(f"wrote {n} rows to {args.out}")


def cmd_seed(args) -> None:
    """Puts the eval emails into the mailbox via IMAP APPEND.

    APPEND keeps each email's original From header (the fake supplier address). Sending through
    Gmail SMTP would rewrite From to your own address, which would make supplier_email useless.
    """
    from .mailbox import Mailbox

    files = sorted(Path(args.dir).glob("*.eml"))
    with Mailbox() as mb:
        pipeline.start_cursor(store.connect(), mb)  # so the poller picks up exactly these new emails
        mb.select(readonly=False)
        for f in files:
            mb.append(f.read_bytes())
            console.print(f"appended {f.name}")


def cmd_send_demo(args) -> None:
    """Sends two real emails to the inbox through Gmail SMTP: an offer with a PDF, and a non-offer.

    Gmail always sends from your own address, so each email carries a made-up sender in its
    display name and Reply-To; the pipeline uses Reply-To as the supplier address. Each send gets
    a unique reference in the subject so the duplicate check doesn't skip a repeat send.
    """
    import random
    import smtplib
    from email.message import EmailMessage

    pdf = Path("demo/Riverside_Pricelist.pdf")
    if not pdf.exists():
        raise SystemExit("Run `uv run python evalset/demo_assets.py` first to create the demo PDF.")
    to = args.to or settings.imap_user
    ref = f"RH-{random.randint(1000, 9999)}"

    offer = EmailMessage()
    offer["From"] = f"Hannah Price - Riverside Housewares <{settings.imap_user}>"
    offer["Reply-To"] = "Hannah Price <hannah.price@riverside-housewares.example>"
    offer["To"] = to
    offer["Subject"] = f"Riverside price list + one extra item (ref {ref})"
    offer.set_content(
        "Hi,\n\nOur December price list is attached.\n"
        "Also available: 500 bamboo serving trays at $6.80 each, FOB Portland.\n\n"
        "Thanks,\nHannah Price\nSales Manager, Riverside Housewares\nPortland, OR"
    )
    offer.add_attachment(pdf.read_bytes(), maintype="application", subtype="pdf", filename=pdf.name)

    chat = EmailMessage()
    chat["From"] = f"Jordan Ellis <{settings.imap_user}>"
    chat["Reply-To"] = "Jordan Ellis <jordan.ellis@harborelectronics.example>"
    chat["To"] = to
    chat["Subject"] = f"Coffee next week? ({ref})"
    chat.set_content("Hey, are you free on Tuesday for a quick coffee? No agenda.\n\nJordan")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(settings.imap_user, settings.imap_password)
        for m in ([offer] if args.offer_only else [offer, chat]):
            smtp.send_message(m)
            console.print(f"sent: {m['Subject']}")
    console.print("Wait ~10 seconds for Gmail to deliver, then run: [bold]uv run offer-inbox poll --once[/]")


def cmd_eval(args) -> None:
    from .evaluate import run

    summary = run(Path(args.evalset), Path(args.out), args.only, args.workers)
    console.print_json(json.dumps(summary))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="offer-inbox", description="Reads supplier offers out of a mailbox.")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("poll", help="poll the IMAP inbox and process new mail")
    s.add_argument("--once", action="store_true", help="poll once and exit")
    s.add_argument("--interval", type=int, default=120, help="seconds between polls")
    s.set_defaults(func=cmd_poll)

    s = sub.add_parser("process", help="process local .eml files (no mailbox needed)")
    s.add_argument("files", nargs="+")
    s.set_defaults(func=cmd_process)

    s = sub.add_parser("show", help="print recent emails and extracted items")
    s.add_argument("--emails", type=int, default=8, help="how many emails to list")
    s.add_argument("--limit", type=int, default=12, help="how many items to list")
    s.add_argument("--review", action="store_true", help="only rows flagged for review")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("export", help="export all items to CSV")
    s.add_argument("--out", default=str(settings.data_dir / "offer_items.csv"))
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("seed", help="append the eval emails to the IMAP inbox")
    s.add_argument("--dir", default="evalset/emails")
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("send-demo", help="send a fresh offer email (with PDF) + a non-offer to the inbox")
    s.add_argument("--to", help="recipient (default: IMAP_USER)")
    s.add_argument("--offer-only", action="store_true", help="send only the offer email")
    s.set_defaults(func=cmd_send_demo)

    s = sub.add_parser("eval", help="score the pipeline against the labelled eval set")
    s.add_argument("--evalset", default="evalset")
    s.add_argument("--out", default="eval_runs")
    s.add_argument("--only", nargs="*", help="substring filter on email ids")
    s.add_argument("--workers", type=int, default=4)
    s.set_defaults(func=cmd_eval)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
