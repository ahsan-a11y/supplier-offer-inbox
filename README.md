# Supplier Offer Inbox

Reads a shared purchasing mailbox, decides which emails are supplier offers, and pulls every
offered item (from the body, PDFs, photos, scans and spreadsheets) into a SQLite table with a
link back to the source email and attachment.

```
Gmail (IMAP, read-only) ──► parse MIME ──► classify ──► extract ──► normalize ──► SQLite ──► CSV
                                            Haiku 5.5    Sonnet 5.5   (Python)     emails log
                                            text only    PDFs/images               offer_items
                                                         read natively
```

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env    # then fill in the three values below
```

| Variable | What |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `IMAP_USER` | Gmail address |
| `IMAP_PASSWORD` | Gmail **app password** (needs 2-Step Verification: Google Account → Security → App passwords) |

## Usage

```bash
uv run python evalset/build.py        # (re)generate the 18 test emails + labels
uv run offer-inbox seed               # put them into the Gmail inbox (IMAP APPEND)
uv run offer-inbox poll               # poll every 2 min; --once for a single pass
uv run offer-inbox send-demo          # email a fresh offer (PDF) + a non-offer to the inbox
uv run offer-inbox show               # recent emails + extracted rows (--review: flagged rows only)
uv run offer-inbox export             # data/offer_items.csv
uv run offer-inbox process some.eml   # run one local .eml file through the pipeline
uv run offer-inbox eval               # score against the labelled eval set -> eval_runs/
```

**Why `seed` uses IMAP APPEND instead of sending:** Gmail's SMTP rewrites the `From` header to
your own address, so every test offer would look like it came from you and `supplier_email`
would be meaningless. APPEND puts the exact message (fake supplier `From`, attachments,
`Message-ID`) into the inbox. For the demo, `send-demo` sends real emails through Gmail SMTP, so
those show your own address as `supplier_email`.

## Architecture

| Module | Job |
|---|---|
| `mailbox.py` | IMAP over SSL. Fetches messages with UID > last seen, using `BODY.PEEK` so read/unread state is untouched. Never moves or deletes mail. |
| `emails.py` | MIME → `Email` (sender, subject, date, body, attachments). Prefers the HTML part (keeps tables) and flattens it to text. |
| `attachments.py` | PDFs and images go to Claude as native document/image blocks. XLSX/CSV are converted to CSV text locally (exact, cheaper than vision). Large photos are downscaled and EXIF-rotated. |
| `llm.py` | Two calls, both with JSON-schema structured output: **classify** (Haiku 5.5, low effort, sees body + attachment names + spreadsheet previews but no PDFs/images) and **extract** (Sonnet 5.5, sees everything). |
| `pipeline.py` | Idempotent per-email processing, normalization (ISO currency, ISO dates, numbers), review flag, error capture and retries. |
| `store.py` | SQLite: `emails` (processing log for every email, including non-offers), `offer_items` (one row per item), `state` (last IMAP UID). CSV export. |
| `evaluate.py` | Runs the model steps on the eval set and scores them. |

**Two-stage design.** Most inbox mail is not an offer. Classifying on cheap text first means
non-offers cost a fraction of a cent and never send PDFs/images to the bigger model. The risk is
an offer whose only signal is inside a PDF; the classifier still sees the attachment filename,
type and any spreadsheet preview, and the prompt tells it so. The eval measures this.

**Duplicates and retries.** `Message-ID` is the primary key, so re-polling never reprocesses.
A content hash (sender + subject + body + attachment bytes) catches the same offer re-sent with a
new Message-ID; it is logged as `duplicate`. Failures are stored as `error` with the message and
retried on later polls up to `MAX_ATTEMPTS`. Reprocessing an email replaces its rows, so a retry
never doubles items.

**Starting point.** On the first run the poller starts at the newest message, so mail already in
the inbox is never processed: no cost, and old private mail is never sent to the model. `seed`
sets that starting point before appending, so the poller picks up exactly the seeded emails.
If Gmail's `UIDVALIDITY` changes (the folder was renumbered), the cursor restarts at the newest
message and logs a warning.

### Output schema

All fields from the brief, plus:

| Added field | Why |
|---|---|
| `source_link` | Gmail search link (`rfc822msgid:`) that opens the exact source email |
| `attachment_path` | local copy of the attachment the row came from, so a reviewer can open it without the mailbox |
| `needs_review` | 1 when confidence < `REVIEW_THRESHOLD` (0.8) or the row has no price/product name |

`category` is constrained to a fixed list (Furniture, Electronics, …) so it can be filtered on.
`condition` is constrained to New / Refurbished / Used / blank. Unstated values are left blank;
the prompt forbids guessing, and the eval counts a guessed value where the label is blank as wrong.

## Eval results

20 hand-labelled emails (14 offers with 100 items, 6 non-offers), in `evalset/`. Full reports
per run are in `eval_runs/`; the scoring rules are at the top of `src/offer_inbox/evaluate.py`.

| | Before eval-driven fixes | After | After (repeat) |
|---|---|---|---|
| Classifier accuracy | 95% (19/20) | **100%** | 100% |
| Item recall / precision | 95% / 99% | **100% / 100%** | 100% / 100% |
| Field accuracy, matched rows (16 fields) | 99.7% | **100%** | 100% |
| Field accuracy end to end (missed rows = wrong) | 94.7% | **100%** | 100% |
| Notes contain key facts (MOQ, tiers…) | – | 100% | 100% |

**What the eval changed:** the first version of the classifier skipped an offer whose only
content was a PDF (the body said just "Please see attached"), losing all 5 items. The classifier
now reads the PDF's text layer locally, and it says "offer" when it can't read an attachment.
Extraction also stopped splitting price tiers into separate rows and stopped assuming "New". The
full story is in [WRITEUP.md](WRITEUP.md).

These are fake emails I wrote, so 100% shows the formats are handled, not that real mail would
score 100%. WRITEUP.md covers how the set would grow from real mistakes.

### Cost per email

| | Cost | Time |
|---|---|---|
| Non-offer (classifier only) | ~$0.0001 | ~2 s |
| Offer email, average | ~$0.019 | ~9 s |
| 36-item PDF | $0.077 | |
| Whole eval run (20 emails) | $0.26 | |
| **500 emails/day at 40% offers** | **~$4/day (~$115/month)**, about half with the Batch API | |

Prices used: Haiku 5.5 $0.10/$0.50 and Sonnet 5.5 $2/$10 per million input/output tokens.

## How I used AI coding assistants

Built with Claude Code. I set the scope and design (two-stage pipeline, IMAP APPEND seeding,
eval rules), and Claude Code wrote most of the code and the eval-set generator, which I then
reviewed, ran and corrected. The eval labels come from the same spec that generates the emails,
and I checked each against the rendered email/attachment.
