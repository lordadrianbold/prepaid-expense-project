"""
Project 6, Piece 3a: deterministic amortization schedule.

No LLM here. Dates and dollars are arithmetic, so they are computed with
Decimal and checked, not generated. Every schedule sums to exactly the
invoice amount: rounding differences land in the final period.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def _money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def end_from_term(start, term_months) -> date:
    """Coverage end for a document that states a start date and a term in months:
    the day before the term elapses (e.g. 12 months from 2026-11-16 -> 2027-11-15).
    Computed in code because models get this arithmetic wrong. If the start day
    does not exist in the final month (Jan 31 + 1 month) it clamps to month end."""
    st = parse_date(start)
    n = int(term_months)
    if n < 1:
        raise ValueError("term_months must be at least 1")
    y, m = divmod(st.year * 12 + (st.month - 1) + n, 12)
    last = calendar.monthrange(y, m + 1)[1]
    return date(y, m + 1, min(st.day, last)) - timedelta(days=1)


def derive_prepayment_type(coverage_start, coverage_end) -> str:
    """Prepayment type is a fact about the dates, not a judgment call:
    coverage inside ONE calendar month is a one-time prepayment (a single
    schedule row); coverage touching two or more months is multi-period.
    The model's own label for this is advisory and is overridden."""
    s, e = parse_date(coverage_start), parse_date(coverage_end)
    return "one_time_prepayment" if (s.year, s.month) == (e.year, e.month) else "multi_period_prepayment"


def _months_touched(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def build_schedule(amount, coverage_start, coverage_end, method="daily"):
    """
    Returns a list of period rows:
      {period: 'YYYY-MM', period_end: date, days: int, amount: Decimal,
       cumulative: Decimal, remaining: Decimal}
    method: 'daily' (prorate by actual days) or 'monthly_equal'.
    """
    start, end = parse_date(coverage_start), parse_date(coverage_end)
    if end < start:
        raise ValueError(f"coverage_end {end} is before coverage_start {start}")
    total = _money(amount)
    if total <= 0:
        raise ValueError("amount must be positive")
    if method not in ("daily", "monthly_equal"):
        raise ValueError(f"unknown method {method!r}")

    months = list(_months_touched(start, end))
    total_days = (end - start).days + 1
    rows, running = [], Decimal("0.00")
    for i, (y, m) in enumerate(months):
        first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        days = (min(end, last) - max(start, first)).days + 1
        if i == len(months) - 1:
            amt = total - running                      # remainder to last period
        elif method == "daily":
            amt = _money(total * days / total_days)
        else:
            amt = _money(total / len(months))
        running += amt
        rows.append({"period": f"{y}-{m:02d}", "period_end": last, "days": days,
                     "amount": amt, "cumulative": running, "remaining": total - running})
    assert running == total, "schedule must sum exactly to the invoice amount"
    return rows





