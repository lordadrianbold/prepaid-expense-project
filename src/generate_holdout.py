"""
Project 6: genuine holdout set.

Every vendor here is entirely novel - none appear in the tuning set.
This is the same discipline already proven in Project 4: a model that
learned real patterns (coverage-period language, contract terms)
should generalize to unseen vendors; a model that memorized the
tuning set's specific vendor names should not.
"""

import json
from datetime import date

random_seed_note = "novel vendors only - no overlap with tuning_set.json"


def d(y, m, day):
    return date(y, m, day).isoformat()


holdout_records = [
    # --- genuine multi-period prepayments, novel vendors ---
    {
        "id": "HO-001",
        "vendor": "Meridian Cyber Insurance Partners",
        "invoice_date": d(2026, 8, 1),
        "amount": 21000.00,
        "description": "Cyber liability insurance, policy period "
                        "September 1, 2026 through August 31, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 9, 1),
        "true_coverage_end": d(2027, 8, 31),
    },
    {
        "id": "HO-002",
        "vendor": "Zendesk Inc.",
        "invoice_date": d(2026, 9, 10),
        "amount": 15600.00,
        "description": "Customer support platform - annual "
                        "subscription, coverage October 1, 2026 to "
                        "September 30, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 10, 1),
        "true_coverage_end": d(2027, 9, 30),
    },
    {
        "id": "HO-003",
        "vendor": "Coastal Business Park Holdings",
        "invoice_date": d(2026, 7, 20),
        "amount": 7500.00,
        "description": "Prepaid warehouse rent for August, "
                        "September, and October 2026, $2,500/month",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 8, 1),
        "true_coverage_end": d(2026, 10, 31),
    },
    {
        "id": "HO-004",
        "vendor": "Aegis Property & Casualty",
        "invoice_date": d(2026, 5, 28),
        "amount": 26400.00,
        "description": "Commercial umbrella insurance policy, "
                        "12-month term beginning July 1, 2026",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 7, 1),
        "true_coverage_end": d(2027, 6, 30),
    },
    # --- genuine one-time prepayments, novel vendors ---
    {
        "id": "HO-005",
        "vendor": "Grandview Hotel & Conference Center",
        "invoice_date": d(2026, 8, 15),
        "amount": 6300.00,
        "description": "Deposit for annual sales kickoff event, "
                        "dates September 9-11, 2026",
        "true_label": "one_time_prepayment",
        "true_coverage_start": d(2026, 9, 9),
        "true_coverage_end": d(2026, 9, 11),
    },
    {
        "id": "HO-006",
        "vendor": "Whitfield & Associates Consulting",
        "invoice_date": d(2026, 6, 2),
        "amount": 9800.00,
        "description": "Retainer for a one-time compensation "
                        "benchmarking study, scoped for June 2026 "
                        "delivery only",
        "true_label": "one_time_prepayment",
        "true_coverage_start": d(2026, 6, 1),
        "true_coverage_end": d(2026, 6, 30),
    },
    # --- ordinary expenses that resemble a prepayment, novel vendors ---
    {
        "id": "HO-007",
        "vendor": "Staples Business Advantage",
        "invoice_date": d(2026, 7, 8),
        "amount": 3100.00,
        "description": "Bulk order of paper, ink cartridges, and "
                        "binders, stock for the next two quarters",
        "true_label": "ordinary_expense",
    },
    {
        "id": "HO-008",
        "vendor": "United Airlines",
        "invoice_date": d(2026, 9, 1),
        "amount": 4600.00,
        "description": "Advance booking of flights for multiple "
                        "employees attending various conferences "
                        "through year end",
        "true_label": "ordinary_expense",
    },
    {
        "id": "HO-009",
        "vendor": "Riverside Print Shop",
        "invoice_date": d(2026, 8, 5),
        "amount": 780.00,
        "description": "Annual membership renewal - local print "
                        "vendor loyalty program",
        "true_label": "ordinary_expense",
        # tricky: "annual" language again, small dollar amount,
        # not a genuine coverage-period service
    },
    {
        "id": "HO-010",
        "vendor": "Ironclad Legal Technologies",
        "invoice_date": d(2026, 9, 12),
        "amount": 11000.00,
        "description": "50% upfront deposit for a contract migration "
                        "project, remainder due on completion within "
                        "45 days",
        "true_label": "ordinary_expense",
        # tricky: "deposit" language again, but a project milestone
        # payment, not a coverage period
    },
    {
        "id": "HO-011",
        "vendor": "Total Wine & More",
        "invoice_date": d(2026, 6, 20),
        "amount": 1450.00,
        "description": "Bulk purchase for company holiday party, "
                        "event scheduled for December 2026",
        "true_label": "ordinary_expense",
        # tricky: a future event date is mentioned, similar surface
        # shape to a one-time prepayment, but this is inventory/
        # consumable goods purchased in advance, not a genuine
        # prepaid service - a real, deliberate edge case
    },
]

output_path = "/home/claude/prepaid-expense-project/data/holdout_set.json"
with open(output_path, "w") as f:
    json.dump(holdout_records, f, indent=2)

# Confirm zero vendor overlap with the tuning set
with open("/home/claude/prepaid-expense-project/data/tuning_set.json") as f:
    tuning = json.load(f)

tuning_vendors = {r["vendor"] for r in tuning}
holdout_vendors = {r["vendor"] for r in holdout_records}
overlap = tuning_vendors & holdout_vendors

print(f"Wrote {len(holdout_records)} holdout records to {output_path}")
print(f"Tuning set vendors: {len(tuning_vendors)}")
print(f"Holdout set vendors: {len(holdout_vendors)}")
print(f"Vendor overlap between tuning and holdout: {len(overlap)} "
      f"{'(CLEAN - genuine holdout)' if len(overlap) == 0 else overlap}")
