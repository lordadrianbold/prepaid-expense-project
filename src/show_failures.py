"""
Print what actually went wrong in an extraction run: for every file where a
field was misread OR the classification disagrees with the truth, show the
truth next to what the model extracted, its description, and its reasoning.

  python -m src.show_failures results/ext_v3_photo_extraction.json
  python -m src.show_failures results/ext_v3_photo_extraction.json --all-wrong-only
"""
import argparse
import json
from pathlib import Path

from .config import ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--manifest", default=str(ROOT / "test_invoices" / "manifest.json"))
    a = ap.parse_args()

    truth = {e["file"]: e for e in json.load(open(a.manifest))}
    rows = json.load(open(a.results))
    shown = 0
    for r in rows:
        t, ext, pred = truth[r["file"]], r["extracted"], r["prediction"]
        bad_fields = [k for k, ok in r["fields"].items() if not ok]
        wrong_class = pred["predicted_classification"] != t["true_label"]
        if not (bad_fields or wrong_class):
            continue
        blocking = (r.get("doc_checks") or {}).get("blocking", [])
        shown += 1
        print("=" * 78)
        print(f"{r['file']}   ({t['layout']}, {t['level']})")
        if bad_fields:
            for k in bad_fields:
                print(f"  FIELD {k}: truth={t[k]!r}  extracted={ext.get(k)!r}")
        if r.get("disagreement"):
            print(f"  runs disagreed on: {', '.join(r['disagreement'])}")
        elif bad_fields:
            print("  runs did NOT disagree: the wrong value was consistent across runs")
        if blocking:
            for m in blocking:
                print(f"  CAUGHT BY CHECK: {m}")
        if r.get("pipeline_review"):
            for m in r.get("review_reasons") or []:
                if m not in blocking:
                    print(f"  CAUGHT BY PIPELINE REVIEW: {m}")
        if not blocking and not r.get("pipeline_review") and "doc_checks" in r:
            if r.get("wrong"):
                print("  *** SILENT: no document check flagged this ***")
            else:
                print("  (model label wrong, but the booking is still right, e.g. under the "
                      "$500 capitalization threshold)")
        if wrong_class or bad_fields:
            print(f"  classification: truth={t['true_label']}  predicted={pred['predicted_classification']}")
            print(f"  truth coverage: {t['true_coverage_start']} -> {t['true_coverage_end']}  |  "
                  f"predicted: {pred['predicted_coverage_start']} -> {pred['predicted_coverage_end']}")
            print(f"  extracted description: {ext.get('description')!r}")
            print(f"  reasoning: {pred['reasoning']}")
    print("=" * 78)
    print(f"{shown} of {len(rows)} files shown")


if __name__ == "__main__":
    main()




    