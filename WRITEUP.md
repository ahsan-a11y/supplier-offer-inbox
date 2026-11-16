# Supplier Offer Inbox: write-up

## How I built it

**Pipeline.** Gmail over IMAP (read-only, `BODY.PEEK`) → parse MIME → **classify** with Claude
Haiku 5.5 on text only → **extract** with Claude Sonnet 5.5, which reads PDFs and images natively →
deterministic clean-up in Python (ISO currency and dates, numbers, review flag) → SQLite, with a
Gmail link and a saved copy of the source attachment on every row. Both model calls use JSON-schema
structured output, so the response always parses and always has every field. Fields the email
doesn't state come back as `null` instead of an invented value.

**Choices I made, and what I cut.**
- *Two stages instead of one call.* Most inbox mail is not an offer. A Haiku call with no
  attachments costs about $0.0001, against about $0.019 for extraction. At 500 emails a day the
  saving is large, but it adds a risk (below), which the eval was built to measure.
- *Spreadsheets as text, PDFs and images native.* XLSX/CSV → CSV text is exact and cheap. I
  didn't add OCR or PDF parsing for extraction: Sonnet reads the photo and the noisy scan correctly,
  and a separate OCR step would be one more thing to tune.
- *Cut:* a web review UI (the `needs_review` flag plus `offer-inbox show --review` covers it),
  Gmail push notifications (polling is fine for this volume), OAuth (app password is enough for
  a demo; see security below), and splitting very long attachments into chunks (not needed at the
  sizes tested).

**The eval set.** 20 fake emails built from one spec file (`evalset/spec.py`): the same data
generates the email, its attachments and the expected rows, so labels can't drift from content. I
checked each rendered email and attachment by eye. The set covers: a digital PDF, a phone photo
(rotated, blurred, JPEG artefacts), a grayscale scan, an XLSX, a CSV, an HTML table, a 36-row PDF,
body-text offers, Spanish with European number formats, a relative date ("through Friday"), a
sold-out line that must be skipped, and 6 non-offers. Three of the non-offers are deliberately
hard: an order confirmation with a price table, an invoice PDF, and a customer asking *us* for a
quote. There are 100 labelled rows. A label can list several acceptable answers where two readings
are fair, and `null` means "must be left blank", so a guessed value counts as wrong.

Scoring: rows are matched by SKU, otherwise by the most similar product name. Then 16 fields are
compared (numbers to the cent; text ignoring case and punctuation, allowing small wording
differences for names and shipping terms). `notes` is free text, so it is scored separately:
did the key numbers (MOQ, tiers) make it in? Before trusting the scorer I checked that it rejects
wrong values (wrong price, wrong currency, a guessed date, a different product) and accepts
fair rewordings, and that the labels scored against themselves give 100%.

## What the eval showed, and what I changed

**Run 1** (first 18 emails): 100% on everything. That told me the set was too easy to say
anything about weak points. So I added two emails aimed at the parts of my design I was least sure of:

| # | Email | Why |
|---|---|---|
| 19 | Body says only "Please see attached", the offer is inside `doc_0412.pdf` | The classifier never sees PDF contents |
| 20 | Tiered prices, a "call for price" item, an item with no quantity | Tests "leave blank rather than guess" |

**Run 2** (all 20, before changes):

- **#19 was classified as "not an offer" and skipped.** All 5 items were lost, and nothing
  flagged it. The classifier's reason: *"generic 'Please see attached' note … the only attachment
  is an opaque 2 KB PDF."* This is the worst kind of failure: a missed offer is lost for good,
  while a false alarm costs about $0.02.
- #20: one product with two price tiers became **two rows**, and `condition` was filled in as
  "New" on 3 rows where the email never says so.
- One of my labels was too strict (currency on a row that has no price), so I loosened it.

**Changes:**
1. The classifier now gets the PDF's text layer (extracted locally with `pypdf`, so no model
   cost) as part of the preview.
2. The classifier prompt now fails open: if an attachment can't be read as text (an image, a
   scanned PDF) and could plausibly be a price list, it says "offer" with lower confidence.
3. Extraction prompt: price tiers stay one row (the smallest-tier price goes in `unit_price`, the
   rest in `notes`); "call for price" means a blank price; `condition` only when explicitly stated.

**Run 3** (all 20, after changes): every metric back to 100%, including the 18 emails that
passed before, so no regressions. A second, identical run gave the same scores at the same cost.

| | Run 2 (before) | Run 3 (after) |
|---|---|---|
| Classifier accuracy | 95% (19/20) | 100% (20/20) |
| Item recall | 95% (95/100) | 100% (100/100) |
| Item precision | 99% (95/96) | 100% |
| Field accuracy on matched rows | 99.7% | 100% |
| Field accuracy end to end (missed rows count as wrong) | 94.7% | 100% |
| Cost per email | $0.013 | $0.013 |

**What 100% does not mean.** The set is small and I wrote it, and the emails are cleaner than
real ones: rendered, not photographed; one language per email; no real supplier quirks. 100% here
means the pipeline handles these formats, not that it would score 100% on real mail. The next
step is the production loop below: sample real emails, label them, and grow the eval set from
the mistakes buyers correct.

## Running it at 500+ emails a day

**Ingestion.** Replace polling with Gmail push (`users.watch` → Pub/Sub) or Microsoft Graph
change notifications, with a 10-minute poll kept as a safety net. Ingestion only stores the raw
message (to S3/GCS, keyed by Message-ID) and enqueues a job. Workers pull from the queue (SQS,
Cloud Tasks), so a slow PDF never blocks the inbox, and workers scale with the backlog.

**Retries and duplicates.** Each stage is idempotent: Message-ID is the key, and re-running an email
replaces its rows. Already in this repo: a content hash catches the same offer re-sent with a new
Message-ID; failures are stored with the error and retried up to 3 times; the SDK retries 429/5xx
with backoff. In production: exponential backoff on the queue, a dead-letter queue after N
attempts with an alert, and a "same supplier + SKU + price within 7 days" check so the same offer
sent twice in a week (or forwarded by a colleague) shows once.

**Cost.** Measured: about $0.0001 per non-offer and about $0.019 per offer (the 36-row PDF costs $0.077).
At 500 emails a day with 40% offers, that is about **$4 a day / $115 a month**. Levers, in order:
the Batch API (50% off; latency of minutes is fine here), prompt caching of the fixed system
prompt, and Haiku for extraction on simple text-only offers if the eval shows it holds up
(it is one setting to try, `EXTRACT_MODEL`). Set a daily spend alert.

**Keeping accuracy up over time.** The eval runs in CI on every prompt or model change, and a
change ships only if no metric drops. Every week, sample about 30 real processed emails (stratified:
low-confidence rows, new suppliers, each attachment type), have a buyer label them, and add them to
the eval set. Every buyer correction in the review queue is logged as a label, so the set grows
from real mistakes. Track per-supplier metrics: a sudden rise in review flags from one supplier
usually means they changed their template.

**Human review.** Rows go to a review queue when confidence < 0.8, price or product name is
missing, the price is far from that supplier's history for the same SKU, or the classifier was
unsure. The reviewer sees the row next to the source page or image (the link and attachment path
are already stored) and fixes or approves it. Approved rows flow to buyers. Track how often
reviewers change each field and use that to tune the 0.8 threshold.

**New supplier formats.** The model reads formats it hasn't seen without templates, which is the
main reason to use it. Guard rails: flag every email from a first-time sender for review for its
first few emails; if one supplier's rows keep getting corrected, add a short per-supplier hint to
the prompt (e.g. "Prices on this sheet are per case of 6"), looked up by sender domain; add one
example of every new format to the eval set.

**Securing mailbox access.** Use OAuth (Gmail API / Microsoft Graph) with a read-only scope
(`gmail.readonly` or `Mail.Read` on that one shared mailbox only), not an app password. Keep
tokens in a secrets manager, never in the repo, and rotate them. Run the worker with its own
service identity and least privilege. Attachments are untrusted input: parse them in a sandboxed
worker, cap sizes and pages, and never execute macros (`openpyxl` doesn't). Email text goes to the
model as data, and the output is forced into a schema, so a malicious "ignore your instructions"
email can at worst produce bad rows, which review catches. Turn on audit logging; keep
attachments encrypted with a retention period.

## How I used AI assistants

I built this with Claude Code: I made the design calls and the eval rules, Claude Code wrote most
of the code and the test-email generator, and I reviewed, ran and corrected it. Model calls in
the product use the Anthropic API.
