"""
Project 6, Piece 2: Identification.

Given an extracted invoice record (vendor, amount, invoice_date,
description), decides whether it is a genuine multi-period prepayment, a
one-time prepayment, or an ordinary expense that only looks like a
prepayment, and extracts the coverage dates from the document's own
language.

Fix vs. the first draft: the prompt used str.format() while containing a
literal JSON example with { } braces, which raises KeyError on the first
call. Fields are now substituted with str.replace on explicit markers.
"""
import json
import re
import os

from .config import MODEL, get_prompt_version
from .llm import create_message

PROMPT_V1 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and amortized over time) or an ordinary expense that should be recognized immediately.

Apply these real accounting principles:
1. A GENUINE PREPAYMENT has real, explicit coverage-period language on the document - a stated service period, contract term, subscription period, or insurance policy term that extends into future periods.
2. A ONE-TIME PREPAYMENT is a genuine prepayment, but the entire coverage period falls within a single accounting period (e.g., a deposit for an event happening next month, or a service performed entirely within the current period) - it still gets capitalized and then recognized, but there's no multi-period amortization schedule needed.
3. A MULTI-PERIOD PREPAYMENT has a coverage period spanning multiple real accounting periods (e.g., a 12-month insurance policy, an annual software license) - this needs a real, period-by-period amortization schedule.
4. An ORDINARY EXPENSE merely resembles a prepayment on the surface but is NOT one - watch for these specific traps:
   - Bulk purchases of consumable goods/supplies (even if described as "6-month supply" or "annual") - these are inventory/supply purchases, not service-period prepayments
   - Project deposits or milestone payments (e.g., "50% deposit," "retainer") where the payment is tied to project completion, not a real coverage period
   - Small-dollar "annual membership" renewals where the real economic substance doesn't justify prepaid-asset treatment
   - Advance travel bookings for multiple, non-contiguous future dates - this is prepaid travel, typically expensed as incurred per trip, not amortized as a single asset
   - Purchases of goods/inventory for a future event, even if a future date is mentioned - the goods themselves are the expense, not a coverage period

Only use dates that are stated in the description. If no explicit coverage period or term is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD or null",
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPT_V2 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and then recognized as expense later) or an ordinary expense that should be recognized immediately.

THE KEY QUESTION: was this paid BEFORE the service, right, rental, or event access it buys is received, with the dates of that service stated on the document? If yes, it is a prepayment. If the service was already delivered, or the document states no service dates, or the payment buys goods or a project deliverable rather than a service over time, it is an ordinary expense.

Apply these accounting principles:
1. A GENUINE PREPAYMENT has explicit coverage language on the document - a stated service period, contract term, subscription period, policy term, rental period, or event/booking date - that is still in the future (or extends into future periods) when the invoice is dated.
2. A ONE-TIME PREPAYMENT is a genuine prepayment where the stated dates fall entirely within a single calendar month: a fee paid ahead for a specific event, booking, reservation, rental, session, or service on stated dates. It is capitalized when paid and recognized as expense when the service or event occurs. IMPORTANT: lacking a multi-month coverage period is NOT a reason to call something an ordinary expense. "It is expensed when the event happens" is exactly what makes it a one-time prepayment - the only question is whether payment came before the service.
3. A MULTI-PERIOD PREPAYMENT has stated coverage spanning two or more calendar months (e.g., a 12-month insurance policy, an annual software license, rent paid for several months ahead). It needs a period-by-period amortization schedule. If the document gives only a start date and a duration (e.g., "36-month term beginning March 1, 2027"), work out the end date as the day before the duration elapses.
4. An ORDINARY EXPENSE is anything that merely resembles a prepayment. Watch for these specific traps:
   - Services already rendered: the stated service period ended before the invoice date (billed in arrears). Nothing is prepaid.
   - Bulk purchases of consumable goods or supplies, even if described as a "6-month supply" or "annual" - these are inventory/supply purchases, not service-period prepayments.
   - Project deposits, retainers, or milestone payments (e.g., "50% deposit," "milestone 1") where payment is tied to completing a project or deliverable rather than to a period of service.
   - Small-dollar "annual membership" or subscription renewals where the economic substance doesn't justify prepaid-asset treatment.
   - Advance travel bookings for multiple, non-contiguous future dates - expensed as incurred per trip, not treated as one asset.
   - PURCHASES OF GOODS for a future event (items you will own or give away: apparel, printed materials, awards, gifts). This is different from RENTING equipment or space, or booking lodging or services, for stated dates - those are services and are prepayments under rules 1-3.

Only use dates that are stated in the description. If no explicit coverage period, term, or event date is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD or null",
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPT_V3 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and then recognized as expense later) or an ordinary expense that should be recognized immediately.

THE KEY QUESTION: was this paid BEFORE the service, right, rental, or event access it buys is received, with the dates of that service stated on the document? If yes, it is a prepayment. If the service was already delivered, or the document states no service dates, or the payment buys goods or a project deliverable rather than a service over time, it is an ordinary expense.

Apply these accounting principles:
1. A GENUINE PREPAYMENT has explicit coverage language on the document - a stated service period, contract term, subscription period, policy term, rental period, or event/booking date - that is still in the future (or extends into future periods) when the invoice is dated.
2. A ONE-TIME PREPAYMENT is a genuine prepayment where the stated dates fall entirely within a single calendar month: a fee paid ahead for a specific event, booking, reservation, rental, session, or service on stated dates. It is capitalized when paid and recognized as expense when the service or event occurs. IMPORTANT: lacking a multi-month coverage period is NOT a reason to call something an ordinary expense. "It is expensed when the event happens" is exactly what makes it a one-time prepayment - the only question is whether payment came before the service.
3. A MULTI-PERIOD PREPAYMENT has stated coverage spanning two or more calendar months (e.g., a 12-month insurance policy, an annual software license, rent paid for several months ahead). It needs a period-by-period amortization schedule. If the document gives only a start date and a duration (e.g., "36-month term beginning March 1, 2027" or "2-year term from March 1, 2027"), do NOT work out the end date yourself: set coverage_end to null and put the duration in months in term_months (2 years = 24). Code computes the end date.
4. An ORDINARY EXPENSE is anything that merely resembles a prepayment. Watch for these specific traps:
   - Services already rendered: the stated service period ended before the invoice date (billed in arrears). Nothing is prepaid.
   - Bulk purchases of consumable goods or supplies, even if described as a "6-month supply" or "annual" - these are inventory/supply purchases, not service-period prepayments.
   - Project deposits, retainers, or milestone payments (e.g., "50% deposit," "milestone 1") where payment is tied to completing a project or deliverable rather than to a period of service.
   - Small-dollar "annual membership" or subscription renewals where the economic substance doesn't justify prepaid-asset treatment.
   - Advance travel bookings for multiple, non-contiguous future dates - expensed as incurred per trip, not treated as one asset.
   - PURCHASES OF GOODS for a future event (items you will own or give away: apparel, printed materials, awards, gifts). This is different from RENTING equipment or space, or booking lodging or services, for stated dates - those are services and are prepayments under rules 1-3.

Only use dates that are stated in the description. If no explicit coverage period, term, or event date is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD, or null if the document gives only a start date and a duration",
  "term_months": duration in whole months when the document states only a start date and a duration, otherwise null,
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPT_V4 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and then recognized as expense later) or an ordinary expense that should be recognized immediately.

THE KEY QUESTION: was this paid BEFORE the service, right, rental, or event access it buys is received, with the dates of that service stated on the document? If yes, it is a prepayment. If the service was already delivered, or the document states no service dates, or the payment buys goods or a project deliverable rather than a service over time, it is an ordinary expense.

Apply these accounting principles:
1. A GENUINE PREPAYMENT has explicit coverage language on the document - a stated service period, contract term, subscription period, policy term, rental period, or event/booking date - that is still in the future (or extends into future periods) when the invoice is dated.
2. A ONE-TIME PREPAYMENT is a genuine prepayment where the stated dates fall entirely within a single calendar month: a fee paid ahead for a specific event, booking, reservation, rental, session, or service on stated dates. It is capitalized when paid and recognized as expense when the service or event occurs. IMPORTANT: lacking a multi-month coverage period is NOT a reason to call something an ordinary expense. "It is expensed when the event happens" is exactly what makes it a one-time prepayment - the only question is whether payment came before the service.
3. A MULTI-PERIOD PREPAYMENT has stated coverage spanning two or more calendar months (e.g., a 12-month insurance policy, an annual software license, rent paid for several months ahead). It needs a period-by-period amortization schedule. If the document gives only a start date and a duration (e.g., "36-month term beginning March 1, 2027" or "2-year term from March 1, 2027"), do NOT work out the end date yourself: set coverage_end to null and put the duration in months in term_months (2 years = 24). Code computes the end date.
4. An ORDINARY EXPENSE is anything that merely resembles a prepayment. Watch for these specific traps:
   - Services already rendered: the ENTIRE stated service period ended before the invoice date (billed in arrears). Nothing is prepaid. This applies only when the period has completely ended. A period that began before the invoice date but ends after it is NOT this case (see PARTLY ELAPSED below).
   - Bulk purchases of consumable goods or supplies, even if described as a "6-month supply" or "annual" - these are inventory/supply purchases, not service-period prepayments.
   - Project deposits, retainers, or milestone payments (e.g., "50% deposit," "milestone 1") where payment is tied to completing a project or deliverable rather than to a period of service.
   - Small-dollar "annual membership" or subscription renewals where the economic substance doesn't justify prepaid-asset treatment.
   - Advance travel bookings for multiple, non-contiguous future dates - expensed as incurred per trip, not treated as one asset.
   - PURCHASES OF GOODS for a future event (items you will own or give away: apparel, printed materials, awards, gifts). This is different from RENTING equipment or space, or booking lodging or services, for stated dates - those are services and are prepayments under rules 1-3.

PARTLY ELAPSED PERIODS: if the stated period began before the invoice date but ends after it (for example, an invoice dated March 15 for a service year that began January 1), the part still ahead is a prepayment. Classify it as multi_period_prepayment (or one_time_prepayment if the whole period is inside one calendar month) and report the FULL stated start and end dates; the months already elapsed are handled by code, so do not shorten the period and do not call it an ordinary expense.

Only use dates that are stated in the description. If no explicit coverage period, term, or event date is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD, or null if the document gives only a start date and a duration",
  "term_months": duration in whole months when the document states only a start date and a duration, otherwise null,
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPT_V5 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and then recognized as expense later) or an ordinary expense that should be recognized immediately.

THE KEY QUESTION: was this paid BEFORE the service, right, rental, or event access it buys is received, with the dates of that service stated on the document? If yes, it is a prepayment. If the service was already delivered, or the document states no service dates, or the payment buys goods or a project deliverable rather than a service over time, it is an ordinary expense.

Apply these accounting principles:
1. A GENUINE PREPAYMENT has explicit coverage language on the document - a stated service period, contract term, subscription period, policy term, rental period, or event/booking date - that is still in the future (or extends into future periods) when the invoice is dated.
2. A ONE-TIME PREPAYMENT is a genuine prepayment where the stated dates fall entirely within a single calendar month: a fee paid ahead for a specific event, booking, reservation, rental, session, or service on stated dates. It is capitalized when paid and recognized as expense when the service or event occurs. IMPORTANT: lacking a multi-month coverage period is NOT a reason to call something an ordinary expense. "It is expensed when the event happens" is exactly what makes it a one-time prepayment - the only question is whether payment came before the service.
3. A MULTI-PERIOD PREPAYMENT has stated coverage spanning two or more calendar months (e.g., a 12-month insurance policy, an annual software license, rent paid for several months ahead). It needs a period-by-period amortization schedule. If the document gives only a start date and a duration (e.g., "36-month term beginning March 1, 2027" or "2-year term from March 1, 2027"), do NOT work out the end date yourself: set coverage_end to null and put the duration in months in term_months (2 years = 24). Code computes the end date.
4. An ORDINARY EXPENSE is anything that merely resembles a prepayment. Watch for these specific traps:
   - Services already rendered: the ENTIRE stated service period ended before the invoice date (billed in arrears). Nothing is prepaid. This applies only when the period has completely ended. A period that began before the invoice date but ends after it is NOT this case (see PARTLY ELAPSED below).
   - Bulk purchases of consumable goods or supplies, even if described as a "6-month supply" or "annual" - these are inventory/supply purchases, not service-period prepayments.
   - Project deposits, retainers, or milestone payments (e.g., "50% deposit," "milestone 1") where payment is tied to completing a project or deliverable rather than to a period of service.
   - Small-dollar "annual membership" or subscription renewals where the economic substance doesn't justify prepaid-asset treatment.
   - Advance travel bookings for multiple, non-contiguous future dates - expensed as incurred per trip, not treated as one asset.
   - PURCHASES OF GOODS for a future event (items you will own or give away: apparel, printed materials, awards, gifts). This is different from RENTING equipment or space, or booking lodging or services, for stated dates - those are services and are prepayments under rules 1-3.

LAST COVERED DAY: coverage ends on the last day the service is actually received. When the document gives an "expiration date", "expires", or a policy term as "effective date ... expiration date" (typical for insurance, where coverage stops at the start of the expiration date), the last covered day is the DAY BEFORE that date. Example: "Policy Effective Date 05/17/2026, Policy Expiration Date 05/17/2027" means coverage_start 2026-05-17 and coverage_end 2027-05-16. When the document names a last day directly ("through March 31, 2028", "ending June 30, 2027", "service period April 1 to April 30"), use that date as written. If it is unclear which meaning applies, use the date as written and say so in the reasoning.

PARTLY ELAPSED PERIODS: if the stated period began before the invoice date but ends after it (for example, an invoice dated March 15 for a service year that began January 1), the part still ahead is a prepayment. Classify it as multi_period_prepayment (or one_time_prepayment if the whole period is inside one calendar month) and report the FULL stated start and end dates; the months already elapsed are handled by code, so do not shorten the period and do not call it an ordinary expense.

Only use dates that are stated in the description. If no explicit coverage period, term, or event date is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD, or null if the document gives only a start date and a duration",
  "term_months": duration in whole months when the document states only a start date and a duration, otherwise null,
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPT_V6 = """You are an accounting assistant helping determine whether an invoice line item represents a genuine prepaid expense (an asset to be capitalized and then recognized as expense later) or an ordinary expense that should be recognized immediately.

THE KEY QUESTION: was this paid BEFORE the service, right, rental, or event access it buys is received, with the dates of that service stated on the document? If yes, it is a prepayment. If the service was already delivered, or the document states no service dates, or the payment buys goods or a project deliverable rather than a service over time, it is an ordinary expense.

Apply these accounting principles:
1. A GENUINE PREPAYMENT has explicit coverage language on the document - a stated service period, contract term, subscription period, policy term, rental period, or event/booking date - that is still in the future (or extends into future periods) when the invoice is dated.
2. A ONE-TIME PREPAYMENT is a genuine prepayment where the stated dates fall entirely within a single calendar month: a fee paid ahead for a specific event, booking, reservation, rental, session, or service on stated dates. It is capitalized when paid and recognized as expense when the service or event occurs. IMPORTANT: lacking a multi-month coverage period is NOT a reason to call something an ordinary expense. "It is expensed when the event happens" is exactly what makes it a one-time prepayment - the only question is whether payment came before the service.
3. A MULTI-PERIOD PREPAYMENT has stated coverage spanning two or more calendar months (e.g., a 12-month insurance policy, an annual software license, rent paid for several months ahead). It needs a period-by-period amortization schedule. If the document gives only a start date and a duration (e.g., "36-month term beginning March 1, 2027" or "2-year term from March 1, 2027"), do NOT work out the end date yourself: set coverage_end to null and put the duration in months in term_months (2 years = 24). Code computes the end date.
4. An ORDINARY EXPENSE is anything that merely resembles a prepayment. Watch for these specific traps:
   - Services already rendered: the ENTIRE stated service period ended before the invoice date (billed in arrears). Nothing is prepaid. This applies only when the period has completely ended. A period that began before the invoice date but ends after it is NOT this case (see PARTLY ELAPSED below).
   - Bulk purchases of consumable goods or supplies, even if described as a "6-month supply" or "annual" - these are inventory/supply purchases, not service-period prepayments.
   - Project deposits, retainers, or milestone payments (e.g., "50% deposit," "milestone 1") where payment is tied to completing a project or deliverable rather than to a period of service.
   - Small-dollar "annual membership" or subscription renewals where the economic substance doesn't justify prepaid-asset treatment.
   - Advance travel bookings for multiple, non-contiguous future dates - expensed as incurred per trip, not treated as one asset.
   - PURCHASES OF GOODS for a future event (items you will own or give away: apparel, printed materials, awards, gifts). This is different from RENTING equipment or space, or booking lodging or services, for stated dates - those are services and are prepayments under rules 1-3.

EXPIRATION DATES: if the end date on the document is an "expiration date" or "expires" date (typical for insurance policies, where coverage stops at the start of that day), copy that date EXACTLY as written into coverage_end and set end_is_expiration to true. Do NOT subtract a day yourself and do not change the year; code makes that adjustment. Example: "Policy Effective Date 05/17/2026, Policy Expiration Date 05/17/2027" gives coverage_start 2026-05-17, coverage_end 2027-05-17, end_is_expiration true. When the document names a last day directly ("through March 31, 2028", "ending June 30, 2027", "April 1 to April 30"), copy it as written and set end_is_expiration to false. If it is unclear, use false.

PARTLY ELAPSED PERIODS: if the stated period began before the invoice date but ends after it (for example, an invoice dated March 15 for a service year that began January 1), the part still ahead is a prepayment. Classify it as multi_period_prepayment (or one_time_prepayment if the whole period is inside one calendar month) and report the FULL stated start and end dates; the months already elapsed are handled by code, so do not shorten the period and do not call it an ordinary expense.

Only use dates that are stated in the description. If no explicit coverage period, term, or event date is stated, set coverage_start and coverage_end to null and say so in the reasoning - do not guess.

Respond with ONLY a JSON object (no other text) in this exact format:
{
  "is_prepayment": true or false,
  "classification": "multi_period_prepayment" or "one_time_prepayment" or "ordinary_expense",
  "coverage_start": "YYYY-MM-DD or null",
  "coverage_end": "YYYY-MM-DD, or null if the document gives only a start date and a duration",
  "term_months": duration in whole months when the document states only a start date and a duration, otherwise null,
  "end_is_expiration": true if coverage_end is an expiration date as described above, otherwise false,
  "reasoning": "one or two sentences citing the specific language in the document that drove this determination"
}

Invoice details:
Vendor: <<VENDOR>>
Invoice date: <<INVOICE_DATE>>
Amount: $<<AMOUNT>>
Description: <<DESCRIPTION>>
"""

PROMPTS = {"v1": PROMPT_V1, "v2": PROMPT_V2, "v3": PROMPT_V3, "v4": PROMPT_V4, "v5": PROMPT_V5, "v6": PROMPT_V6}

IDENTIFICATION_PROMPT = PROMPT_V1  # kept for backward compatibility

VALID_CLASSES = {"multi_period_prepayment", "one_time_prepayment", "ordinary_expense"}


def build_prompt(record: dict, version: str = None) -> str:
    version = version or get_prompt_version()
    if version not in PROMPTS:
        raise ValueError(f"unknown prompt version {version!r}; choose from {sorted(PROMPTS)}")
    return (PROMPTS[version]
            .replace("<<VENDOR>>", str(record["vendor"]))
            .replace("<<INVOICE_DATE>>", str(record["invoice_date"]))
            .replace("<<AMOUNT>>", f"{record['amount']:,.2f}")
            .replace("<<DESCRIPTION>>", str(record["description"])))


def parse_model_json(raw_text: str) -> dict:
    """Parse the model's JSON, tolerating markdown fences. Never raises."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
        if parsed.get("classification") not in VALID_CLASSES:
            parsed["classification"] = "PARSE_ERROR"
            parsed["reasoning"] = f"Unrecognized classification. Raw: {text[:200]}"
        return parsed
    except (json.JSONDecodeError, ValueError):
        recovered = _recover_fields(text)
        if recovered:
            return recovered
        return {"is_prepayment": None, "classification": "PARSE_ERROR",
                "coverage_start": None, "coverage_end": None,
                "reasoning": f"Failed to parse model output: {text[:600]}"}


def _field(text, name):
    m = re.search(r'"%s"\s*:\s*(?:"([^"]*)"|(null|true|false|-?\d+))' % name, text)
    return None if not m else (m.group(1) if m.group(1) is not None else m.group(2))


def _recover_fields(text):
    """Last resort for JSON that is almost valid (e.g. an unescaped quote inside the
    reasoning text). Recover only the constrained fields; if the classification is
    not one of the three allowed values, give up and let the invoice go to review."""
    cls = _field(text, "classification")
    if cls not in VALID_CLASSES:
        return None
    def clean(v):
        return None if v in (None, "null", "") else v
    term = clean(_field(text, "term_months"))
    return {"is_prepayment": cls != "ordinary_expense", "classification": cls,
            "coverage_start": clean(_field(text, "coverage_start")),
            "coverage_end": clean(_field(text, "coverage_end")),
            "term_months": int(term) if term and term.lstrip("-").isdigit() else None,
            "reasoning": "(fields recovered from malformed JSON) " + text[:300]}


def apply_term(parsed: dict) -> dict:
    """If the model gave a start date and a term in months but no end date, compute
    the end in code. A model-supplied end date is left alone."""
    from .schedule import end_from_term
    start, end, term = parsed.get("coverage_start"), parsed.get("coverage_end"), parsed.get("term_months")
    if start and start != "null" and term not in (None, "", "null") and end in (None, "", "null"):
        try:
            parsed["coverage_end"] = end_from_term(start, term).isoformat()
            parsed["end_computed_from_term"] = True
        except (ValueError, TypeError):
            pass
    return parsed


def apply_expiration(parsed: dict) -> dict:
    """If the model says the end date is an insurance-style EXPIRATION date, the last covered
    day is the day before. Code does this subtraction (the model got it wrong when asked)."""
    from datetime import timedelta
    from .schedule import parse_date
    flag = parsed.get("end_is_expiration")
    if flag in (True, "true", "True") and not parsed.get("end_computed_from_term"):
        s_, e_ = parsed.get("coverage_start"), parsed.get("coverage_end")
        try:
            if s_ and e_ and "null" not in (s_, e_):
                new_end = parse_date(e_) - timedelta(days=1)
                if new_end >= parse_date(s_):
                    parsed["coverage_end"] = new_end.isoformat()
                    parsed["end_adjusted_for_expiration"] = True
        except (ValueError, TypeError):
            pass
    return parsed


def _get_client():
    from anthropic import Anthropic  # imported lazily so tests run offline
    return Anthropic()


def identify_single(record: dict, client=None) -> dict:
    """Run identification on one extracted invoice record."""
    client = client or _get_client()
    response = create_message(
        client,
        model=MODEL,
        max_tokens=800,
        messages=[{"role": "user", "content": build_prompt(record)}],
    )
    parsed = parse_model_json(response.content[0].text)
    apply_term(parsed)
    apply_expiration(parsed)
    return {
        "id": record["id"],
        "vendor": record["vendor"],
        "predicted_classification": parsed.get("classification"),
        "predicted_coverage_start": parsed.get("coverage_start"),
        "predicted_coverage_end": parsed.get("coverage_end"),
        "reasoning": parsed.get("reasoning"),
        "true_label": record.get("true_label"),
        "true_coverage_start": record.get("true_coverage_start"),
        "true_coverage_end": record.get("true_coverage_end"),
        "tags": record.get("tags"),
        "amount": record.get("amount"),
        "prompt_version": get_prompt_version(),
    }


def run_batch(dataset_path, output_path, client=None) -> list:
    with open(dataset_path) as f:
        records = json.load(f)
    client = client or _get_client()
    results = []
    for i, record in enumerate(records, 1):
        result = identify_single(record, client)
        results.append(result)
        print(f"  [{i}/{len(records)}] {record['id']} {record['vendor']}: "
              f"{result['predicted_classification']} (true: {result['true_label']})")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    return results


if __name__ == "__main__":
    from .config import DATA_DIR, RESULTS_DIR
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY not set.")
    RESULTS_DIR.mkdir(exist_ok=True)
    run_batch(DATA_DIR / "tuning_set.json", RESULTS_DIR / "tuning_predictions.json")




    