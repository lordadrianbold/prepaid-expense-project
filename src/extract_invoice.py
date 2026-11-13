"""
Project 6, Piece 1: vendor invoice extraction (vision-direct).

Claude reads the invoice image/PDF itself (the approach proven in Project 5).
Beyond vendor / date / total / description it also reads the fields that let
the code CHECK the read: subtotal, tax, due date, and the Notes/Memo/Terms
text (where many invoices put the service period). document_checks.py then
verifies footing, date plausibility and that nothing was dropped.

With runs > 1 it reads several times and records any field the runs disagree
on. A misread that repeats identically across runs is NOT caught that way
(seen on rendered photos), which is why the arithmetic checks exist.
"""
import base64
import json
import mimetypes
import re
from collections import Counter
from pathlib import Path

from .config import MODEL
from .llm import BudgetExceeded, create_message

EXTRACTION_PROMPT = """Read this vendor invoice and respond with ONLY a JSON object:
{
  "vendor": "name of the company that issued the invoice",
  "invoice_date": "YYYY-MM-DD, the date the invoice was ISSUED (not the due date)",
  "due_date": "YYYY-MM-DD or null",
  "subtotal": subtotal before tax as a number, or null if not printed,
  "tax": tax amount in dollars as a number, or null if there is no tax line,
  "amount": the TOTAL amount due as a number, no currency symbol,
  "description": "the line-item description(s), copying VERBATIM any service period, coverage period, policy term, event date or contract term wording exactly as printed",
  "notes": "the verbatim text of EVERY Notes, Memo, Remarks, Terms or Comments section on the page, or null if there is none"
}
Rules: copy only what is printed; do not infer or calculate anything. Read every digit carefully, including the year in each date. If a field is not present, use null."""

FIELDS_COMPARED = ("vendor", "invoice_date", "due_date", "subtotal", "tax", "amount", "description")


_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december",
           "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec")


def _desc_signature(text):
    """The parts of a description that matter for accounting: numbers/dates and
    month names. Wording, case, spacing and punctuation differences are ignored."""
    toks = re.findall(r"[a-z]+|\d+(?:[.,]\d+)*", (text or "").lower())
    return tuple(sorted({t.replace(",", "") for t in toks if t[0].isdigit() or t in _MONTHS}))


def _field_key(field, value):
    return _desc_signature(value) if field == "description" else str(value)


def _num(v):
    if v in (None, "", "null"):
        return None
    try:
        return float(re.sub(r"[,$\s]", "", str(v)))
    except ValueError:
        return None


def _content_block(path: Path):
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = base64.standard_b64encode(path.read_bytes()).decode()
    kind = "document" if mime == "application/pdf" else "image"
    return {"type": kind, "source": {"type": "base64", "media_type": mime, "data": data}}


def image_long_side(path: Path):
    """Pixel length of an image's longer side; None for PDFs (resolution not applicable)."""
    if path.suffix.lower() == ".pdf":
        return None
    from PIL import Image
    with Image.open(path) as im:
        return max(im.size)


def extract_once(path: Path, client, run: int = 0) -> dict:
    resp = create_message(
        client, cache_salt=f"extract-run-{run}", model=MODEL, max_tokens=1000,
        messages=[{"role": "user", "content": [_content_block(path),
                                               {"type": "text", "text": EXTRACTION_PROMPT}]}])
    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    raw = json.loads(text)
    for k in ("subtotal", "tax", "amount"):
        raw[k] = _num(raw.get(k))
    return raw


def extract_invoice(path, client=None, runs: int = 1) -> dict:
    path = Path(path)
    if client is None:
        from anthropic import Anthropic
        client = Anthropic()
    results, errors = [], []
    for run in range(runs):
        try:
            results.append(extract_once(path, client, run))
        except BudgetExceeded:
            raise
        except Exception as e:  # keep going; disagreement is itself information
            errors.append(str(e))
            if len(errors) == 1:
                print(f"  extraction error on {path.name}: {e}")
    if not results:
        return {"id": path.stem, "source_file": path.name, "extraction_error": "; ".join(errors)}
    chosen = Counter(json.dumps(r, sort_keys=True) for r in results).most_common(1)[0][0]
    record = json.loads(chosen)
    record.update({
        "id": path.stem, "source_file": path.name, "runs": len(results),
        "image_long_side": image_long_side(path),
        "fields_with_disagreement": [k for k in FIELDS_COMPARED if len({_field_key(k, r.get(k)) for r in results}) > 1]})
    return record


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(json.dumps(extract_invoice(p, runs=3), indent=2))




        