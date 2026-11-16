"""Scores the pipeline against the hand-labelled eval set.

Steps per email: run classify (+ extract if it says "offer"), match predicted rows to
labelled rows, then compare field by field.

Matching: same SKU wins; otherwise the most similar product name (>= 0.55). Unmatched
labelled rows are misses, unmatched predicted rows are extras.

Field rules (see `field_correct`):
  - numbers must match to the cent; strings are compared case/punctuation-insensitively
  - product_name / supplier_name / ship_from / price_basis allow small wording differences
  - a label may list several acceptable answers; null means "should be left blank",
    so a value where the label is null counts as wrong (a guess)
  - `notes` is free text, so it is scored separately: did the key numbers make it in?
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .emails import parse_email
from .llm import FIELDS
from .pipeline import run_models

SCORED_FIELDS = [f for f in FIELDS if f != "notes"] + ["source_attachment"]

UNIT_SYNONYMS = {
    "unit": "units", "units": "units", "pcs": "units", "pc": "units", "pieces": "units", "piece": "units",
    "each": "units", "ea": "units", "unidades": "units",
    "case": "cases", "cases": "cases", "cs": "cases", "cartons": "cases", "carton": "cases",
    "pallet": "pallets", "pallets": "pallets", "kg": "kg", "kgs": "kg", "kilograms": "kg",
    "set": "sets", "sets": "sets", "pack": "packs", "packs": "packs", "bag": "bags", "bags": "bags", "bolsas": "bags", "box": "boxes", "boxes": "boxes",
}
COMPANY_SUFFIX = re.compile(r"\b(co|inc|ltd|llc|gmbh|bv|b v|sa|s a|corp|company)\b")


def norm(s) -> str:
    s = str(s).casefold().replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def _one_correct(f: str, exp, got) -> bool:
    if exp is None:
        return got in (None, "")
    if got in (None, ""):
        return False
    if f in ("unit_price", "quantity_available"):
        try:
            return abs(float(exp) - float(got)) < 0.005
        except (TypeError, ValueError):
            return False
    if f == "quantity_unit":
        return UNIT_SYNONYMS.get(norm(got), norm(got)) == UNIT_SYNONYMS.get(norm(exp), norm(exp))
    if f == "supplier_name":
        a, b = COMPANY_SUFFIX.sub("", norm(exp)).strip(), COMPANY_SUFFIX.sub("", norm(got)).strip()
        return a == b or similar(a, b) >= 0.85
    if f == "product_name":
        return similar(exp, got) >= 0.8 or norm(exp) in norm(got)
    if f in ("ship_from", "price_basis"):
        a, b = norm(exp), norm(got)
        a = a.replace("ex works", "exw").replace("each", "unit").replace("piece", "unit")
        b = b.replace("ex works", "exw").replace("each", "unit").replace("piece", "unit")
        return a == b or a in b or b in a
    return norm(exp) == norm(got)


def field_correct(f: str, exp, got) -> bool:
    options = exp if isinstance(exp, list) else [exp]
    return any(_one_correct(f, o, got) for o in options)


def notes_ok(exp: str | None, got: str | None) -> bool | None:
    """Loose check: every number in the expected note appears in the predicted note."""
    if not exp:
        return None
    nums = re.findall(r"\d+", exp)
    return bool(got) and all(n in re.findall(r"\d+", got) for n in nums)


def _first(v):
    return v[0] if isinstance(v, list) else v


def match(expected: list[dict], predicted: list[dict]) -> list[tuple[dict | None, dict | None]]:
    pairs, used = [], set()
    for exp in expected:
        best, best_score = None, 0.0
        for i, got in enumerate(predicted):
            if i in used:
                continue
            exp_skus = [s for s in (exp["sku"] if isinstance(exp["sku"], list) else [exp["sku"]]) if s]
            if got.get("sku") and any(norm(s) == norm(got["sku"]) for s in exp_skus):
                best, best_score = i, 2.0
                break
            names = exp["product_name"] if isinstance(exp["product_name"], list) else [exp["product_name"]]
            score = max(similar(n, got.get("product_name") or "") for n in names)
            if score > best_score:
                best, best_score = i, score
        if best is not None and best_score >= 0.55:
            used.add(best)
            pairs.append((exp, predicted[best]))
        else:
            pairs.append((exp, None))
    pairs += [(None, got) for i, got in enumerate(predicted) if i not in used]
    return pairs


@dataclass
class EmailScore:
    id: str
    kind: str
    expected_offer: bool
    predicted_offer: bool | None = None
    classify_reason: str = ""
    n_expected: int = 0
    n_predicted: int = 0
    n_matched: int = 0
    field_hits: dict = field(default_factory=dict)  # field -> [correct, total]
    notes_hits: list = field(default_factory=lambda: [0, 0])
    errors: list = field(default_factory=list)       # human-readable field mistakes
    cost_usd: float = 0.0
    seconds: float = 0.0
    failure: str | None = None


def score_email(eml: Path, label: dict) -> EmailScore:
    s = EmailScore(label["id"], label["kind"], label["is_offer"], n_expected=len(label["items"]))
    t0 = time.time()
    try:
        res = run_models(parse_email(eml.read_bytes()))
    except Exception as exc:
        s.failure = f"{type(exc).__name__}: {exc}"
        return s
    s.seconds = round(time.time() - t0, 1)
    s.cost_usd = res.cost_usd
    s.predicted_offer = res.is_offer
    s.classify_reason = res.classify_reason
    s.n_predicted = len(res.items)
    for exp, got in match(label["items"], res.items):
        if exp is None:
            s.errors.append(f"extra row: {got.get('product_name')!r}")
            continue
        if got is None:
            s.errors.append(f"missed row: {_first(exp['product_name'])!r}")
            continue
        s.n_matched += 1
        for f in SCORED_FIELDS:
            ok = field_correct(f, exp.get(f), got.get(f))
            hit = s.field_hits.setdefault(f, [0, 0])
            hit[0] += ok
            hit[1] += 1
            if not ok:
                s.errors.append(f"{_first(exp['product_name'])[:30]!r}.{f}: expected {exp.get(f)!r}, got {got.get(f)!r}")
        n = notes_ok(exp.get("notes"), got.get("notes"))
        if n is not None:
            s.notes_hits[0] += n
            s.notes_hits[1] += 1
    return s


def run(evalset: Path, out_dir: Path, only: list[str] | None = None, workers: int = 4) -> dict:
    labels = {p.stem: json.loads(p.read_text()) for p in sorted((evalset / "labels").glob("*.json"))}
    if only:
        labels = {k: v for k, v in labels.items() if any(o in k for o in only)}
    with ThreadPoolExecutor(workers) as pool:
        scores = list(pool.map(lambda k: score_email(evalset / "emails" / f"{k}.eml", labels[k]), labels))
    summary = summarize(scores)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (out_dir / f"{stamp}.json").write_text(json.dumps(
        {"summary": summary, "emails": [s.__dict__ for s in scores]}, indent=2, default=str))
    (out_dir / f"{stamp}.md").write_text(to_markdown(summary, scores))
    summary["report"] = str(out_dir / f"{stamp}.md")
    return summary


def summarize(scores: list[EmailScore]) -> dict:
    done = [s for s in scores if s.failure is None]
    tp = sum(s.expected_offer and s.predicted_offer for s in done)
    tn = sum(not s.expected_offer and not s.predicted_offer for s in done)
    fp = sum(not s.expected_offer and s.predicted_offer for s in done)
    fn = sum(s.expected_offer and not s.predicted_offer for s in done)
    fields: dict[str, list[int]] = {}
    for s in done:
        for f, (c, t) in s.field_hits.items():
            fields.setdefault(f, [0, 0])
            fields[f][0] += c
            fields[f][1] += t
    n_exp = sum(s.n_expected for s in done)
    n_pred = sum(s.n_predicted for s in done if s.expected_offer)
    n_match = sum(s.n_matched for s in done)
    correct = sum(c for c, _ in fields.values())
    total = sum(t for _, t in fields.values())
    notes = [sum(s.notes_hits[0] for s in done), sum(s.notes_hits[1] for s in done)]
    offers = [s for s in done if s.expected_offer]
    return {
        "emails": len(scores),
        "failures": [f"{s.id}: {s.failure}" for s in scores if s.failure],
        "classifier": {"accuracy": round((tp + tn) / max(1, len(done)), 3), "tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "items": {"expected": n_exp, "predicted": n_pred, "matched": n_match,
                  "recall": round(n_match / max(1, n_exp), 3), "precision": round(n_match / max(1, n_pred), 3)},
        "field_accuracy_on_matched": round(correct / max(1, total), 3),
        # Counts missed rows as all-fields-wrong: what a buyer actually gets.
        "field_accuracy_end_to_end": round(correct / max(1, n_exp * len(SCORED_FIELDS)), 3),
        "per_field": {f: round(c / max(1, t), 3) for f, (c, t) in sorted(fields.items())},
        "notes_key_facts": round(notes[0] / max(1, notes[1]), 3),
        "cost_usd_total": round(sum(s.cost_usd for s in done), 4),
        "cost_usd_per_email": round(sum(s.cost_usd for s in done) / max(1, len(done)), 4),
        "cost_usd_per_offer_email": round(sum(s.cost_usd for s in offers) / max(1, len(offers)), 4),
        "avg_seconds_per_email": round(sum(s.seconds for s in done) / max(1, len(done)), 1),
    }


def to_markdown(summary: dict, scores: list[EmailScore]) -> str:
    c, it = summary["classifier"], summary["items"]
    lines = [
        "# Eval report", "",
        f"- Classifier accuracy: **{c['accuracy']:.1%}** (TP {c['tp']}, TN {c['tn']}, FP {c['fp']}, FN {c['fn']})",
        f"- Item recall: **{it['recall']:.1%}** ({it['matched']}/{it['expected']}), precision {it['precision']:.1%}",
        f"- Field accuracy on matched rows: **{summary['field_accuracy_on_matched']:.1%}**",
        f"- Field accuracy end to end (missed rows count as wrong): **{summary['field_accuracy_end_to_end']:.1%}**",
        f"- Notes contain the key facts: {summary['notes_key_facts']:.1%}",
        f"- Cost: ${summary['cost_usd_total']:.4f} total, ${summary['cost_usd_per_email']:.4f}/email, "
        f"${summary['cost_usd_per_offer_email']:.4f}/offer email; {summary['avg_seconds_per_email']}s/email",
        "", "## Per field", "", "| field | accuracy |", "|---|---|",
        *[f"| {f} | {a:.1%} |" for f, a in summary["per_field"].items()],
        "", "## Per email", "", "| email | offer? exp/got | rows exp/got/matched | field acc | cost |", "|---|---|---|---|---|",
    ]
    for s in scores:
        c_ = sum(v[0] for v in s.field_hits.values())
        t_ = sum(v[1] for v in s.field_hits.values())
        acc = f"{c_ / t_:.0%}" if t_ else "-"
        got = "ERR" if s.failure else ("yes" if s.predicted_offer else "no")
        lines.append(f"| {s.id} | {'yes' if s.expected_offer else 'no'}/{got} | "
                     f"{s.n_expected}/{s.n_predicted}/{s.n_matched} | {acc} | ${s.cost_usd:.4f} |")
    lines += ["", "## Mistakes", ""]
    for s in scores:
        if s.failure:
            lines.append(f"- **{s.id}** failed: {s.failure}")
        if s.expected_offer != s.predicted_offer and not s.failure:
            lines.append(f"- **{s.id}** misclassified ({s.classify_reason})")
        for e in s.errors[:40]:
            lines.append(f"- {s.id}: {e}")
    return "\n".join(lines) + "\n"
