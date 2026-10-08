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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import psycopg

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
)

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
    for row in rng.sample(customer_rows, k=max(1, len(customer_rows) // 100)):
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
    orphans = rng.sample(item_rows, k=max(1, len(item_rows) // 200))
    for item in orphans:
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
    """Turns generated rows into text-typed tuples, mess included."""
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
    """Writes CSVs for object storage and a DuckDB file for the local-file adapter."""
    ENVIRONMENT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)

    for table in RAW_TABLES:
        rows = tables.get(table)
        if not rows:
            continue
        path = ENVIRONMENT / f"{table}.csv"
        with path.open("w", encoding="utf-8") as handle:
            handle.write(",".join(COLUMNS[table]) + "\n")
            for row in render(table, rows, rng):
                values = [
                    "" if value is None else
                    str(value).replace("\\", "\\\\").replace(",", "\\,")
                    for value in row
                ]
                handle.write(",".join(values) + "\n")
    print(f"  csv: {ENVIRONMENT}")

    database = duckdb.connect(str(ENVIRONMENT / "demo.duckdb"))
    try:
        for table in RAW_TABLES:
            rows = tables.get(table)
            if not rows:
                continue
            database.execute(f"DROP TABLE IF EXISTS raw_{table}")
            columns = ", ".join(f"{name} VARCHAR" for name in COLUMNS[table])
            database.execute(f"CREATE TABLE raw_{table} ({columns})")
            database.executemany(
                f"INSERT INTO raw_{table} VALUES ({','.join('?' * len(COLUMNS[table]))})",
                render(table, rows, rng),
            )
        print(f"  duckdb: {ENVIRONMENT / 'demo.duckdb'}")
    finally:
        database.close()


def seed(count_customers: int, count_orders: int, as_of: str | None) -> None:
    # The dataset is anchored to an end timestamp. Left to the wall clock, two
    # runs differ in their absolute timestamps, so reproducibility needs an
    # explicit anchor: `seed --as-of 2026-01-31T00:00:00` twice is identical.
    if as_of:
        now = datetime.fromisoformat(as_of)
    else:
        now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    print(f"building {count_customers} customers and ~{count_orders} orders since "
          f"{(now - timedelta(days=HISTORY_DAYS)).date()}")
    dataset = build_dataset(SEED, count_customers, count_orders, now)

    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        with connection.cursor() as cursor:
            cursor.execute(schema)
            cursor.execute("SELECT raw.truncate_all()")
        rng = random.Random(SEED)
        write_postgres(connection, dataset, rng)
    write_exports(dataset)
    print("seed complete")


def append(count: int) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
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
    seed_parser.add_argument(
        "--as-of",
        help="ISO timestamp anchoring the end of the history window, for reproducible builds",
    )

    append_parser = sub.add_parser("append", help="add recent activity")
    append_parser.add_argument("--count", type=int, default=25)

    sub.add_parser("export", help="rewrite CSV and DuckDB outputs")
    sub.add_parser("verify", help="print row counts")

    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    if args.command == "seed":
        seed(args.customers, args.orders, args.as_of)
    elif args.command == "append":
        append(args.count)
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
