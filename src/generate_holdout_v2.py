"""
Project 6: holdout v2, 48 records, built to be hard and to be defensible.

LABELING POLICY (fixed BEFORE any model run on this set, and derived from
the principles already stated in identify.py's prompt, not from model output):

 multi_period_prepayment  A service/right with a STATED coverage period or
                          term (dates, or a duration + start) spanning 2+
                          calendar months. Includes terms already partly
                          elapsed at invoice date (a catch-up flag, still a
                          prepayment) and multi-year terms.
 one_time_prepayment      A service/right paid in advance whose stated dates
                          fall inside ONE calendar month (venue/lodging/
                          booking deposits, event registration, a one-month
                          rental).
 ordinary_expense         Everything else, specifically:
   - bulk consumable supplies, however long they are said to last
   - deposits/retainers/milestone payments for a PROJECT or DELIVERABLE
   - small-dollar memberships/subscriptions (policy: under $500)
   - advance travel for multiple non-contiguous dates
   - goods bought for a future event
   - services already rendered (coverage ended before the invoice: in
     arrears, nothing is prepaid)
   - plain completed repairs/services

 Deliberately NOT included: borderline cases where reasonable accountants
 disagree (e.g. a retainer for a single-month deliverable: see HO-006 in
 holdout v1 and PP-011 in the tuning set, which sit on that line). Every
 record here is meant to have one defensible answer under the policy above.

Descriptions and ground-truth dates are produced from the same date
values, so text and labels cannot drift apart. Some records give only a
start plus a duration ("36-month term commencing ..."): the model must do
the date arithmetic, a deliberate hard case.
"""
import json
import random
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "holdout_v2.json"
DATA = OUT.parent


def fm(d):  # "April 15, 2026" (no %-d, works on Windows too)
    return f"{d:%B} {d.day}, {d.year}"


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def term_end(start, months):
    return add_months(start, months) - timedelta(days=1)


R = []


def mp(vendor, inv, amount, text, start, end, tags):
    R.append(dict(vendor=vendor, invoice_date=str(inv), amount=amount, description=text,
                  true_label="multi_period_prepayment", true_coverage_start=str(start),
                  true_coverage_end=str(end), tags=tags))


def ot(vendor, inv, amount, text, start, end, tags):
    R.append(dict(vendor=vendor, invoice_date=str(inv), amount=amount, description=text,
                  true_label="one_time_prepayment", true_coverage_start=str(start),
                  true_coverage_end=str(end), tags=tags))


def oe(vendor, inv, amount, text, tags):
    R.append(dict(vendor=vendor, invoice_date=str(inv), amount=amount, description=text,
                  true_label="ordinary_expense", tags=tags))


D = date

# ---------------- multi-period prepayments (18) ----------------
s, e = D(2026, 10, 15), D(2027, 10, 14)
mp("Hartwell Mutual Insurance", D(2026, 10, 1), 27450.00,
   f"Commercial property insurance premium, policy period {fm(s)} through {fm(e)}", s, e,
   ["insurance", "mid_month_start"])
s = D(2027, 1, 1); e = term_end(s, 24)
mp("Pinnacle Surety & Bond Co.", D(2026, 12, 10), 41800.00,
   f"Professional liability insurance, 24-month policy term commencing {fm(s)}", s, e,
   ["insurance", "multi_year", "duration_only", "leap_year"])
s, e = D(2027, 2, 1), D(2028, 1, 31)
mp("Lakeshore Workers Comp Group", D(2027, 1, 12), 63200.50,
   f"Workers' compensation premium, policy effective {fm(s)} to {fm(e)}", s, e, ["insurance"])
s, e = D(2027, 7, 1), D(2028, 6, 30)
mp("Northgate Fleet Insurance", D(2027, 6, 15), 19875.00,
   f"Commercial auto fleet policy, coverage period {fm(s)} through {fm(e)}", s, e,
   ["insurance", "leap_year"])
s, e = D(2026, 11, 1), D(2027, 10, 31)
mp("Atlassian Pty Ltd", D(2026, 10, 20), 18720.00,
   f"Annual Jira and Confluence cloud subscription, subscription period {fm(s)} through {fm(e)}", s, e, ["saas"])
s, e = D(2027, 1, 1), D(2028, 12, 31)
mp("Snowflake Inc.", D(2026, 12, 18), 240000.00,
   f"Data platform capacity commitment, 24-month term {fm(s)} to {fm(e)}", s, e,
   ["saas", "multi_year", "leap_year"])
s = D(2026, 11, 16); e = term_end(s, 12)
mp("Okta, Inc.", D(2026, 11, 2), 14400.00,
   f"Annual identity platform license, 12-month term beginning {fm(s)}", s, e,
   ["saas", "duration_only", "mid_month_start"])
s, e = D(2026, 1, 1), D(2026, 12, 31)
mp("HubSpot Inc.", D(2026, 3, 15), 9600.00,
   f"Marketing Hub annual subscription, service period {fm(s)} through {fm(e)}", s, e,
   ["saas", "partly_elapsed"])
s, e = D(2027, 7, 1), D(2027, 12, 31)
mp("Cedar Ridge Office Partners", D(2027, 6, 20), 54000.00,
   f"Prepaid rent for Suite 400, rental period {fm(s)} through {fm(e)}", s, e, ["rent"])
s = D(2027, 3, 16); e = term_end(s, 6)
mp("Harborview Storage LLC", D(2027, 3, 5), 7800.00,
   f"Prepaid warehouse space rental, 6-month period starting {fm(s)}", s, e,
   ["rent", "duration_only", "mid_month_start"])
s, e = D(2027, 1, 1), D(2027, 12, 31)
mp("Summit Elevator Services", D(2026, 12, 28), 8640.00,
   f"Annual elevator maintenance contract, service period {fm(s)} through {fm(e)}", s, e, ["maintenance"])
s, e = D(2027, 4, 1), D(2030, 3, 31)
mp("Brightline HVAC Solutions", D(2027, 3, 22), 32400.00,
   f"Preventive maintenance agreement, 36-month term {fm(s)} to {fm(e)}", s, e,
   ["maintenance", "multi_year", "leap_year"])
s, e = D(2027, 3, 1), D(2028, 2, 29)
mp("Vertex Copier Service", D(2027, 2, 15), 5280.00,
   f"Managed print support plan, coverage {fm(s)} through {fm(e)}", s, e,
   ["maintenance", "leap_year"])
s, e = D(2027, 7, 1), D(2028, 6, 30)
mp("Midwest Industrial Trade Association", D(2027, 6, 1), 12500.00,
   f"Annual membership dues for the membership year {fm(s)} to {fm(e)}", s, e,
   ["dues", "leap_year"])
s, e = D(2026, 8, 10), D(2027, 8, 9)
mp("Esri Southeast", D(2026, 7, 28), 22300.00,
   f"Annual GIS software license, license term {fm(s)} through {fm(e)}", s, e,
   ["software", "mid_month_start"])
s, e = D(2027, 1, 1), D(2027, 12, 31)
mp("Metro Transit Advertising", D(2026, 12, 15), 36000.00,
   f"Twelve-month bus shelter advertising campaign, run dates {fm(s)} through {fm(e)}", s, e, ["marketing"])
s, e = D(2027, 5, 1), D(2029, 4, 30)
mp("Reliant Equipment Protection", D(2027, 4, 18), 11900.00,
   f"Extended warranty on production equipment, coverage {fm(s)} to {fm(e)}", s, e,
   ["warranty", "multi_year"])
s = D(2027, 9, 1); e = term_end(s, 24)
mp("Cloudmark Hosting", D(2027, 8, 20), 4320.00,
   f"Domain registration and managed hosting, 24-month term beginning {fm(s)}", s, e,
   ["hosting", "multi_year", "duration_only"])

# ---------------- one-time prepayments (8) ----------------
s, e = D(2026, 10, 12), D(2026, 10, 14)
ot("Lakeside Resort & Conference Center", D(2026, 8, 20), 12500.00,
   f"Venue deposit for annual leadership retreat, event dates {fm(s)} to {fm(e)}", s, e, ["event_deposit"])
s, e = D(2027, 3, 8), D(2027, 3, 10)
ot("Austin Convention Partners", D(2027, 1, 25), 4350.00,
   f"Registration fees for 3 attendees, industry summit held {fm(s)} through {fm(e)}", s, e, ["event_registration"])
s, e = D(2027, 5, 4), D(2027, 5, 6)
ot("Boston Sales Academy", D(2027, 4, 2), 6800.00,
   f"Team training workshop tuition, sessions held {fm(s)} to {fm(e)}", s, e, ["training"])
s = e = D(2027, 9, 18)
ot("Evergreen Event Rentals", D(2027, 8, 12), 3900.00,
   f"Tent, staging and AV rental for company picnic on {fm(s)}", s, e, ["event_deposit"])
s, e = D(2027, 2, 1), D(2027, 2, 28)
ot("Meridian Equipment Rentals", D(2027, 1, 18), 15600.00,
   f"Crane rental for the period {fm(s)} through {fm(e)}", s, e, ["rental", "single_month"])
s = e = D(2026, 11, 9)
ot("Radiant Studio Productions", D(2026, 10, 5), 5000.00,
   f"Studio rental booking fee for a one-day shoot on {fm(s)}", s, e, ["event_deposit"])
s, e = D(2027, 6, 14), D(2027, 6, 16)
ot("Harbor Hotels Group", D(2027, 5, 10), 8160.00,
   f"Room block for client summit guests, nights of {fm(s)} through {fm(e)}", s, e, ["lodging"])
s, e = D(2027, 1, 20), D(2027, 1, 22)
ot("Rocky Mountain Retreat Lodge", D(2026, 12, 2), 9450.00,
   f"Lodging and meeting-space rental for team offsite, stay {fm(s)} to {fm(e)}", s, e, ["lodging"])

# ---------------- ordinary expenses (22) ----------------
oe("Uline Shipping Supply", D(2026, 11, 5), 3480.00,
   "Bulk order of cartons, tape and packing supplies sufficient for the next 12 months", ["bulk_supplies"])
oe("Quill Corporation", D(2027, 1, 14), 2215.00,
   "Annual supply of toner cartridges and copy paper, delivered in a single shipment", ["bulk_supplies"])
oe("Grainger Industrial Supply", D(2027, 2, 9), 4870.00,
   "Six-month stock of safety gloves, lubricants and replacement filters", ["bulk_supplies"])
oe("CleanPro Janitorial Wholesale", D(2027, 3, 3), 1690.00,
   "Bulk cleaning chemicals and restroom supplies to cover the year", ["bulk_supplies"])
oe("Alder Design Studio", D(2026, 9, 22), 14000.00,
   "50% deposit on website redesign project, balance due on launch", ["project_deposit"])
oe("Keystone General Contractors", D(2027, 4, 6), 48500.00,
   "First milestone payment (30%) for office build-out, phase 1 completion", ["project_deposit"])
oe("Brightpath Software Development", D(2027, 5, 17), 20000.00,
   "Retainer toward custom integration project, applied against deliverables on acceptance", ["project_deposit"])
oe("Whitaker Architects", D(2027, 6, 8), 9200.00,
   "40% design deposit for tenant improvement drawings", ["project_deposit"])
oe("Chamber of Commerce Greater Metro", D(2027, 1, 4), 395.00,
   "Annual membership renewal", ["small_membership"])
oe("Professional Accountants Network", D(2026, 12, 14), 275.00,
   "Annual membership dues, membership year 2027", ["small_membership"])
oe("Trade Journal Publishing", D(2027, 2, 2), 149.00,
   "Annual print and digital trade journal subscription", ["small_membership"])
oe("Southwest Airlines", D(2027, 1, 11), 5260.00,
   "Advance purchase of airfare for four separate client visits in February, May and September 2027", ["advance_travel"])
oe("Marriott Business Travel", D(2027, 2, 16), 3840.00,
   "Prepaid hotel stays for three conferences: March 2027, June 2027 and October 2027", ["advance_travel"])
oe("Amtrak Corporate", D(2027, 1, 19), 2900.00,
   "Prepaid rail tickets for client trips scheduled on various dates between January and June 2027", ["advance_travel"])
oe("Premier Promotional Products", D(2027, 7, 12), 6750.00,
   "500 branded tote bags and gifts for the annual customer conference in October 2027", ["goods_future_event"])
oe("Festivity Wholesale", D(2026, 11, 3), 1980.00,
   "Decorations and giveaway items for the December 2026 holiday party", ["goods_future_event"])
oe("Summit Apparel Co", D(2027, 4, 5), 4100.00,
   "200 embroidered company polo shirts for the May 2027 staff retreat", ["goods_future_event"])
oe("Nimbus Web Hosting", D(2027, 4, 3), 780.00,
   f"Hosting services for the month of March 2027", ["arrears"])
oe("Apex Cleaning Services", D(2027, 4, 8), 5400.00,
   "Janitorial services provided January through March 2027", ["arrears"])
oe("Prism IT Consulting", D(2026, 12, 4), 11250.00,
   "Consulting hours worked during November 2026", ["arrears"])
oe("Metro Auto Repair", D(2026, 11, 2), 1285.40,
   "Repair of delivery van, brake replacement completed October 28, 2026", ["plain"])
oe("Quickfix Plumbing", D(2027, 1, 11), 640.00,
   "Emergency pipe repair service call performed January 9, 2027", ["plain"])


def validate(records):
    assert len(records) == 48, len(records)
    seen_v = set()
    for r in records:
        assert r["vendor"] not in seen_v, f"duplicate vendor {r['vendor']}"
        seen_v.add(r["vendor"])
        assert r["true_label"] in {"multi_period_prepayment", "one_time_prepayment", "ordinary_expense"}
        if r["true_label"] != "ordinary_expense":
            s, e = date.fromisoformat(r["true_coverage_start"]), date.fromisoformat(r["true_coverage_end"])
            assert e >= s
            same_month = (s.year, s.month) == (e.year, e.month)
            if r["true_label"] == "multi_period_prepayment":
                assert not same_month, f"{r['vendor']}: multi-period inside one month"
            else:
                assert same_month, f"{r['vendor']}: one-time spans months"
    for name in ("tuning_set.json", "holdout_set.json"):
        p = DATA / name
        if p.exists():
            old = {x["vendor"] for x in json.load(open(p))}
            assert not (old & seen_v), f"vendor overlap with {name}: {old & seen_v}"


def main():
    validate(R)
    random.Random(7).shuffle(R)          # interleave classes; fixed seed
    for i, r in enumerate(R, 1):
        r["id"] = f"H2-{i:03d}"
    out = [{"id": r["id"], **{k: v for k, v in r.items() if k != "id"}} for r in R]
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    from collections import Counter
    print("Wrote", OUT, "|", dict(Counter(r["true_label"] for r in out)))


if __name__ == "__main__":
    main()





    