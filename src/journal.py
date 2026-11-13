"""
Project 6, Piece 3b: journal entries, built from the identification and
the schedule. Pure functions. Every entry is checked to balance.
"""
from decimal import Decimal

from .config import ACCOUNTS, EXPENSE_ACCOUNT_KEYWORDS


def expense_account_for(description: str):
    d = (description or "").lower()
    for keywords, account in EXPENSE_ACCOUNT_KEYWORDS:
        if any(k in d for k in keywords):
            return account
    return ACCOUNTS["default_expense"]


def _entry(je_date, memo, ref, lines):
    debits = sum(l["debit"] for l in lines)
    credits = sum(l["credit"] for l in lines)
    if debits != credits:
        raise ValueError(f"Unbalanced entry {ref}: debits {debits} != credits {credits}")
    return {"date": je_date, "memo": memo, "ref": ref, "lines": lines}


def _line(account, debit=Decimal("0.00"), credit=Decimal("0.00")):
    return {"account_no": account[0], "account": account[1], "debit": debit, "credit": credit}


def capitalization_entry(record, amount):
    """Invoice recorded: Dr Prepaid, Cr AP."""
    return _entry(record["invoice_date"],
                  f"Record prepaid - {record['vendor']}", f"{record['id']}-CAP",
                  [_line(ACCOUNTS["prepaid"], debit=amount), _line(ACCOUNTS["ap"], credit=amount)])


def expense_entry(record, amount):
    """Ordinary expense: Dr Expense, Cr AP. No schedule."""
    exp = expense_account_for(record["description"])
    return _entry(record["invoice_date"],
                  f"Expense as incurred - {record['vendor']}", f"{record['id']}-EXP",
                  [_line(exp, debit=amount), _line(ACCOUNTS["ap"], credit=amount)])


def amortization_entries(record, schedule):
    """One entry per period: Dr Expense, Cr Prepaid."""
    exp = expense_account_for(record["description"])
    return [_entry(row["period_end"],
                   f"Amortize prepaid - {record['vendor']} ({row['period']})",
                   f"{record['id']}-AM-{row['period']}",
                   [_line(exp, debit=row["amount"]), _line(ACCOUNTS["prepaid"], credit=row["amount"])])
            for row in schedule]
