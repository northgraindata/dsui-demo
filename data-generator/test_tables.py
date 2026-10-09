"""Guards the weighted-choice tables.

Every `_pick` / `weighted` call takes `(value, weight)` pairs and unpacks two
elements per row. A table written as a flat list, or as `(a, b, weight)`, does
not fail where it is defined: it fails later, on whichever code path happens to
reach it, which in a generator means a crash that only shows up for some seeds
or some volumes. Three such tables shipped in the first draft of `sources.py`.

So the shape is asserted here instead, once, for every table the module exposes.

Run with: python test_tables.py
"""

from __future__ import annotations

import datetime
import sys

import sources

WEIGHTED = [
    "CARD_BRANDS",
    "CARD_COUNTRIES",
    "CURRENCIES",
    "SUBSCRIPTION_STATUSES",
    "FAILURE_CODES",
    "POSTHOG_EVENTS",
    "FEATURE_FLAGS",
    "BROWSERS",
    "OSES",
    "GA4_SOURCES",
]

# Sampled with `rng.choice`, so a flat list is correct and weights would be a bug.
UNWEIGHTED = ["PAGES"]


def check_weighted() -> list[str]:
    problems = []
    for name in WEIGHTED:
        table = getattr(sources, name)
        if not table:
            problems.append(f"{name}: empty")
            continue
        for entry in table:
            if not isinstance(entry, tuple):
                problems.append(f"{name}: {entry!r} is not a tuple")
            elif len(entry) != 2:
                problems.append(f"{name}: {entry!r} has {len(entry)} elements, expected 2")
            elif not isinstance(entry[1], float):
                problems.append(f"{name}: {entry!r} weight is {type(entry[1]).__name__}")
    return problems


def check_unweighted() -> list[str]:
    problems = []
    for name in UNWEIGHTED:
        table = getattr(sources, name)
        if not table:
            problems.append(f"{name}: empty")
        for entry in table:
            if isinstance(entry, tuple):
                problems.append(f"{name}: {entry!r} is weighted but sampled with rng.choice")
    return problems


def check_plans() -> list[str]:
    """`plans` is built inside `build_accounts`, so it is checked by sampling."""
    import random

    problems = []
    try:
        for seed in range(50):
            sources.build_accounts(random.Random(seed), 3, datetime.datetime(2026, 1, 31))
    except Exception as error:  # noqa: BLE001 - the point is to report any failure
        problems.append(f"build_accounts raised: {error!r}")
    return problems


def check_country_codes() -> list[str]:
    """A country code is two letters.

    `_pick` already returns the value, so indexing its result once more yields
    a single character. That shipped as `"country": "D"` before this check.
    """
    import random

    problems = []
    valid = {code for code, _ in sources.CARD_COUNTRIES}
    for seed in range(50):
        for account in sources.build_accounts(
            random.Random(seed), 25, datetime.datetime(2026, 1, 31)
        ):
            if account["country"] not in valid:
                problems.append(f"build_accounts country={account['country']!r}")
                break
    return problems


def main() -> int:
    problems = (
        check_weighted() + check_unweighted() + check_plans() + check_country_codes()
    )
    if problems:
        print("FAIL")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"ok: {len(WEIGHTED)} weighted tables, {len(UNWEIGHTED)} unweighted, "
        f"plans and country codes sample cleanly"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
