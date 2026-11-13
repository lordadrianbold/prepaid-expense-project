# Project 6: Notes — the full, honest story

This is the detailed account of what was built, what was tried, what worked, what did not,
and why. It includes several mistakes that were caught and fixed using direct evidence,
not guesses.

**What the project does:** it reads a vendor invoice (PDF or photo), decides if it is a
prepayment or an ordinary expense, builds the monthly schedule and journal entries, and
writes an Excel worksheet for month-end close. Anything the checks cannot vouch for goes
to a "Needs Review" list. It is never booked.

**Where it ended up:** deployed as a web demo on AWS ECS Fargate. On the untouched fresh set the PDFs
were right 48 of 48, and the photos had 7 flagged and 1 wrong-and-unflagged. A first test on 5 real
PDF bills got all 5 booking decisions right. Real photos were not tested. See sections 1, 1b and 10.

## 1. Evaluation (synthetic invoices, four kinds of tests)

**Test 1: the decision on its own (text records).** Holdout v2 (48 records): 45 of 48
right. The three misses were one-time prepayments, like a hotel room block, that the AI
called ordinary expenses. A better prompt (v2) fixed that group on the next set (holdout
v3, 40 records): one-time misses went from 3 to 0. With two code rules added (anything
under $500 is expensed, and the prepayment type comes from the dates), the booking result
on that set was 40 of 40.

**Test 2: the whole path on rendered invoices.** A renderer turns the records into PDFs in
four layouts and into photo-style images at three quality levels (light, medium, heavy).
This tested reading, deciding and the safety checks together (section 5).

**Honest note:** holdout v2, holdout v3 and the first rendered set all guided fixes. Once a
test guides a fix, it is a "used" test, and a high score on it proves little.

**Test 3: one fair test (holdout v4).** 48 brand-new records, with new vendors and new
wording, written before the AI saw any of them and run once with prompt v4:

| | PDFs | Photos (2 reads each) |
|---|---|---|
| Vendor, date and amount all right | 48 of 48 | 42 of 48 |
| Booked correctly | 48 of 48 | not counted (some amounts unreadable) |
| Sent to review | 0 | 7 |
| Wrong and NOT flagged | 0 | 1 |

- All 3 partly-elapsed invoices and all 4 "start date plus term" invoices were right.
- The AI called 3 small memberships (under $500) prepayments. The $500 rule fixed them.
- All 7 flagged photos were real misreads: two wrong subtotals found by the addition check,
  four dates or vendors that the two reads disagreed on, and one total that could not be read.
- **The one unflagged mistake:** a date read 3 days off (same month), the same on both
  reads. The amount, type and service dates were still right, so the effect was tiny.
- **A near miss:** one heavy photo had its amount read as $1,150 instead of $3,150 on both
  reads. It was caught only because the date reads happened to disagree. A wrong amount
  that is read the same way every time is the biggest remaining risk with photos.
- Blurry photos (about 1100 pixels) caused 6 of the 8 field problems.
- Each set has only 48 files, so one mistake moves a rate by about 2 points.

## 1b. First test on real invoices (5 personal bills)

There were no work invoices to use, so 5 real personal PDF bills were run once with
`process_folder` (prompt v4, 1 read each, 10 live calls, nothing re-run).

| Bill | Decision | Right? |
|---|---|---|
| AT&T internet, $80.26 | Expense | Yes |
| Home insurance (policy 05/17/2026 to 05/17/2027), $831.17 | Amortize over 12 months | Yes |
| Claude Pro, $20.00 | Expense | Yes |
| JEA utilities, $219.98 | Expense | Yes |
| T-Mobile, $56.24 | Expense | Yes |

- Vendor, date and amount were read correctly on all 5, and all 5 booking decisions were right.
- **Honest caveat:** the AI's own label was wrong on 3 of 5 (it called AT&T a one-time
  prepayment, and Claude Pro and T-Mobile multi-period prepayments). All three were under
  $500, so the $500 rule in code expensed them correctly. On a bill over $500 that same
  mistake could have been booked, so the code rule is doing real work.
- **Re-run with prompt v6 (after the fix below):** the insurance bill now shows a service period
  of 2026-05-17 to 2027-05-16 (365 days) and is amortized. The other four decisions did not change.
  This is one real bill, so it shows the fix works here, not that it works on every wording.
- All 5 were clean PDFs. This says nothing about photos, and 5 bills is a very small test.
- My first guess for the insurance amount ($1,500) was wrong. I checked the PDF text: the
  full-payment amount is $831.17, and the tool had it right.

## 2. What the stress testing found

Photos showed failure patterns that the text records never did:
- **Year misreads:** a date read as 2007 instead of 2027, and another as 2025 instead of
  2026. The same wrong value came back on repeated reads.
- **Skipped notes:** on some layouts the service period is in a Notes box. One photo lost
  it and kept only "Charges per agreement, see notes below".
- **Consistent wrong amounts:** one photo read $1,150 instead of $3,150 on every read.
- **Wrong end dates:** for "24-month term beginning September 1, 2027" the AI gave an end
  date before the start. It is not reliable at date arithmetic.
- **A broken reply:** one reply was almost-valid JSON and could not be read.
- **The AI contradicting itself:** for a one-year term that began January 1 and was invoiced
  March 15, the AI said "ordinary expense" every time but still gave a service period that
  ran to December 31.

**The key lesson:** reading a photo twice and getting the same answer does not mean the
answer is right.

## 3. The fixes: checks in code, not more prompting

| Failure | What now catches it |
|---|---|
| Year misread | An invoice date more than about a year ahead or three years back; a due date that does not fit the invoice date |
| Skipped notes | "See notes" in the description but no notes read |
| Wrong subtotal or tax | Subtotal plus tax must equal the total |
| Unstable reading | Two or more reads that disagree on a field |
| Wrong end date | The code works out the end date from the start date and the term in months |
| Broken reply | A recovery step; if it cannot recover, the invoice goes to review |
| AI contradicts itself | "Ordinary expense" plus a service period still running goes to review |

The last check does not change the AI's answer. It only sends the invoice to a person.

**Honest limit:** these checks cannot catch a wrong value that looks believable. That is
exactly what the unflagged 3-day date error and the $1,150 near miss were.

## 4. How it was built, step by step

### Design: one job for the AI
The AI reads the invoice, decides the type and reports the service dates. Everything else
is plain code with tests: the schedule (exact decimal money), the journal entries, the $500
rule, the prepayment type, and the checks.

### The pieces
Extraction, identification, schedule, journal entries, and an Excel worksheet with six
tabs: Read Me, Register, Schedule, Recon, Journal Entries and Needs Review.

### Small bugs caught early
- **A crash in the prompt builder.** Curly braces in the example JSON broke Python's string
  formatting. Fixed with simple text markers.
- **A wrong balance on the Recon tab.** A $36,000 prepayment appeared in June, before its
  invoice date. Fixed with an invoice date column and zero before it.
- **Weak tests.** Two tests could never fail, and "&" versus "and" in vendor names broke a
  match. The tests were made stricter, and "&" is treated as "and".
- **A demo overwrote the real worksheet.** Demo output now gets a `_DEMO` name.

### The renderer
There were no real invoices to test with, so the renderer made them from the records, with
made-up vendor names.

## 5. The tuning rounds on the rendered set (96 files)

### First run
A first attempt failed on every file (see section 7, the temperature mistake). The first
valid run came after that:
- PDFs: vendor, date and amount right on 48 of 48. Booked right on 46 of 48.
- Photos (3 reads): 43 of 48 dates right. Two mistakes were NOT flagged.

### The two unflagged mistakes
- **H2-040:** a date read as 2028 instead of 2026, the same on every read.
- **H2-030:** an invoice dated March 15 for a service year that began January 1, called an
  ordinary expense every time.

New checks (future-date and open-period, from the table above) were added. After that,
nothing was unflagged on either set.

### What the "false alarms" really were
The summary called some flags "false alarms" when the vendor, date and amount were right.
But many were real: a wrong subtotal, a wrong due date, reads that disagreed. The summary
scores only three fields, so it could not see them. It was relabelled "flags on correct
core fields", and a new report, `show_flagged`, lists the reason for every flag.

### The end-date and broken-reply fixes
The end-date problem led to prompt v3 (the AI gives the start and the number of months;
code calculates the end). The broken reply led to the recovery step. The test scoring now
counts "end before start" as wrong. After these, the PDFs reached 47 of 48 booked correctly
with 0 unflagged. The last miss was H2-030, still flagged for review.

## 6. Prompt versions

- **v1:** the first prompt.
- **v2:** a clear rule that "paid before the service" is what makes a prepayment, even if
  the service lasts only a few days.
- **v3:** stopped asking the AI to calculate end dates.
- **v4:** added a rule for partly-elapsed terms. The AI must report the full stated dates
  and not call the invoice an ordinary expense. "Already rendered" applies only when the
  whole period has ended.

- **v5 (replaced by v6):** added a "last covered day" rule. It was found on a real bill: the home insurance
  policy said "Policy Expiration Date 05/17/2027", and the tool counted that day as covered,
  giving a 366-day schedule instead of 365 days (it touches 13 calendar months either way,
  because the policy starts mid-month). The total was right,
  but months were off by 10 to 20 cents, and the last month by about $2. v5 tells the AI that
  an expiration date means the day before is the last covered day, while "through" or "ending"
  dates are used as written. None of the synthetic test sets contain "expires" wording, so
  they could not have caught this. v5 was checked by unit tests and one re-read of the real
  bill, not by a new fresh set. I had also wrongly said the first schedule was right, before
  checking the AI's end date.

- **v5 failed on the real bill, and the safety check caught it.** The AI was asked to subtract
  a day itself. It gave an end date of 2026-05-16 (wrong year) for a start of 2026-05-17. The
  "end before start" check sent the bill to review and nothing was booked. This is the same
  lesson as v3: the AI is not reliable at date arithmetic.
- **v6:** the AI copies the expiration date exactly as written and sets a flag
  (`end_is_expiration`). Code subtracts the day. Same design as v3 (code does the arithmetic).
  Checked by unit tests and by re-reading the one real bill. Not validated on a fresh set.

A new prompt always gets a new version name. The old ones stay in the code.

## 7. Design mistakes, caught and fixed

- **The temperature mistake.** I added a "temperature 0" option so results would repeat,
  without checking that the installed tool accepts it. It did not. All 96 files failed
  with the same error, and the summary looked like "every error was caught" because
  everything was flagged. That was meaningless. Errors are now shown, and the option is
  skipped if rejected.
- **A wrong claim from me.** I said upgrading the tool would fix it. It did the opposite:
  the current Anthropic tool (2.8.0) has no temperature option at all (also no `top_p` or
  `top_k`). Results can change a little between runs. A cache now makes a saved run
  repeatable.
- **Mislabelled catches.** Covered in section 5.
- **Tuning on the test set.** Every fix used up the set that found it. That is why the fair
  test (holdout v4) was needed.
- **A code stamp that was too sensitive.** It changed with spaces and line endings, so
  files looked out of date when they were not. It now ignores spaces and line breaks.
  Your copy matched mine (`6861c356`).

## 8. Cost and process fixes

A lot of money and time went on repeat runs, files that were not up to date, and no safety
limit. What was added:
- A cache: the same request is answered from disk for free.
- A usage line at the end of every run: live calls, free cache hits, tokens.
- `preflight`: shows the code version, tool version, prompt, missing files and the worst-case
  number of calls before anything is spent.
- A call cap: `set P6_MAX_LIVE_CALLS=150` stops a run cleanly. Finished replies stay cached.
- A rule that tests must pass before any run.

The 48-photo fair run used 139 live calls, about 216,000 input tokens and 18,000 output
tokens.

## 9. Process lessons worth stating honestly

- Reading twice and getting the same answer is not proof.
- Math checks catch what repeat reads cannot.
- Keep a test set untouched until the end. Once it guides a fix, it is used.
- Check that a tool accepts an option before using it.
- Test with a few files first and set a call limit.
- Verify before claiming. Separate what was run from what was only assumed.
- The layers worked as a team, and none was enough alone: the prompt fixed the common cases,
  code rules fixed what the AI is bad at, and the checks caught most photo mistakes.
- An API key was pasted into a chat once. It should be revoked and set only in the user's
  own terminal.

## 10. Deployment (AWS ECS Fargate)

Deployed to the same cluster, roles and network as Projects 1 to 5. A web demo (FastAPI) runs in
a container: five free sample bills, rate-limited uploads (5 per visitor per hour, 50 per day,
8 MB), and a "To be reviewed by user" box for anything the checks cannot vouch for or any image
under 1500 pixels. The API key lives in AWS Secrets Manager (the Project 5 secret), not in the
image. The reply cache is off in the container, so uploaded bills are never saved to disk.

**Verified:** the service reached one running task and a live PDF upload through the public
address returned the right result (the annual insurance bill: AMORTIZE, 12 monthly rows, $31,800
spread over 366 days, ending at $0.00). The same record gave the same schedule as the free sample.

**Problems hit, in order (all were caused by not checking the Project 5 notes first):**
1. **Log group permission.** Every task start failed (43 tries) with `logs:CreateLogGroup` denied.
   The task role could create the Project 5 log group but not the new one. Fix: create the log
   group by hand with one command, and leave the task definition to use it.
2. **A wrong setting I wrote.** I set `awslogs-create-group` to `false`. AWS only accepts `true`
   or leaving the option out, so the whole task definition was rejected. Fix: removed the option.
3. **Library version mismatch.** The container installed Anthropic 1.17.0, because I copied the
   `<2` pin from Project 5. Everything here had been tested on 2.8.0. Caught by checking before the
   task ran. Fix: both requirements files pinned to `anthropic==2.8.0`.
4. **Redeploy left the count at 0.** After a stop, `deploy.bat` did not switch the service back on.
   Fixed by setting the desired count in the update.
5. **Two tasks at once after a redeploy.** Normal for a rolling update, but the first address
   printed can belong to the old task. Wait until `runningCount` is 1, then get the address.
6. **The public IP changes** on every start or redeploy (no load balancer). Same limit as
   Projects 1 to 5.

**Lesson:** read the previous project's deployment notes before deploying, and walk the list item
by item. Items 1 and 3 were both on it in spirit.

**Running it (cmd):** `deploy\deploy.bat` to deploy, `deploy\status.bat`, `deploy\ip.bat`,
`deploy\start.bat`, `deploy\stop.bat`. Stop it when you are not demoing, to stop the compute cost.

## 11. What's still open and recommendations

- **Test on real photos and bills over $500.** Skipped for now. Only 5 real PDFs have been tested.
  A short real-photo run (about 15 calls) would be the most useful next check.
- **Folder command: done.** `python -m src.process_folder <folder>` reads a folder of bills.
- **Blurry-photo rule: done.** Any image under 1500 pixels on the long side now always goes to
  review with the message "To be reviewed by user". PDFs are not affected. The cost is more
  items for a person to check; the benefit is that no blurry-photo misread is booked silently.
  The web demo will show this message to the user. Not yet re-run on photos (no new spend).
- **Handle partly-elapsed terms fully in code.** Today they are flagged. The next step is to
  split the amount into the part already expensed and the part still prepaid.
- **Read the amount a second time, only on blurry photos.** A consistent amount misread is
  the biggest remaining risk.
- **Find the cause of the one broken reply.** My guess (a stray quote mark) was never
  proven.
- **Use public invoice sets for variety.** FATURA (10,000 generated invoices, 50 templates,
  CC BY 4.0) and DocILE (6,680 annotated real documents; its license was not stated on the
  paper page) were identified as candidates.
- **Stable address.** The demo is deployed, but its IP changes on each start. A load balancer or a
  domain would fix that.
- **README.md: done.** It now has the final results, the cost safeguards and the deploy steps.
- **Track the review rate on real invoices.** It turns confidence into a real number.



