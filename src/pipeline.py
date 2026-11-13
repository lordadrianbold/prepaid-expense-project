"""
Project 6: end-to-end pipeline.

record -> identify (LLM) -> validate (deterministic) -> schedule
(deterministic) -> journal entries -> worksheet.

The LLM makes ONE judgment (what is this item, what dates does the
document state). Everything after that is checked arithmetic. Anything the
checks can't vouch for goes to a human review list instead of being
silently booked.

Run from the project root:
  python -m src.pipeline --input data/holdout_set.json --period 2026-09
  python -m src.pipeline --input data/holdout_set.json --period 2026-09 --demo-truth   (no API key; uses ground-truth labels, marked DEMO)
"""
import argparse
import json
import os
from datetime import date
from decimal import Decimal

from . import journal
from .config import CAPITALIZATION_THRESHOLD, DEFAULT_METHOD, RESULTS_DIR
from .document_checks import check_extraction
from .identify import identify_single
from .schedule import _money, build_schedule, derive_prepayment_type, parse_date


def _validate(record, ident):
    """Return (flags, usable_dates). Flags are plain-English review reasons."""
    flags, cls = [], ident["predicted_classification"]
    if cls == "PARSE_ERROR":
        return ["Model output could not be parsed; classify manually."], None
    if cls == "ordinary_expense":
        # Control on the model's own output: if it stated a service period that
        # runs past the invoice date but still called this an ordinary expense,
        # part of it may be prepaid (e.g. a year billed in March from January).
        e = ident.get("predicted_coverage_end")
        try:
            if e and e != "null" and parse_date(e) >= parse_date(record["invoice_date"]):
                flags.append(f"Classified as ordinary expense, but a service period ending {e} runs past "
                             f"the invoice date; part of it may be prepaid. Review.")
        except (ValueError, KeyError, TypeError):
            pass
        return flags, None

    s, e = ident["predicted_coverage_start"], ident["predicted_coverage_end"]
    if not s or not e or s == "null" or e == "null":
        return ["Classified as prepayment but no explicit coverage dates were found; "
                "confirm the service period with the vendor/contract."], None
    try:
        start, end = parse_date(s), parse_date(e)
    except ValueError:
        return [f"Coverage dates are not valid ISO dates ({s}, {e})."], None
    if end < start:
        return [f"Coverage end {e} is before start {s}."], None

    inv = parse_date(record["invoice_date"])
    if start < date(inv.year, inv.month, 1):
        flags.append("Coverage began before the invoice month; a catch-up entry for elapsed "
                     "months is needed (not auto-booked).")
    if end < inv:
        flags.append("Coverage ended before the invoice date; this is an expense, not a prepayment.")
    return flags, (start, end)


def process_record(record, identifier=identify_single, method=DEFAULT_METHOD):
    ident = identifier(record)
    flags, dates = _validate(record, ident)
    amount = _money(record["amount"])
    cls = ident["predicted_classification"]

    item = {"record": record, "identification": ident, "flags": flags,
            "amount": amount, "schedule": [], "entries": [], "treatment": None,
            "prepayment_type": None, "notes": []}

    if cls == "PARSE_ERROR" or (cls != "ordinary_expense" and dates is None):
        item["treatment"] = "REVIEW"
        return item

    if cls == "ordinary_expense" or float(amount) < CAPITALIZATION_THRESHOLD:
        if flags and float(amount) >= CAPITALIZATION_THRESHOLD:
            item["treatment"] = "REVIEW"
            return item
        item["treatment"] = "EXPENSE"
        item["entries"] = [journal.expense_entry(record, amount)]
        return item

    item["prepayment_type"] = derive_prepayment_type(*dates)
    if item["prepayment_type"] != cls:
        item["notes"].append(f"Model labeled {cls}; type set to {item['prepayment_type']} "
                             f"from the coverage dates (same schedule either way).")
    item["schedule"] = build_schedule(amount, *dates, method=method)
    item["treatment"] = "AMORTIZE"
    item["entries"] = ([journal.capitalization_entry(record, amount)]
                       + journal.amortization_entries(record, item["schedule"]))
    if any("Coverage ended before" in f for f in flags):
        item["treatment"] = "REVIEW"
    return item


def usable_record(ext: dict) -> dict:
    """The record identification sees: line-item text plus any Notes/Terms text."""
    desc = " ".join(x for x in [(ext.get("description") or "").strip(), (ext.get("notes") or "").strip()] if x)
    amt = ext.get("amount")
    return {"id": ext.get("id"), "vendor": ext.get("vendor") or "", "invoice_date": ext.get("invoice_date") or "",
            "amount": float(amt) if isinstance(amt, (int, float)) and amt > 0 else 0.0, "description": desc}


def process_extracted(ext: dict, identifier=identify_single, method=DEFAULT_METHOD):
    """Document checks first. Anything that fails them is NOT booked: it goes to
    review with the reason, instead of silently flowing into the ledger."""
    checks = check_extraction(ext)
    record = usable_record(ext)
    if ext.get("extraction_error") or record["amount"] <= 0:
        stub = lambda r: {"id": r["id"], "vendor": r["vendor"], "predicted_classification": "PARSE_ERROR",
                          "predicted_coverage_start": None, "predicted_coverage_end": None,
                          "reasoning": "Extraction did not produce a usable record."}
        item = process_record(record, stub, method)
    else:
        item = process_record(record, identifier, method)
    item["flags"] = checks["blocking"] + item["flags"]
    item["notes"] = item["notes"] + checks["warnings"]
    if checks["blocking"]:
        item.update(treatment="REVIEW", schedule=[], entries=[], prepayment_type=None)
    return item


def run_pipeline(records, identifier=identify_single, method=DEFAULT_METHOD):
    return [process_record(r, identifier, method) for r in records]


def truth_identifier(record):
    """DEMO ONLY: echoes ground-truth labels so the worksheet can be built
    without an API key. Never use this to report accuracy."""
    return {"id": record["id"], "vendor": record["vendor"],
            "predicted_classification": record["true_label"],
            "predicted_coverage_start": record.get("true_coverage_start"),
            "predicted_coverage_end": record.get("true_coverage_end"),
            "reasoning": "DEMO: ground-truth label, not model output."}


def main():
    from .worksheet import build_workbook
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--period", required=True, help="Month-end period to reconcile, YYYY-MM")
    ap.add_argument("--method", default=DEFAULT_METHOD, choices=["daily", "monthly_equal"])
    ap.add_argument("--out", default=str(RESULTS_DIR))
    ap.add_argument("--demo-truth", action="store_true")
    args = ap.parse_args()

    if not args.demo_truth and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set. Use --demo-truth to build a DEMO worksheet without it.")
    records = json.load(open(args.input))
    items = run_pipeline(records, truth_identifier if args.demo_truth else identify_single, args.method)

    os.makedirs(args.out, exist_ok=True)
    suffix = "_DEMO" if args.demo_truth else ""
    path = os.path.join(args.out, f"prepaid_worksheet_{args.period}{suffix}.xlsx")
    build_workbook(items, args.period, path, demo=args.demo_truth)
    counts = {t: sum(1 for i in items if i["treatment"] == t) for t in ("AMORTIZE", "EXPENSE", "REVIEW")}
    print(f"Wrote {path}\n{counts}")


if __name__ == "__main__":
    main()




    