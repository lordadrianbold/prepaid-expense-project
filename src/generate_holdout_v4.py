"""
Project 6: holdout v4, 48 records, the FRESH set.

Written after prompt v4 was fixed and BEFORE any model ever saw these records.
Purpose: one untouched end-to-end test. Whatever it scores is the reported
result; no tuning against it afterwards.

COMPOSITION: 12 one_time_prepayment, 14 multi_period (4 duration-only terms,
3 partly elapsed), 22 ordinary_expense (goods, project deposits, non-contiguous
travel, bulk supplies, services in arrears, 3 small memberships, plain repairs).
LABELING POLICY: same as v2/v3. A term already under way at the invoice date but
ending after it (partly_elapsed) is a multi_period_prepayment; the elapsed months
need a catch-up entry. All vendors are fictional and new.
"""
import json
import random
from calendar import monthrange
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "holdout_v4.json"
D = date


def fm(d):
    return f"{d:%B} {d.day}, {d.year}"


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, min(d.day, monthrange(d.year + y, m + 1)[1]))


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


# ---------------- one-time prepayments (12) ----------------
s = e = D(2027, 3, 4)
ot("Harborview Convention Hall", D(2027, 1, 12), 8450.00, f"Ballroom rental for sales conference on {fm(s)}", ["event_rental"], s=s, e=e)
s, e = D(2027, 4, 12), D(2027, 4, 15)
ot("Redwood Summit Lodge", D(2027, 2, 3), 13320.00, f"Lodging for 18 guests, nights of {fm(s)} through {fm(e)}", ["lodging"], s=s, e=e)
s, e = D(2027, 6, 9), D(2027, 6, 13)
ot("Alpine Rigging & Staging", D(2027, 4, 5), 5900.00, f"Stage and lighting rig rental, rental period {fm(s)} to {fm(e)}", ["equipment_rental"], s=s, e=e)
s, e = D(2027, 5, 17), D(2027, 5, 19)
ot("Brightwater Seminars", D(2027, 3, 10), 3600.00, f"Project management bootcamp tuition for 3 staff, sessions {fm(s)} through {fm(e)}", ["training"], s=s, e=e)
s = e = D(2027, 7, 16)
ot("Lakeshore Yacht Charters", D(2027, 5, 3), 11750.00, f"Yacht charter for executive retreat on {fm(s)}", ["event_rental"], s=s, e=e)
s = e = D(2027, 4, 6)
ot("Summit Legal Videography", D(2027, 2, 22), 3250.00, f"Videographer booking for deposition recording on {fm(s)}", ["service_booking"], s=s, e=e)
s = e = D(2027, 1, 21)
ot("Copperline Studio Rentals", D(2026, 12, 8), 2400.00, f"Studio space rental for product photoshoot on {fm(s)}", ["event_rental"], s=s, e=e)
s, e = D(2027, 4, 27), D(2027, 4, 29)
ot("Tidewater Expo Group", D(2027, 1, 27), 16800.00, f"Exhibit space at Midwest Logistics Show, show dates {fm(s)} to {fm(e)}", ["trade_show"], s=s, e=e)
s, e = D(2027, 9, 14), D(2027, 9, 16)
ot("Aspen Ridge Retreat Center", D(2027, 6, 14), 9600.00, f"Retreat facility booking for leadership offsite, stay dates {fm(s)} through {fm(e)}", ["lodging"], s=s, e=e)
s = e = D(2027, 5, 25)
ot("Keystone Translation Partners", D(2027, 3, 29), 2750.00, f"On-site translators for regulatory hearing on {fm(s)}", ["service_booking"], s=s, e=e)
s = e = D(2027, 8, 21)
ot("Pacific Crest Tent & Event", D(2027, 7, 8), 4180.00, f"Tent and seating rental for customer picnic on {fm(s)}", ["event_rental"], s=s, e=e)
s, e = D(2027, 10, 4), D(2027, 10, 7)
ot("Beacon Hill Workshops", D(2027, 8, 17), 6250.00, f"Safety instructor workshop fee, workshop dates {fm(s)} through {fm(e)}", ["training"], s=s, e=e)

# ---------------- multi-period prepayments (14) ----------------
s, e = D(2027, 3, 1), D(2028, 2, 29)
mp("Caldwell Mutual Group", D(2027, 2, 10), 31800.00, f"Commercial auto fleet policy, policy period {fm(s)} through {fm(e)}", ["insurance", "leap_year"], s=s, e=e)
s = D(2027, 4, 1); e = term_end(s, 24)
mp("Ironwood Software Licensing", D(2027, 3, 18), 24000.00, f"Enterprise analytics subscription, 24-month term beginning {fm(s)}", ["saas", "duration_only", "multi_year"], s=s, e=e)
s = D(2027, 6, 1); e = term_end(s, 6)
mp("Silverton Realty Trust", D(2027, 5, 20), 36000.00, f"Prepaid rent for warehouse unit 4, 6-month period starting {fm(s)}", ["rent", "duration_only"], s=s, e=e)
s, e = D(2027, 2, 1), D(2027, 7, 31)
mp("Northgate Facilities Care", D(2027, 1, 5), 14400.00, f"Janitorial services contract, service period {fm(s)} through {fm(e)}", ["services"], s=s, e=e)
s = D(2027, 5, 15); e = term_end(s, 18)
mp("Waverly Data Backup", D(2027, 4, 14), 9360.00, f"Cloud backup service, 18-month term commencing {fm(s)}", ["saas", "duration_only", "mid_month_start"], s=s, e=e)
s, e = D(2027, 1, 1), D(2027, 12, 31)
mp("Pinecrest Underwriters", D(2026, 12, 2), 48750.00, f"Cyber liability policy, policy period {fm(s)} through {fm(e)}", ["insurance"], s=s, e=e)
s, e = D(2027, 7, 1), D(2029, 6, 30)
mp("Cardinal Elevator Maintenance", D(2027, 6, 2), 18600.00, f"Elevator maintenance agreement, coverage {fm(s)} to {fm(e)}", ["maintenance", "multi_year"], s=s, e=e)
s = D(2027, 8, 10); e = term_end(s, 12)
mp("Juniper Fleet Telematics", D(2027, 7, 19), 7800.00, f"Vehicle tracking subscription, 12-month term beginning {fm(s)}", ["saas", "duration_only", "mid_month_start", "leap_year"], s=s, e=e)
s = D(2027, 3, 1); e = term_end(s, 36)
mp("Harlow Archive Storage", D(2027, 2, 25), 5400.00, f"Document storage contract, 3-year term starting {fm(s)}", ["storage", "duration_only", "multi_year"], s=s, e=e)
s, e = D(2027, 9, 1), D(2028, 8, 31)
mp("Stratus Fire Protection", D(2027, 8, 4), 6720.00, f"Fire alarm monitoring, service period {fm(s)} through {fm(e)}", ["services", "leap_year"], s=s, e=e)
s, e = D(2027, 2, 15), D(2028, 2, 14)
mp("Marlowe Tax Software", D(2027, 1, 22), 12900.00, f"Tax preparation software license, license term {fm(s)} through {fm(e)}", ["saas", "mid_month_start", "leap_year"], s=s, e=e)
s, e = D(2027, 1, 1), D(2027, 12, 31)
mp("Delmar Compliance Training", D(2027, 4, 12), 15600.00, f"Annual compliance training library, service period {fm(s)} through {fm(e)}", ["saas", "partly_elapsed"], s=s, e=e)
s, e = D(2027, 3, 15), D(2028, 3, 14)
mp("Ashford Pest Control", D(2027, 5, 27), 3960.00, f"Pest control service agreement, term {fm(s)} through {fm(e)}", ["services", "partly_elapsed", "leap_year"], s=s, e=e)
s, e = D(2027, 1, 1), D(2027, 6, 30)
mp("Lantern Security Monitoring", D(2027, 3, 8), 8400.00, f"Alarm monitoring, service period {fm(s)} through {fm(e)}", ["services", "partly_elapsed"], s=s, e=e)

# ---------------- ordinary expenses (22) ----------------
oe("Greenfield Packaging Supply", D(2027, 2, 9), 6480.00, "Six-month supply of shipping cartons, tape and labels", ["bulk_supplies"])
oe("Ridgecrest Builders", D(2027, 3, 15), 42000.00, "Deposit (40%) for warehouse renovation, due on contract signing", ["project_deposit"])
oe("Atlas Corporate Travel", D(2027, 4, 8), 3150.00, "Airfare for three trips: Denver in May, Chicago in July, Boston in October", ["noncontiguous_travel"])
oe("Fairmont Office Furnishings", D(2027, 1, 18), 8920.00, "Ergonomic chairs and standing desks for new hires", ["goods"])
oe("Sterling Print & Promo", D(2027, 5, 11), 4380.00, "Branded jackets and tote bags for client appreciation event in June", ["goods_for_event"])
oe("Westbrook Industrial Supply", D(2027, 6, 23), 2710.00, "Annual supply of safety gloves, goggles and respirator filters, delivered in two shipments", ["bulk_supplies"])
oe("Clearwater Janitorial", D(2027, 4, 1), 5400.00, f"Cleaning services for the period {fm(D(2027, 1, 1))} through {fm(D(2027, 3, 31))}", ["arrears"])
oe("Hollis Auto Care", D(2027, 2, 14), 1865.40, "Brake replacement and engine diagnostics, fleet vehicle 14", ["repair"])
oe("Lakeland Chamber of Commerce", D(2027, 1, 4), 275.00, "Annual membership dues, membership year 2027", ["small_membership"])
oe("Regional Bookkeepers Association", D(2027, 2, 2), 395.00, f"Annual membership renewal, membership period {fm(D(2027, 3, 1))} through {fm(D(2028, 2, 29))}", ["small_membership"])
oe("Digital Trade Review", D(2027, 3, 3), 189.00, f"Annual online subscription, period {fm(D(2027, 4, 1))} to {fm(D(2028, 3, 31))}", ["small_membership"])
oe("Brightpath Consulting", D(2027, 5, 4), 18500.00, "Milestone 2 payment for ERP implementation, system design phase", ["project_deposit"])
oe("Cascade Software Support", D(2027, 6, 8), 7350.00, f"Hourly technical support for the period {fm(D(2027, 4, 1))} through {fm(D(2027, 5, 31))}, billed in arrears", ["arrears"])
oe("Mason & Pike Electrical", D(2027, 7, 13), 1495.00, "Replacement of lighting fixtures in conference room", ["repair"])
oe("Redline Courier Services", D(2027, 8, 10), 960.00, "Courier and delivery charges for July 2027", ["arrears"])
oe("Peakview Marketing Agency", D(2027, 3, 24), 9000.00, "Retainer, creative campaign project deposit due on kickoff", ["project_deposit"])
oe("Sunrise Uniforms", D(2027, 4, 26), 3290.00, "Employee uniforms and name badges for new store opening in August", ["goods_for_event"])
oe("Crossroads Event Gifts", D(2027, 9, 6), 2140.00, "Award plaques and engraved gifts for annual recognition dinner in November", ["goods_for_event"])
oe("Trailhead Travel Management", D(2027, 5, 17), 5780.00, "Hotel and flights for sales team visits to Seattle in June, Austin in August and Miami in November", ["noncontiguous_travel"])
oe("Granite State Equipment Repair", D(2027, 2, 23), 2380.00, "Calibration and repair of lab instruments, work completed February 2027", ["repair"])
oe("Evergreen Copy Center", D(2027, 6, 30), 1260.00, "Printing of marketing brochures and catalogs", ["goods"])
oe("Silverline Training Supplies", D(2027, 1, 28), 3640.00, "Binders, workbooks and handouts for spring training sessions", ["goods_for_event"])


def validate(records):
    assert len(records) == 48, len(records)
    assert Counter(r["true_label"] for r in records) == {
        "one_time_prepayment": 12, "multi_period_prepayment": 14, "ordinary_expense": 22}
    vendors = [r["vendor"] for r in records]
    assert len(set(vendors)) == len(vendors), "duplicate vendor"
    latest = date(2027, 10, 31)
    for r in records:
        inv = date.fromisoformat(r["invoice_date"])
        assert inv <= latest
        if r["true_label"] != "ordinary_expense":
            s, e = date.fromisoformat(r["true_coverage_start"]), date.fromisoformat(r["true_coverage_end"])
            assert e >= s
            same = (s.year, s.month) == (e.year, e.month)
            assert same == (r["true_label"] == "one_time_prepayment"), f"{r['vendor']}: label vs month span"
            if "partly_elapsed" in r["tags"]:
                assert s < inv <= e, f"{r['vendor']}: not actually partly elapsed"
            else:
                assert inv < s, f"{r['vendor']}: paid after coverage began"
    for name in ("tuning_set.json", "holdout_set.json", "holdout_v2.json", "holdout_v3.json"):
        p = DATA / name
        if p.exists():
            old = {x["vendor"] for x in json.load(open(p))}
            assert not (old & set(vendors)), f"vendor overlap with {name}: {old & set(vendors)}"
    from src.identify import PROMPTS
    for ver, text in PROMPTS.items():
        for r in records:
            assert r["vendor"] not in text, f"{r['vendor']} appears in prompt {ver}"
            assert r["description"] not in text, f"description appears in prompt {ver}"


def main():
    validate(R)
    random.Random(21).shuffle(R)
    out = [{"id": f"H4-{i:03d}", **r} for i, r in enumerate(R, 1)]
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Wrote", OUT, "|", dict(Counter(r["true_label"] for r in out)))


if __name__ == "__main__":
    main()





    