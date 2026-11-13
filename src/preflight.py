"""Run this BEFORE spending anything:  python -m src.preflight [--manifest ...] [--runs N] [--live]

Checks, without calling the API (unless --live): code version, SDK version,
whether a key is set, the prompt in use, that the manifest and its files exist,
and the worst-case number of API calls. --live makes ONE tiny call to confirm the
key and model work (a few hundred tokens)."""
import argparse
import json
import os
import sys
from pathlib import Path

from .config import MODEL, get_prompt_version
from .version import code_version


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--kind", choices=["pdf", "photo", "all"], default="all")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    ok = True

    import anthropic
    print(f"code version : {code_version()}   (compare with the number the run prints)")
    print(f"python       : {sys.version.split()[0]}   anthropic SDK: {anthropic.__version__}")
    print(f"model        : {MODEL}   prompt: {get_prompt_version()}")
    print(f"api key set  : {'yes' if os.environ.get('ANTHROPIC_API_KEY') else 'NO'}")
    ok &= bool(os.environ.get("ANTHROPIC_API_KEY"))
    needed = ["llm.py", "version.py", "document_checks.py", "extract_invoice.py", "identify.py", "pipeline.py"]
    missing = [n for n in needed if not (Path(__file__).parent / n).exists()]
    print(f"src files    : {'all present' if not missing else 'MISSING ' + ', '.join(missing)}")
    ok &= not missing
    cap = os.environ.get("P6_MAX_LIVE_CALLS")
    print(f"call cap     : {cap or 'none (set P6_MAX_LIVE_CALLS to add one)'}")

    if a.manifest:
        m = json.load(open(a.manifest))
        root = Path(a.manifest).parent
        entries = [e for e in m if a.kind in ("all", e["kind"])]
        gone = [e["file"] for e in entries if not (root / e["file"]).exists()]
        calls = len(entries) * a.runs + len(entries)
        print(f"manifest     : {len(entries)} files, {len(gone)} missing; worst case {calls} live calls "
              f"({len(entries) * a.runs} reads + {len(entries)} classifications); cached replies are free")
        ok &= not gone

    if a.live:
        from .llm import STATS, create_message
        r = create_message(anthropic.Anthropic(), model=MODEL, max_tokens=5,
                           messages=[{"role": "user", "content": "Reply with the word OK."}])
        print(f"live check   : model answered {r.content[0].text.strip()!r} "
              f"({STATS['input_tokens']} in / {STATS['output_tokens']} out tokens)")
    print("\nREADY" if ok else "\nNOT READY: fix the items above before running")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()




    