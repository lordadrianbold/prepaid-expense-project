"""One place that calls the model.

- Tolerates SDKs that reject the `temperature` keyword (retries without it).
- On-disk cache: an identical request (model, prompt, image, run number) is
  answered from `.llm_cache/` and costs nothing. Re-running an evaluation after a
  code change that does not alter the prompts or images is free. Set
  P6_NO_CACHE=1 to force live calls. Caching means a re-run returns the SAME
  model replies; use a new --name and P6_NO_CACHE=1 when you want fresh variation.
- Tallies calls, cache hits and tokens so a run can print what it used.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from .config import TEMPERATURE

TEMPERATURE_APPLIED = True  # flips to False if the SDK refused the argument
CACHE_DIR = Path(__file__).resolve().parent.parent / ".llm_cache"
class BudgetExceeded(RuntimeError):
    pass


def _max_live_calls():
    v = os.environ.get("P6_MAX_LIVE_CALLS")
    return int(v) if v and v.isdigit() else None


STATS = {"live_calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}


def reset_stats():
    for k in STATS:
        STATS[k] = 0


def _cache_key(kwargs, salt):
    blob = json.dumps({"kw": kwargs, "salt": salt}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _call(client, kwargs):
    global TEMPERATURE_APPLIED
    if TEMPERATURE_APPLIED:
        try:
            return client.messages.create(temperature=TEMPERATURE, **kwargs)
        except TypeError as e:
            if "temperature" not in str(e):
                raise
            TEMPERATURE_APPLIED = False
            print("NOTE: this anthropic SDK has no 'temperature' option, so calls run without it. "
                  "Results can vary slightly between runs; the cache keeps a saved run repeatable.")
    return client.messages.create(**kwargs)


def create_message(client, cache_salt=None, **kwargs):
    use_cache = not os.environ.get("P6_NO_CACHE")
    path = CACHE_DIR / f"{_cache_key(kwargs, cache_salt)}.json" if use_cache else None
    if path is not None and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            STATS["cache_hits"] += 1
            return SimpleNamespace(content=[SimpleNamespace(text=data["text"])],
                                   usage=SimpleNamespace(input_tokens=0, output_tokens=0), cached=True)
        except (OSError, ValueError, KeyError):
            pass  # unreadable cache entry: fall through to a live call
    cap = _max_live_calls()
    if cap is not None and STATS["live_calls"] >= cap:
        raise BudgetExceeded(f"Stopped before call {cap + 1}: P6_MAX_LIVE_CALLS={cap} reached. "
                             f"Finished replies are cached, so re-running continues from here.")
    resp = _call(client, kwargs)
    STATS["live_calls"] += 1
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    STATS["input_tokens"] += tin
    STATS["output_tokens"] += tout
    try:
        text = resp.content[0].text
    except (AttributeError, IndexError, TypeError):
        text = None
    if path is not None and isinstance(text, str):
        try:
            CACHE_DIR.mkdir(exist_ok=True)
            path.write_text(json.dumps({"text": text, "input_tokens": tin, "output_tokens": tout}),
                            encoding="utf-8")
        except OSError:
            pass
    return resp


def usage_line():
    s = STATS
    return (f"API usage this run: {s['live_calls']} live calls, {s['cache_hits']} answered from cache (free), "
            f"{s['input_tokens']:,} input tokens, {s['output_tokens']:,} output tokens")





