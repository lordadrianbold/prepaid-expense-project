"""Offline tests: no API key needed. Run: python -m pytest -q"""
import json
from datetime import date
from decimal import Decimal

import pytest

from src import journal
from src.identify import build_prompt, identify_single, parse_model_json
from src.pipeline import process_record, run_pipeline, truth_identifier
from src.schedule import build_schedule


# ---------- schedule ----------
def test_twelve_month_policy_sums_exactly():
    rows = build_schedule(18600, "2026-04-01", "2027-03-31")
    assert len(rows) == 12
    assert sum(r["amount"] for r in rows) == Decimal("18600.00")
    assert rows[-1]["remaining"] == Decimal("0.00")


def test_leap_year_february_has_29_days():
    rows = build_schedule(1000, "2028-01-01", "2028-03-31")
    feb = next(r for r in rows if r["period"] == "2028-02")
    assert feb["days"] == 29


def test_mid_month_start_prorates_by_days():
    rows = build_schedule(300, "2026-01-16", "2026-02-28")   # 16 + 28 = 44 days
    assert rows[0]["days"] == 16
    assert rows[0]["amount"] == Decimal("109.09")             # 300*16/44
    assert sum(r["amount"] for r in rows) == Decimal("300.00")


def test_monthly_equal_method():
    rows = build_schedule(1200, "2026-01-01", "2026-12-31", method="monthly_equal")
    assert all(r["amount"] == Decimal("100.00") for r in rows)


def test_single_period_one_row():
    assert len(build_schedule(500, "2026-05-03", "2026-05-20")) == 1


def test_bad_dates_and_amounts_raise():
    with pytest.raises(ValueError):
        build_schedule(100, "2026-05-10", "2026-05-01")
    with pytest.raises(ValueError):
        build_schedule(-5, "2026-01-01", "2026-02-01")


# ---------- identification plumbing ----------
REC = {"id": "T-1", "vendor": "Acme", "invoice_date": "2026-03-01", "amount": 12000.0,
       "description": "Annual software license, term April 1, 2026 to March 31, 2027"}


def test_prompt_builds_without_keyerror():
    """Regression: the first draft used str.format() on a prompt containing JSON braces."""
    p = build_prompt(REC)
    assert "Acme" in p and "<<" not in p and '"classification"' in p


def test_parse_handles_fences_and_garbage():
    ok = '```json\n{"classification":"ordinary_expense","reasoning":"x"}\n```'
    assert parse_model_json(ok)["classification"] == "ordinary_expense"
    assert parse_model_json("not json")["classification"] == "PARSE_ERROR"
    assert parse_model_json('{"classification":"banana"}')["classification"] == "PARSE_ERROR"


class _FakeClient:
    class messages:
        @staticmethod
        def create(**kw):
            class R:
                content = [type("C", (), {"text": json.dumps({
                    "is_prepayment": True, "classification": "multi_period_prepayment",
                    "coverage_start": "2026-04-01", "coverage_end": "2027-03-31",
                    "reasoning": "term stated"})})]
            return R


def test_identify_single_with_fake_client():
    out = identify_single(REC, client=_FakeClient())
    assert out["predicted_classification"] == "multi_period_prepayment"


# ---------- journal ----------
def test_entries_balance_and_map_accounts():
    item = process_record(REC, lambda r: {"id": "T-1", "vendor": "Acme",
        "predicted_classification": "multi_period_prepayment", "predicted_coverage_start": "2026-04-01",
        "predicted_coverage_end": "2027-03-31", "reasoning": "x"})
    assert item["treatment"] == "AMORTIZE" and len(item["entries"]) == 13   # 1 capitalize + 12 amortize
    for e in item["entries"]:
        assert sum(l["debit"] for l in e["lines"]) == sum(l["credit"] for l in e["lines"])
    assert item["entries"][1]["lines"][0]["account"] == "Software & Subscriptions Expense"
    total_amort = sum(l["credit"] for e in item["entries"][1:] for l in e["lines"])
    assert total_amort == Decimal("12000.00")


def test_unbalanced_entry_rejected():
    with pytest.raises(ValueError):
        journal._entry("2026-01-01", "m", "r",
                       [journal._line(("1", "A"), debit=Decimal("5")), journal._line(("2", "B"), credit=Decimal("4"))])


# ---------- pipeline guardrails: things that must go to a human ----------
def _ident(cls, s=None, e=None):
    return lambda r: {"id": r["id"], "vendor": r["vendor"], "predicted_classification": cls,
                      "predicted_coverage_start": s, "predicted_coverage_end": e, "reasoning": "r"}


def test_prepayment_without_dates_goes_to_review_not_booked():
    item = process_record(REC, _ident("multi_period_prepayment"))
    assert item["treatment"] == "REVIEW" and item["entries"] == [] and item["flags"]


def test_parse_error_goes_to_review():
    assert process_record(REC, _ident("PARSE_ERROR"))["treatment"] == "REVIEW"


def test_end_before_start_goes_to_review():
    assert process_record(REC, _ident("multi_period_prepayment", "2026-06-01", "2026-05-01"))["treatment"] == "REVIEW"


def test_ordinary_expense_has_no_schedule():
    item = process_record(REC, _ident("ordinary_expense"))
    assert item["treatment"] == "EXPENSE" and item["schedule"] == [] and len(item["entries"]) == 1


def test_prepayment_type_is_derived_from_dates_not_model_label():
    # model says multi-period, but dates sit in one month -> one-time, noted not flagged
    a = process_record(REC, _ident("multi_period_prepayment", "2026-05-01", "2026-05-20"))
    assert a["prepayment_type"] == "one_time_prepayment" and not a["flags"] and a["notes"]
    assert a["treatment"] == "AMORTIZE" and len(a["schedule"]) == 1
    # model says one-time, but dates span months -> multi-period
    b = process_record(REC, _ident("one_time_prepayment", "2026-05-15", "2026-06-14"))
    assert b["prepayment_type"] == "multi_period_prepayment" and len(b["schedule"]) == 2
    # agreement -> no note
    c = process_record(REC, _ident("multi_period_prepayment", "2026-05-01", "2026-12-31"))
    assert c["prepayment_type"] == "multi_period_prepayment" and not c["notes"]


def test_derive_prepayment_type_edges():
    from src.schedule import derive_prepayment_type as d
    assert d("2027-08-02", "2027-08-27") == "one_time_prepayment"
    assert d("2027-01-31", "2027-02-01") == "multi_period_prepayment"   # 2 days, 2 months
    assert d("2027-03-05", "2027-03-05") == "one_time_prepayment"
    assert d("2027-03-01", "2028-02-29") == "multi_period_prepayment"


def test_coverage_before_invoice_month_flagged():
    item = process_record(REC, _ident("multi_period_prepayment", "2026-01-01", "2026-12-31"))
    assert any("catch-up" in f for f in item["flags"])


# ---------- full datasets through pipeline + worksheet ----------
@pytest.mark.parametrize("name", ["tuning_set", "holdout_set", "holdout_v2", "holdout_v3"])
def test_datasets_run_end_to_end_and_every_schedule_ties(name, tmp_path):
    from src.config import DATA_DIR
    from src.worksheet import build_workbook
    records = json.load(open(DATA_DIR / f"{name}.json"))
    items = run_pipeline(records, truth_identifier)
    assert len(items) == len(records)
    for it in items:
        if it["schedule"]:
            assert sum(r["amount"] for r in it["schedule"]) == it["amount"]
    build_workbook(items, "2026-09", str(tmp_path / "w.xlsx"), demo=True)
    assert (tmp_path / "w.xlsx").exists()


def test_holdout_v2_structure_and_no_vendor_overlap():
    from collections import Counter
    from src.config import DATA_DIR
    v2 = json.load(open(DATA_DIR / "holdout_v2.json"))
    assert len(v2) == 48 and len({r["id"] for r in v2}) == 48
    assert Counter(r["true_label"] for r in v2) == {
        "ordinary_expense": 22, "multi_period_prepayment": 18, "one_time_prepayment": 8}
    old = {r["vendor"] for n in ("tuning_set", "holdout_set") for r in json.load(open(DATA_DIR / f"{n}.json"))}
    assert not old & {r["vendor"] for r in v2}


def test_evaluate_scores_and_tags():
    from src.evaluate import score
    preds = [
        {"id": "a", "predicted_classification": "ordinary_expense", "true_label": "ordinary_expense",
         "predicted_coverage_start": None, "predicted_coverage_end": None, "tags": ["plain"], "reasoning": ""},
        {"id": "b", "predicted_classification": "multi_period_prepayment", "true_label": "ordinary_expense",
         "predicted_coverage_start": "2026-01-01", "predicted_coverage_end": "2026-12-31", "tags": ["plain"], "reasoning": ""},
        {"id": "c", "predicted_classification": "ordinary_expense", "true_label": "multi_period_prepayment",
         "predicted_coverage_start": "null", "predicted_coverage_end": None,
         "true_coverage_start": "2026-01-01", "true_coverage_end": "2026-12-31", "tags": ["saas"], "reasoning": ""},
    ]
    s = score(preds)
    assert s["false_capitalizations"] == ["b"] and s["missed_prepayments"] == ["c"]
    assert s["by_tag"] == {"plain": "1/2", "saas": "0/1"}


# ---------- prompt versions, threshold, v3 ----------
@pytest.mark.parametrize("version", ["v1", "v2"])
def test_both_prompt_versions_build(version):
    p = build_prompt(REC, version)
    assert "Acme" in p and "<<" not in p and '"classification"' in p


def test_unknown_prompt_version_raises():
    with pytest.raises(ValueError):
        build_prompt(REC, "v9")


def test_prompt_version_env_switch(monkeypatch):
    monkeypatch.setenv("P6_PROMPT_VERSION", "v1")
    assert "THE KEY QUESTION" not in build_prompt(REC)
    monkeypatch.setenv("P6_PROMPT_VERSION", "v2")
    assert "THE KEY QUESTION" in build_prompt(REC)


def test_threshold_expenses_small_prepayment_even_if_model_says_prepaid():
    small = dict(REC, id="S-1", amount=275.0)
    item = process_record(small, _ident("multi_period_prepayment", "2027-01-01", "2027-12-31"))
    assert item["treatment"] == "EXPENSE" and item["schedule"] == []


def test_pipeline_level_scoring_applies_threshold():
    from src.evaluate import score
    preds = [{"id": "m", "predicted_classification": "multi_period_prepayment", "true_label": "ordinary_expense",
              "predicted_coverage_start": "2027-01-01", "predicted_coverage_end": "2027-12-31",
              "amount": 275.0, "tags": ["small_membership"], "reasoning": ""},
             {"id": "n", "predicted_classification": "ordinary_expense", "true_label": "one_time_prepayment",
              "predicted_coverage_start": None, "predicted_coverage_end": None,
              "true_coverage_start": "2027-06-14", "true_coverage_end": "2027-06-16",
              "amount": 8160.0, "tags": ["lodging"], "reasoning": ""}]
    s = score(preds)
    assert s["false_capitalizations"] == ["m"]                       # model level
    assert s["pipeline_level"]["false_capitalizations"] == []         # threshold catches it
    assert s["pipeline_level"]["missed_prepayments"] == ["n"]         # threshold can't catch a miss


def test_pipeline_level_scoring_uses_derived_type_not_model_label():
    from src.evaluate import score
    p = {"id": "x", "predicted_classification": "multi_period_prepayment", "true_label": "one_time_prepayment",
         "predicted_coverage_start": "2027-08-02", "predicted_coverage_end": "2027-08-27",
         "true_coverage_start": "2027-08-02", "true_coverage_end": "2027-08-27",
         "amount": 3880.0, "tags": [], "reasoning": ""}
    s = score([p])
    assert s["correct"] == 0                      # model level: label wrong
    assert s["pipeline_level"]["correct"] == 1    # pipeline level: dates decide the type


def test_holdout_v3_structure_no_overlap_no_prompt_leakage():
    from collections import Counter
    from src.config import DATA_DIR
    from src.identify import PROMPTS
    v3 = json.load(open(DATA_DIR / "holdout_v3.json"))
    assert len(v3) == 40 and len({r["id"] for r in v3}) == 40
    assert Counter(r["true_label"] for r in v3) == {
        "one_time_prepayment": 14, "multi_period_prepayment": 8, "ordinary_expense": 18}
    old = {r["vendor"] for n in ("tuning_set", "holdout_set", "holdout_v2") for r in json.load(open(DATA_DIR / f"{n}.json"))}
    assert not old & {r["vendor"] for r in v3}
    for text in PROMPTS.values():
        assert not any(r["vendor"] in text or r["description"] in text for r in v3)


# ---------- renderer + end-to-end extraction harness (offline) ----------
def test_renderer_writes_valid_pdfs_and_photos_with_manifest(tmp_path):
    import subprocess, sys
    from src import render_invoices as r
    recs = json.load(open(r.DATA_DIR / "holdout_v3.json"))[:6]
    for i, rec in enumerate(recs):
        layout = r.LAYOUTS[i % 4]
        pdf = r.render_pdf(rec, layout, "t")
        assert pdf[:4] == b"%PDF"
        jpg = r.photograph(pdf, r.LEVELS[i % 3], "t")
        assert jpg[:2] == b"\xff\xd8"                      # JPEG magic bytes


def test_rendered_invoice_contains_truth_and_a_testdata_watermark():
    import pymupdf
    from src import render_invoices as r
    recs = json.load(open(r.DATA_DIR / "holdout_v3.json"))
    for i, rec in enumerate(recs):
        text = pymupdf.open(stream=r.render_pdf(rec, r.LAYOUTS[i % 4], "t"), filetype="pdf")[0].get_text()
        assert f"{rec['amount']:,.2f}" in text, rec["id"]           # total due is printed
        assert "SAMPLE - TEST DATA" in text and "Not a real invoice" in text
        flat = " ".join(text.split())
        assert " ".join(rec["description"].split()) in flat, f"{rec['id']}: description not printed intact"


def test_tax_lines_always_sum_to_amount_due():
    import random
    from src import render_invoices as r
    for rec in json.load(open(r.DATA_DIR / "holdout_v3.json")):
        for layout in r.LAYOUTS:
            x = r.make_context(rec, layout, random.Random(f"6-{rec['id']}"))
            assert round(x["subtotal"] + x["tax"], 2) == round(x["amount"], 2)


def test_field_checks_and_vendor_normalization():
    from src.evaluate_extraction import amount_ok, vendor_ok
    assert vendor_ok("Snowflake Inc", "Snowflake Inc.") and vendor_ok("SNOWFLAKE", "Snowflake Inc.")
    assert vendor_ok("Pioneer Scaffold and Lift Rental", "Pioneer Scaffold & Lift Rental")
    assert not vendor_ok("Different Vendor LLC", "Snowflake Inc.") and not vendor_ok(None, "X")
    assert amount_ok("$21,600.00", 21600.0) and not amount_ok("21600.50", 21600.0) and not amount_ok(None, 1)


def test_end_to_end_harness_plumbing_with_fake_extractor_and_identifier():
    from pathlib import Path
    from src.evaluate_extraction import evaluate_entry, summarize
    entry = {"file": "pdf/x.pdf", "record_id": "H3-001", "vendor": "Stonebridge Office Systems",
             "invoice_date": "2027-07-15", "amount": 21600.0, "true_label": "multi_period_prepayment",
             "true_coverage_start": "2027-08-01", "true_coverage_end": "2030-07-31",
             "tags": ["maintenance"], "kind": "pdf", "level": "clean", "layout": "A_classic"}
    good = lambda p: {"vendor": "Stonebridge Office Systems", "invoice_date": "2027-07-15", "amount": 21600.0,
                      "description": "Equipment service agreement, 36-month term August 1, 2027 to July 31, 2030"}
    ident = lambda r: {"id": r["id"], "vendor": r["vendor"], "predicted_classification": "multi_period_prepayment",
                       "predicted_coverage_start": "2027-08-01", "predicted_coverage_end": "2030-07-31", "reasoning": "x"}
    row = evaluate_entry(entry, Path("."), good, ident)
    assert all(row["fields"].values()) and row["prediction"]["predicted_classification"] == "multi_period_prepayment"
    bad_amt = lambda p: dict(good(p), amount=2160.0)                 # a dropped zero
    row2 = evaluate_entry(entry, Path("."), bad_amt, ident)
    assert row2["fields"]["amount"] is False
    failed = lambda p: {"extraction_error": "boom"}
    row3 = evaluate_entry(entry, Path("."), failed, ident)
    assert row3["prediction"]["predicted_classification"] == "PARSE_ERROR"
    out = summarize([row, row2, row3])
    assert "ALL" in out and "kind:pdf" in out and "layout:A_classic" in out


# ---------- document checks: replay of the three REAL failure shapes seen on photos ----------
from src.document_checks import check_extraction


def _ext(**kw):
    base = {"vendor": "V", "invoice_date": "2027-09-01", "due_date": "2027-10-16", "subtotal": 5094.34,
            "tax": 305.66, "amount": 5400.0, "description": "Certification course fee, class dates October 12, 2027 to October 15, 2027",
            "notes": None, "fields_with_disagreement": [], "image_long_side": None}
    base.update(kw)
    return base


def test_clean_extraction_passes_all_checks():
    assert check_extraction(_ext()) == {"blocking": [], "warnings": []}


def test_H3_024_shape_digit_swap_in_amount_is_caught_by_footing():
    # real failure: total read as 5,904.34 although subtotal+tax = 5,400.00
    r = check_extraction(_ext(amount=5904.34))
    assert any("Footing check failed" in m for m in r["blocking"])


def test_H3_024_shape_digit_swap_in_subtotal_is_also_caught():
    r = check_extraction(_ext(subtotal=5904.34))
    assert any("Footing check failed" in m for m in r["blocking"])


def test_H3_021_shape_misread_year_is_caught_by_due_date_plausibility():
    # real failure: invoice date read as 2007-01-25 instead of 2027-01-20
    r = check_extraction(_ext(invoice_date="2007-01-25", due_date="2027-02-19"))
    assert any("implausible" in m for m in r["blocking"])


def test_H3_035_shape_dropped_notes_block_is_caught():
    # real failure: only the generic line item was captured, the Notes block was lost
    lost = _ext(description="Charges per agreement (see notes below)", notes=None)
    assert any("not captured" in m for m in check_extraction(lost)["blocking"])
    kept = _ext(description="Charges per agreement (see notes below)",
                notes="Dockside venue buyout for client reception on October 1, 2027")
    assert check_extraction(kept)["blocking"] == []


def test_no_tax_line_still_foots_when_subtotal_equals_total():
    assert check_extraction(_ext(subtotal=5400.0, tax=None))["blocking"] == []
    assert check_extraction(_ext(subtotal=5300.0, tax=None))["blocking"]       # 100 unexplained


def test_low_resolution_is_always_review_and_pdfs_and_sharp_photos_are_exempt():
    r = check_extraction(_ext(image_long_side=1100))
    assert any("To be reviewed by user" in b for b in r["blocking"])
    assert check_extraction(_ext(image_long_side=1600))["blocking"] == []
    assert check_extraction(_ext(image_long_side=None))["blocking"] == []


def test_run_disagreement_and_missing_fields_block():
    assert check_extraction(_ext(fields_with_disagreement=["invoice_date"]))["blocking"]
    assert check_extraction(_ext(amount=None))["blocking"]
    assert check_extraction(_ext(invoice_date=None))["blocking"]
    assert check_extraction({"extraction_error": "boom"})["blocking"]


# ---------- temperature, extraction parsing, pipeline gating ----------
class _CaptureClient:
    def __init__(self, text):
        self.kw, self.text = None, text
        outer = self
        class _M:
            @staticmethod
            def create(**kw):
                outer.kw = kw
                return type("R", (), {"content": [type("C", (), {"text": outer.text})]})
        self.messages = _M


def test_both_model_calls_use_temperature_zero():
    from src.config import TEMPERATURE
    assert TEMPERATURE == 0.0
    c = _CaptureClient(json.dumps({"classification": "ordinary_expense", "reasoning": "x"}))
    identify_single(REC, client=c)
    assert c.kw["temperature"] == 0.0
    from pathlib import Path
    from src.extract_invoice import extract_once
    import tempfile
    c2 = _CaptureClient(json.dumps({"vendor": "V", "amount": "$1,234.50", "subtotal": "1,200.00", "tax": 34.5}))
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(b"\xff\xd8\xff")
    out = extract_once(Path(f.name), c2)
    assert c2.kw["temperature"] == 0.0
    assert out["amount"] == 1234.5 and out["subtotal"] == 1200.0 and out["tax"] == 34.5


def test_process_extracted_blocks_suspicious_reads_and_books_clean_ones():
    from src.pipeline import process_extracted
    ok = {"id": "X1", "vendor": "Acme", "invoice_date": "2026-03-01", "amount": 12000.0, "subtotal": None,
          "tax": None, "due_date": "2026-03-31",
          "description": "Annual software license, term April 1, 2026 to March 31, 2027", "notes": None}
    ident = _ident("multi_period_prepayment", "2026-04-01", "2027-03-31")
    good = process_extracted(ok, ident)
    assert good["treatment"] == "AMORTIZE" and len(good["entries"]) == 13
    bad = process_extracted(dict(ok, invoice_date="2006-03-01"), ident)       # misread year
    assert bad["treatment"] == "REVIEW" and bad["entries"] == [] and bad["schedule"] == []
    assert any("implausible" in f for f in bad["flags"])
    dead = process_extracted({"id": "X2", "extraction_error": "boom"}, ident)
    assert dead["treatment"] == "REVIEW"


def test_notes_text_reaches_identification():
    from src.pipeline import usable_record
    u = usable_record({"id": "N", "vendor": "V", "invoice_date": "2027-08-30", "amount": 9800.0,
                       "description": "Charges per agreement (see notes below)",
                       "notes": "Dockside venue buyout for client reception on October 1, 2027"})
    assert "October 1, 2027" in u["description"] and "Charges per agreement" in u["description"]


def test_control_metric_separates_caught_from_silent_errors():
    from pathlib import Path
    from src.evaluate_extraction import evaluate_entry
    entry = {"file": "x.jpg", "record_id": "H", "vendor": "V", "invoice_date": "2027-09-01", "amount": 5400.0,
             "true_label": "ordinary_expense", "true_coverage_start": None, "true_coverage_end": None,
             "tags": [], "kind": "photo", "level": "heavy", "layout": "D_dense"}
    ident = lambda r: {"id": r["id"], "vendor": r["vendor"], "predicted_classification": "ordinary_expense",
                       "predicted_coverage_start": None, "predicted_coverage_end": None, "reasoning": "x"}
    caught = evaluate_entry(entry, Path("."), lambda p: _ext(vendor="V", amount=5904.34, description="supplies"), ident)
    assert caught["wrong"] and caught["flagged"]                     # wrong AND flagged: caught
    silent = evaluate_entry(entry, Path("."), lambda p: _ext(vendor="V", subtotal=None, tax=None, amount=5900.0,
                                                             description="supplies"), ident)
    assert silent["wrong"] and not silent["flagged"]                 # wrong, nothing to catch it: SILENT
    fine = evaluate_entry(entry, Path("."), lambda p: _ext(vendor="V", description="supplies"), ident)
    assert not fine["wrong"] and not fine["flagged"]


def test_rendered_invoices_never_name_real_businesses():
    import pymupdf
    from src import render_invoices as r
    real = ["Atlassian", "Snowflake", "Okta", "HubSpot", "Esri", "Southwest Airlines", "Marriott", "Amtrak",
            "Uline", "Quill Corporation", "Grainger", "Jira", "Confluence", "Salesforce", "Adobe Inc", "Zendesk",
            "Delta Airlines", "United Airlines", "Costco", "Staples", "NetSuite", "DataDog", "Total Wine",
            "Amazon", "Office Depot", "Uline", "Verizon", "Travelers", "Ironclad"]
    from src.config import DATA_DIR
    for name in ("holdout_v2.json", "tuning_set.json", "holdout_set.json", "holdout_v3.json"):
        for i, rec in enumerate(json.load(open(DATA_DIR / name))):
            text = pymupdf.open(stream=r.render_pdf(r.fictionalize(rec), r.LAYOUTS[i % 4], "t"), filetype="pdf")[0].get_text()
            for bad in real:
                assert bad not in text, f"{name}/{rec['id']} renders real name {bad!r}"


def test_temperature_rejected_by_old_sdk_is_retried_without_it():
    import src.llm as llm
    llm.TEMPERATURE_APPLIED = True
    calls = []
    class _M:
        @staticmethod
        def create(**kw):
            calls.append(kw)
            if "temperature" in kw:
                raise TypeError("Messages.create() got an unexpected keyword argument 'temperature'")
            return "ok"
    client = type("C", (), {"messages": _M})
    assert llm.create_message(client, model="m", max_tokens=1) == "ok"
    assert "temperature" not in calls[-1] and llm.TEMPERATURE_APPLIED is False
    llm.TEMPERATURE_APPLIED = True


def test_unrelated_type_errors_are_not_swallowed():
    import src.llm as llm
    llm.TEMPERATURE_APPLIED = True
    class _M:
        @staticmethod
        def create(**kw):
            raise TypeError("something else")
    client = type("C", (), {"messages": _M})
    with pytest.raises(TypeError):
        llm.create_message(client, model="m", max_tokens=1)


def test_implausible_invoice_year_is_blocked():
    from datetime import date
    from src.document_checks import check_extraction
    base = {"amount": 100.0, "subtotal": None, "tax": None, "description": "x"}
    today = date(2026, 10, 1)
    assert check_extraction(dict(base, invoice_date="2028-10-05"), today=today)["blocking"]
    assert check_extraction(dict(base, invoice_date="2021-10-05"), today=today)["blocking"]
    assert not check_extraction(dict(base, invoice_date="2026-11-05"), today=today)["blocking"]


def test_ordinary_expense_with_open_service_period_goes_to_review():
    from src.pipeline import process_record
    rec = {"id": "X", "vendor": "V", "invoice_date": "2026-03-15", "amount": 9600.0, "description": "d"}
    def ident(coverage_end):
        return lambda r: {"id": "X", "vendor": "V", "predicted_classification": "ordinary_expense",
                          "predicted_coverage_start": "2026-01-01", "predicted_coverage_end": coverage_end,
                          "reasoning": ""}
    item = process_record(rec, ident("2026-12-31"))
    assert item["treatment"] == "REVIEW" and not item["entries"]
    assert process_record(rec, ident("2026-02-28"))["treatment"] == "EXPENSE"   # already ended
    assert process_record(rec, ident(None))["treatment"] == "EXPENSE"


def test_description_disagreement_ignores_wording_but_not_dates():
    from src.extract_invoice import _desc_signature
    a = "Annual dues, membership year 2027 (Jan 1 - Dec 31)"
    b = "annual   membership dues - membership year 2027, Jan 1 to Dec 31"
    assert _desc_signature(a) == _desc_signature(b)
    assert _desc_signature("shoot on November 9, 2026") != _desc_signature("shoot on November 9, 2028")
    assert _desc_signature("fee $1,200.00") != _desc_signature("fee $1,020.00")


def test_end_from_term_is_computed_in_code():
    from datetime import date
    from src.schedule import end_from_term
    assert end_from_term("2026-11-16", 12) == date(2027, 11, 15)
    assert end_from_term("2027-09-01", 24) == date(2029, 8, 31)
    assert end_from_term("2027-03-01", 36) == date(2030, 2, 28)
    assert end_from_term("2027-01-31", 1) == date(2027, 2, 27)


def test_apply_term_fills_missing_end_only():
    from src.identify import apply_term
    p = apply_term({"coverage_start": "2027-09-01", "coverage_end": None, "term_months": 24})
    assert p["coverage_end"] == "2029-08-31"
    q = apply_term({"coverage_start": "2027-09-01", "coverage_end": "2028-08-31", "term_months": 24})
    assert q["coverage_end"] == "2028-08-31"          # model-supplied end is not overridden
    assert apply_term({"coverage_start": None, "coverage_end": None, "term_months": 12})["coverage_end"] is None


def test_prompt_v3_asks_for_term_not_arithmetic():
    from src.identify import PROMPTS, build_prompt
    assert "term_months" in PROMPTS["v3"] and "term_months" not in PROMPTS["v2"]
    assert "Code computes the end date" in build_prompt(REC, "v3")


def test_end_before_start_is_scored_wrong_at_pipeline_level():
    from src.evaluate import score
    p = {"id": "X", "predicted_classification": "multi_period_prepayment", "true_label": "multi_period_prepayment",
         "predicted_coverage_start": "2027-09-01", "predicted_coverage_end": "2027-08-31",
         "true_coverage_start": "2027-09-01", "true_coverage_end": "2029-08-31", "amount": 4320.0, "reasoning": ""}
    assert score([p])["pipeline_level"]["correct"] == 0


def test_malformed_json_with_unescaped_quote_is_recovered():
    from src.identify import apply_term, parse_model_json
    raw = ('{\n "is_prepayment": true,\n "classification": "multi_period_prepayment",\n'
           ' "coverage_start": "2027-01-01",\n "coverage_end": null,\n "term_months": 24,\n'
           ' "reasoning": "The description says "24-month policy term" which is explicit."\n}')
    out = apply_term(parse_model_json(raw))
    assert out["classification"] == "multi_period_prepayment"
    assert out["coverage_end"] == "2028-12-31"


def test_unrecoverable_output_is_still_a_parse_error():
    from src.identify import parse_model_json
    assert parse_model_json("sorry, I cannot do that")["classification"] == "PARSE_ERROR"
    assert parse_model_json('{"classification": "banana", oops')["classification"] == "PARSE_ERROR"


def test_prompt_v4_covers_partly_elapsed_and_has_no_leakage():
    from src.identify import PROMPTS
    t = PROMPTS["v4"]
    assert "PARTLY ELAPSED" in t and "ENTIRE stated service period" in t and "term_months" in t
    assert "PARTLY ELAPSED" not in PROMPTS["v3"]


def test_prompt_v5_adds_expiration_rule_and_keeps_v4_rules():
    from src.identify import PROMPTS
    from src.config import DEFAULT_PROMPT_VERSION
    v4, v5 = PROMPTS["v4"], PROMPTS["v5"]
    assert "LAST COVERED DAY" in v5 and "LAST COVERED DAY" not in v4
    assert "2027-05-16" in v5 and "as written" in v5
    for must in ("PARTLY ELAPSED", "term_months", "ENTIRE stated service period", "<<DESCRIPTION>>"):
        assert must in v5
    assert DEFAULT_PROMPT_VERSION == "v6"


def test_prompt_v6_asks_for_flag_not_arithmetic_and_keeps_rules():
    from src.identify import PROMPTS
    v6 = PROMPTS["v6"]
    assert "end_is_expiration" in v6 and "Do NOT subtract a day yourself" in v6
    assert "LAST COVERED DAY" not in v6
    for must in ("PARTLY ELAPSED", "term_months", "ENTIRE stated service period", "<<DESCRIPTION>>"):
        assert must in v6


def test_expiration_adjustment_is_done_in_code():
    from src.identify import apply_expiration
    p = apply_expiration({"coverage_start": "2026-05-17", "coverage_end": "2027-05-17", "end_is_expiration": True})
    assert p["coverage_end"] == "2027-05-16"
    q = apply_expiration({"coverage_start": "2026-05-17", "coverage_end": "2027-05-17", "end_is_expiration": False})
    assert q["coverage_end"] == "2027-05-17"
    r = apply_expiration({"coverage_start": "2026-05-17", "coverage_end": None, "end_is_expiration": True})
    assert r["coverage_end"] is None
    # never produces an end before the start
    z = apply_expiration({"coverage_start": "2026-05-17", "coverage_end": "2026-05-17", "end_is_expiration": True})
    assert z["coverage_end"] == "2026-05-17"
    # a term-derived end is left alone
    w = apply_expiration({"coverage_start": "2026-05-17", "coverage_end": "2027-05-16",
                          "end_is_expiration": True, "end_computed_from_term": True})
    assert w["coverage_end"] == "2027-05-16"


def test_identify_single_applies_expiration_from_model_json():
    import json
    from src.identify import identify_single
    reply = json.dumps({"is_prepayment": True, "classification": "multi_period_prepayment",
                        "coverage_start": "2026-05-17", "coverage_end": "2027-05-17",
                        "term_months": None, "end_is_expiration": True, "reasoning": "policy"})
    u = type("U", (), {"input_tokens": 1, "output_tokens": 1})
    client = type("C", (), {"messages": type("M", (), {"create": staticmethod(
        lambda **k: type("R", (), {"content": [type("T", (), {"text": reply})], "usage": u}))})})
    out = identify_single({"id": "x", "vendor": "Ins Co", "invoice_date": "2026-03-30", "amount": 831.17,
                           "description": "Policy Effective 05/17/2026, Expiration 05/17/2027"}, client=client)
    assert out["predicted_coverage_end"] == "2027-05-16"


def test_one_year_policy_ending_day_before_expiration_is_365_days():
    from decimal import Decimal
    from src.schedule import build_schedule, parse_date
    rows = build_schedule(Decimal("831.17"), parse_date("2026-05-17"), parse_date("2027-05-16"), method="daily")
    assert len(rows) == 13 and sum(r["days"] for r in rows) == 365   # 13 calendar months touched, 365 days
    assert rows[-1]["period"] == "2027-05" and rows[-1]["days"] == 16
    assert sum(r["amount"] for r in rows) == Decimal("831.17")


def test_cache_answers_repeat_requests_for_free_and_separates_runs(tmp_path, monkeypatch):
    import src.llm as llm
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("P6_NO_CACHE", raising=False)
    llm.reset_stats()
    n = {"calls": 0}
    class _M:
        @staticmethod
        def create(**kw):
            n["calls"] += 1
            u = type("U", (), {"input_tokens": 10, "output_tokens": 5})
            return type("R", (), {"content": [type("C", (), {"text": f"reply{n['calls']}"})], "usage": u})
    client = type("C", (), {"messages": _M})
    a = llm.create_message(client, cache_salt="r0", model="m", max_tokens=1, messages=["x"])
    b = llm.create_message(client, cache_salt="r0", model="m", max_tokens=1, messages=["x"])
    c = llm.create_message(client, cache_salt="r1", model="m", max_tokens=1, messages=["x"])
    assert a.content[0].text == b.content[0].text and n["calls"] == 2   # repeat was free
    assert c.content[0].text != a.content[0].text                        # a different run is a fresh read
    assert llm.STATS["cache_hits"] == 1 and llm.STATS["input_tokens"] == 20
    monkeypatch.setenv("P6_NO_CACHE", "1")
    llm.create_message(client, cache_salt="r0", model="m", max_tokens=1, messages=["x"])
    assert n["calls"] == 3


def test_call_cap_stops_before_overspending(monkeypatch, tmp_path):
    import src.llm as llm
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("P6_MAX_LIVE_CALLS", "2")
    llm.reset_stats()
    n = {"c": 0}
    class _M:
        @staticmethod
        def create(**kw):
            n["c"] += 1
            return type("R", (), {"content": [type("C", (), {"text": "x"})]})
    client = type("C", (), {"messages": _M})
    llm.create_message(client, cache_salt="a", model="m", max_tokens=1, messages=["1"])
    llm.create_message(client, cache_salt="b", model="m", max_tokens=1, messages=["2"])
    with pytest.raises(llm.BudgetExceeded):
        llm.create_message(client, cache_salt="c", model="m", max_tokens=1, messages=["3"])
    assert n["c"] == 2


def test_budget_exceeded_is_not_swallowed_by_extraction(monkeypatch, tmp_path):
    import src.llm as llm
    from src.extract_invoice import extract_invoice
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("P6_MAX_LIVE_CALLS", "0")
    llm.reset_stats()
    f = tmp_path / "x.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    client = type("C", (), {"messages": type("M", (), {"create": staticmethod(lambda **k: None)})})
    with pytest.raises(llm.BudgetExceeded):
        extract_invoice(f, client=client, runs=1)


def test_code_version_is_stable_and_short():
    from src.version import code_version
    assert code_version() == code_version() and len(code_version()) == 8


def test_process_folder_dry_run_lists_files_and_needs_no_key(tmp_path, monkeypatch, capsys):
    import sys
    import src.process_folder as pf
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "b.png").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path), "--dry-run"])
    pf.main()
    out = capsys.readouterr().out
    assert "a.pdf" in out and "b.png" in out and "notes.txt" not in out
    assert "at most 4 live calls" in out


def test_process_folder_small_prepayment_is_expensed_and_insurance_amortized(tmp_path, monkeypatch, capsys):
    import sys
    import src.process_folder as pf
    import src.pipeline as pl
    (tmp_path / "ins.pdf").write_bytes(b"%PDF")
    (tmp_path / "sub.pdf").write_bytes(b"%PDF")
    data = {"ins.pdf": ("Acme Insurance", 1500.0, "multi_period_prepayment", "2026-05-17", "2027-05-16"),
            "sub.pdf": ("Cloud Co", 20.0, "multi_period_prepayment", "2026-11-11", "2026-12-11")}

    def fake_extract(path, runs=1, client=None):
        v, a, *_ = data[path.name]
        return {"id": path.stem, "source_file": path.name, "vendor": v, "invoice_date": "2026-11-11",
                "due_date": None, "subtotal": None, "tax": None, "amount": a, "description": "x",
                "notes": None, "runs": runs, "image_long_side": None, "fields_with_disagreement": []}

    def fake_ident(rec):
        _, _, c, s, e = next(v for v in data.values() if v[0] == rec["vendor"])
        return {"id": rec["id"], "vendor": rec["vendor"], "predicted_classification": c,
                "predicted_coverage_start": s, "predicted_coverage_end": e, "reasoning": "fake"}

    orig = pl.process_extracted
    monkeypatch.setattr(pf, "extract_invoice", fake_extract)
    monkeypatch.setattr(pf, "process_extracted", lambda ext: orig(ext, identifier=fake_ident))
    monkeypatch.setattr(pf, "RESULTS_DIR", tmp_path / "res")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path), "--period", "2026-11"])
    pf.main()
    out = capsys.readouterr().out
    assert "ins.pdf: AMORTIZE" in out and "sub.pdf: EXPENSE" in out


# ---------------- web demo ----------------
def _client():
    from fastapi.testclient import TestClient
    import src.service as svc
    svc._ip_hits.clear(); svc._day.update(date=None, count=0)
    return TestClient(svc.app), svc


def test_demo_health_and_index():
    c, _ = _client()
    assert c.get("/health").json()["status"] == "ok"
    assert "Prepaid Expense" in c.get("/").text


def test_demo_samples_run_through_real_rules():
    c, _ = _client()
    ids = [s["id"] for s in c.get("/samples").json()]
    assert len(ids) == 5
    got = {i: c.get(f"/sample/{i}").json() for i in ids}
    assert got["h4-006"]["decision"] == "AMORTIZE" and len(got["h4-006"]["schedule"]) == 12
    assert got["h4-011"]["decision"] == "EXPENSE"          # under $500 rule
    assert got["h4-001"]["decision"] == "EXPENSE"
    blurry = got["h4-004"]
    assert blurry["decision"] == "REVIEW" and blurry["needs_review"]
    assert any("To be reviewed by user" in r for r in blurry["review_reasons"])
    assert blurry["schedule"] == [] and blurry["entries"] == []   # nothing booked
    assert c.get("/sample/nope").status_code == 404


def test_demo_upload_rejects_bad_files_and_needs_key(monkeypatch):
    c, _ = _client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    assert c.post("/process", files={"file": ("a.txt", b"hi")}).status_code == 400
    assert c.post("/process", files={"file": ("a.pdf", b"not a pdf")}).status_code == 400
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert c.post("/process", files={"file": ("a.pdf", b"%PDF-1.4")}).status_code == 503


def test_demo_upload_size_limit(monkeypatch):
    c, svc = _client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(svc, "MAX_UPLOAD_BYTES", 100)
    assert c.post("/process", files={"file": ("a.pdf", b"%PDF" + b"x" * 500)}).status_code == 413


def test_demo_upload_limits_per_visitor_and_per_day(monkeypatch):
    c, svc = _client()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(svc, "PER_IP_PER_HOUR", 2)
    monkeypatch.setattr(svc, "PER_DAY_TOTAL", 3)
    import src.extract_invoice as ei
    calls = []
    monkeypatch.setattr(ei, "extract_invoice", lambda p, runs=1, client=None: calls.append(1) or {
        "id": "u", "source_file": "u.pdf", "vendor": "V", "invoice_date": "2026-11-01", "due_date": None,
        "subtotal": None, "tax": None, "amount": 50.0, "description": "x", "notes": None, "runs": 1,
        "image_long_side": None, "fields_with_disagreement": []})
    import src.pipeline as pl
    monkeypatch.setattr(svc, "process_extracted", lambda ext: pl.process_extracted(ext, identifier=lambda r: {
        "id": r["id"], "vendor": r["vendor"], "predicted_classification": "ordinary_expense",
        "predicted_coverage_start": None, "predicted_coverage_end": None, "reasoning": "fake"}))
    post = lambda ip: c.post("/process", files={"file": ("a.pdf", b"%PDF-1.4")}, headers={"x-forwarded-for": ip})
    assert post("1.1.1.1").status_code == 200
    assert post("1.1.1.1").status_code == 200
    assert post("1.1.1.1").status_code == 429      # per-visitor limit
    assert post("2.2.2.2").status_code == 200      # a different visitor is fine
    assert post("3.3.3.3").status_code == 429      # daily total (3) used up
    assert len(calls) == 3                         # blocked requests never reached the AI



    