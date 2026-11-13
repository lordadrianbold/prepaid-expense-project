"""List every file the pipeline sent to review, with the reasons, and whether
the review was warranted. Usage: python -m src.show_flagged results/<name>_extraction.json"""
import json
import sys

rows = json.load(open(sys.argv[1]))
n = 0
for r in rows:
    if not r.get("flagged"):
        continue
    n += 1
    reasons = list(r["doc_checks"]["blocking"]) + [m for m in r.get("review_reasons", [])
                                                   if m not in r["doc_checks"]["blocking"]]
    print(f"{r['file']}: {'REAL ERROR' if r['wrong'] else 'flag on correct vendor/date/amount/booking (may still be a real misread of subtotal/tax/due date)'}")
    for m in reasons or ["(no reason recorded)"]:
        print(f"    - {m}")
print(f"\n{n} flagged of {len(rows)}")





