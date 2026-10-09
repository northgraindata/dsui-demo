"""Seeds and refreshes the synthetic e-commerce dataset behind the demo.

One dataset feeds the whole story: raw tables in PostgreSQL, CSV exports for
object storage, and a local DuckDB file. A visitor should never see two
unrelated worlds.

The raw tables are written the way real ingestion writes them, which is to say
badly. Dates arrive in five formats, money arrives as a number and as a decorated
string, statuses change case, roughly one percent of customers are duplicated,
and a few order items point at orders that do not exist. That mess is not
sloppiness, it is the input dbt exists to clean, and typing it away here would
hide the work the demo is meant to show.

Usage:

    python generate.py seed      # rebuild history from scratch
    python generate.py append    # add a trickle of recent activity
    python generate.py export    # rewrite the CSV and DuckDB outputs
    python generate.py verify    # row counts, for a smoke check

Every mode is seeded, so two `seed` runs with the same `--as-of` produce
byte-identical tables. Left to the wall clock they differ only in their absolute
timestamps.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

import sources

HISTORY_DAYS = 540
SEED = 20240817

ENVIRONMENT = Path(os.environ.get("DEMO_EXPORT_DIR", "./out"))

RAW_TABLES = (
    "customers",
    "products",
    "subscriptions",
    "orders",
    "order_items",
    "payments",
    "refunds",
    "events",
    "accounts",
    "stripe_customers",
    "stripe_subscriptions",
    "stripe_invoices",
    "stripe_charges",
    "stripe_refunds",
    "stripe_balance_transactions",
    "posthog_people",
    "posthog_events",
    "ga4_sessions",
)

# Tables whose rows come from `sources` and are projected by that module's own
# `*_rows` helper, because they carry vendor payload columns the generic
# renderer does not model.
SOURCE_TABLES = frozenset({
    "accounts",
    "stripe_customers",
    "stripe_subscriptions",
    "stripe_invoices",
    "stripe_charges",
    "stripe_refunds",
    "stripe_balance_transactions",
    "posthog_people",
    "posthog_events",
    "ga4_sessions",
})

COLUMNS = {
    "customers": (
        "customer_id",
        "email",
        "full_name",
        "country",
        "signup_at",
        "plan",
        "mrr",
        "is_trial",
        "referred_by",
        "last_seen_at",
    ),
    "products": ("sku", "name", "category", "price", "cost", "launched_at"),
    "subscriptions": (
        "subscription_id",
        "customer_id",
        "plan",
        "status",
        "seats",
        "mrr",
        "started_at",
        "ended_at",
    ),
    "orders": (
        "order_id",
        "customer_id",
        "placed_at",
        "status",
        "currency",
        "total",
        "channel",
        "coupon_code",
    ),
    "order_items": ("order_id", "sku", "quantity", "unit_price", "discount"),
    "payments": (
        "payment_id",
        "order_id",
        "method",
        "status",
        "amount",
        "captured_at",
        "failure_reason",
    ),
    "refunds": (
        "refund_id",
        "payment_id",
        "order_id",
        "created_at",
        "amount",
        "reason",
    ),
    "events": (
        "event_id",
        "customer_id",
        "name",
        "occurred_at",
        "properties",
    ),
    "accounts": (
        "account_id",
        "name",
        "plan",
        "seats",
        "country",
        "created_at",
        "status",
        "mrr",
        "trial_ends_at",
        "churned_at",
    ),
    "stripe_customers": ("stripe_id", "created_at", "payload"),
    "stripe_subscriptions": (
        "stripe_id", "customer_id", "status", "created_at", "current_period_end", "payload",
    ),
    "stripe_invoices": (
        "stripe_id", "customer_id", "subscription_id", "status", "created_at", "payload",
    ),
    "stripe_charges": (
        "charge_id", "customer_id", "status", "currency", "amount", "created_at", "payload",
    ),
    "stripe_refunds": ("refund_id", "charge_id", "created_at", "amount", "payload"),
    "stripe_balance_transactions": (
        "txn_id", "charge_id", "type", "created_at", "amount", "fee", "net", "payload",
    ),
    "posthog_people": ("distinct_id", "created_at", "properties"),
    "posthog_events": (
        "event_id", "event", "distinct_id", "occurred_at",
        "current_url", "referrer", "browser", "os", "properties",
    ),
    "ga4_sessions": (
        "session_id", "occurred_at", "country", "device_category", "traffic_source",
        "source_medium", "campaign", "session_number", "engagement_time_msec", "is_bounce",
    ),
}

COUNTRIES = [
    ("DE", 0.19), ("US", 0.17), ("GB", 0.11), ("FR", 0.09), ("NL", 0.07),
    ("PL", 0.06), ("ES", 0.05), ("SE", 0.05), ("IE", 0.04), ("IT", 0.04),
    ("DK", 0.03), ("PT", 0.03), ("FI", 0.02), ("CZ", 0.02), ("NO", 0.01),
    ("AT", 0.01), ("BE", 0.01),
]

CATEGORIES = [
    ("Audio", 0.16), ("Lighting", 0.14), ("Kitchen", 0.14), ("Outdoor", 0.12),
    ("Storage", 0.11), ("Wearables", 0.10), ("Furniture", 0.09),
    ("Stationery", 0.08), ("Fitness", 0.06),
]

PRODUCT_WORDS = [
    "Halo", "Nimbus", "Vertex", "Lumen", "Cobalt", "Atlas", "Quartz", "Ember",
    "Harbor", "Onyx", "Slate", "Prism", "Cascade", "Beacon", "Drift", "Fathom",
    "Grid", "Marlin", "Pebble", "Summit", "Tundra", "Willow", "Zephyr",
]
PRODUCT_NOUNS = [
    "Speaker", "Lamp", "Kettle", "Pack", "Watch", "Desk", "Notebook", "Rack",
    "Throw", "Sensor", "Bar", "Set", "Stand", "Cabinet", "Mat", "Hub",
]

# Each entry is (payload, weight); `weighted` returns the payload. The weights
# follow a realistic SaaS shape: mostly free and cheap, very few enterprise.
PLANS = [
    (("Free", 0.00, 0, 1), 0.34),
    (("Starter", 29.00, 29, 3), 0.31),
    (("Growth", 99.00, 89, 12), 0.22),
    (("Scale", 299.00, 249, 40), 0.10),
    (("Enterprise", 1200.00, 950, 120), 0.03),
]

CHANNELS = [
    ("web", 0.52), ("ios", 0.18), ("android", 0.15), ("partner", 0.09),
    ("marketplace", 0.06),
]

PAYMENT_METHODS = [
    ("card", 0.68), ("paypal", 0.16), ("wallet", 0.09), ("bank_transfer", 0.05),
    ("credit_note", 0.02),
]

ORDER_STATUSES = [
    ("delivered", 0.71), ("shipped", 0.11), ("fulfilled", 0.06),
    ("paid", 0.05), ("cancelled", 0.04), ("refunded", 0.02), ("pending", 0.01),
]

FAILURE_REASONS = [
    "insufficient_funds", "card_declined", "expired_card",
    "authentication_required", "processor_unavailable",
]

EVENT_NAMES = [
    ("product_viewed", 0.26), ("search_performed", 0.19),
    ("cart_updated", 0.15), ("checkout_started", 0.11),
    ("subscription_renewed", 0.09), ("login", 0.08), ("report_exported", 0.05),
    ("invite_sent", 0.03), ("api_error", 0.025), ("webhook_failed", 0.015),
]

FIRST_NAMES = [
    "Anna", "Lukas", "Marta", "Jonas", "Karin", "Piotr", "Elena", "Tomas",
    "Nina", "Marek", "Julia", "Adam", "Klara", "Pavel", "Ines", "Rafał",
    "Sofia", "David", "Lena", "Michał", "Ola", "Jan", "Maja", "Kuba",
]
LAST_NAMES = [
    "Nowak", "Kowalski", "Weber", "Schmidt", "Muller", "Novak", "Silva",
    "Kaya", "Jansen", "Bakker", "Lindqvist", "Hansen", "Moreau", "Rossi",
    "Ferreira", "Kowalczyk", "Wójcik", "Zielinski", "Andersen", "Virtanen",
]


def utcnow() -> datetime:
    """Naive UTC, everywhere.

    The generator mixes timestamps it reads from the wall clock with ones it
    generates, and comparing an aware datetime to a naive one raises rather
    than guessing. So there is exactly one clock and it is naive.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def weighted(rng: random.Random, options: list[tuple]) -> object:
    """Picks one entry from ``(value, weight)`` pairs."""
    total = sum(weight for _, weight in options)
    threshold = rng.random() * total
    cumulative = 0.0
    for value, weight in options:
        cumulative += weight
        if threshold <= cumulative:
            return value
    return options[-1][0]


# --------------------------------------------------------------------------
# Messy rendering. These four functions are the reason the demo exists.
# --------------------------------------------------------------------------


def messy_timestamp(moment: datetime, rng: random.Random) -> str:
    """Renders a timestamp in one of the formats ingestion actually produces."""
    roll = rng.random()
    if roll < 0.84:
        return moment.strftime("%Y-%m-%d %H:%M:%S")
    if roll < 0.91:
        return moment.strftime("%d/%m/%Y %H:%M")
    if roll < 0.95:
        return moment.isoformat() + "Z"
    if roll < 0.975:
        return moment.strftime("%Y-%m-%d")
    return str(int(moment.replace(tzinfo=timezone.utc).timestamp()))


def messy_money(amount: float, rng: random.Random) -> str:
    """Renders an amount as a number, or decorated in ways spreadsheets produce."""
    roll = rng.random()
    if roll < 0.88:
        return f"{amount:.2f}"
    if roll < 0.94:
        return f"${amount:,.2f}"
    if roll < 0.97:
        return f"{amount:.2f} EUR"
    return f"{amount:.2f}".replace(".", ",")


def messy_status(status: str, rng: random.Random) -> str:
    """Leaves casing to chance, the way three upstream systems would."""
    roll = rng.random()
    if roll < 0.90:
        return status
    if roll < 0.95:
        return status.upper()
    return status.capitalize()


def messy_integer(value: int, rng: random.Random) -> str:
    """Occasionally delivers a number as text with stray whitespace."""
    if rng.random() < 0.03:
        return f" {value} "
    return str(value)


def parse_timestamp(value: str | None) -> datetime | None:
    """Recovers a datetime from a raw timestamp string.

    The counterpart to `messy_timestamp`. Any reader of the raw tables needs
    this, which is why dbt gets an equivalent macro later: the generator writes
    the mess on purpose and then has to read its own writing back.

    `DD/MM/YYYY` is parsed day-first, matching what `messy_timestamp` emits.
    """
    if not value:
        return None
    text = value.strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), timezone.utc).replace(tzinfo=None)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_money(value: str | None) -> float:
    """Recovers a number from a raw money string.

    The appender reads the same messy table everything else does, so it has to
    live with the decorations the seed wrote. A real incremental load parses
    these too, usually worse.

    Both separators appear in the wild and mean different things depending on
    where they sit: "1,234.56" groups thousands, "1234,56" uses a decimal
    comma. Which one it is follows from what comes after the last separator.
    """
    if not value:
        return 0.0
    cleaned = value.replace("$", "").replace("EUR", "").strip()
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(",", "")
            if cleaned.rfind(",") < cleaned.rfind(".")
            else cleaned.replace(".", "").replace(",", ".")
        )
    elif "," in cleaned:
        tail = cleaned.rsplit(",", 1)[1]
        cleaned = cleaned.replace(",", ".") if len(tail) == 2 else cleaned.replace(",", "")
    return float(cleaned)


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def seasonality(day: datetime) -> float:
    """Order volume by calendar: growth, weekly rhythm, and a Q4 peak."""
    progress = (day - day.replace(day=1)).days
    growth = 0.62 + 0.75 * (progress / 31.0)
    weekly = 1.0
    if day.weekday() == 5:
        weekly = 0.78
    elif day.weekday() == 6:
        weekly = 0.94
    elif day.weekday() in (0, 1):
        weekly = 1.14
    quarter = (day.month - 1) // 3
    yearly = [0.92, 0.88, 1.04, 1.32][quarter]
    noise = 1.0 + (random.Random(day.toordinal()).random() - 0.5) * 0.18
    return growth * weekly * yearly * noise


def build_dataset(seed: int, customers: int, orders: int, now: datetime):
    """Builds the whole dataset in memory, deterministically."""
    rng = random.Random(seed)
    start = now - timedelta(days=HISTORY_DAYS)

    products = []
    for index in range(800):
        category = weighted(rng, CATEGORIES)
        name = f"{rng.choice(PRODUCT_WORDS)} {rng.choice(PRODUCT_NOUNS)} {index % 7 or 1}"
        price = round(rng.lognormvariate(3.4, 0.85), 2)
        cost = round(price * rng.uniform(0.34, 0.78), 2)
        launched = start - timedelta(days=rng.randint(0, 900))
        products.append({
            "sku": f"SKU-{100000 + index}",
            "name": name,
            "category": category,
            "price": price,
            "cost": cost,
            "launched_at": launched,
        })

    customer_rows = []
    customer_ids = []
    for index in range(customers):
        customer_id = f"CUS-{50000 + index}"
        customer_ids.append(customer_id)
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        country = weighted(rng, COUNTRIES)
        plan, plan_price, _, _ = weighted(rng, PLANS)
        signup = start + timedelta(
            days=rng.random() * HISTORY_DAYS,
            seconds=rng.randint(0, 86399),
        )
        # Roughly two percent arrive with no email at all.
        email = None if rng.random() < 0.02 else f"{first}.{last}{index}@example.com".lower()
        customer_rows.append({
            "customer_id": customer_id,
            "email": email,
            "full_name": f"{first} {last}",
            "country": country,
            "signup_at": signup,
            "plan": plan,
            "mrr": plan_price,
            "is_trial": rng.random() < 0.28,
            "referred_by": rng.random() < 0.18,
            "last_seen_at": signup + timedelta(days=rng.randint(0, 400)),
        })

    # About one percent of customers arrive twice, as a near-duplicate row.
    duplicates = []
    twin_count = min(len(customer_rows), len(customer_rows) // 100)
    if twin_count:
        for row in rng.sample(customer_rows, k=twin_count):
            twin = dict(row)
            twin["customer_id"] = f"{row['customer_id']}-DUP"
            duplicates.append(twin)

    subscriptions = []
    for row in customer_rows:
        if not row["is_trial"] and rng.random() < 0.06:
            continue
        plan, _, plan_mrr, plan_seats = weighted(rng, PLANS)
        started = row["signup_at"] + timedelta(days=rng.randint(0, 20))
        churned = rng.random() < 0.14
        subscriptions.append({
            "subscription_id": f"SUB-{rng.randint(100000, 999999)}",
            "customer_id": row["customer_id"],
            "plan": plan,
            "status": "cancelled" if churned else "active",
            "seats": max(1, int(plan_seats * rng.uniform(0.6, 1.8))),
            "mrr": plan_mrr,
            "started_at": started,
            "ended_at": started + timedelta(days=rng.randint(30, 480)) if churned else None,
        })

    order_rows = []
    item_rows = []
    payment_rows = []
    refund_rows = []

    skus = [p["sku"] for p in products]
    prices = {p["sku"]: p["price"] for p in products}
    currency_for = {row["customer_id"]: rng.choice(["EUR", "EUR", "EUR", "USD", "GBP"])
                    for row in customer_rows}

    placed_days = []
    cursor = start
    while cursor.date() <= now.date():
        placed_days.append(cursor)
        cursor += timedelta(days=1)

    per_day = max(1, orders // len(placed_days))
    for day in placed_days:
        for _ in range(int(per_day * seasonality(day))):
            customer_id = rng.choice(customer_ids)
            placed = day + timedelta(seconds=rng.randint(0, 86399))
            order_id = f"ORD-{rng.randint(1000000, 9999999)}"
            line_count = min(rng.randint(1, 6), len(skus))
            chosen = rng.sample(skus, line_count)
            total = 0.0
            for sku in chosen:
                quantity = rng.choices([1, 2, 3, 4, 6], weights=[64, 20, 9, 4, 3])[0]
                discount = round(prices[sku] * quantity * rng.choice([0, 0, 0, 0.05, 0.1]), 2)
                line_total = round(prices[sku] * quantity - discount, 2)
                total += line_total
                item_rows.append({
                    "order_id": order_id,
                    "sku": sku,
                    "quantity": quantity,
                    "unit_price": prices[sku],
                    "discount": discount,
                    "placed_at": placed,
                })
            status = weighted(rng, ORDER_STATUSES)
            order_rows.append({
                "order_id": order_id,
                "customer_id": customer_id,
                "placed_at": placed,
                "status": status,
                "currency": currency_for[customer_id],
                "total": round(total, 2),
                "channel": weighted(rng, CHANNELS),
                "coupon_code": rng.choice(
                    [None, None, None, None, "WELCOME10", "SPRING15", "LOYALTY20", "welcome10"]
                ),
            })

            method = weighted(rng, PAYMENT_METHODS)
            failed = rng.random() < 0.045
            captured = placed + timedelta(seconds=rng.randint(30, 7200))
            payment_id = f"PAY-{rng.randint(100000, 999999)}"
            payment_rows.append({
                "payment_id": payment_id,
                "order_id": order_id,
                "method": method,
                "status": "failed" if failed else "captured",
                "amount": round(total, 2),
                "captured_at": captured,
                "failure_reason": rng.choice(FAILURE_REASONS) if failed else None,
                "placed_at": placed,
            })
            if not failed and status in ("refunded", "delivered") and rng.random() < 0.04:
                refund_rows.append({
                    "refund_id": f"REF-{rng.randint(100000, 999999)}",
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "created_at": captured + timedelta(days=rng.randint(1, 21)),
                    "amount": round(total * rng.uniform(0.15, 1.0), 2),
                    "reason": rng.choice(
                        ["damaged", "not_as_described", "late_delivery", "changed_mind"]
                    ),
                    "placed_at": placed,
                })

    # A handful of line items point at orders that were never written. Joining
    # them is the first thing a staging model has to survive.
    orphan_count = min(len(item_rows), len(item_rows) // 200)
    if orphan_count:
        for item in rng.sample(item_rows, k=orphan_count):
            item["order_id"] = f"ORD-{rng.randint(1000000, 9999999)}"

    event_rows = []
    for row in customer_rows:
        base = row["signup_at"]
        for _ in range(rng.randint(12, 90)):
            occurred = base + timedelta(
                days=rng.random() * max(1, (now - base).days),
                seconds=rng.randint(0, 86399),
            )
            if occurred > now:
                occurred = now - timedelta(seconds=rng.randint(0, 600))
            event_rows.append({
                "event_id": f"EVT-{rng.randint(1000000, 9999999)}",
                "customer_id": row["customer_id"],
                "name": weighted(rng, EVENT_NAMES),
                "occurred_at": occurred,
                "properties": json.dumps(
                    {"source": weighted(rng, CHANNELS), "session": f"s-{rng.randint(10000, 99999)}"},
                    separators=(",", ":"),
                ),
            })
    event_rows.sort(key=lambda row: row["occurred_at"])

    return {
        "customers": customer_rows + duplicates,
        "products": products,
        "subscriptions": subscriptions,
        "orders": order_rows,
        "order_items": item_rows,
        "payments": payment_rows,
        "refunds": refund_rows,
        "events": event_rows,
    }


def recent_activity(seed: int, count: int, now: datetime):
    """A trickle of new activity, so the demo's charts keep moving.

    Deliberately reads the existing dimension tables rather than inventing new
    customers and products, so appended rows stay referentially coherent with
    the seeded history.
    """
    rng = random.Random(seed + now.hour * 60 + now.minute)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT customer_id, country FROM raw.customers LIMIT 4000")
            customers = cursor.fetchall()
            cursor.execute("SELECT sku, price FROM raw.products")
            products = [(sku, parse_money(price)) for sku, price in cursor.fetchall()]

    skus = [sku for sku, _ in products]
    prices = dict(products)

    orders, items, payments, events = [], [], [], []
    for _ in range(count):
        customer_id, country = rng.choice(customers)
        placed = now - timedelta(seconds=rng.randint(5, 900))
        order_id = f"ORD-{rng.randint(1000000, 9999999)}"
        total = 0.0
        for sku in rng.sample(skus, rng.randint(1, 4)):
            quantity = rng.randint(1, 3)
            line = round(prices[sku] * quantity, 2)
            total += line
            items.append({
                "order_id": order_id,
                "sku": sku,
                "quantity": quantity,
                "unit_price": prices[sku],
                "discount": 0.0,
                "placed_at": placed,
            })
        failed = rng.random() < 0.05
        orders.append({
            "order_id": order_id,
            "customer_id": customer_id,
            "placed_at": placed,
            "status": weighted(rng, [("paid", 0.5), ("fulfilled", 0.3), ("shipped", 0.2)]),
            "currency": "EUR" if country != "US" else "USD",
            "total": round(total, 2),
            "channel": weighted(rng, CHANNELS),
            "coupon_code": rng.choice([None, "WELCOME10"]),
        })
        payments.append({
            "payment_id": f"PAY-{rng.randint(100000, 999999)}",
            "order_id": order_id,
            "method": weighted(rng, PAYMENT_METHODS),
            "status": "failed" if failed else "captured",
            "amount": round(total, 2),
            "captured_at": placed + timedelta(seconds=rng.randint(5, 120)),
            "failure_reason": rng.choice(FAILURE_REASONS) if failed else None,
            "placed_at": placed,
        })
        events.append({
            "event_id": f"EVT-{rng.randint(1000000, 9999999)}",
            "customer_id": customer_id,
            "name": weighted(rng, EVENT_NAMES),
            "occurred_at": placed,
            "properties": json.dumps({"source": "live", "session": f"s-{rng.randint(10000, 99999)}"}),
        })
    return {"orders": orders, "order_items": items, "payments": payments, "events": events}


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def render(table: str, rows: list[dict], rng: random.Random) -> list[tuple]:
    """Turns generated rows into text-typed tuples, mess included.

    Vendor tables are projected by their own module, which knows the columns
    those payloads actually have.
    """
    if table in SOURCE_TABLES:
        projector = {
            "accounts": lambda rs: [
                (r["account_id"], r["name"], r["plan"], messy_integer(r["seats"], rng),
                 r["country"], messy_timestamp(r["created_at"], rng),
                 messy_status(r["status"], rng), messy_money(r["mrr"], rng),
                 messy_timestamp(r["trial_ends_at"], rng) if r["trial_ends_at"] else None,
                 messy_timestamp(r["churned_at"], rng) if r["churned_at"] else None)
                for r in rs
            ],
            "posthog_people": lambda rs: sources.posthog_rows("posthog_people", rs),
            "posthog_events": lambda rs: sources.posthog_rows("posthog_events", rs),
            "ga4_sessions": lambda rs: sources.ga4_rows(rs),
        }.get(table)
        if projector is not None:
            return projector(rows)
        return sources.stripe_rows(table, rows)

    rendered = []
    for row in rows:
        if table == "customers":
            rendered.append((
                row["customer_id"], row["email"], row["full_name"], row["country"],
                messy_timestamp(row["signup_at"], rng), messy_status(row["plan"], rng),
                messy_money(row["mrr"], rng), "true" if row["is_trial"] else "false",
                "true" if row["referred_by"] else None,
                messy_timestamp(row["last_seen_at"], rng),
            ))
        elif table == "products":
            rendered.append((
                row["sku"], row["name"], row["category"],
                messy_money(row["price"], rng), messy_money(row["cost"], rng),
                messy_timestamp(row["launched_at"], rng),
            ))
        elif table == "subscriptions":
            rendered.append((
                row["subscription_id"], row["customer_id"], row["plan"],
                messy_status(row["status"], rng), messy_integer(row["seats"], rng),
                messy_money(row["mrr"], rng), messy_timestamp(row["started_at"], rng),
                messy_timestamp(row["ended_at"], rng) if row["ended_at"] else None,
            ))
        elif table == "orders":
            rendered.append((
                row["order_id"], row["customer_id"], messy_timestamp(row["placed_at"], rng),
                messy_status(row["status"], rng), row["currency"],
                messy_money(row["total"], rng), row["channel"], row["coupon_code"],
            ))
        elif table == "order_items":
            rendered.append((
                row["order_id"], row["sku"], messy_integer(row["quantity"], rng),
                messy_money(row["unit_price"], rng), messy_money(row["discount"], rng),
            ))
        elif table == "payments":
            rendered.append((
                row["payment_id"], row["order_id"], row["method"],
                messy_status(row["status"], rng), messy_money(row["amount"], rng),
                messy_timestamp(row["captured_at"], rng), row["failure_reason"],
            ))
        elif table == "refunds":
            rendered.append((
                row["refund_id"], row["payment_id"], row["order_id"],
                messy_timestamp(row["created_at"], rng), messy_money(row["amount"], rng),
                row["reason"],
            ))
        else:
            rendered.append((
                row["event_id"], row["customer_id"], row["name"],
                messy_timestamp(row["occurred_at"], rng), row["properties"],
            ))
    return rendered


def write_postgres(connection, tables: dict[str, list[dict]], rng: random.Random) -> None:
    with connection.cursor() as cursor:
        for table in RAW_TABLES:
            rows = tables.get(table)
            if not rows:
                continue
            columns = ", ".join(COLUMNS[table])
            with cursor.copy(f"COPY raw.{table} ({columns}) FROM STDIN") as copy:
                for row in render(table, rows, rng):
                    copy.write_row(row)
            print(f"  raw.{table}: {len(rows)}")


def write_exports(tables: dict[str, list[dict]]) -> None:
    """Writes the landing zone: CSV for object storage, Parquet for dbt.

    The generator deliberately does not produce a `.duckdb` file. DuckDB allows
    one writing process, so a generator that kept a handle on it would lock out
    every reader, including the very dbt run the landing zone exists to feed.
    DuckDB is dbt's engine and its output, not the generator's.

    Each file is written to a temporary name and renamed into place, so a reader
    never observes a half-written file and needs no lock.
    """
    ENVIRONMENT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    written = 0

    for table in RAW_TABLES:
        rows = tables.get(table)
        if not rows:
            continue
        rendered = render(table, rows, rng)

        csv_path = ENVIRONMENT / f"{table}.csv"
        with _atomic(csv_path) as handle:
            handle.write(",".join(COLUMNS[table]) + "\n")
            for row in rendered:
                values = [
                    "" if value is None else
                    str(value).replace("\\", "\\\\").replace(",", "\\,")
                    for value in row
                ]
                handle.write(",".join(values) + "\n")

        parquet_path = ENVIRONMENT / f"{table}.parquet"
        write_parquet(table, rendered, parquet_path)
        written += 1

    print(f"  landing: {ENVIRONMENT} ({written} tables as csv + parquet)")


def write_parquet(table: str, rows: list[tuple], path: Path) -> None:
    """Writes one table as Parquet, atomically, all columns as text.

    Text throughout is the point: the raw layer is malformed by design and dbt
    does the typing. Casting here would hide the work.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    columns = COLUMNS[table]
    schema = pa.schema([(name, pa.string()) for name in columns])
    arrays = [
        pa.array(["" if row[index] is None else str(row[index]) for row in rows],
                 type=pa.string())
        for index in range(len(columns))
    ]
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), temporary,
                   compression="zstd")
    temporary.replace(path)


@contextmanager
def _atomic(path: Path):
    """Yields a handle to a temporary sibling, renamed over `path` on success."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    handle = temporary.open("w", encoding="utf-8")
    try:
        yield handle
        handle.close()
        temporary.replace(path)
    except BaseException:
        handle.close()
        temporary.unlink(missing_ok=True)
        raise


def build_full_dataset(seed: int, count_customers: int, count_orders: int,
                       count_accounts: int, now: datetime) -> dict:
    """The whole demo world: the e-commerce side plus every external source.

    All of it shares one `random.Random`, so a single `--as-of` anchors the whole
    dataset and one seed reproduces every source together.
    """
    rng = random.Random(seed)
    dataset = build_dataset(seed, count_customers, count_orders, now)

    accounts = sources.build_accounts(rng, count_accounts, now)
    dataset["accounts"] = accounts
    dataset.update(sources.build_stripe_history(rng, accounts, now))
    dataset.update(sources.build_posthog(rng, accounts, now))
    dataset["ga4_sessions"] = sources.build_ga4(rng, accounts, now, HISTORY_DAYS)
    return dataset


def seed(count_customers: int, count_orders: int, count_accounts: int,
         as_of: str | None) -> None:
    # The dataset is anchored to an end timestamp. Left to the wall clock, two
    # runs differ in their absolute timestamps, so reproducibility needs an
    # explicit anchor: `seed --as-of 2026-01-31T00:00:00` twice is identical.
    if as_of:
        now = datetime.fromisoformat(as_of)
    else:
        now = utcnow()
    print(f"building {count_customers} customers, ~{count_orders} orders and "
          f"{count_accounts} accounts since {(now - timedelta(days=HISTORY_DAYS)).date()}")
    dataset = build_full_dataset(
        SEED, count_customers, count_orders, count_accounts, now
    )

    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema)
            cursor.execute("SELECT raw.truncate_all()")
        rng = random.Random(SEED)
        write_postgres(connection, dataset, rng)
    write_exports(dataset)
    print("seed complete")


# --------------------------------------------------------------------------
# Continuous mode
# --------------------------------------------------------------------------


def tick_volume(moment: datetime, rng: random.Random, burst: float) -> int:
    """How much activity lands in one tick.

    Shaped rather than uniform: quiet overnight, a morning and afternoon bump, a
    weekday bias, and a campaign multiplier when a burst is running. Uniform
    random appends look synthetic in a way that undermines the whole demo.
    """
    hour = moment.hour + moment.minute / 60
    diurnal = 0.35 + 0.95 * max(0.0, -(((hour - 14) / 7) ** 2))
    weekday = 0.55 if moment.weekday() >= 5 else 1.0
    noise = rng.uniform(0.7, 1.4)
    return max(1, int(round(90 * diurnal * weekday * burst * noise)))


def row_estimate(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.posthog_events")
        return cursor.fetchone()[0]


def reset(count_customers: int, count_orders: int, count_accounts: int,
         as_of: str | None) -> None:
    """Rebuilds the whole history window with a fresh anchor."""
    anchor = as_of or utcnow().isoformat(timespec="seconds")
    print(f"reset: reseeding with anchor {anchor}")
    seed(count_customers, count_orders, count_accounts, anchor)


def serve(count_customers: int, count_orders: int, count_accounts: int,
          cap: int, max_age_days: int, as_of: str | None,
          tick_seconds: int, min_reset_interval: int) -> None:
    """Runs until stopped, appending activity and reseeding when it grows too big.

    The cap is enforced in-process rather than by a cron, because a cron that
    misses a window leaves the demo quietly oversized. `scripts/reset.sh` exists
    for a manual or scheduled reset, but it is a convenience, not the mechanism
    that keeps the database bounded.

    A cap below the seeded size cannot ever be satisfied: reseeding rebuilds the
    whole history window, so the size comes straight back over the cap and the
    loop resets forever, hammering the database. That is a configuration error,
    so it is reported and the process exits rather than spinning.
    """
    rng = random.Random(SEED + 7919)
    connection = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        seeded_at = utcnow()
        last_reset: datetime | None = None
        burst = 1.0
        burst_until = seeded_at

        while True:
            now = utcnow()
            rows = row_estimate(connection)
            age_days = (now - seeded_at).days
            due = rows > cap or age_days >= max_age_days

            if due and last_reset is not None and (
                now - last_reset
            ) < timedelta(seconds=min_reset_interval):
                due = False
                print(f"over cap ({rows} > {cap}) but resetting again within "
                      f"{min_reset_interval}s of the last one; holding off")

            if due:
                connection.close()
                reset(count_customers, count_orders, count_accounts, as_of)
                connection = psycopg.connect(os.environ["DATABASE_URL"])
                seeded_at = last_reset = utcnow()
                burst, burst_until = 1.0, seeded_at
                reseeded_rows = row_estimate(connection)
                if reseeded_rows > cap:
                    raise SystemExit(
                        f"cap {cap} is below the seeded size ({reseeded_rows} rows), "
                        "so it can never be satisfied. Raise --cap, or lower "
                        "--customers / --orders / --accounts."
                    )

            # Roughly one burst a week, ramping spend and traffic together.
            if now > burst_until:
                burst = 1.0
                burst_until = now + timedelta(days=rng.randint(4, 11))
            elif rng.random() < 0.02:
                burst = rng.uniform(2.2, 4.5)

            volume = tick_volume(now, rng, burst)
            tables = sources_recent(now, rng, volume, burst)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")  # cheap liveness probe before writing
            write_postgres(connection, tables, rng)
            connection.commit()

            if burst > 1.5:
                print(f"campaign burst x{burst:.1f}: +{volume} events")
            sleep_for = tick_seconds * rng.uniform(0.6, 1.8)
            print(f"appended {volume} at {now.isoformat(timespec='seconds')}; "
                  f"sleeping {sleep_for:.0f}s; rows~{rows}")
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        print("stopping")
    finally:
        connection.close()


def sources_recent(now: datetime, rng: random.Random, volume: int,
                   burst: float) -> dict[str, list[dict]]:
    """A tick's worth of new rows across the external sources.

    Reads the seeded dimensions from the database rather than inventing new
    entities, so appended activity stays referentially coherent with history.
    """
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_id, plan, seats, country, created_at "
                "FROM raw.accounts WHERE lower(status) <> 'churned'"
            )
            accounts = []
            for row in cursor.fetchall():
                created = parse_timestamp(row[4])
                if created is None:
                    continue
                accounts.append({
                    "account_id": row[0], "plan": row[1],
                    "seats": int(parse_money(row[2]) or 1) if row[2] else 1,
                    "country": row[3], "created_at": created,
                    "trial_ends_at": None, "churned_at": None, "status": "active",
                    "mrr": 0.0, "name": row[0],
                })
            cursor.execute("SELECT distinct_id FROM raw.posthog_people LIMIT 20000")
            people = [row[0] for row in cursor.fetchall()]

    accounts = [a for a in accounts if a["created_at"] <= now]
    tables: dict[str, list[dict]] = {
        "posthog_events": _recent_posthog(rng, people, now, volume),
        "ga4_sessions": _recent_ga4(rng, now, int(volume * 0.6 * burst)),
    }
    tables.update(_recent_charges(rng, accounts, now, volume, burst))
    return {table: rows for table, rows in tables.items() if rows}


def _recent_ga4(rng: random.Random, now: datetime, count: int) -> list[dict]:
    """A few minutes' worth of sessions, shaped like the seeded history."""
    sessions = sources.build_ga4(rng, [], now, span_minutes=4)
    return sessions[:count]


def _recent_posthog(rng: random.Random, people: list[str], now: datetime,
                    volume: int) -> list[dict]:
    if not people:
        return []
    events = []
    for _ in range(volume):
        occurred = now - timedelta(seconds=rng.randint(1, 600))
        name = rng.choice(sources.POSTHOG_EVENTS)[0]
        properties = {
            "$current_url": rng.choice(sources.PAGES),
            "$referrer": "https://www.google.com/",
            "$browser": rng.choice(sources.BROWSERS)[0],
            "$os": rng.choice(sources.OSES)[0],
            "$lib": "web",
        }
        if name == "$feature_flag_called":
            properties["$feature_flag"] = rng.choice(sources.FEATURE_FLAGS)[0]
            properties["$feature_flag_variant"] = rng.choice(["control", "treatment"])
        events.append({
            "event_id": f"ph_{rng.getrandbits(64):016x}",
            "event": name,
            "distinct_id": rng.choice(people),
            "occurred_at": sources._messy_timestamp(occurred, rng),
            "current_url": properties["$current_url"],
            "referrer": properties["$referrer"],
            "browser": properties["$browser"],
            "os": properties["$os"],
            "properties": json.dumps(properties, separators=(",", ":")),
        })
    return events


def _recent_charges(rng: random.Random, accounts: list[dict], now: datetime,
                    volume: int, burst: float) -> dict[str, list[dict]]:
    """New successful charges for existing accounts, plus their balance rows."""
    if not accounts:
        return []
    charges, balance = [], []
    for _ in range(max(1, int(volume * 0.05 * burst))):
        account = rng.choice(accounts)
        amount = float(account["plan"] and {
            "Starter": 29.0, "Growth": 99.0, "Scale": 299.0, "Enterprise": 1200.0,
        }.get(account["plan"], 99.0))
        amount *= rng.choice([1, 1, 1, 1, 1.5, 2])
        currency = rng.choice(["eur", "eur", "usd", "gbp"])
        charge = sources._make_charge(
            rng, f"cus_live{rng.getrandbits(40):010x}", None, amount, currency,
            now, account, f"in_live{rng.getrandbits(40):010x}",
        )
        charges.append(charge)
        sources._append_balance(rng, balance, charge, account, now)
    return {"stripe_charges": charges, "stripe_balance_transactions": balance}


def append(count: int) -> None:
    now = utcnow()
    tables = recent_activity(SEED, count, now)
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        write_postgres(connection, tables, random.Random(SEED + now.hour))
    print(f"appended {count} orders at {now.isoformat()}")


def verify() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'raw' ORDER BY table_name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            for table in tables:
                cursor.execute(f"SELECT count(*) FROM raw.{table}")
                print(f"  raw.{table}: {cursor.fetchone()[0]}")
            cursor.execute(
                "SELECT min(placed_at), max(placed_at) FROM raw.orders"
            )
            low, high = cursor.fetchone()
            print(f"  order window: {low} .. {high}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    seed_parser = sub.add_parser("seed", help="rebuild the dataset from scratch")
    seed_parser.add_argument("--customers", type=int, default=5000)
    seed_parser.add_argument("--orders", type=int, default=60000)
    seed_parser.add_argument("--accounts", type=int, default=1200)
    seed_parser.add_argument(
        "--as-of",
        help="ISO timestamp anchoring the end of the history window, for reproducible builds",
    )

    append_parser = sub.add_parser("append", help="add recent activity")
    append_parser.add_argument("--count", type=int, default=25)

    serve_parser = sub.add_parser(
        "serve", help="run continuously, appending activity and reseeding when capped"
    )
    serve_parser.add_argument("--customers", type=int, default=5000)
    serve_parser.add_argument("--orders", type=int, default=60000)
    serve_parser.add_argument("--accounts", type=int, default=1200)
    serve_parser.add_argument(
        "--cap", type=int, default=400_000,
        help="reseed once the event table passes this row count",
    )
    serve_parser.add_argument(
        "--max-age-days", type=int, default=30,
        help="reseed once the seed is this old, regardless of size",
    )
    serve_parser.add_argument("--tick-seconds", type=int, default=300)
    serve_parser.add_argument(
        "--min-reset-interval", type=int, default=3600,
        help="refuse to reseed again within this many seconds of the last one",
    )
    serve_parser.add_argument("--as-of", help="anchor used when reseeding")

    reset_parser = sub.add_parser("reset", help="reseed now and exit")
    reset_parser.add_argument("--customers", type=int, default=5000)
    reset_parser.add_argument("--orders", type=int, default=60000)
    reset_parser.add_argument("--accounts", type=int, default=1200)
    reset_parser.add_argument("--as-of", help="ISO timestamp anchoring the new window")

    sub.add_parser("export", help="rewrite CSV and DuckDB outputs")
    sub.add_parser("verify", help="print row counts")

    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    if args.command == "seed":
        seed(args.customers, args.orders, args.accounts, args.as_of)
    elif args.command == "append":
        append(args.count)
    elif args.command == "serve":
        serve(args.customers, args.orders, args.accounts, args.cap,
              args.max_age_days, args.as_of, args.tick_seconds,
              args.min_reset_interval)
    elif args.command == "reset":
        reset(args.customers, args.orders, args.accounts, args.as_of)
    elif args.command == "export":
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            tables: dict[str, list[dict]] = {}
            with connection.cursor() as cursor:
                for table in RAW_TABLES:
                    cursor.execute(
                        f"SELECT {', '.join(COLUMNS[table])} FROM raw.{table}"
                    )
                    names = [description.name for description in cursor.description]
                    tables[table] = [dict(zip(names, row)) for row in cursor.fetchall()]
        write_exports(tables)
    elif args.command == "verify":
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
