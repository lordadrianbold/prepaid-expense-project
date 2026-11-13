"""
Project 6: deterministic checks on an EXTRACTED invoice. No model involved.

The model can misread a digit and be perfectly confident, and reading the
same image three times can return the same wrong answer three times. These
checks use arithmetic and plain logic instead.

Returns {"blocking": [...], "warnings": [...]}:
  blocking  the extraction can't be trusted; the invoice goes to human review
            instead of being booked
  warnings  worth knowing, not worth blocking (none at the moment). A low-resolution
            image is now a blocking 'to be reviewed by user' item: in the fair test,
            blurry photos caused 6 of the 8 field problems.
"""
import re
from datetime import date

from datetime import timedelta

from .config import MAX_FUTURE_DAYS, MAX_PAST_DAYS, MIN_IMAGE_LONG_SIDE

_REFERS_ELSEWHERE = re.compile(
    r"\b(see|per|refer(?:ence)?s?\s+to|as\s+per)\b[^.]{0,40}\b(notes?|attached|attachment|agreement|contract|below|terms|schedule)\b", re.I)


def _num(v):
    try:
        return None if v in (None, "", "null") else float(v)
    except (TypeError, ValueError):
        return None


def _date(v):
    try:
        return date.fromisoformat(v) if v else None
    except (TypeError, ValueError):
        return None


def check_extraction(ext: dict, min_long_side: int = MIN_IMAGE_LONG_SIDE, today: date = None) -> dict:
    blocking, warnings = [], []
    if ext.get("extraction_error"):
        return {"blocking": [f"Extraction failed: {str(ext['extraction_error'])[:120]}"], "warnings": []}

    total, sub, tax = _num(ext.get("amount")), _num(ext.get("subtotal")), _num(ext.get("tax"))
    if total is None or total <= 0:
        blocking.append("No usable total amount was extracted.")
    elif sub is not None:
        expected = round(sub + (tax or 0.0), 2)
        if abs(expected - total) > 0.01:
            blocking.append(f"Footing check failed: subtotal {sub:,.2f} + tax {(tax or 0):,.2f} = "
                            f"{expected:,.2f}, but total read as {total:,.2f}.")

    inv, due = _date(ext.get("invoice_date")), _date(ext.get("due_date"))
    if inv is None:
        blocking.append("Invoice date is missing or not a valid date.")
    elif inv > (today or date.today()) + timedelta(days=MAX_FUTURE_DAYS):
        blocking.append(f"Invoice date {inv} is implausible: more than {MAX_FUTURE_DAYS} days in the future "
                        f"(the year was probably misread).")
    elif inv < (today or date.today()) - timedelta(days=MAX_PAST_DAYS):
        blocking.append(f"Invoice date {inv} is implausible: more than {MAX_PAST_DAYS} days in the past "
                        f"(the year was probably misread).")
    elif due is not None and (due < inv or (due - inv).days > 180):
        blocking.append(f"Due date {due} is implausible next to invoice date {inv} "
                        f"(one of them was probably misread).")

    description, notes = (ext.get("description") or ""), (ext.get("notes") or "").strip()
    if _REFERS_ELSEWHERE.search(description) and not notes:
        blocking.append("The description refers to other text on the invoice (notes/terms/attachment) "
                        "that was not captured; the service period may be missing.")

    if ext.get("fields_with_disagreement"):
        blocking.append("Repeated reads disagreed on: " + ", ".join(ext["fields_with_disagreement"]) + ".")

    long_side = ext.get("image_long_side")
    if long_side and long_side < min_long_side:
        blocking.append(f"To be reviewed by user: low-quality image ({long_side}px on the long side, "
                        f"under {min_long_side}px). Amounts and dates may be misread; check them "
                        f"against the original.")
    return {"blocking": blocking, "warnings": warnings}



