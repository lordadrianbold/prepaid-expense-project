"""
Project 6, Piece 4: the month-end reconciliation workbook.

What the accountant gets:
  Read Me         how to use it, conventions, DEMO banner if applicable
  Register        every invoice: vendor, amount, period, treatment, flags
  Schedule        month-by-month amortization grid (live SUM formulas)
  Recon           pick a period; expected amortization and expected prepaid
                  balance are looked up by formula; type what the GL
                  actually shows (yellow cells); variance and status compute
  Journal Entries every proposed entry, flat, ready to compare or upload
  Needs Review    anything the checks could not vouch for
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

HDR = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF")
INPUT = PatternFill("solid", fgColor="FFF2CC")
MONEY = '#,##0.00;(#,##0.00);"-"'
DATE = "yyyy-mm-dd"


def _header(ws, row, labels):
    for c, text in enumerate(labels, 1):
        cell = ws.cell(row=row, column=c, value=text)
        cell.fill, cell.font = HDR, HDR_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[L(i)].width = w


def _d(s):
    from datetime import date
    return date.fromisoformat(s) if s else None


def build_workbook(items, period, path, demo=False):
    wb = Workbook()

    # ---- Read Me ----
    ws = wb.active
    ws.title = "Read Me"
    lines = ["Prepaid Expense & Amortization Worksheet", f"Reconciliation period: {period}", ""]
    if demo:
        lines += ["*** DEMO: classifications come from ground-truth labels, NOT from the model. ***", ""]
    lines += [
        "How to reconcile:",
        "1. Go to the Recon sheet and confirm the period in cell B2 (dropdown).",
        "2. Type the amortization amount your GL posted for each item into the yellow 'GL posted' column,",
        "   and the GL prepaid balance per item into the yellow 'GL balance' column.",
        "3. Variance = GL - Expected. Status shows Tied / Investigate / Not entered.",
        "4. Work the Needs Review sheet: those items were NOT auto-booked.",
        "",
        "Conventions: the model decides what each invoice is and reads the dates stated on it;",
        "schedules, rounding (remainder goes to the final period) and entries are computed, not generated.",
        "Accounts and the expense mapping come from src/config.py: replace with your chart of accounts.",
    ]
    for i, t in enumerate(lines, 1):
        ws.cell(row=i, column=1, value=t)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 110

    # ---- Register ----
    reg = wb.create_sheet("Register")
    _header(reg, 1, ["ID", "Vendor", "Invoice date", "Amount", "Model classification", "Prepayment type (from dates)",
                     "Treatment", "Coverage start", "Coverage end", "Periods", "Flags", "Notes", "Model reasoning"])
    for r, it in enumerate(items, 2):
        rec, ident = it["record"], it["identification"]
        reg.append([rec["id"], rec["vendor"], _d(rec["invoice_date"]), float(it["amount"]),
                    ident["predicted_classification"], it["prepayment_type"], it["treatment"],
                    _d(ident["predicted_coverage_start"]) if it["schedule"] else None,
                    _d(ident["predicted_coverage_end"]) if it["schedule"] else None,
                    len(it["schedule"]) or None, "; ".join(it["flags"]) or None,
                    "; ".join(it["notes"]) or None, ident["reasoning"]])
        reg.cell(row=r, column=3).number_format = DATE
        reg.cell(row=r, column=4).number_format = MONEY
        reg.cell(row=r, column=8).number_format = DATE
        reg.cell(row=r, column=9).number_format = DATE
    _widths(reg, [9, 30, 12, 13, 24, 24, 11, 12, 12, 8, 50, 50, 70])
    reg.freeze_panes = "A2"

    # ---- Schedule ----
    sched = wb.create_sheet("Schedule")
    scheduled = [it for it in items if it["schedule"]]
    periods = sorted({row["period"] for it in scheduled for row in it["schedule"]})
    first_p = 7                                  # column G (F = invoice date)
    last_p = first_p + max(len(periods), 1) - 1
    _header(sched, 1, ["ID", "Vendor", "Amount", "Coverage start", "Coverage end", "Invoice date"] + periods
            + ["Total amortized", "Remaining"])
    for r, it in enumerate(scheduled, 2):
        rec = it["record"]
        by_period = {row["period"]: float(row["amount"]) for row in it["schedule"]}
        sched.cell(row=r, column=1, value=rec["id"])
        sched.cell(row=r, column=2, value=rec["vendor"])
        sched.cell(row=r, column=3, value=float(it["amount"])).number_format = MONEY
        sched.cell(row=r, column=4, value=_d(it["identification"]["predicted_coverage_start"])).number_format = DATE
        sched.cell(row=r, column=5, value=_d(it["identification"]["predicted_coverage_end"])).number_format = DATE
        sched.cell(row=r, column=6, value=_d(rec["invoice_date"])).number_format = DATE
        for c, p in enumerate(periods, first_p):
            if p in by_period:
                sched.cell(row=r, column=c, value=by_period[p]).number_format = MONEY
        tot_c = last_p + 1
        sched.cell(row=r, column=tot_c, value=f"=SUM({L(first_p)}{r}:{L(last_p)}{r})").number_format = MONEY
        sched.cell(row=r, column=tot_c + 1, value=f"=C{r}-{L(tot_c)}{r}").number_format = MONEY
    n = len(scheduled)
    if n:
        tr = n + 2
        sched.cell(row=tr, column=2, value="TOTAL").font = Font(bold=True)
        for c in [3] + list(range(first_p, last_p + 3)):
            sched.cell(row=tr, column=c, value=f"=SUM({L(c)}2:{L(c)}{n + 1})").number_format = MONEY
            sched.cell(row=tr, column=c).font = Font(bold=True)
    _widths(sched, [9, 30, 13, 13, 13, 13] + [11] * (len(periods) + 2))
    sched.freeze_panes = "G2"

    # ---- Recon ----
    rec_ws = wb.create_sheet("Recon")
    rec_ws["A1"], rec_ws["A2"] = "Month-end reconciliation", "Period (YYYY-MM):"
    rec_ws["A1"].font = Font(bold=True, size=14)
    rec_ws["A2"].font = Font(bold=True)
    default_period = period if period in periods else (periods[0] if periods else period)
    rec_ws["B2"] = default_period
    rec_ws["B2"].fill = INPUT
    if periods:
        dv = DataValidation(type="list", formula1=f"=Schedule!${L(first_p)}$1:${L(last_p)}$1", allow_blank=False)
        rec_ws.add_data_validation(dv)
        dv.add("B2")
    if periods and period not in periods:
        rec_ws["C2"] = f"Requested period {period} is outside all coverage; showing {default_period}."
    _header(rec_ws, 4, ["ID", "Vendor", "Invoice amount", "Expected amortization", "GL posted",
                        "Variance", "Status", "Expected prepaid balance", "GL balance", "Balance variance"])
    hdr_rng = f"Schedule!${L(first_p)}$1:${L(last_p)}$1"
    for i, it in enumerate(scheduled):
        r, sr = 5 + i, 2 + i
        row_rng = f"Schedule!${L(first_p)}{sr}:${L(last_p)}{sr}"
        match = f"MATCH($B$2,{hdr_rng},0)"
        rec_ws.cell(row=r, column=1, value=f"=Schedule!A{sr}")
        rec_ws.cell(row=r, column=2, value=f"=Schedule!B{sr}")
        rec_ws.cell(row=r, column=3, value=f"=Schedule!C{sr}")
        rec_ws.cell(row=r, column=4, value=f"=N(INDEX({row_rng},{match}))")
        rec_ws.cell(row=r, column=5).fill = INPUT
        rec_ws.cell(row=r, column=6, value=f'=IF(E{r}="","",E{r}-D{r})')
        rec_ws.cell(row=r, column=7, value=f'=IF(E{r}="","Not entered",IF(ABS(E{r}-D{r})<0.005,"Tied","Investigate"))')
        rec_ws.cell(row=r, column=8,
                    value=f"=IF(Schedule!$F{sr}>EOMONTH(DATEVALUE($B$2&\"-01\"),0),0,"
                          f"IF(Schedule!$D{sr}>EOMONTH(DATEVALUE($B$2&\"-01\"),0),Schedule!$C{sr},"
                          f"Schedule!$C{sr}-SUM(Schedule!${L(first_p)}{sr}:INDEX({row_rng},{match}))))")
        rec_ws.cell(row=r, column=9).fill = INPUT
        rec_ws.cell(row=r, column=10, value=f'=IF(I{r}="","",I{r}-H{r})')
        for c in (3, 4, 5, 6, 8, 9, 10):
            rec_ws.cell(row=r, column=c).number_format = MONEY
    if n:
        tr = 5 + n
        rec_ws.cell(row=tr, column=2, value="TOTAL").font = Font(bold=True)
        for c in (3, 4, 5, 6, 8, 9, 10):
            rec_ws.cell(row=tr, column=c, value=f"=SUM({L(c)}5:{L(c)}{tr - 1})").number_format = MONEY
            rec_ws.cell(row=tr, column=c).font = Font(bold=True)
    _widths(rec_ws, [9, 30, 15, 16, 14, 13, 13, 18, 14, 16])
    rec_ws.freeze_panes = "A5"

    # ---- Journal Entries ----
    je = wb.create_sheet("Journal Entries")
    _header(je, 1, ["Date", "Ref", "Memo", "Account #", "Account", "Debit", "Credit"])
    for it in items:
        for entry in it["entries"]:
            for line in entry["lines"]:
                je.append([_d(entry["date"]) if isinstance(entry["date"], str) else entry["date"],
                           entry["ref"], entry["memo"], line["account_no"], line["account"],
                           float(line["debit"]) or None, float(line["credit"]) or None])
    for row in je.iter_rows(min_row=2):
        row[0].number_format = DATE
        row[5].number_format = MONEY
        row[6].number_format = MONEY
    _widths(je, [12, 20, 46, 11, 32, 13, 13])
    je.freeze_panes = "A2"

    # ---- Needs Review ----
    rv = wb.create_sheet("Needs Review")
    _header(rv, 1, ["ID", "Vendor", "Amount", "Treatment", "Why it needs review", "Model reasoning"])
    for it in items:
        if it["flags"] or it["treatment"] == "REVIEW":
            rv.append([it["record"]["id"], it["record"]["vendor"], float(it["amount"]),
                       it["treatment"], "; ".join(it["flags"]) or "Flagged",
                       it["identification"]["reasoning"]])
    for row in rv.iter_rows(min_row=2):
        row[2].number_format = MONEY
    _widths(rv, [9, 30, 13, 11, 70, 70])

    wb.save(path)
    return path




