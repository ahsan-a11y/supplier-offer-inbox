"""The two model calls: classify (cheap, text only) and extract (reads attachments)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from . import attachments as att_mod
from .config import cost_usd, settings
from .emails import Email

client = anthropic.Anthropic(max_retries=4)

FIELDS = [
    "supplier_name", "supplier_email", "product_name", "brand", "sku", "category",
    "condition", "quantity_available", "quantity_unit", "unit_price", "currency",
    "price_basis", "ship_from", "valid_until", "notes",
]

CATEGORIES = [
    "Furniture", "Electronics", "Computers", "Food & Beverage", "Fresh Produce",
    "Apparel", "Tools & Hardware", "Office Supplies", "Health & Beauty",
    "Household", "Industrial", "Other",
]


def _nullable(t: str, **extra) -> dict:
    return {"type": [t, "null"], **extra}


ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "product_name": {"type": "string"},
        "brand": _nullable("string"),
        "sku": _nullable("string"),
        "category": {"type": "string", "enum": CATEGORIES},
        "condition": {"anyOf": [{"type": "string", "enum": ["New", "Refurbished", "Used"]}, {"type": "null"}]},
        "quantity_available": _nullable("number"),
        "quantity_unit": _nullable("string"),
        "unit_price": _nullable("number"),
        "currency": _nullable("string"),
        "price_basis": _nullable("string"),
        "ship_from": _nullable("string"),
        "valid_until": _nullable("string"),
        "notes": _nullable("string"),
        "source_attachment": _nullable("string"),
        "confidence": {"type": "number"},
    },
    "required": [
        "product_name", "brand", "sku", "category", "condition", "quantity_available",
        "quantity_unit", "unit_price", "currency", "price_basis", "ship_from",
        "valid_until", "notes", "source_attachment", "confidence",
    ],
    "additionalProperties": False,
}

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_name": _nullable("string"),
        "items": {"type": "array", "items": ITEM_SCHEMA},
    },
    "required": ["supplier_name", "items"],
    "additionalProperties": False,
}

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "is_offer": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["is_offer", "confidence", "reason"],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = """You triage a wholesale distributor's shared purchasing inbox.

Decide if an email is a SUPPLIER OFFER: a supplier proposing goods for us to buy, with prices,
stock or availability (price lists, stock offers, closeouts, special deals), in the body or an attachment.

NOT offers, even when they mention products and prices:
- order confirmations, invoices, payment reminders, shipping/delivery notices (they concern a purchase already made)
- requests for quotes or price enquiries sent TO us (we would be the seller)
- newsletters, market news, event invites, general chatter

Attachments are shown as a text preview. If an attachment's contents are NOT readable as text
(an image, a scanned PDF) and the sender could plausibly be sending a price list or offer, answer
is_offer=true with lower confidence: a missed offer is lost for good, while a false alarm only costs
one extra extraction call.

Give confidence between 0 and 1 and a one-sentence reason."""

EXTRACT_SYSTEM = f"""You extract supplier offers from emails for a wholesale buyer. Return one item per offered product
(each size/colour/model with its own price or SKU counts as its own product), covering the email body AND every attachment.
If the email turns out to contain no offered products, return an empty items list.

Rules:
- Only use what the email states. If a value is not stated, use null. Never guess.
- Header-level terms (currency, ship-from/incoterms, validity date, condition) apply to every item they cover;
  copy them onto each item.
- product_name: as written by the supplier, without the brand/SKU if those are separate columns.
- sku: supplier SKU or model number exactly as written.
- category: the closest of {", ".join(CATEGORIES)}.
- condition: New, Refurbished or Used, only when the email explicitly says so (e.g. "brand new", "grade A refurb",
  "all items new"). Do not assume New just because nothing else is said.
- quantity_available + quantity_unit: how many are offered and in what unit (units, cases, pallets, kg, ...).
- unit_price: a plain number (no symbols or thousand separators). Watch for European formats ("1.234,50" = 1234.50).
  Price tiers for the same product stay ONE row: unit_price = the price for the smallest order tier, other tiers in notes.
  "Call for price" / "POA" means unit_price null (note it in notes). currency: ISO 4217 code (USD, EUR, GBP...),
  inferred from symbols like $, €, £ when unambiguous.
- price_basis: what the price covers, e.g. "per unit", "per case of 12", "per kg", "per pallet".
- ship_from: location and/or shipping terms as written, e.g. "FOB Chicago", "EXW Rotterdam".
- valid_until: ISO date YYYY-MM-DD. Resolve relative dates ("end of this week") against the email date.
- notes: other useful terms for that item: MOQ, lead time, tiered prices, packaging. Keep it short. Null if none.
- source_attachment: the filename the item came from, or null if it came from the email body.
- confidence: 0-1, how sure you are this row is complete and correct (lower it for blurry images,
  ambiguous columns or values you had to interpret).
- Skip items that are explicitly marked sold out / unavailable.
- supplier_name: the company making the offer (from signature, letterhead or domain)."""


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost(self) -> float:
        return cost_usd(self.model, self.input_tokens, self.output_tokens)


def _header(e: Email) -> str:
    date = e.date.isoformat() if e.date else "unknown"
    names = ", ".join(a.filename for a in e.attachments) or "none"
    return (
        f"From: {e.from_name} <{e.from_addr}>\n"
        + (f"Reply-To: {e.reply_name} <{e.reply_addr}>\n" if e.reply_addr else "")
        + f"Date: {date}\nSubject: {e.subject}\n"
        f"Attachments: {names}\n\n--- body ---\n{e.body[:20000]}"
    )


def _json_text(resp) -> dict:
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model refused: {resp.stop_details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("output truncated at max_tokens")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def classify(e: Email) -> tuple[dict, Usage]:
    previews = "\n\n".join(f"<attachment {a.filename}>\n{att_mod.preview(a)}" for a in e.attachments)
    resp = client.messages.create(
        model=settings.classify_model,
        max_tokens=2048,
        system=CLASSIFY_SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
        messages=[{"role": "user", "content": _header(e) + ("\n\n" + previews if previews else "")}],
    )
    u = Usage(settings.classify_model, resp.usage.input_tokens, resp.usage.output_tokens)
    return _json_text(resp), u


def extract(e: Email) -> tuple[dict, Usage]:
    content: list[dict] = []
    for a in e.attachments:
        content.extend(att_mod.to_blocks(a))
    content.append({"type": "text", "text": _header(e)})
    content.append({"type": "text", "text": "Extract every offered item from this email and its attachments."})

    with client.messages.stream(
        model=settings.extract_model,
        max_tokens=64000,
        system=EXTRACT_SYSTEM,
        output_config={"effort": settings.extract_effort, "format": {"type": "json_schema", "schema": EXTRACT_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        resp = stream.get_final_message()
    u = Usage(settings.extract_model, resp.usage.input_tokens, resp.usage.output_tokens)
    return _json_text(resp), u
