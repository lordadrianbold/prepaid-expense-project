"""
Project 6: scores identification predictions against ground truth.

Reports the numbers that matter to an accountant, not just accuracy:
  - false capitalizations: ordinary expenses wrongly booked as prepaid
  - missed prepayments:    real prepayments wrongly expensed
  - coverage-date exact match on real prepayments

Run on the tuning set AND the novel-vendor holdout; the holdout is the
number to trust, because the prompt was tuned against the first set.

  python -m src.evaluate --predictions results/holdout_predictions.json --name holdout
  python -m src.evaluate --run data/holdout_set.json --name holdout       (needs API key)
"""
import argparse
import json
import os
from collections import Counter

from .config import CAPITALIZATION_THRESHOLD, RESULTS_DIR
from .schedule import derive_prepayment_type

PREPAY = {"multi_period_prepayment", "one_time_prepayment"}


def _norm(v):
    return None if v in (None, "", "null", "None") else v


def score(preds):
    for p in preds:  # model may emit the string "null"; treat as missing
        for k in ("predicted_coverage_start", "predicted_coverage_end",
                  "true_coverage_start", "true_coverage_end"):
            p[k] = _norm(p.get(k))
    n = len(preds)
    correct = [p for p in preds if p["predicted_classification"] == p["true_label"]]
    confusion = Counter((p["true_label"], p["predicted_classification"]) for p in preds)
    false_cap = [p for p in preds if p["true_label"] == "ordinary_expense"
                 and p["predicted_classification"] in PREPAY]
    missed = [p for p in preds if p["true_label"] in PREPAY
              and p["predicted_classification"] == "ordinary_expense"]
    true_pp = [p for p in preds if p["true_label"] in PREPAY]
    date_ok = [p for p in true_pp
               if p["predicted_coverage_start"] == p["true_coverage_start"]
               and p["predicted_coverage_end"] == p["true_coverage_end"]]
    # Pipeline level: what actually gets booked after the deterministic
    # capitalization threshold overrides the model. Needs amounts.
    pipeline_level = None
    if all(p.get("amount") is not None for p in preds):
        def eff(p):
            """What the pipeline actually books: the $500 threshold, then
            prepayment type derived from the model's dates (not its label)."""
            if p["amount"] < CAPITALIZATION_THRESHOLD:
                return "ordinary_expense"
            if (p["predicted_classification"] in PREPAY
                    and p["predicted_coverage_start"] and p["predicted_coverage_end"]):
                if str(p["predicted_coverage_end"]) < str(p["predicted_coverage_start"]):
                    return "INVALID_DATES"   # pipeline cannot book this; it goes to review
                try:
                    return derive_prepayment_type(p["predicted_coverage_start"], p["predicted_coverage_end"])
                except ValueError:
                    pass
            return p["predicted_classification"]
        pl_correct = [p for p in preds if eff(p) == p["true_label"]]
        pipeline_level = {
            "threshold": CAPITALIZATION_THRESHOLD,
            "correct": len(pl_correct), "accuracy": len(pl_correct) / n if n else 0,
            "false_capitalizations": [p["id"] for p in preds if p["true_label"] == "ordinary_expense"
                                      and eff(p) in PREPAY],
            "missed_prepayments": [p["id"] for p in preds if p["true_label"] in PREPAY
                                   and eff(p) == "ordinary_expense"]}
    by_tag = {}
    for p in preds:
        for t in (p.get("tags") or []):
            row = by_tag.setdefault(t, [0, 0])
            row[1] += 1
            row[0] += p["predicted_classification"] == p["true_label"]
    return {"n": n, "accuracy": len(correct) / n if n else 0,
            "by_tag": {t: f"{c}/{k}" for t, (c, k) in sorted(by_tag.items())},
            "pipeline_level": pipeline_level,
            "prompt_version": next((p.get("prompt_version") for p in preds if p.get("prompt_version")), None),
            "correct": len(correct), "confusion": {f"{t} -> {p}": c for (t, p), c in sorted(confusion.items())},
            "false_capitalizations": [p["id"] for p in false_cap],
            "missed_prepayments": [p["id"] for p in missed],
            "coverage_date_exact_match": f"{len(date_ok)}/{len(true_pp)}",
            "wrong": [{"id": p["id"], "true": p["true_label"], "predicted": p["predicted_classification"],
                       "reasoning": p["reasoning"]} for p in preds if p not in correct]}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--predictions")
    g.add_argument("--run", help="dataset to run identification on first (needs API key)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt-version", choices=["v1", "v2", "v3", "v4"],
                    help="identification prompt to use with --run (default from config)")
    ap.add_argument("--dataset", help="with --predictions: dataset to take amounts/tags from "
                                      "(for predictions saved before those fields existed)")
    a = ap.parse_args()
    if a.prompt_version:
        os.environ["P6_PROMPT_VERSION"] = a.prompt_version

    RESULTS_DIR.mkdir(exist_ok=True)
    if a.run:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY not set.")
        from .identify import run_batch
        pred_path = RESULTS_DIR / f"{a.name}_predictions.json"
        preds = run_batch(a.run, pred_path)
    else:
        preds = json.load(open(a.predictions))
        if a.dataset:
            by_id = {r["id"]: r for r in json.load(open(a.dataset))}
            for p in preds:
                src = by_id.get(p["id"], {})
                p.setdefault("amount", src.get("amount"))
                p.setdefault("tags", src.get("tags"))
    s = score(preds)
    out = RESULTS_DIR / f"{a.name}_scores.json"
    out.write_text(json.dumps(s, indent=2))
    print(f"\n{a.name} (prompt {s['prompt_version'] or 'n/a'}): "
          f"{s['correct']}/{s['n']} correct ({s['accuracy']:.1%})  <- model level")
    print(f"  false capitalizations: {s['false_capitalizations'] or 'none'}")
    print(f"  missed prepayments:    {s['missed_prepayments'] or 'none'}")
    print(f"  coverage dates exact:  {s['coverage_date_exact_match']}")
    pl = s["pipeline_level"]
    if pl:
        print(f"  pipeline level (after ${pl['threshold']:,.0f} capitalization threshold): "
              f"{pl['correct']}/{s['n']} ({pl['accuracy']:.1%}); "
              f"false capitalizations {pl['false_capitalizations'] or 'none'}; "
              f"missed {pl['missed_prepayments'] or 'none'}")
    if s["by_tag"]:
        print("  by tag:", ", ".join(f"{t} {v}" for t, v in s["by_tag"].items()))
    for w in s["wrong"]:
        print(f"  WRONG {w['id']}: true={w['true']} predicted={w['predicted']}")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()





    