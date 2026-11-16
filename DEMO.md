# Demo script (about 7 minutes)

**Before recording**
- Open Terminal and run `cd ~/workspace/supplier-offer-inbox`
- Make the Terminal window wide (maximize it, or press Cmd and minus until the tables fit)
- Open Gmail in the browser
- You can run `send-demo` as many times as you like: each send gets a new reference number,
  so it is never skipped as a duplicate

---

## 1. Intro (30 s)
*Show README.md on GitHub, scrolled to the diagram.*

> "This is my Supplier Offer Inbox. A distributor gets hundreds of supplier emails a day. This system
> reads the inbox, decides which emails are supplier offers, and pulls every offered product (from
> the email text, PDFs, photos and spreadsheets) into a database, with a link back to the email."

## 2. How it works (1 min)
*Stay on the diagram.*

> "Each new email goes through two AI steps. First a small, cheap model (Claude Haiku) decides
> whether it is an offer at all. Most emails aren't, so they stop there for about a hundredth of
> a cent. Offers go to a stronger model (Claude Sonnet), which reads the attachments and returns
> one row per product, and leaves a field blank rather than guessing. Then plain code cleans up
> currencies and dates, flags uncertain rows for a person to check, and saves everything to SQLite."

## 3. What's already in it (45 s)
```
uv run offer-inbox show
```
> "These are the 20 test emails I made: 14 offers in different formats (a PDF, a phone photo, a
> scan, a spreadsheet, plain text, Spanish) and 6 that aren't offers, like an order confirmation
> and an invoice. All 100 products were extracted."

## 4. Send a fresh email (1 min)
```
uv run offer-inbox send-demo
```
*Switch to Gmail and show the two new emails arriving. Open the Riverside one and show the PDF.*

> "I've just sent two new emails to the inbox: a price list from a supplier with a PDF attached,
> plus one extra product in the email text, and a coffee invite that isn't an offer."

## 5. Process it (1 min)
```
uv run offer-inbox poll --once
```
> "The poller fetches only new mail. It doesn't touch read/unread status and never re-processes an
> email. The coffee email is classified as not an offer and skipped. The price list goes to extraction."

## 6. Show what was stored (1.5 min)
```
uv run offer-inbox show
```
> "At the top: the new email, 5 products extracted for about 1.6 cents. Four came from the PDF and
> one from the email text, which is why the 'from file' column says email body. Notice the terms
> in the PDF header, FOB Portland and valid until 15 December, were copied onto every row."

```
uv run offer-inbox export
open data/offer_items.csv
```
*Scroll to the bottom rows. Click a `source_link` cell so Gmail opens the source email.*

> "Every row links back to the exact email it came from, and to a saved copy of the attachment."

## 7. How I measured it (1.5 min)
*Open WRITEUP.md on GitHub and scroll to the before/after table.*

> "I hand-labelled all 20 emails, 100 products and every field, and wrote a scorer. My first 18
> emails scored 100%, which told me the test was too easy, so I added two emails aimed at weak spots.
> One was an offer hidden in a PDF with just 'please see attached' in the body. The first version
> skipped it completely, because the cheap classifier couldn't see inside the PDF. I fixed it: the
> classifier now reads the PDF text, and if it can't read an attachment it sends the email on rather
> than dropping it. I also fixed tiered prices being split into two rows, and the model assuming
> 'New' when the email didn't say so. Before: 95% classification and 95% of products found.
> After: 100%, and the same on a repeat run."

## 8. Production (30 s)
*Scroll to "Running it at 500+ emails a day".*

> "The write-up covers running this at 500 emails a day: push notifications and a queue instead of
> polling, retries and duplicate handling, about 4 dollars a day in AI cost, a weekly eval refresh
> from real emails, a human review queue for flagged rows, and read-only OAuth for the mailbox."
