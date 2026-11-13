# Project 6: Prepaid Expense Identification & Amortization

Reads a vendor invoice (PDF or photo), decides whether it is a genuine prepayment or an ordinary
expense, builds the monthly amortization schedule and journal entries, and exports a month-end
Excel workbook an accountant can tie to the general ledger. Anything the checks cannot vouch for
goes to a **Needs Review** list and is never booked.

**Status:** built, tested, and deployed as a web demo on AWS ECS Fargate (same cluster and pattern as
Projects 1 to 5). The full story, including the mistakes, is in [Notes.md](Notes.md).

## Results at a glance

| Test | Result |
|---|---|
| Untouched fresh set, PDFs (48 made-up invoices, written before any model saw them, run once) | Vendor, date and amount right on 48/48. Booked correctly 48/48. 0 flagged, 0 silent errors. |
| Same set, photo versions (2 reads each) | Core fields right on 42/48. 7 flagged for review (all real misreads). **1 wrong and not flagged** (a date 3 days off, no effect on amount or schedule). |
| Real invoices (5 personal PDF bills, run once) | All 5 booking decisions right. The AI's own label was wrong on 3 of 5; a code rule ($500 threshold) corrected them. |
| Unit tests | 78 passing, offline, no API key needed. |

**Read these with the caveats.** Each test set has 48 files or fewer, so one error moves a rate by about 2
points. Earlier sets guided fixes, so they are tuning sets, not proof. Only the 48-record fresh set is an
untouched result. Real data is 5 PDF bills only; **real photos have not been tested.** The blurry-photo
rule was added after the fair test and has not been re-measured.

## How it works

The AI makes one judgment: what is this item, and what service dates does the document state. Everything
else is plain, tested code:
- Schedules use exact decimal money (daily or monthly-equal method). Journal entries balance.
- Anything under **$500** is expensed (a capitalization threshold in code).
- The prepayment type comes from the dates, not from the AI's label.
- When a document gives only a start date and a term, **code** works out the end date.
- When a document gives an insurance-style "expiration date", **code** subtracts the day.

**Checks that send an invoice to review instead of the ledger:** subtotal + tax must equal the total;
due date and invoice year must be plausible; "see notes" text with no notes captured; repeated reads that
disagree; missing total or date; an "ordinary expense" that states a service period still running; a service
end before its start; and **any image under 1500 pixels on the long side** ("To be reviewed by user"). PDFs
are exempt from the image rule.

**Honest limit:** these checks cannot catch a wrong value that looks believable and is read the same way
every time. Examples: the 3-day date error, and an amount read as $1,150 instead of $3,150 on both reads
(caught only by luck). Also, the installed Anthropic SDK (2.8.0) has no `temperature` option, so runs are
not at temperature 0 and can differ slightly. A reply cache makes a saved run repeatable.

## Layout
```
src/
  config.py            model, accounts, thresholds, default prompt version (v6)
  extract_invoice.py   vision extraction (PDF or photo sent straight to the model)
  identify.py          prompt versions v1 to v6, classification + coverage dates, end-date helpers
  schedule.py          deterministic Decimal schedules, end date from a term, prepayment type
  journal.py           balanced capitalization and amortization entries
  document_checks.py   the review checks above
  pipeline.py          record -> identify -> validate -> schedule -> entries
  worksheet.py         Excel workbook (Read Me, Register, Schedule, Recon, Journal Entries, Needs Review)
  llm.py               one place for model calls: cache, call cap, usage tally
  process_folder.py    run a folder of real bills and print a plain table
  service.py           web demo (FastAPI)
  evaluate.py, evaluate_extraction.py, show_flagged.py, show_failures.py, preflight.py, version.py
  render_invoices.py, generate_*.py   made-up invoice records and renderer (watermarked SAMPLE)
static/index.html      the demo page
data/                  demo_samples.json and the made-up record sets
deploy/                deploy.bat, status.bat, ip.bat, start.bat, stop.bat, task-definition.json
tests/                 test_core.py, conftest.py
Dockerfile, requirements.txt, requirements-service.txt
```

## Run it (Windows cmd, from the project root)
```
pip install -r requirements.txt
python -m pytest -q                       # 78 pass, no key needed
```
**Your own bills (needs the API key in your own terminal):**
```
python -m src.process_folder actual_invoices --dry-run          # lists files, free
set P6_MAX_LIVE_CALLS=12
python -m src.process_folder actual_invoices --runs 1 --period 2026-11
```
It prints a plain table and writes a worksheet. The results JSON is private; do not share it.

**Web demo on your computer:** `python -m uvicorn src.service:app --port 8000`, then open http://localhost:8000.
- Five saved sample bills are free. They go through the real checks, schedules and entries; the AI step uses
  a saved answer key and is labelled "sample".
- Uploads need `ANTHROPIC_API_KEY`. Limits: 5 per visitor per hour, 50 per day, 8 MB
  (`P6_DEMO_PER_IP_HOUR`, `P6_DEMO_PER_DAY`, `P6_MAX_UPLOAD_MB`). Limits are in memory and reset on restart.
- A failed check or a blurry image shows an amber "To be reviewed by user" box and books nothing.

**Evaluation on the made-up sets** (spends API calls, so read the cost safeguards first):
```
python -m src.preflight --manifest <manifest> --kind photo --runs 2
python -m src.evaluate_extraction --manifest <manifest> --name <name> --kind <pdf|photo> --runs <n>
python -m src.show_flagged results/<name>_extraction.json                 # free
python -m src.show_failures results/<name>_extraction.json --manifest <manifest>   # free
```

## Cost safeguards
1. Tests must pass first.
2. `preflight` shows the code version, SDK, prompt and the worst-case number of calls before anything is spent.
3. `set P6_MAX_LIVE_CALLS=<n>` caps live calls. A run stops cleanly and finished replies stay cached.
4. Every run prints a usage line (live calls, free cache hits, tokens) and a code version.
5. A leftover `P6_PROMPT_VERSION` setting overrides the default prompt. Clear it with `set P6_PROMPT_VERSION=`.
6. Reference: the 48-photo fair run at 2 reads used 139 live calls (about 216k input and 18k output tokens).

## Prompt versions
v1 first prompt; v2 "paid before the service" rule; v3 code computes end dates from a term; v4 partly-elapsed
rule; v5 asked the model to subtract a day for expiration dates (failed: wrong year on a real bill, caught by
the end-before-start check); **v6 (default)** the model copies the expiration date and sets a flag, code
subtracts the day. v6 was checked on one real bill and unit tests, not on a fresh set. A new prompt always
gets a new version name; older ones stay in the code.

## Deployment (AWS ECS Fargate)
Cluster `ts-forecast-cluster`, service `prepaid-expense-service`. The API key comes from AWS Secrets Manager,
never the image; the reply cache is off in the container so uploaded bills are not written to disk.
Create the log group once: `aws logs create-log-group --log-group-name /ecs/prepaid-expense-service --region us-east-1`.
```
deploy\deploy.bat     build, push, register, update (turns the service on)
deploy\status.bat     running or stopped (stopped = not billing)
deploy\ip.bat         prints the public address (wait until runningCount is 1 first)
deploy\start.bat / deploy\stop.bat
```
The public IP changes on every start (no load balancer). Same limit as Projects 1 to 5. Pin:
`anthropic==2.8.0`, the version everything was tested on.

## Not done
Real-photo testing, a stable address (load balancer or domain), splitting a partly-elapsed term into the
elapsed and still-prepaid parts in code (today it is flagged), and a second amount read for blurry photos.



