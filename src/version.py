"""A short fingerprint of the code in src/, printed by preflight and at the start of
every run. It ignores spaces, tabs and line breaks, so only a real change in the
code changes the number."""
import hashlib
import re
from pathlib import Path


def code_version() -> str:
    h = hashlib.sha256()
    for p in sorted(Path(__file__).resolve().parent.glob("*.py")):
        if p.name == "version.py":
            continue
        h.update(p.name.encode())
        text = p.read_bytes().decode("utf-8", errors="replace")
        h.update(re.sub(r"\s+", "", text).encode())
    return h.hexdigest()[:8]



