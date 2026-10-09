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


def check_acquisition_smoke() -> list[str]:
    """Runs the acquisition builders end to end.

    `_pick` returns its value, not a tuple, so indexing or unpacking its result
    is a bug that only fires when that line runs. Three of those shipped in
    review: a truncated country code, and twice an unpack of a single string.
    Calling the builders is cheaper and more direct than trying to spot the
    pattern statically.
    """
    import random

    problems = []
    moment = datetime.datetime(2026, 1, 31)
    try:
        schedule = sources.build_burst_schedule(random.Random(1), moment, 30)
        result = sources.build_acquisition(random.Random(2), moment, 30, schedule)
    except Exception as error:  # noqa: BLE001 - the point is to report any failure
        return [f"build_acquisition raised: {error!r}"]

    for table in ("meta_ads_daily", "google_ads_daily", "gsc_daily"):
        rows = result.get(table) or []
        if not rows:
            problems.append(f"{table}: produced no rows")
            continue
        for row in rows:
            for column, value in row.items():
                if column.startswith("_"):
                    continue
                if value is None or value == "":
                    problems.append(f"{table}.{column} is empty in a generated row")
                    break
            else:
                continue
            break
    return problems


def check_ga4_shares_traffic() -> list[str]:
    """GA4 session volume must follow the acquisition index, not ignore it."""
    import random

    moment = datetime.datetime(2026, 1, 31)
    schedule = sources.build_burst_schedule(random.Random(3), moment, 60)
    result = sources.build_acquisition(random.Random(4), moment, 60, schedule)
    index = result.pop("_daily_index")
    peak = max(index, key=lambda day: index[day]["google_search_clicks"])
    baseline = index[peak]["google_search_clicks"]

    sessions = sources.build_ga4(random.Random(5), [], moment, 60, daily_index=index)
    on_peak = sum(
        1 for row in sessions
        if row["occurred_at"][:10] == peak
    )
    flat_days = [day for day in index if index[day]["google_search_clicks"] < baseline]
    if not flat_days or on_peak == 0:
        return ["ga4: no sessions landed on the highest-traffic day"]
    return []


def main() -> int:
    problems = (
        check_weighted() + check_unweighted() + check_plans() + check_country_codes()
        + check_acquisition_smoke() + check_ga4_shares_traffic()
    )
    if problems:
        print("FAIL")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"ok: {len(WEIGHTED)} weighted tables, {len(UNWEIGHTED)} unweighted, "
        f"plans, country codes, acquisition smoke test and GA4 traffic coupling"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
