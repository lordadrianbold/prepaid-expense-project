"""
Project 6: holdout v3, 40 records. Built AFTER holdout v2 exposed a weak
spot (one-time prepayments were being expensed) and AFTER prompt v2 was
written, to answer one question: did the prompt fix generalize to data it
was never shaped by, without over-correcting?

COMPOSITION (weighted toward the weak category, with lookalike traps):
  14 one_time_prepayment   rentals, bookings, lodging, event/training fees,
                           service bookings, all on stated dates inside ONE month
   8 multi_period          incl. leap-year spans, duration-only terms, one
                           partly-elapsed term
  18 ordinary_expense      the traps the one-time fix could wrongly capture:
                           goods for events, non-contiguous travel, project
                           deposits, bulk supplies, small memberships,
                           services in arrears, plain repairs

LABELING POLICY: identical to holdout v2's (see generate_holdout_v2.py) plus
two clarifications decided before this set was run:
  - Renting equipment/space, booking lodging, or booking a service for stated
    single-month dates, paid before delivery, is a one_time_prepayment.
  - Purchasing GOODS for an event is an ordinary_expense.
Borderline cases (single-trip airfare, catering, "deposit" to a service
provider tied to a deliverable) were deliberately left out: each record has
one defensible answer.

NOTE: 3 small memberships ($180-$325, with explicit period language) are
included on purpose. The MODEL may still capitalize them; the pipeline's
$500 threshold is what catches them, so score both levels.
"""
import json
import random
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "holdout_v3.json"
D = date


def fm(d):
    return f"{d:%B} {d.day}, {d.year}"


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def term_end(start, months):
    return add_months(start, months) - timedelta(days=1)


R = []


def rec(label, vendor, inv, amount, text, tags, s=None, e=None):
    r = dict(vendor=vendor, invoice_date=str(inv), amount=amount, description=text,
             true_label=label, tags=tags)
    if s:
        r["true_coverage_start"], r["true_coverage_end"] = str(s), str(e)
    R.append(r)


def ot(*a, s, e): rec("one_time_prepayment", *a, s=s, e=e)
def mp(*a, s, e): rec("multi_period_prepayment", *a, s=s, e=e)
def oe(*a): rec("ordinary_expense", *a)


# ---------------- one-time prepayments (14) ----------------
s = e = D(2027, 11, 6)
ot("Crestview Banquet Hall", D(2027, 9, 20), 7200.00,
   f"Hall rental fee for annual awards dinner on {fm(s)}", ["event_rental"], s=s, e=e)
s = e = D(2027, 4, 27)
ot("Lumen Audio Visual Services", D(2027, 3, 18), 4650.00,
   f"Sound system rental and AV technician for shareholder meeting on {fm(s)}", ["equipment_rental"], s=s, e=e)
s, e = D(2027, 8, 2), D(2027, 8, 27)
ot("Pioneer Scaffold & Lift Rental", D(2027, 7, 19), 3880.00,
   f"Scissor lift rental for the period {fm(s)} through {fm(e)}", ["equipment_rental", "single_month"], s=s, e=e)
s, e = D(2027, 1, 25), D(2027, 1, 28)
ot("Seaside Inn & Suites", D(2026, 12, 15), 11520.00,
   f"12 rooms reserved for sales kickoff, nights of {fm(s)} through {fm(e)}", ["lodging"], s=s, e=e)
s, e = D(2027, 10, 12), D(2027, 10, 15)
ot("Northwind Training Institute", D(2027, 9, 1), 5400.00,
   f"Certification course fee, class dates {fm(s)} to {fm(e)}", ["training"], s=s, e=e)
s, e = D(2027, 5, 19), D(2027, 5, 21)
ot("Vista Exhibition Services", D(2027, 3, 30), 14250.00,
   f"Exhibit booth space at Healthcare Finance Expo, show dates {fm(s)} to {fm(e)}", ["trade_show"], s=s, e=e)
s = e = D(2027, 7, 23)
ot("Parkside Pavilion Rentals", D(2027, 6, 14), 2300.00,
   f"Pavilion rental for employee appreciation day on {fm(s)}", ["event_rental"], s=s, e=e)
s = e = D(2027, 9, 9)
ot("SilverLine Charter Buses", D(2027, 8, 5), 3150.00,
   f"Charter bus service for company offsite transport on {fm(s)}", ["service_booking"], s=s, e=e)
s = e = D(2027, 12, 4)
ot("Orchid Lane Event Photography", D(2027, 10, 26), 2800.00,
   f"Photography services prepayment for company gala to be held {fm(s)}", ["service_booking"], s=s, e=e)
s, e = D(2027, 3, 22), D(2027, 3, 24)
ot("Maple Grove Conference Suites", D(2027, 2, 8), 6100.00,
   f"Meeting-room block for board strategy sessions, dates {fm(s)} to {fm(e)}", ["event_rental"], s=s, e=e)
s, e = D(2027, 6, 7), D(2027, 6, 18)
ot("Titan Portable Power Rentals", D(2027, 5, 24), 5075.00,
   f"Generator rental for plant maintenance shutdown, rental period {fm(s)} through {fm(e)}", ["equipment_rental"], s=s, e=e)
s = e = D(2027, 2, 17)
ot("Cobalt Interpretation Services", D(2027, 1, 12), 4400.00,
   f"Conference interpreters for investor day on {fm(s)}", ["service_booking"], s=s, e=e)
s = e = D(2027, 10, 1)
ot("Bayfront Marina Club", D(2027, 8, 30), 9800.00,
   f"Dockside venue buyout for client reception on {fm(s)}", ["event_rental"], s=s, e=e)
s, e = D(2027, 6, 2), D(2027, 6, 4)
ot("Granite Peak Executive Education", D(2027, 4, 27), 7960.00,
   f"Leadership seminar registration for 4 managers, seminar held {fm(s)} through {fm(e)}", ["training"], s=s, e=e)

# ---------------- multi-period prepayments (8) ----------------
s, e = D(2027, 12, 1), D(2028, 11, 30)
mp("Granville Cyber Defense", D(2027, 11, 15), 38400.00,
   f"Managed security monitoring, 12-month service term {fm(s)} through {fm(e)}", ["security", "leap_year"], s=s, e=e)
s, e = D(2027, 9, 15), D(2028, 9, 14)
mp("Ridgeway Surety Insurance", D(2027, 9, 1), 52300.00,
   f"Directors and officers liability policy period {fm(s)} through {fm(e)}", ["insurance", "mid_month_start", "leap_year"], s=s, e=e)
s = D(2027, 5, 10); e = term_end(s, 12)
mp("Quantum Learning Systems", D(2027, 4, 22), 16800.00,
   f"Annual e-learning platform license, 12-month term beginning {fm(s)}", ["saas", "duration_only", "mid_month_start", "leap_year"], s=s, e=e)
s = D(2027, 10, 1); e = term_end(s, 3)
mp("Oakmont Property Management", D(2027, 9, 24), 27000.00,
   f"Prepaid rent for Suite 12B, 3-month period starting {fm(s)}", ["rent", "duration_only"], s=s, e=e)
s, e = D(2027, 8, 1), D(2030, 7, 31)
mp("Stonebridge Office Systems", D(2027, 7, 15), 21600.00,
   f"Equipment service agreement, 36-month term {fm(s)} to {fm(e)}", ["maintenance", "multi_year", "leap_year"], s=s, e=e)
s, e = D(2027, 2, 1), D(2028, 1, 31)
mp("Evermark Compliance Software", D(2027, 3, 20), 12900.00,
   f"Annual compliance software subscription, period {fm(s)} through {fm(e)}", ["saas", "partly_elapsed"], s=s, e=e)
s, e = D(2027, 9, 1), D(2028, 8, 31)
mp("Westlake Publishing Group", D(2027, 8, 10), 9450.00,
   f"Annual research database access, access period {fm(s)} to {fm(e)}", ["subscription", "leap_year"], s=s, e=e)
s, e = D(2027, 10, 18), D(2028, 4, 17)
mp("Lighthouse Bay Marketing", D(2027, 10, 4), 18000.00,
   f"Six-month sponsorship of regional radio program, airing {fm(s)} through {fm(e)}", ["marketing", "mid_month_start", "leap_year"], s=s, e=e)

# ---------------- ordinary expenses (18) ----------------
oe("Bannerline Print Co.", D(2027, 12, 14), 3240.00,
   "12 retractable banners and printed brochures for the March 2028 trade fair", ["goods_future_event"])
oe("Summit Gifts & Awards", D(2027, 11, 29), 5925.00,
   "150 engraved glass awards for the January 2028 sales recognition event", ["goods_future_event"])
oe("Peak Promotions Wholesale", D(2027, 5, 7), 4350.00,
   "1,000 branded water bottles to hand out at the June 2027 field day", ["goods_future_event"])
oe("JetNorth Corporate Travel", D(2027, 2, 10), 4980.00,
   "Advance purchase of airfare for sales trips on March 8, July 12 and November 2, 2027", ["advance_travel"])
oe("Roadway Rail Passes", D(2027, 3, 2), 3350.00,
   "Prepaid train tickets for site visits on several dates in April, August and December 2027", ["advance_travel"])
oe("Crown Hotel Reservations", D(2027, 12, 20), 6720.00,
   "Prepaid hotel nights for three separate client conferences in February, June and September 2028", ["advance_travel"])
oe("Ironwood Interiors", D(2027, 6, 21), 22750.00,
   "35% deposit toward office renovation project, balance due on completion", ["project_deposit"])
oe("Delta Analytics Partners", D(2027, 7, 6), 30000.00,
   "Milestone 1 payment (25%) for data warehouse implementation project", ["project_deposit"])
oe("Greenfield Landscape Design", D(2027, 4, 13), 8600.00,
   "50% deposit for courtyard redesign project, remaining balance due on project completion", ["project_deposit"])
oe("Paperworks Distribution", D(2027, 1, 20), 2780.00,
   "Annual supply of printer paper and envelopes ordered in one bulk shipment", ["bulk_supplies"])
oe("Shield Safety Supply", D(2027, 2, 24), 3960.00,
   "Bulk purchase of protective equipment and first-aid kits to last through next year", ["bulk_supplies"])
oe("Regional Business Roundtable", D(2027, 12, 8), 325.00,
   "Annual membership dues, membership year 2028", ["small_membership"])
oe("Finance Professionals Chapter 14", D(2027, 8, 16), 180.00,
   "Chapter dues for the 2027-2028 program year", ["small_membership"])
oe("DataTrend Newsletter", D(2027, 12, 2), 299.00,
   "Annual online subscription for the period January 1, 2028 through December 31, 2028", ["small_membership"])
oe("Bluewave Telecom", D(2027, 9, 6), 1120.00,
   "Phone and internet service for the month of August 2027", ["arrears"])
oe("Meridian Security Patrol", D(2027, 10, 5), 7350.00,
   "Security patrol services provided July through September 2027", ["arrears"])
oe("Cascade Temp Staffing", D(2027, 11, 3), 9860.00,
   "Temporary staffing services for weeks ending in October 2027", ["arrears"])
oe("Allied Locksmith", D(2027, 8, 4), 485.00,
   "Lock replacement and rekey completed on August 3, 2027", ["plain"])


def validate(records):
    from collections import Counter
    assert len(records) == 40, len(records)
    assert Counter(r["true_label"] for r in records) == {
        "one_time_prepayment": 14, "multi_period_prepayment": 8, "ordinary_expense": 18}
    vendors = [r["vendor"] for r in records]
    assert len(set(vendors)) == len(vendors), "duplicate vendor in v3"
    for r in records:
        if r["true_label"] != "ordinary_expense":
            s, e = date.fromisoformat(r["true_coverage_start"]), date.fromisoformat(r["true_coverage_end"])
            assert e >= s
            same = (s.year, s.month) == (e.year, e.month)
            assert same == (r["true_label"] == "one_time_prepayment"), f"{r['vendor']}: label vs month span"
            if "partly_elapsed" not in r["tags"]:
                assert date.fromisoformat(r["invoice_date"]) < s, f"{r['vendor']}: paid after coverage began"
    # no overlap with any earlier set
    for name in ("tuning_set.json", "holdout_set.json", "holdout_v2.json"):
        p = DATA / name
        if p.exists():
            old = {x["vendor"] for x in json.load(open(p))}
            assert not (old & set(vendors)), f"vendor overlap with {name}: {old & set(vendors)}"
    # prompts must not contain any v3 vendor name or description (no leakage)
    from src.identify import PROMPTS
    for ver, text in PROMPTS.items():
        for r in records:
            assert r["vendor"] not in text, f"v3 vendor {r['vendor']} appears in prompt {ver}"
            assert r["description"] not in text, f"v3 description appears in prompt {ver}"


def main():
    validate(R)
    random.Random(11).shuffle(R)
    out = []
    for i, r in enumerate(R, 1):
        out.append({"id": f"H3-{i:03d}", **r})
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    from collections import Counter
    print("Wrote", OUT, "|", dict(Counter(r["true_label"] for r in out)))


if __name__ == "__main__":
    main()





    