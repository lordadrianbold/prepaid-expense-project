"""
Project 6: Prepaid Expense Identification & Amortization
Synthetic dataset generator.

Design goals (from the established plan):
- Genuine prepayments with real coverage-period language and dates
- Ordinary expenses that merely resemble a prepayment on the surface
  (a real, deliberate negative-case design, same spirit as Project 4's
  novel-vendor holdout test)
- Explicit one-time vs. multi-period prepayment cases, since the
  identification step now needs to distinguish these, not just
  detect "is this a prepayment"

Each record simulates the fields Project 1/5's extraction pipeline
would produce from a real invoice: vendor name, amount, invoice date,
and the raw line-item/description text an LLM identification step
would read for coverage-period language.
"""

import json
import random
from datetime import date, timedelta

random.seed(42)  # reproducible dataset


def d(y, m, day):
    return date(y, m, day).isoformat()


# ---------------------------------------------------------------------
# 1. GENUINE MULTI-PERIOD PREPAYMENTS (the clear positive case)
# ---------------------------------------------------------------------
multi_period_prepayments = [
    {
        "id": "PP-001",
        "vendor": "Salesforce Inc.",
        "invoice_date": d(2026, 1, 15),
        "amount": 24000.00,
        "description": "Annual subscription - Sales Cloud Enterprise, "
                        "coverage period February 1, 2026 through "
                        "January 31, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 2, 1),
        "true_coverage_end": d(2027, 1, 31),
    },
    {
        "id": "PP-002",
        "vendor": "Travelers Insurance Group",
        "invoice_date": d(2026, 3, 1),
        "amount": 18600.00,
        "description": "General liability insurance premium, policy "
                        "term April 1, 2026 to March 31, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 4, 1),
        "true_coverage_end": d(2027, 3, 31),
    },
    {
        "id": "PP-003",
        "vendor": "Crestline Property Management",
        "invoice_date": d(2026, 6, 10),
        "amount": 9000.00,
        "description": "Rent prepayment covering July, August, and "
                        "September 2026 (3 months at $3,000/month)",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 7, 1),
        "true_coverage_end": d(2026, 9, 30),
    },
    {
        "id": "PP-004",
        "vendor": "Adobe Inc.",
        "invoice_date": d(2026, 2, 20),
        "amount": 6600.00,
        "description": "Creative Cloud for Teams - annual license, "
                        "term March 1, 2026 - February 28, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 3, 1),
        "true_coverage_end": d(2027, 2, 28),
    },
    {
        "id": "PP-005",
        "vendor": "SecureGuard Maintenance Services",
        "invoice_date": d(2026, 4, 5),
        "amount": 14400.00,
        "description": "HVAC maintenance contract, 12-month service "
                        "agreement effective May 1, 2026 through "
                        "April 30, 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 5, 1),
        "true_coverage_end": d(2027, 4, 30),
    },
    {
        "id": "PP-006",
        "vendor": "NetSuite (Oracle)",
        "invoice_date": d(2026, 7, 1),
        "amount": 36000.00,
        "description": "ERP platform subscription renewal, 12-month "
                        "term August 2026 through July 2027",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 8, 1),
        "true_coverage_end": d(2027, 7, 31),
    },
    {
        "id": "PP-007",
        "vendor": "Westfield Business Park LLC",
        "invoice_date": d(2026, 1, 2),
        "amount": 5000.00,
        "description": "Security deposit plus 2 months prepaid rent "
                        "for suite 220, covering January and "
                        "February 2026",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 1, 1),
        "true_coverage_end": d(2026, 2, 28),
    },
    {
        "id": "PP-008",
        "vendor": "DataDog Inc.",
        "invoice_date": d(2026, 5, 12),
        "amount": 9600.00,
        "description": "Infrastructure monitoring - 6 month prepaid "
                        "plan, June 1, 2026 through November 30, 2026",
        "true_label": "multi_period_prepayment",
        "true_coverage_start": d(2026, 6, 1),
        "true_coverage_end": d(2026, 11, 30),
    },
]

# ---------------------------------------------------------------------
# 2. GENUINE ONE-TIME PREPAYMENTS (real, but the whole coverage period
#    falls inside a single period, or is a short, single-period service)
# ---------------------------------------------------------------------
one_time_prepayments = [
    {
        "id": "PP-009",
        "vendor": "Sterling Trade Show Productions",
        "invoice_date": d(2026, 3, 5),
        "amount": 8000.00,
        "description": "Booth and sponsorship fee for FinTech Summit "
                        "2026, event held April 22-24, 2026",
        "true_label": "one_time_prepayment",
        "true_coverage_start": d(2026, 4, 22),
        "true_coverage_end": d(2026, 4, 24),
    },
    {
        "id": "PP-010",
        "vendor": "Riverside Conference Center",
        "invoice_date": d(2026, 6, 1),
        "amount": 4200.00,
        "description": "Venue deposit for all-hands offsite, event "
                        "date June 18, 2026",
        "true_label": "one_time_prepayment",
        "true_coverage_start": d(2026, 6, 18),
        "true_coverage_end": d(2026, 6, 18),
    },
    {
        "id": "PP-011",
        "vendor": "Harbor Legal Group",
        "invoice_date": d(2026, 2, 10),
        "amount": 12000.00,
        "description": "Retainer covering legal services for the "
                        "February 2026 contract review engagement "
                        "only",
        "true_label": "one_time_prepayment",
        "true_coverage_start": d(2026, 2, 1),
        "true_coverage_end": d(2026, 2, 28),
    },
]

# ---------------------------------------------------------------------
# 3. ORDINARY EXPENSES THAT RESEMBLE A PREPAYMENT ON THE SURFACE
#    (the real, deliberate negative-case design)
# ---------------------------------------------------------------------
lookalike_ordinary_expenses = [
    {
        "id": "OE-001",
        "vendor": "Office Depot",
        "invoice_date": d(2026, 3, 3),
        "amount": 2800.00,
        "description": "Bulk purchase of office supplies and printer "
                        "toner for Q1-Q2 restocking",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-002",
        "vendor": "Delta Airlines",
        "invoice_date": d(2026, 4, 1),
        "amount": 3400.00,
        "description": "Advance purchase of airfare for sales team "
                        "conference travel, multiple future flight "
                        "dates April-June 2026",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-003",
        "vendor": "Uline",
        "invoice_date": d(2026, 5, 15),
        "amount": 1950.00,
        "description": "Shipping boxes and packaging materials, "
                        "6-month supply order",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-004",
        "vendor": "Costco Wholesale",
        "invoice_date": d(2026, 1, 20),
        "amount": 620.00,
        "description": "Bulk purchase of coffee and kitchen supplies "
                        "for the year",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-005",
        "vendor": "Fresh Meadow Catering",
        "invoice_date": d(2026, 6, 3),
        "amount": 5200.00,
        "description": "Catering deposit for a series of quarterly "
                        "team lunches through the remainder of the "
                        "year",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-006",
        "vendor": "Amazon Business",
        "invoice_date": d(2026, 2, 18),
        "amount": 890.00,
        "description": "Annual Prime Business membership renewal",
        "true_label": "ordinary_expense",
        # deliberately tricky: "annual" appears, but this is a
        # real, small, non-material membership fee most real
        # capitalization policies would expense immediately given
        # its size, not a genuine prepaid asset
    },
    {
        "id": "OE-007",
        "vendor": "Verizon Wireless",
        "invoice_date": d(2026, 7, 1),
        "amount": 480.00,
        "description": "Monthly mobile plan charge for July 2026, "
                        "current period only",
        "true_label": "ordinary_expense",
    },
    {
        "id": "OE-008",
        "vendor": "Bluebird Design Studio",
        "invoice_date": d(2026, 4, 22),
        "amount": 7500.00,
        "description": "50% deposit for logo and brand refresh "
                        "project, work to be completed within 30 "
                        "days",
        "true_label": "ordinary_expense",
        # tricky: "deposit" language, but no real, multi-period
        # coverage - a project deposit, not a coverage period
    },
]

# ---------------------------------------------------------------------
# Combine, shuffle, and write out
# ---------------------------------------------------------------------
all_records = (
    multi_period_prepayments + one_time_prepayments + lookalike_ordinary_expenses
)
random.shuffle(all_records)

output_path = "/home/claude/prepaid-expense-project/data/tuning_set.json"
with open(output_path, "w") as f:
    json.dump(all_records, f, indent=2)

print(f"Wrote {len(all_records)} records to {output_path}")
print(f"  - Multi-period prepayments: {len(multi_period_prepayments)}")
print(f"  - One-time prepayments: {len(one_time_prepayments)}")
print(f"  - Ordinary expenses (negative cases): {len(lookalike_ordinary_expenses)}")
