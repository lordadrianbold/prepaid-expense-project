"""
Project 6: END-TO-END test. For each rendered invoice (PDF or photo):

  1. extract_invoice  : Claude reads the document itself -> vendor, date,
                        amount, description
  2. field checks     : vendor / invoice date / amount against ground truth
  3. identify_single  : classify the EXTRACTED record (not the clean one)
  4. score            : same scoring as the text-only evaluation, so the two
                        are directly comparable

The number that answers "does it survive real documents?" is the gap between
this and the text-only result (v3: 36/40 model level, 22/22 dates).

  python -m src.evaluate_extraction --manifest test_invoices/manifest.json --name ext_v3 --kind pdf
  python -m src.evaluate_extraction --manifest test_invoices/manifest.json --name ext_v3 --kind photo --runs 3

Cost: roughly (files x runs) vision calls for extraction + one text call per
file for identification. --limit N to try a few first.
"""
import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from .config import RESULTS_DIR, ROOT
from .document_checks import check_extraction
from .evaluate import score
from .pipeline import usable_record

_SUFFIX = re.compile(r"\b(inc|llc|ltd|co|corp|corporation|company|pty|group|the)\b\.?", re.I)


def norm_vendor(v) -> str:
    v = re.sub(r"[^a-z0-9 ]", " ", str(v or "").lower().replace("&", " and "))
    return re.sub(r"\s+", " ", _SUFFIX.sub(" ", v)).strip()


def vendor_ok(extracted, truth) -> bool:
    a, b = norm_vendor(extracted), norm_vendor(truth)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def amount_ok(extracted, truth) -> bool:
    try:
        return abs(float(str(extracted).replace(",", "").replace("$", "")) - float(truth)) < 0.005
    except (TypeError, ValueError):
        return False


def check_fields(rec: dict, entry: dict) -> dict:
    return {"vendor": vendor_ok(rec.get("vendor"), entry["vendor"]),
            "invoice_date": rec.get("invoice_date") == entry["invoice_date"],
            "amount": amount_ok(rec.get("amount"), entry["amount"])}


def evaluate_entry(entry, root, extractor, identifier):
    """extractor(path) -> record dict; identifier(record) -> identification dict."""
    ext = extractor(root / entry["file"])
    checks = check_extraction(ext)
    if ext.get("extraction_error"):
        fields = {"vendor": False, "invoice_date": False, "amount": False}
        pred = {"id": entry["record_id"], "vendor": entry["vendor"],
                "predicted_classification": "PARSE_ERROR", "predicted_coverage_start": None,
                "predicted_coverage_end": None, "reasoning": f"extraction failed: {ext['extraction_error'][:150]}",
                "amount": None}
    else:
        fields = check_fields(ext, entry)
        try:
            amt = float(str(ext.get("amount")).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            amt = None
        usable = usable_record(dict(ext, id=entry["record_id"]))
        usable["amount"] = amt if amt is not None else 0.0
        pred = identifier(usable)
        pred["amount"] = amt
    pred.update({"true_label": entry["true_label"], "true_coverage_start": entry["true_coverage_start"],
                 "true_coverage_end": entry["true_coverage_end"], "tags": (entry.get("tags") or []) + [
                     f"kind:{entry['kind']}", f"level:{entry['level']}", f"layout:{entry['layout']}"]})
    one = score([dict(pred)])
    pipeline_ok = (one["pipeline_level"]["correct"] == 1) if one["pipeline_level"] else (one["correct"] == 1)
    wrong = (not all(fields.values())) or (not pipeline_ok)
    # flagged = the pipeline would send it to review: a document check failed,
    # or the identification result itself needs review (e.g. open service period).
    from .pipeline import process_extracted
    item = process_extracted(dict(ext, id=entry["record_id"]), identifier=lambda r: dict(pred))
    pipeline_review = item["treatment"] == "REVIEW"
    from . import llm
    return {"temperature_applied": llm.TEMPERATURE_APPLIED, "pipeline_review": pipeline_review,
            "review_reasons": item["flags"],
            "file": entry["file"], "fields": fields, "extracted": ext, "prediction": pred,
            "disagreement": ext.get("fields_with_disagreement") or [],
            "doc_checks": checks, "wrong": wrong, "flagged": bool(checks["blocking"]) or pipeline_review}


def summarize(rows):
    def pct(k, n): return f"{k}/{n} ({k / n:.0%})" if n else "n/a"
    groups = defaultdict(list)
    for r in rows:
        e = r["prediction"]["tags"]
        groups["ALL"].append(r)
        for t in e:
            if t.startswith(("kind:", "level:", "layout:")):
                groups[t].append(r)
    lines = []
    for g, rs in sorted(groups.items(), key=lambda kv: (kv[0] != "ALL", kv[0])):
        n = len(rs)
        f = {k: sum(r["fields"][k] for r in rs) for k in ("vendor", "invoice_date", "amount")}
        allf = sum(all(r["fields"].values()) for r in rs)
        s = score([dict(r["prediction"]) for r in rs])
        pl = s["pipeline_level"]
        no_amt = [r for r in rs if r["prediction"].get("amount") is None]
        pl_text = pct(pl["correct"], n) if pl else "n/a"
        if not pl and no_amt and len(no_amt) < n:
            scored = [dict(r["prediction"]) for r in rs if r["prediction"].get("amount") is not None]
            spl = score(scored)["pipeline_level"]
            pl_text = (f"{pct(spl['correct'], len(scored))} on {len(scored)} files with a readable amount "
                       f"({len(no_amt)} unreadable, all sent to review)")
        flagged = [r for r in rs if r["flagged"]]
        caught = sum(1 for r in flagged if r["wrong"])
        silent = sum(1 for r in rs if r["wrong"] and not r["flagged"])
        warned = sum(1 for r in rs if r["doc_checks"]["warnings"])
        lines.append(f"{g:<16} n={n:<3} fields: vendor {pct(f['vendor'], n)}, date {pct(f['invoice_date'], n)}, "
                     f"amount {pct(f['amount'], n)}, all-three {pct(allf, n)}\n{'':<16} "
                     f"end-to-end: model {pct(s['correct'], n)}, pipeline {pl_text}, "
                     f"dates exact {s['coverage_date_exact_match']}\n{'':<16} "
                     f"CONTROL: flagged for review {len(flagged)} (caught wrong {caught}, flags on correct core fields {len(flagged) - caught}); "
                     f"SILENT wrong {silent}; low-res warnings {warned}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "test_invoices" / "manifest.json"))
    ap.add_argument("--name", required=True)
    ap.add_argument("--kind", choices=["pdf", "photo", "all"], default="all")
    ap.add_argument("--runs", type=int, default=1, help="extraction repeats per file (consistency check)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--prompt-version", choices=["v1", "v2", "v3", "v4"])
    ap.add_argument("--dry-run", action="store_true", help="print how many API calls this would make, then stop")
    a = ap.parse_args()
    if a.prompt_version:
        os.environ["P6_PROMPT_VERSION"] = a.prompt_version
    if not a.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set.")

    from anthropic import Anthropic
    from .extract_invoice import extract_invoice
    from .identify import identify_single

    client = Anthropic()
    manifest = json.load(open(a.manifest))
    root = Path(a.manifest).parent
    entries = [e for e in manifest if a.kind in ("all", e["kind"])]
    if a.limit:
        entries = entries[:a.limit]
    from .config import get_prompt_version
    from .version import code_version
    print(f"Code version {code_version()} | prompt {get_prompt_version()} | "
          f"call cap {os.environ.get('P6_MAX_LIVE_CALLS', 'none')}")
    print(f"{len(entries)} files x {a.runs} extraction run(s) = {len(entries) * a.runs} vision calls "
          f"+ {len(entries)} identification calls")

    if a.dry_run:
        from .llm import CACHE_DIR
        print(f"DRY RUN: nothing sent. Worst case {len(entries) * a.runs + len(entries)} live calls; "
              f"already-cached replies are free (cache folder: {CACHE_DIR}).")
        return
    from . import llm
    llm.reset_stats()
    cv = code_version()
    extractor = lambda p: extract_invoice(p, client=client, runs=a.runs)
    identifier = lambda r: identify_single(r, client=client)
    rows = []
    for i, e in enumerate(entries, 1):
        row = evaluate_entry(e, root, extractor, identifier)
        rows.append(row)
        bad = [k for k, v in row["fields"].items() if not v]
        p = row["prediction"]
        print(f"  [{i}/{len(entries)}] {e['file']}: fields {'OK' if not bad else 'WRONG ' + ','.join(bad)}"
              f" | {p['predicted_classification']} (true {e['true_label']})"
              f"{' | runs disagree on ' + ','.join(row['disagreement']) if row['disagreement'] else ''}"
              f"{' | FLAGGED: ' + str(len(row['doc_checks']['blocking'])) + ' check(s)' if row['flagged'] else ''}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{a.name}_extraction.json"
    out.write_text(json.dumps(rows, indent=2, default=str))
    print("\n" + summarize(rows))
    print(llm.usage_line())
    print("Temperature 0 applied: " + ("yes" if rows and rows[0].get("temperature_applied") else
          "NO (installed SDK rejects it; results are not pinned to temperature 0)"))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()





    