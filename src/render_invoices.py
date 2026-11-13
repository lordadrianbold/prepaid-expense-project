"""
Project 6: invoice renderer. Turns holdout records into invoice documents so
extraction can be tested end to end with KNOWN ground truth.

Produces, for every record:
  pdf/<id>_<layout>.pdf                 clean, digitally generated invoice
  photos/<id>_<layout>_<level>.jpg      the same invoice, photographed:
                                        desk background, tilt, perspective,
                                        uneven lighting/shadow, blur, noise,
                                        reduced resolution, JPEG compression
  manifest.json                         file -> record id, layout, level, truth

Four layouts on purpose, because real invoices don't share one:
  A classic        description in the line-item table
  B minimal        ISO dates, large "amount due" block
  C memo           generic line item ("Charges per agreement"); the real
                   description lives in a Notes block, as on many real invoices
  D dense          narrow description column that wraps over several lines,
                   item codes, tax column

Built-in traps for the reader: due date next to invoice date, PO/customer/order
numbers that look like amounts, subtotal + tax lines where the TOTAL is the
amount due, four different date formats (month names only: numeric dates
like 03/05/2027 would be ambiguous and unfair).

HONESTY / SAFETY: every page carries a diagonal "SAMPLE - TEST DATA" watermark
and a footer saying it is not a real invoice; invoice numbers start with
TEST-; no logos or brand styling; addresses and phone numbers are invented.
Vendor names come from the records (some are real company names used only as
labels in this synthetic test data). These are test fixtures, not documents to
send to anyone. This tests READING and IDENTIFICATION on clean-text-quality
layouts; it does not test the layout diversity of real-world invoices.

  python -m src.render_invoices --records data/holdout_v3.json --out test_invoices
"""
import argparse
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from .config import DATA_DIR, ROOT

# Real company names that appear in some record sets are swapped for invented
# ones on rendered invoices, so no rendered document names a real business.
FICTIONAL_NAMES = {
    "Atlassian Pty Ltd": "Atlas Ridge Software Pty Ltd", "Snowflake Inc.": "Frostline Data Inc.",
    "Okta, Inc.": "Oakline Identity, Inc.", "HubSpot Inc.": "Hubwell Marketing Inc.",
    "Esri Southeast": "Terra Grid Southeast", "Southwest Airlines": "Southern Skies Airlines",
    "Marriott Business Travel": "Meridian Business Travel", "Amtrak Corporate": "Transcontinental Rail Corporate",
    "Uline Shipping Supply": "Unity Line Shipping Supply", "Quill Corporation": "Quillbrook Corporation",
    "Grainger Industrial Supply": "Graymont Industrial Supply", "Salesforce Inc.": "Sales Harbor Inc.",
    "NetSuite (Oracle)": "NetCrest Systems", "Adobe Inc.": "Adobe Ridge Creative Inc.", "DataDog Inc.": "DataDock Inc.",
    "Zendesk Inc.": "Zenfield Inc.", "Delta Airlines": "Delmar Airlines", "United Airlines": "Unity Skies Airlines",
    "Amazon Business": "Amberly Business Supply", "Office Depot": "Office Harbor", "Uline": "Unity Line",
    "Verizon Wireless": "Veriwave Wireless", "Travelers Insurance Group": "Travelmark Insurance Group",
    "Ironclad Legal Technologies": "Ironvale Legal Technologies",
    "Staples Business Advantage": "Stapleford Business Supply", "Costco Wholesale": "Costmart Wholesale",
    "Total Wine & More": "Total Cellar & More",
}
# Product names swapped inside descriptions for the same reason.
DESCRIPTION_FIXES = {"Jira and Confluence": "issue-tracking and wiki", "Marketing Hub": "marketing automation"}


def fictionalize(rec: dict) -> dict:
    rec = dict(rec)
    rec["vendor"] = FICTIONAL_NAMES.get(rec["vendor"], rec["vendor"])
    for real, fake in DESCRIPTION_FIXES.items():
        rec["description"] = rec["description"].replace(real, fake)
    return rec


LAYOUTS = ["A_classic", "B_minimal", "C_memo", "D_dense"]
LEVELS = ["light", "medium", "heavy"]
W, H = letter
BILL_TO = ["Harborlight Analytics Group", "Accounts Payable", "410 Meridian Plaza, Suite 900", "Denver, CO 80202"]

STREETS = ["Commerce Way", "Industrial Pkwy", "Lakeview Dr", "Harbor St", "Summit Ave", "Oak Ridge Rd", "Market Plaza"]
CITIES = [("Austin", "TX", "78701"), ("Columbus", "OH", "43215"), ("Raleigh", "NC", "27601"),
          ("Portland", "OR", "97204"), ("Tampa", "FL", "33602"), ("Madison", "WI", "53703")]
DATE_FORMATS = {"A_classic": "%B %d, %Y", "B_minimal": "%Y-%m-%d", "C_memo": "%b %d, %Y", "D_dense": "%d %b %Y"}


def money(x) -> str:
    return f"${x:,.2f}"


def _fmt(d: date, layout: str) -> str:
    return d.strftime(DATE_FORMATS[layout]).replace(" 0", " ") if layout != "B_minimal" else d.isoformat()


def _style(size=9, bold=False, leading=None, color=colors.black, align=0):
    return ParagraphStyle("s", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size,
                          leading=leading or size * 1.25, textColor=color, alignment=align)


def para(c, text, x, y_top, width, style):
    p = Paragraph(text, style)
    _, h = p.wrap(width, 2000)
    p.drawOn(c, x, y_top - h)
    return y_top - h


def table(c, data, col_widths, x, y_top, style_cmds):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle(style_cmds))
    _, h = t.wrap(0, 0)
    t.drawOn(c, x, y_top - h)
    return y_top - h


def watermark_and_footer(c):
    c.saveState()
    c.setFillColor(colors.Color(0.88, 0.88, 0.88))
    c.setFont("Helvetica-Bold", 58)
    c.translate(W / 2, H / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "SAMPLE - TEST DATA")
    c.restoreState()
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.Color(0.45, 0.45, 0.45))
    c.drawCentredString(W / 2, 28, "Test document generated for software evaluation. Not a real invoice. Do not pay.")
    c.setFillColor(colors.black)


def make_context(rec, layout, rng):
    inv = date.fromisoformat(rec["invoice_date"])
    amount = float(rec["amount"])
    rate = rng.choice([0.0, 0.0, 0.06, 0.0825]) if layout in ("B_minimal", "D_dense") else rng.choice([0.0, 0.0, 0.07])
    subtotal = round(amount / (1 + rate), 2) if rate else amount
    tax = round(amount - subtotal, 2)           # subtotal + tax == amount exactly
    city, st, zp = rng.choice(CITIES)
    return {
        "inv": inv, "due": inv + timedelta(days=rng.choice([15, 30, 45])),
        "amount": amount, "rate": rate, "subtotal": subtotal, "tax": tax,
        "number": f"TEST-{rng.randint(10000, 99999)}",
        "po": f"PO-{rng.randint(100000, 999999)}", "cust": f"C{rng.randint(1000, 9999)}",
        "order": f"{rng.randint(100000, 999999)}",
        "addr": [f"{rng.randint(100, 9899)} {rng.choice(STREETS)}", f"{city}, {st} {zp}",
                 f"Tel 555-01{rng.randint(10, 99)}"],
        "vendor": escape(rec["vendor"]), "desc": escape(rec["description"]),
    }


def layout_a(c, rec, x, f):
    y = H - 54
    para(c, f"<b>{x['vendor']}</b>", 54, y, 300, _style(16, True))
    yy = y - 24
    for line in x["addr"]:
        yy = para(c, line, 54, yy, 300, _style(9))
    para(c, "INVOICE", W - 54 - 200, y, 200, _style(24, True, align=2))
    table(c, [["Invoice No.", x["number"]], ["Invoice Date", f("inv")], ["Due Date", f("due")],
              ["PO Number", x["po"]]], [80, 120], W - 54 - 200, y - 34,
          [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
           ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    yb = para(c, "<b>Bill To</b>", 54, H - 190, 250, _style(10))
    for line in BILL_TO:
        yb = para(c, line, 54, yb, 250, _style(9))
    d = Paragraph(x["desc"], _style(9))
    y = table(c, [["Description", "Qty", "Unit Price", "Amount"],
                  [d, "1", money(x["subtotal"]), money(x["subtotal"])]],
              [310, 40, 80, 80], 54, yb - 30,
              [("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
               ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("ALIGN", (1, 0), (-1, -1), "RIGHT")])
    rows = [["Subtotal", money(x["subtotal"])]]
    if x["rate"]:
        rows.append([f"Tax ({x['rate'] * 100:.2f}%)", money(x["tax"])])
    rows.append(["TOTAL DUE", money(x["amount"])])
    table(c, rows, [90, 90], W - 54 - 180, y - 18,
          [("FONT", (0, 0), (-1, -1), "Helvetica", 10), ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
           ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black)])
    para(c, "Terms: payment due by the due date shown. Please reference the invoice number with payment.",
         54, 90, 480, _style(8))


def layout_b(c, rec, x, f):
    para(c, "Invoice", 54, H - 54, 300, _style(30))
    para(c, f"<b>{x['vendor']}</b><br/>" + "<br/>".join(x["addr"]), 54, H - 100, 250, _style(9, leading=12))
    table(c, [["INVOICE #", "ISSUED", "PAYMENT DUE"], [x["number"], f("inv"), f("due")]],
          [110, 100, 100], 54, H - 190,
          [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7), ("TEXTCOLOR", (0, 0), (-1, 0), colors.grey),
           ("FONT", (0, 1), (-1, 1), "Helvetica", 10)])
    para(c, "<b>AMOUNT DUE (USD)</b>", W - 54 - 200, H - 60, 200, _style(8, color=colors.grey, align=2))
    para(c, money(x["amount"]), W - 54 - 200, H - 74, 200, _style(24, True, align=2))
    para(c, "<b>BILLED TO</b><br/>" + "<br/>".join(BILL_TO) + f"<br/>Customer ID {x['cust']}", W - 54 - 200, H - 120, 200,
         _style(9, leading=12, align=2))
    d = Paragraph(x["desc"], _style(10))
    y = table(c, [["ITEM", "AMOUNT"], [d, money(x["subtotal"])]], [400, 100], 54, H - 290,
              [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7), ("TEXTCOLOR", (0, 0), (-1, 0), colors.grey),
               ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey), ("LINEBELOW", (0, 1), (-1, 1), 0.5, colors.lightgrey),
               ("VALIGN", (0, 1), (-1, 1), "TOP"), ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    rows = [["Subtotal", money(x["subtotal"])]]
    if x["rate"]:
        rows.append(["Sales tax", money(x["tax"])])
    rows.append(["Total", money(x["amount"])])
    table(c, rows, [400, 100], 54, y - 14, [("FONT", (0, 0), (-1, -1), "Helvetica", 10),
          ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11), ("ALIGN", (1, 0), (1, -1), "RIGHT")])


def layout_c(c, rec, x, f):
    y = H - 54
    para(c, f"<b>{x['vendor']}</b>", 54, y, 300, _style(14, True))
    yy = y - 20
    for line in x["addr"]:
        yy = para(c, line, 54, yy, 300, _style(9))
    para(c, "Tax Invoice", W - 54 - 200, y, 200, _style(18, True, align=2))
    table(c, [["Invoice", x["number"]], ["Date", f("inv")], ["Terms", f"Due {f('due')}"], ["Order", x["order"]]],
          [60, 140], W - 54 - 200, y - 28,
          [("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
           ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    yb = para(c, "<b>Customer</b>", 54, H - 180, 250, _style(10))
    for line in BILL_TO:
        yb = para(c, line, 54, yb, 250, _style(9))
    y = table(c, [["Item", "Total"], ["Charges per agreement (see notes below)", money(x["subtotal"])]],
              [420, 90], 54, yb - 28,
              [("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
               ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.93, 0.93, 0.93))])
    rows = []
    if x["rate"]:
        rows += [["Subtotal", money(x["subtotal"])], ["Tax", money(x["tax"])]]
    rows.append(["Balance due", money(x["amount"])])
    y = table(c, rows, [420, 90], 54, y - 6, [("FONT", (0, 0), (-1, -1), "Helvetica", 10),
              ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11), ("ALIGN", (1, 0), (1, -1), "RIGHT")])
    yn = para(c, "<b>Notes</b>", 54, y - 28, 480, _style(10))
    para(c, x["desc"], 54, yn - 2, 480, _style(10, leading=14))


def layout_d(c, rec, x, f):
    y = H - 50
    para(c, f"<b>{x['vendor']}</b>", 54, y, 280, _style(13, True))
    yy = y - 18
    for line in x["addr"]:
        yy = para(c, line, 54, yy, 280, _style(8))
    para(c, "INVOICE", W - 54 - 220, y, 220, _style(20, True, align=2))
    table(c, [["Invoice No", x["number"], "Customer ID", x["cust"]],
              ["Invoice Date", f("inv"), "Order No", x["order"]],
              ["Due Date", f("due"), "PO No", x["po"]]], [70, 90, 70, 90], W - 54 - 320, y - 30,
          [("FONT", (0, 0), (-1, -1), "Helvetica", 8), ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8),
           ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8), ("BOX", (0, 0), (-1, -1), 0.5, colors.grey)])
    yb = para(c, "<b>Bill To / Service Location</b>", 54, H - 160, 300, _style(9))
    for line in BILL_TO:
        yb = para(c, line, 54, yb, 300, _style(8))
    d = Paragraph(x["desc"], _style(8, leading=10))
    taxcol = f"{x['rate'] * 100:.2f}%" if x["rate"] else "0%"
    y = table(c, [["Item", "Description", "Qty", "Rate", "Tax", "Amount"],
                  [f"SVC-{rec['id'][-3:]}", d, "1", money(x["subtotal"]), taxcol, money(x["subtotal"])]],
              [48, 190, 28, 70, 40, 76], 54, yb - 26,
              [("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
               ("FONT", (0, 1), (-1, 1), "Helvetica", 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.92, 0.95))])
    rows = [["Subtotal", money(x["subtotal"])]]
    if x["rate"]:
        rows.append(["Tax", money(x["tax"])])
    rows.append(["INVOICE TOTAL", money(x["amount"])])
    table(c, rows, [90, 90], W - 54 - 180, y - 12, [("FONT", (0, 0), (-1, -1), "Helvetica", 9),
          ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
          ("BOX", (0, -1), (-1, -1), 0.8, colors.black)])


RENDERERS = {"A_classic": layout_a, "B_minimal": layout_b, "C_memo": layout_c, "D_dense": layout_d}


def render_pdf(rec, layout, seed) -> bytes:
    rng = random.Random(f"{seed}-{rec['id']}")
    x = make_context(rec, layout, rng)
    fmt = lambda key: _fmt(x[key], layout)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    watermark_and_footer(c)
    RENDERERS[layout](c, rec, x, fmt)
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------- photo effect
LEVEL_PARAMS = {  # long side px, tilt deg, blur radius, noise sigma, jpeg quality, shadow strength
    "light":  dict(long=2400, tilt=1.5, blur=0.4, noise=3,  q=88, shadow=0.10),
    "medium": dict(long=1600, tilt=3.5, blur=0.9, noise=6,  q=75, shadow=0.22),
    "heavy":  dict(long=1100, tilt=6.0, blur=1.4, noise=10, q=55, shadow=0.35),
}


def photograph(pdf_bytes: bytes, level: str, seed) -> bytes:
    import numpy as np
    import pymupdf
    from PIL import Image, ImageFilter

    p = LEVEL_PARAMS[level]
    rng = random.Random(f"{seed}-{level}-{len(pdf_bytes)}")
    nprng = np.random.default_rng(rng.randint(0, 2**31))
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=200)
    page = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    page = page.rotate(rng.uniform(-p["tilt"], p["tilt"]), expand=True, fillcolor=(0, 0, 0), resample=Image.BICUBIC)
    m = int(0.10 * page.width)
    canvas_w, canvas_h = page.width + 2 * m, page.height + 2 * m
    base = np.array([rng.randint(70, 120), rng.randint(55, 95), rng.randint(40, 75)], dtype=np.float32)  # desk tone
    desk = np.clip(base + nprng.normal(0, 8, (canvas_h, canvas_w, 1)), 0, 255)
    desk = np.repeat(desk[:, :, :1], 3, axis=2) * (base / base.mean())
    img = Image.fromarray(np.clip(desk, 0, 255).astype("uint8"))
    # page footprint: pure-black pixels came from the rotate() expand fill (the page itself is never pure black)
    corner = (np.array(page).sum(axis=2) == 0)
    rot_mask = Image.fromarray(np.where(corner, 0, 255).astype("uint8")).filter(ImageFilter.MinFilter(3))
    img.paste(page, (m, m), rot_mask)

    # mild perspective, as if the phone were not perfectly overhead
    w, h = img.size
    j = lambda: rng.uniform(-0.03, 0.03) * w
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [(j(), j()), (w + j(), j()), (w + j(), h + j()), (j(), h + j())]
    coeffs = _perspective_coeffs(dst, src)
    img = img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=(40, 30, 20))

    # uneven lighting: a diagonal gradient plus a soft shadow band
    arr = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    ang = rng.uniform(0, np.pi)
    grad = (xx * np.cos(ang) + yy * np.sin(ang)) / (w + h)
    light = 1.0 + p["shadow"] * (grad - 0.5) * 2
    band_c = rng.uniform(0.2, 0.8)
    band = np.exp(-(((xx / w) - band_c) ** 2) / 0.01) * p["shadow"] * 1.5
    arr = arr * (light - band)[:, :, None]

    arr += nprng.normal(0, p["noise"], arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(p["blur"]))
    scale = p["long"] / max(img.size)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=p["q"])
    return out.getvalue()


def _perspective_coeffs(dst, src):
    import numpy as np
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, dtype=np.float64), np.array(B, dtype=np.float64)).tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default=str(DATA_DIR / "holdout_v3.json"))
    ap.add_argument("--out", default=str(ROOT / "test_invoices"))
    ap.add_argument("--seed", default="6")
    ap.add_argument("--no-photos", action="store_true")
    a = ap.parse_args()

    out = Path(a.out)
    (out / "pdf").mkdir(parents=True, exist_ok=True)
    (out / "photos").mkdir(exist_ok=True)
    records = [fictionalize(r) for r in json.load(open(a.records))]
    manifest = []
    for i, rec in enumerate(records):
        layout, level = LAYOUTS[i % len(LAYOUTS)], LEVELS[i % len(LEVELS)]
        pdf = render_pdf(rec, layout, a.seed)
        pdf_name = f"{rec['id']}_{layout}.pdf"
        (out / "pdf" / pdf_name).write_bytes(pdf)
        base = {"record_id": rec["id"], "layout": layout, "vendor": rec["vendor"],
                "invoice_date": rec["invoice_date"], "amount": rec["amount"],
                "true_label": rec["true_label"], "true_coverage_start": rec.get("true_coverage_start"),
                "true_coverage_end": rec.get("true_coverage_end"), "tags": rec.get("tags")}
        manifest.append({**base, "file": f"pdf/{pdf_name}", "kind": "pdf", "level": "clean"})
        if not a.no_photos:
            photo_name = f"{rec['id']}_{layout}_{level}.jpg"
            (out / "photos" / photo_name).write_bytes(photograph(pdf, level, a.seed))
            manifest.append({**base, "file": f"photos/{photo_name}", "kind": "photo", "level": level})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Rendered {len(records)} records -> {len(manifest)} files in {out}")


if __name__ == "__main__":
    main()




    