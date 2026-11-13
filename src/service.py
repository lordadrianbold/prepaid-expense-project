"""Project 6: web demo (FastAPI). Same pipeline as the command line, behind a page.

  uvicorn src.service:app --port 8000        then open http://localhost:8000

Two modes on the page:
  * Sample bills: free. Saved sample records go through the REAL code checks, schedule and
    journal entries. The AI step uses the saved answer key (clearly labelled "sample").
  * Upload your own: reads the file with the AI (costs a little). Limited per visitor per
    hour and per day, so a public demo cannot run up a bill.
"""
import json
import os
import tempfile
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from decimal import Decimal
from pathlib import Path

try:  # optional: loads ANTHROPIC_API_KEY from a .env file on the developer machine
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from . import llm
from .config import RESULTS_DIR
from .document_checks import check_extraction
from .pipeline import process_extracted, truth_identifier
from .version import code_version

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SAMPLES_FILE = ROOT / "data" / "demo_samples.json"

MAX_UPLOAD_BYTES = int(os.environ.get("P6_MAX_UPLOAD_MB", "8")) * 1024 * 1024
PER_IP_PER_HOUR = int(os.environ.get("P6_DEMO_PER_IP_HOUR", "5"))
PER_DAY_TOTAL = int(os.environ.get("P6_DEMO_PER_DAY", "50"))
ALLOWED = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MAGIC = {".pdf": b"%PDF", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff", ".png": b"\x89PNG"}

app = FastAPI(title="Prepaid Expense Identification & Amortization")

_lock = threading.Lock()
_ip_hits = defaultdict(deque)   # ip -> timestamps (last hour)
_day = {"date": None, "count": 0}
_worksheets = {}                # token -> xlsx path (small, newest 30 kept)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")  # behind a load balancer on AWS
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?"))


def _check_limits(ip: str):
    """Raise 429 when this visitor or the whole demo is over its live-upload limit."""
    now, today = time.time(), date.today().isoformat()
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, count=0)
        if _day["count"] >= PER_DAY_TOTAL:
            raise HTTPException(429, "The demo has reached its daily limit of live uploads. "
                                     "Please try the sample bills, or come back tomorrow.")
        hits = _ip_hits[ip]
        while hits and now - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= PER_IP_PER_HOUR:
            raise HTTPException(429, f"Limit of {PER_IP_PER_HOUR} live uploads per hour reached. "
                                     f"Please try the sample bills, or come back later.")
        hits.append(now)
        _day["count"] += 1


def _money(x):
    return float(x) if isinstance(x, Decimal) else x


def _jsonable(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def result_payload(ext: dict, item: dict, source: str, worksheet_token=None) -> dict:
    """Plain, JSON-safe answer for the page."""
    ident = item["identification"]
    amount = ext.get("amount")
    start, end = ident.get("predicted_coverage_start"), ident.get("predicted_coverage_end")
    return _jsonable({
        "source": source,  # "ai" or "sample"
        "file": ext.get("source_file"),
        "vendor": ext.get("vendor"),
        "invoice_date": ext.get("invoice_date"),
        "amount": amount,
        "ai_says": ident["predicted_classification"],
        "service_period": {"start": start, "end": end} if start and start != "null" else None,
        "decision": item["treatment"],
        "needs_review": item["treatment"] == "REVIEW",
        "review_reasons": item["flags"],
        "notes": item["notes"],
        "prepayment_type": item["prepayment_type"],
        "description_read": (ext.get("description") or "")[:300],
        "schedule": item["schedule"],
        "entries": item["entries"],
        "reads_disagreed_on": ext.get("fields_with_disagreement") or [],
        "worksheet_token": worksheet_token,
    })


def _build_worksheet(item: dict):
    try:
        from .worksheet import build_workbook
        RESULTS_DIR.mkdir(exist_ok=True)
        token = uuid.uuid4().hex[:12]
        path = RESULTS_DIR / f"demo_{token}.xlsx"
        build_workbook([item], date.today().strftime("%Y-%m"), str(path))
        with _lock:
            _worksheets[token] = str(path)
            while len(_worksheets) > 30:
                old = _worksheets.pop(next(iter(_worksheets)))
                Path(old).unlink(missing_ok=True)
        return token
    except Exception:
        return None  # the answer on the page is the main result


def load_samples() -> list:
    if not SAMPLES_FILE.exists():
        return []
    return json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))


def run_sample(sample: dict) -> dict:
    """Saved sample: real checks/schedule/entries, saved answer key for the AI step."""
    ext = dict(sample["extracted"])
    ident = sample["answer_key"]
    item = process_extracted(ext, identifier=lambda rec: {
        "id": rec["id"], "vendor": rec["vendor"],
        "predicted_classification": ident["classification"],
        "predicted_coverage_start": ident.get("start"), "predicted_coverage_end": ident.get("end"),
        "reasoning": "Saved sample answer (no AI call)."})
    return result_payload(ext, item, "sample", _build_worksheet(item))


@app.get("/health")
async def health():
    return {"status": "ok", "code_version": code_version(),
            "live_uploads_enabled": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/samples")
async def samples():
    return [{"id": s["id"], "title": s["title"], "blurb": s["blurb"]} for s in load_samples()]


@app.get("/sample/{sample_id}")
async def sample(sample_id: str):
    for s in load_samples():
        if s["id"] == sample_id:
            return run_sample(s)
    raise HTTPException(404, "Unknown sample.")


@app.post("/process")
async def process(request: Request, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "Please upload a PDF, JPG or PNG file.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "Live uploads are switched off on this server. Please try the sample bills.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is too large (limit {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")
    if not data.startswith(MAGIC[suffix]):
        raise HTTPException(400, "That file does not look like a real " + suffix.strip(".").upper() + ".")
    _check_limits(_client_ip(request))

    from .extract_invoice import extract_invoice
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(data)
        try:
            ext = extract_invoice(path, runs=1)
            ext["source_file"] = Path(file.filename).name[:80]
            item = process_extracted(ext)
        except llm.BudgetExceeded:
            raise HTTPException(503, "The demo's call budget is used up. Please try the sample bills.")
    return result_payload(ext, item, "ai", _build_worksheet(item))


@app.get("/worksheet/{token}")
async def worksheet(token: str):
    path = _worksheets.get(token)
    if not path or not Path(path).exists():
        raise HTTPException(404, "Worksheet expired. Please run the bill again.")
    return FileResponse(path, filename="prepaid_worksheet.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))



