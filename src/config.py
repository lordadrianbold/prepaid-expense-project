"""Project 6 settings in one place, so nothing is a magic number elsewhere."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"

# Override with env var if you want to compare models.
MODEL = os.environ.get("P6_MODEL", "claude-sonnet-4-5-20250929")

# Amortization convention. "daily" prorates by actual days in each month
# (exact; handles mid-month starts and leap years). "monthly_equal" splits
# evenly across the calendar months the coverage touches. Which one is
# correct is a company POLICY choice, so it is a setting, not hidden logic.
DEFAULT_METHOD = "daily"

# Below this amount, many companies expense immediately instead of
# capitalizing a prepayment (materiality). 0 = capitalize everything the
# model identifies. Set per company policy. Set to $500 AFTER holdout v2
# showed the model capitalizing a $275 membership: a dollar cutoff is a
# company policy, so it lives here as a deterministic rule, not in the prompt.
CAPITALIZATION_THRESHOLD = 500.0

# Chart of accounts. Replace with the real GL numbers when you wire this
# to a company's books.
ACCOUNTS = {
    "prepaid": ("1400", "Prepaid Expenses"),
    "ap": ("2000", "Accounts Payable"),
    "default_expense": ("6900", "Other Operating Expense"),
}

# First keyword found in the description picks the expense account the
# amortization is charged to. Deterministic on purpose: the LLM decides
# WHAT the item is; the ledger mapping is a reviewable lookup table.
EXPENSE_ACCOUNT_KEYWORDS = [
    (("insurance", "policy", "premium"), ("6400", "Insurance Expense")),
    (("software", "saas", "license", "subscription", "platform", "cloud"),
     ("6500", "Software & Subscriptions Expense")),
    (("rent", "lease"), ("6200", "Rent Expense")),
    (("maintenance", "support contract", "warranty"), ("6600", "Maintenance & Support Expense")),
    (("membership", "dues"), ("6700", "Dues & Memberships Expense")),
    (("advertis", "marketing", "sponsorship"), ("6800", "Marketing Expense")),
]


# Randomness off for both model calls: the same input should give the same
# answer, otherwise run-to-run noise (seen on holdout v3: one record flipped
# between identical-input runs) is mistaken for real differences.
TEMPERATURE = float(os.environ.get("P6_TEMPERATURE", "0"))

# Images shorter than this on their long side get a WARNING (not a block):
# every field error seen on rendered photos was at ~1100px; 1600px was clean.
MIN_IMAGE_LONG_SIDE = 1500

# Which identification prompt to use: "v1" (original) or "v2" (revised after
# holdout v2). Read at call time so the evaluator can switch it per run.
DEFAULT_PROMPT_VERSION = "v6"  # v6: code applies the expiration-date adjustment (v5 asked the model to, and it got the year wrong on a real bill)


def get_prompt_version() -> str:
    return os.environ.get("P6_PROMPT_VERSION", DEFAULT_PROMPT_VERSION)

# Invoice-date plausibility: an invoice dated further than this into the future
# is treated as a probable misread (e.g. 2026 read as 2028). Real invoices are
# dated today or earlier; the default is loose because the test fixtures are
# dated up to ~9 months ahead. Tighten it (e.g. P6_MAX_FUTURE_DAYS=30) in real use.
MAX_FUTURE_DAYS = int(os.environ.get("P6_MAX_FUTURE_DAYS", "366"))
MAX_PAST_DAYS = int(os.environ.get("P6_MAX_PAST_DAYS", "1100"))



