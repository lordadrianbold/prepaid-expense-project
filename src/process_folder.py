"""Read a folder of REAL invoices (PDF or photo) and show what the tool would do.

    python -m src.process_folder actual_invoices            (one read per file)
    python -m src.process_folder actual_invoices --dry-run  (costs nothing)

For each file it reads the invoice, decides prepayment or expense, runs the safety
checks, and prints one plain line per invoice. It also writes the month-end Excel
worksheet and a results file. There is no answer key here: YOU compare what it says
with the invoice. Everything stays on your computer; paste only the printed table
when you ask for help, not the results file (it holds the text read from the invoices).
"""
import argparse
import json
import os
from datetime import date
from pathlib import Path

from . import llm
from .config import RESULTS_DIR, get_prompt_version
from .extract_invoice import extract_invoice
from .pipeline import process_extracted
from .version import code_version

EXTS = {".pdf", ".jpg", ".jpeg", ".png"}


def _short(text, n=70):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def summarize_item(path, ext, item):
    ident = item["identification"]
    return {
        "file": path.name,
        "vendor": ext.get("vendor"),
        "invoice_date": ext.get("invoice_date"),
        "amount": ext.get("amount"),
        "ai_says": ident["predicted_classification"],
        "service_period": (f"{ident['predicted_coverage_start']} to {ident['predicted_coverage_end']}"
                           if ident.get("predicted_coverage_start") else None),
        "decision": item["treatment"],
        "why_review": item["flags"],
        "notes": item["notes"],
        "read_description": _short(ext.get("description"), 120),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--runs", type=int, default=1, help="reads per file (2 also checks the reads agree)")
    ap.add_argument("--period", help="month-end to reconcile, YYYY-MM (default: this month)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    folder = Path(a.folder)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTS) if folder.is_dir() else []
    if not files:
        raise SystemExit(f"No PDF or image files found in '{folder}'.")
    worst = len(files) * a.runs + len(files)
    print(f"Code version {code_version()} | prompt {get_prompt_version()} | "
          f"call cap {os.environ.get('P6_MAX_LIVE_CALLS', 'none')}")
    print(f"{len(files)} files x {a.runs} read(s) + {len(files)} decisions = at most {worst} live calls "
          f"(already-cached replies are free).")
    if a.dry_run:
        for p in files:
            print("  ", p.name)
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set.")

    llm.reset_stats()
    rows, items = [], []
    for i, p in enumerate(files, 1):
        ext = extract_invoice(p, runs=a.runs)
        item = process_extracted(ext)
        row = summarize_item(p, ext, item)
        if ext.get("fields_with_disagreement"):
            row["reads_disagreed_on"] = ext["fields_with_disagreement"]
        rows.append(row)
        items.append(item)
        print(f"[{i}/{len(files)}] {p.name}: {row['decision']}")

    print("\n" + "=" * 78)
    for r in rows:
        amt = f"${r['amount']:,.2f}" if isinstance(r["amount"], (int, float)) else "?"
        print(f"\n{r['file']}")
        print(f"  Vendor: {r['vendor']} | Invoice date: {r['invoice_date']} | Amount: {amt}")
        print(f"  AI says: {r['ai_says']}" + (f" | service period {r['service_period']}" if r["service_period"] else ""))
        print(f"  DECISION: {r['decision']}")
        print(f"  Description read: {r['read_description']}")
        for m in r["why_review"]:
            print(f"  REVIEW REASON: {m}")
        for m in r["notes"]:
            print(f"  Note: {m}")
        if r.get("reads_disagreed_on"):
            print(f"  Reads disagreed on: {', '.join(r['reads_disagreed_on'])}")

    period = a.period or date.today().strftime("%Y-%m")
    RESULTS_DIR.mkdir(exist_ok=True)
    out_json = RESULTS_DIR / f"real_invoices_{folder.name}.json"
    out_json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    try:
        from .worksheet import build_workbook
        xlsx = RESULTS_DIR / f"prepaid_worksheet_{period}_real.xlsx"
        build_workbook(items, period, str(xlsx))
        print(f"\nWorksheet: {xlsx}")
    except Exception as e:  # the table above is the main result; do not lose it over the worksheet
        print(f"\n(Worksheet not written: {e})")
    counts = {t: sum(1 for r in rows if r["decision"] == t) for t in ("AMORTIZE", "EXPENSE", "REVIEW")}
    print(f"Totals: {counts}")
    print(f"Saved {out_json}  (private: do not paste this file)")
    print(llm.usage_line())


if __name__ == "__main__":
    main()





    