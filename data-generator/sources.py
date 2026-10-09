"""External source generators: Stripe, PostHog, GA4.

Each source mimics how that vendor actually hands data over, because that
determines the landing shape:

* **Stripe** arrives as verbatim webhook JSON. Amounts are integers in the
  smallest currency unit, timestamps are epoch seconds, currency codes are
  lowercased ISO, and a balance transaction for a charge has a *negative* amount
  with a separate fee. Those four details are what make generated Stripe data
  read as real, and all four are wrong if you invent them.
* **PostHog** arrives as an event envelope: `event`, `distinct_id`, `timestamp`,
  and a free-form `properties` map carrying `$current_url`, `$set` /
  `$set_once` person properties, and `$feature_flag_called` with its variant.
* **GA4** arrives as session rows keyed on `session_id` and `user_pseudo_id`,
  with acquisition split into `source` / `medium` / `campaign`.

Sources share the `raw.accounts` dimension, which is what lets the reconciliation
model disagree with itself convincingly: Stripe knows who is subscribed, PostHog
knows who is active, and GA4 knows who arrived. They are different facts.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

API_VERSION = "2024-06-20"

HISTORY_SPAN_DAYS = 540

CARD_BRANDS = [
    ("visa", 0.62), ("mastercard", 0.22), ("amex", 0.08), ("elo", 0.04),
    ("sepa_debit", 0.04),
]
CARD_COUNTRIES = [("US", 0.34), ("GB", 0.18), ("DE", 0.16), ("FR", 0.08),
                  ("NL", 0.07), ("ES", 0.06), ("PL", 0.05), ("SE", 0.06)]
CURRENCIES = [("eur", 0.62), ("usd", 0.22), ("gbp", 0.16)]

SUBSCRIPTION_STATUSES = [("active", 0.86), ("trialing", 0.04),
                         ("past_due", 0.05), ("canceled", 0.05)]

FAILURE_CODES = [
    ("card_declined", 0.36), ("insufficient_funds", 0.22), ("expired_card", 0.16),
    ("incorrect_cvc", 0.12), ("authentication_required", 0.09),
    ("processing_error", 0.05),
]

POSTHOG_EVENTS = [
    ("$identify", 0.02), ("dashboard_viewed", 0.16), ("report_created", 0.09),
    ("report_exported", 0.05), ("query_run", 0.14), ("source_connected", 0.04),
    ("source_synced", 0.11), ("alert_created", 0.05), ("teammate_invited", 0.03),
    ("billing_page_viewed", 0.04), ("integrated_marketplace", 0.02),
    ("$feature_flag_called", 0.10), ("session_started", 0.09),
    ("onboarding_step_completed", 0.06),
]

FEATURE_FLAGS = [
    ("new-query-builder", 0.30), ("ai-insights", 0.24),
    ("usage-based-pricing-preview", 0.18), ("workspace-templates", 0.16),
    ("sso-enforcement", 0.12),
]

BROWSERS = [("Chrome", 0.46), ("Safari", 0.24), ("Firefox", 0.11),
            ("Edge", 0.13), ("Samsung Internet", 0.06)]
OSES = [("Mac OS X", 0.31), ("Windows", 0.34), ("iOS", 0.16),
        ("Android", 0.13), ("Linux", 0.06)]

GA4_SOURCES = [
    (("google", "organic"), 0.33), (("google", "cpc"), 0.17),
    (("(direct)", "none"), 0.21), (("meta", "paid_social"), 0.13),
    (("bing", "cpc"), 0.04), (("newsletter", "email"), 0.05),
    (("duckduckgo", "organic"), 0.03), (("partner", "referral"), 0.04),
]

# No weighting to express here, so this stays a plain list and is sampled with
# `rng.choice` rather than going through `_pick`.
PAGES = [
    "/", "/pricing", "/docs/quickstart", "/product/lineage", "/product/agent",
    "/docs/adapter-sdk", "/signup", "/login", "/changelog", "/blog/state-of-data",
]


def _pick(rng: random.Random, options: list[tuple]) -> object:
    total = sum(weight for _, weight in options)
    threshold = rng.random() * total
    cumulative = 0.0
    for value, weight in options:
        cumulative += weight
        if threshold <= cumulative:
            return value
    return options[-1][0]


def _json(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _timestamp(moment: datetime) -> int:
    """Stripe measures time in whole seconds since the epoch."""
    return int(moment.timestamp())


def _messy_timestamp(moment: datetime, rng: random.Random) -> str:
    """Webhook and export timestamps arrive in several shapes."""
    roll = rng.random()
    if roll < 0.55:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if roll < 0.72:
        return str(_timestamp(moment))
    if roll < 0.86:
        return moment.isoformat()
    if roll < 0.95:
        return moment.strftime("%d/%m/%Y %H:%M")
    return moment.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


ACCOUNT_WORDS = [
    "Northwind", "Contoso", "Fabrikam", "Initech", "Globex", "Umbrella",
    "Soylent", "Stark", "Wayne", "Wonka", "Acme", "Hooli", "Pied Piper",
    "Vandelay", "Dunder", "Bluth", "Paper Street", "Aperture", "Cyberdyne",
    "Tyrell",
]


def build_accounts(rng: random.Random, count: int, now: datetime) -> list[dict]:
    """The product's own account dimension, which every other source joins to."""
    plans = [(("Starter", 29), 0.34), (("Growth", 99), 0.34),
             (("Scale", 299), 0.22), (("Enterprise", 1200), 0.10)]
    accounts = []
    for index in range(count):
        plan, price = _pick(rng, plans)
        created = now - timedelta(days=rng.random() * 540, seconds=rng.randint(0, 86399))
        trialing = rng.random() < 0.08
        churned = rng.random() < 0.09
        accounts.append({
            "account_id": f"ACC-{100000 + index}",
            "name": f"{rng.choice(ACCOUNT_WORDS)} "
                    f"{rng.choice(ACCOUNT_WORDS)} {index}",
            "plan": plan,
            "seats": max(1, int(rng.randint(1, 4) * (price / 29) * 6)),
            "country": _pick(rng, CARD_COUNTRIES),
            "created_at": created,
            "status": "churned" if churned else "active",
            "mrr": 0.0 if churned else float(price),
            "trial_ends_at": created + timedelta(days=14) if trialing else None,
            "churned_at": created + timedelta(days=rng.randint(60, 500)) if churned else None,
        })
    return accounts


def build_stripe_history(rng: random.Random, accounts: list[dict], now: datetime,
                         burst_schedule: dict | None = None):
    """Full Stripe history for the seeded accounts.

    One customer per account, one subscription per customer, a monthly invoice
    cycle, and the failures and cancellations that make a subscription business
    look like one.
    """
    customers, subscriptions, invoices, charges, refunds, balance = [], [], [], [], [], []
    burst_schedule = burst_schedule or {}

    for account in accounts:
        customer_id = f"cus_{rng.getrandbits(48):012x}"
        created = account["created_at"]
        # A signup follows a campaign push, so acquisition spend and new
        # subscriptions move together rather than independently.
        if burst_schedule:
            for candidate in (created.date() - timedelta(days=1), created.date()):
                weight = burst_schedule.get(candidate.isoformat(), 1.0)
                if weight > 1.0 and rng.random() < 0.16 * (weight - 1.0):
                    created -= timedelta(days=rng.randint(0, 2))
        customers.append({
            "stripe_id": customer_id,
            "created_at": _messy_timestamp(created, rng),
            "payload": _json({
                "id": customer_id,
                "object": "customer",
                "created": _timestamp(created),
                "currency": _pick(rng, CURRENCIES),
                "default_source": None,
                "delinquent": False,
                "description": None,
                "email": f"billing@{account['account_id'].lower()}.example.com",
                "invoice_settings": {
                    "custom_fields": None,
                    "default_payment_method": None,
                    "footer": None,
                },
                "livemode": False,
                "metadata": {"account_id": account["account_id"]},
                "name": account["name"],
                "phone": None,
            }),
        })

        plan_price = account["mrr"] or 99.0
        currency = _pick(rng, CURRENCIES)
        # Clamped to the anchor for the same reason billing_end is: an account
        # created near `now` would otherwise get a subscription dated after it.
        started = min(created + timedelta(days=rng.randint(0, 5)), now)
        subscription_id = f"sub_{rng.getrandbits(48):012x}"
        period_end = started + timedelta(days=30)
        status = "trialing" if account["trial_ends_at"] else "active"

        subscription = {
            "stripe_id": subscription_id,
            "customer_id": customer_id,
            "status": status,
            "created_at": _messy_timestamp(started, rng),
            "current_period_end": _messy_timestamp(period_end, rng),
            "payload": None,
        }

        # Monthly billing up to now, or up to churn.
        # A churn date can be later than the anchor, and billing it out to
        # that date produced charges and refunds stamped in the future.
        billing_end = min(account["churned_at"], now) if account["churned_at"] else now
        cycle = started
        while cycle < billing_end:
            cycle_end = min(cycle + timedelta(days=30), billing_end)
            failed = rng.random() < 0.035
            canceled = account["churned_at"] is not None and cycle_end >= account["churned_at"]
            amount = plan_price if not account["trial_ends_at"] or cycle > account["trial_ends_at"] else 0.0

            invoice_id = f"in_{rng.getrandbits(48):012x}"
            invoice_status = "draft" if amount == 0 else ("open" if failed else "paid")
            invoices.append({
                "stripe_id": invoice_id,
                "customer_id": customer_id,
                "subscription_id": subscription_id,
                "status": invoice_status,
                "created_at": _messy_timestamp(cycle, rng),
                "payload": _json({
                    "id": invoice_id,
                    "object": "invoice",
                    "amount_due": int(amount * 100),
                    "amount_paid": 0 if (failed or amount == 0) else int(amount * 100),
                    "amount_remaining": int(amount * 100) if failed else 0,
                    "attempt_count": 2 if failed else 1,
                    "attempted": amount > 0,
                    "auto_advance": False,
                    "billing_reason": "subscription_cycle",
                    "charge": None,
                    "collection_method": "charge_automatically",
                    "created": _timestamp(cycle),
                    "currency": currency,
                    "customer": customer_id,
                    "lines": {
                        "object": "list",
                        "data": [{
                            "id": f"il_{rng.getrandbits(32):08x}",
                            "object": "line_item",
                            "amount": int(amount * 100),
                            "currency": currency,
                            "description": f"{account['plan']} plan",
                            "period": {"start": _timestamp(cycle), "end": _timestamp(cycle_end)},
                            "price": {"id": f"price_{rng.getrandbits(32):08x}"},
                            "quantity": account["seats"],
                        }],
                        "has_more": False,
                    },
                    "livemode": False,
                    "number": f"{rng.getrandbits(32):08X}-0001",
                    "paid": not failed and amount > 0,
                    "status": invoice_status,
                    "subscription": subscription_id,
                    "total": int(amount * 100),
                }),
            })

            if amount > 0 and not failed:
                charge = _make_charge(
                    rng, customer_id, subscription_id, amount, currency,
                    cycle, account, invoice_id,
                )
                charges.append(charge)
                _append_balance(rng, balance, charge, account, cycle_end)
                if canceled or rng.random() < 0.02:
                    refund = _make_refund(rng, charge, cycle_end)
                    if refund:
                        refunds.append(refund)
                        _append_balance(rng, balance, refund, account, cycle_end)
            elif failed:
                # A past-due invoice leaves a failed payment intent behind. Real
                # revenue reporting has to exclude these, which is the point.
                charges.append({
                    "charge_id": f"ch_{rng.getrandbits(48):012x}",
                    "customer_id": customer_id,
                    "status": "failed",
                    "currency": currency,
                    "amount": str(int(amount * 100)),
                    "created_at": _messy_timestamp(cycle + timedelta(days=3), rng),
                    "payload": _json({
                        "id": f"ch_{rng.getrandbits(48):012x}",
                        "object": "charge",
                        "amount": int(amount * 100),
                        "amount_captured": 0,
                        "amount_refunded": 0,
                        "captured": False,
                        "created": _timestamp(cycle + timedelta(days=3)),
                        "currency": currency,
                        "customer": customer_id,
                        "failure_code": _pick(rng, FAILURE_CODES),
                        "failure_message": "The payment was declined.",
                        "livemode": False,
                        "paid": False,
                        "payment_method_details": {"type": "card"},
                        "status": "failed",
                    }),
                })

            if canceled:
                subscription["status"] = "canceled"
                subscription["current_period_end"] = _messy_timestamp(cycle_end, rng)
                break
            cycle = cycle_end

        subscription["payload"] = _json({
            "id": subscription_id,
            "object": "subscription",
            "cancel_at_period_end": subscription["status"] == "canceled",
            "canceled_at": _timestamp(account["churned_at"]) if account["churned_at"] else None,
            "created": _timestamp(started),
            "currency": currency,
            "current_period_end": _timestamp(period_end),
            "customer": customer_id,
            "items": {
                "object": "list",
                "data": [{
                    "id": f"si_{rng.getrandbits(32):08x}",
                    "object": "subscription_item",
                    "price": {"id": f"price_{rng.getrandbits(32):08x}",
                              "object": "price",
                              "unit_amount": int(plan_price * 100),
                              "currency": currency,
                              "recurring": {"interval": "month"}},
                    "quantity": account["seats"],
                }],
                "has_more": False,
            },
            "livemode": False,
            "metadata": {"account_id": account["account_id"]},
            "plan": {"id": f"price_{rng.getrandbits(32):08x}"},
            "start_date": _timestamp(started),
            "status": subscription["status"],
            "subscription_schedule": None,
        })
        subscriptions.append(subscription)

    return {
        "stripe_customers": customers,
        "stripe_subscriptions": subscriptions,
        "stripe_invoices": invoices,
        "stripe_charges": charges,
        "stripe_refunds": refunds,
        "stripe_balance_transactions": balance,
    }


def _make_charge(rng, customer_id, subscription_id, amount, currency, moment,
                 account, invoice_id) -> dict:
    charge_id = f"ch_{rng.getrandbits(48):012x}"
    payment_intent_id = f"pi_{rng.getrandbits(48):012x}"
    brand = _pick(rng, CARD_BRANDS)
    cents = int(round(amount * 100))
    fee = int(round(cents * rng.uniform(0.029, 0.032))) + 30
    country = _pick(rng, CARD_COUNTRIES)

    payload = {
        "id": charge_id,
        "object": "charge",
        "amount": cents,
        "amount_captured": cents,
        "amount_refunded": 0,
        "application": None,
        "application_fee": None,
        "application_fee_amount": None,
        "balance_transaction": f"txn_{rng.getrandbits(48):012x}",
        "billing_details": {
            "address": {"city": None, "country": country, "line1": None,
                        "line2": None, "postal_code": None, "state": None},
            "email": f"billing@{account['account_id'].lower()}.example.com",
            "name": account["name"],
            "phone": None,
        },
        "calculated_statement_descriptor": "NORTHGRAIN",
        "captured": True,
        "created": _timestamp(moment),
        "currency": currency,
        "customer": customer_id,
        "description": None,
        "disputed": False,
        "failure_balance_transaction": None,
        "failure_code": None,
        "failure_message": None,
        "fraud_details": {},
        "livemode": False,
        "metadata": {"account_id": account["account_id"], "invoice": invoice_id},
        "on_behalf_of": None,
        "outcome": {
            "network_status": "approved_by_network",
            "reason": None,
            "risk_level": "normal" if rng.random() > 0.05 else "elevated",
            "risk_score": rng.randint(0, 87),
            "seller_message": "Payment complete.",
            "type": "authorized",
        },
        "paid": True,
        "payment_intent": payment_intent_id,
        "payment_method": f"pm_{rng.getrandbits(32):08x}",
        "payment_method_details": {
            "card": {
                "amount_authorized": cents,
                "brand": brand,
                "checks": {
                    "address_line1_check": None,
                    "address_postal_code_check": None,
                    "cvc_check": "pass" if rng.random() > 0.1 else None,
                },
                "country": country,
                "exp_month": rng.randint(1, 12),
                "exp_year": moment.year + rng.randint(1, 6),
                "fingerprint": f"{rng.getrandbits(64):016x}",
                "funding": "credit",
                "installments": None,
                "last4": f"{rng.randint(0, 9999):04d}",
                "mandate": None,
                "network": brand,
                "three_d_secure": None,
                "wallet": None,
            },
            "type": "card",
        },
        "receipt_email": f"billing@{account['account_id'].lower()}.example.com",
        "receipt_number": None,
        "receipt_url": f"https://pay.stripe.com/receipts/payment/{rng.getrandbits(96)}",
        "refunded": False,
        "review": None,
        "shipping": None,
        "source_transfer": None,
        "statement_descriptor": None,
        "statement_descriptor_suffix": None,
        "status": "succeeded",
        "transfer_data": None,
        "transfer_group": None,
    }
    return {
        "charge_id": charge_id,
        "customer_id": customer_id,
        "status": "succeeded",
        "currency": currency,
        "amount": str(cents),
        "created_at": _messy_timestamp(moment, rng),
        "payload": _json(payload),
        "_balance_transaction": payload["balance_transaction"],
        "_fee": fee,
        "_cents": cents,
    }


def _make_refund(rng, charge: dict, moment: datetime) -> dict | None:
    """A refund against a charge, and the update it makes to that charge.

    Stripe reports `amount_refunded` and `refunded` on the parent charge, so a
    charge that has been fully refunded looks different from an untouched one.
    Generating the refund without updating the charge produces data that no
    reconciliation would believe.
    """
    if charge["status"] != "succeeded":
        return None
    cents = charge["_cents"]
    partial = rng.random() < 0.6
    refunded = int(cents * rng.uniform(0.2, 0.9)) if partial else cents
    if refunded >= cents:
        refunded = max(1, cents - rng.randint(1, 200))
    refund_id = f"re_{rng.getrandbits(32):08x}"
    payload = {
        "id": refund_id,
        "object": "refund",
        "amount": refunded,
        "balance_transaction": f"txn_{rng.getrandbits(48):012x}",
        "charge": charge["charge_id"],
        "created": _timestamp(moment),
        "currency": charge["currency"],
        "metadata": {},
        "payment_intent": None,
        "reason": _pick(rng, [("requested_by_customer", 0.7), ("fraudulent", 0.1),
                              ("duplicate", 0.2)]),
        "status": "succeeded",
    }

    charge_payload = json.loads(charge["payload"])
    already = charge_payload.get("amount_refunded", 0)
    charge_payload["amount_refunded"] = already + refunded
    charge_payload["refunded"] = (already + refunded) >= cents
    charge["payload"] = _json(charge_payload)

    return {
        "refund_id": refund_id,
        "charge_id": charge["charge_id"],
        "created_at": _messy_timestamp(moment, rng),
        "amount": str(refunded),
        "payload": _json(payload),
        # Positive: a refund puts money back on the balance. The sign flip
        # belongs to charges only.
        "_cents": refunded,
        "_balance_transaction": payload["balance_transaction"],
    }


def _append_balance(rng, balance: list, entry: dict, account: dict,
                    moment: datetime) -> None:
    """A balance transaction row.

    Stripe records the impact on the account balance, so a charge is negative and
    a refund is positive. `net` is what actually lands in the bank, after the
    processing fee. Getting this sign wrong is the classic tell of invented
    Stripe data.
    """
    is_refund = "refund_id" in entry
    gross = -entry["_cents"] if not is_refund else entry["_cents"]
    fee = 0 if is_refund else entry["_fee"]
    net = gross - fee
    balance.append({
        "txn_id": entry["_balance_transaction"],
        "charge_id": entry["charge_id"],
        "type": "refund" if is_refund else "charge",
        "created_at": entry["created_at"],
        "amount": str(gross),
        "fee": str(fee),
        "net": str(net),
        "payload": _json({
            "id": entry["_balance_transaction"],
            "object": "balance_transaction",
            "amount": gross,
            "available_on": _timestamp(moment) + rng.randint(0, 172800),
            "created": _timestamp(moment),
            "currency": entry.get("currency", "eur"),
            "description": None,
            "exchange_rate": None,
            "fee": fee,
            "fee_details": [{"amount": fee, "currency": entry.get("currency", "eur"),
                             "type": "stripe"}] if fee else [],
            "net": net,
            "reporting_category": "refund" if is_refund else "charge",
            "source": entry["charge_id"],
            "status": "available" if rng.random() > 0.15 else "pending",
            "type": "refund" if is_refund else "charge",
        }),
    })


def stripe_rows(table: str, rows: list[dict]) -> list[tuple]:
    """Projects generated Stripe rows onto the raw columns."""
    if table == "stripe_customers":
        return [(r["stripe_id"], r["created_at"], r["payload"]) for r in rows]
    if table == "stripe_subscriptions":
        return [(r["stripe_id"], r["customer_id"], r["status"], r["created_at"],
                 r["current_period_end"], r["payload"]) for r in rows]
    if table == "stripe_invoices":
        return [(r["stripe_id"], r["customer_id"], r["subscription_id"], r["status"],
                 r["created_at"], r["payload"]) for r in rows]
    if table == "stripe_charges":
        return [(r["charge_id"], r["customer_id"], r["status"], r["currency"],
                 r["amount"], r["created_at"], r["payload"]) for r in rows]
    if table == "stripe_refunds":
        return [(r["refund_id"], r["charge_id"], r["created_at"], r["amount"],
                 r["payload"]) for r in rows]
    return [(r["txn_id"], r["charge_id"], r["type"], r["created_at"], r["amount"],
             r["fee"], r["net"], r["payload"]) for r in rows]


# ---------------------------------------------------------------------------
# PostHog
# ---------------------------------------------------------------------------


def build_posthog(rng: random.Random, accounts: list[dict], now: datetime):
    """People and their event stream, in PostHog's own envelope shape."""
    people, events = [], []
    for account in accounts:
        for seat in range(min(account["seats"], 6)):
            distinct_id = f"{account['account_id'].lower()}-u{seat + 1}"
            joined = account["created_at"] + timedelta(hours=rng.randint(0, 72))
            people.append({
                "distinct_id": distinct_id,
                "created_at": _messy_timestamp(joined, rng),
                "properties": _json({
                    "$set": {
                        "account_id": account["account_id"],
                        "account_plan": account["plan"],
                        "seats": account["seats"],
                    },
                    "$set_once": {
                        "country": account["country"],
                        "created_at": _messy_timestamp(account["created_at"], rng),
                        "signup_source": _pick(rng, [
                            ("organic_search", 0.28), ("paid_search", 0.22),
                            ("paid_social", 0.18), ("referral", 0.14),
                            ("direct", 0.12), ("events", 0.06),
                        ]),
                    },
                }),
            })

            # Engagement decays after signup, which is what makes a retention
            # curve look like a retention curve rather than a flat line.
            for _ in range(rng.randint(20, 180)):
                age_days = rng.random() ** 1.7 * 540
                occurred = min(joined + timedelta(days=age_days), now)
                name = _pick(rng, POSTHOG_EVENTS)
                properties: dict = {
                    "$current_url": rng.choice(PAGES),
                    "$referrer": _pick(rng, [
                        ("https://www.google.com/", 0.34),
                        ("https://news.ycombinator.com/", 0.12),
                        ("https://dsui.northgraindata.com/", 0.22),
                        ("", 0.32),
                    ]),
                    "$browser": _pick(rng, BROWSERS),
                    "$os": _pick(rng, OSES),
                    "$lib": "web",
                    "$lib_version": "1.19.0",
                }
                if name == "$feature_flag_called":
                    flag = _pick(rng, FEATURE_FLAGS)
                    properties.update({
                        "$feature_flag": flag,
                        "$feature_flag_variant": "treatment" if rng.random() > 0.5 else "control",
                        "$groups": {"account": account["account_id"]},
                    })
                if name == "source_synced":
                    properties["rows_synced"] = rng.randint(120, 480000)
                    properties["duration_ms"] = rng.randint(400, 90000)
                if name == "query_run":
                    properties["duration_ms"] = rng.randint(45, 18000)
                    properties["rows_returned"] = rng.randint(0, 250000)
                events.append({
                    "event_id": f"ph_{rng.getrandbits(64):016x}",
                    "event": name,
                    "distinct_id": distinct_id,
                    "occurred_at": _messy_timestamp(occurred, rng),
                    "current_url": properties["$current_url"],
                    "referrer": properties["$referrer"],
                    "browser": properties["$browser"],
                    "os": properties["$os"],
                    "properties": _json(properties),
                })
    events.sort(key=lambda row: row["occurred_at"])
    return {"posthog_people": people, "posthog_events": events}


def posthog_rows(table: str, rows: list[dict]) -> list[tuple]:
    if table == "posthog_people":
        return [(r["distinct_id"], r["created_at"], r["properties"]) for r in rows]
    return [(r["event_id"], r["event"], r["distinct_id"], r["occurred_at"],
             r["current_url"], r["referrer"], r["browser"], r["os"],
             r["properties"]) for r in rows]


# ---------------------------------------------------------------------------
# GA4
# ---------------------------------------------------------------------------


def build_burst_schedule(rng: random.Random, now: datetime,
                         span_days: int) -> dict[str, float]:
    """Which days carry a campaign push.

    A demo with uniform traffic has nothing in it. B bursts lift spend and
    sessions together over a few days, the way a launch or a promo does, which
    gives the charts a shape worth looking at and gives the reconciliation
    something to explain.
    """
    schedule: dict[str, float] = {}
    day = now
    for _ in range(span_days):
        if rng.random() < 0.06:
            length = rng.randint(2, 5)
            peak = rng.uniform(2.1, 4.6)
            for step in range(length):
                target = (day - timedelta(days=step)).strftime("%Y-%m-%d")
                decay = peak * (1 - 0.18 * step)
                schedule[target] = max(schedule.get(target, 1.0), decay)
        day -= timedelta(days=1)
    return schedule


def build_ga4(rng: random.Random, accounts: list[dict], now: datetime,
              span_days: int = HISTORY_SPAN_DAYS, span_minutes: int | None = None,
              daily_index: dict | None = None) -> list[dict]:
    """GA4 session rows.

    Sessions are anonymous and stop at signup: GA4 knows someone arrived, not
    who they became. That gap against Stripe and PostHog is deliberate, and it
    is the reason the reconciliation model has something to reconcile.

    `span_minutes` narrows the window to the last few minutes, which is what the
    continuous mode uses to append live traffic.
    """
    sessions = []
    known = sorted({account["created_at"] for account in accounts})
    if span_minutes is None and daily_index:
        # One row per click the acquisition model produced, plus a direct and
        # brand baseline. Sessions are a consequence of the ad reports, not an
        # independent random walk.
        for day_key, index in sorted(daily_index.items()):
            when = datetime.strptime(day_key, "%Y-%m-%d")
            if when > now:
                continue
            for _ in range(rng.randint(1, 2)):
                # Sessions land close to the click count they came from, plus a
                # direct and brand baseline that no campaign paid for. A
                # multiplier much above one produces a site with implausible
                # traffic, which is the sort of detail a prospect notices.
                paid = index["google_search_clicks"] + index["meta_clicks"]
                baseline = rng.uniform(34, 78)
                total = int(paid * rng.uniform(0.72, 1.12) + index["organic_clicks"]
                            * rng.uniform(0.85, 1.3) + baseline)
                if index["weekday"] >= 5:
                    total = int(total * 0.78)
                for _ in range(max(1, total)):
                    occurred = when + timedelta(seconds=rng.randint(0, 86399))
                    if occurred > now:
                        break
                    sessions.append(_ga4_session(rng, occurred, known, now))
        sessions.sort(key=lambda row: row["occurred_at"])
        return sessions

    if span_minutes is None:
        count = span_days * rng.randint(40, 90)
    else:
        count = span_minutes * rng.randint(3, 7)
    for _ in range(count):
        occurred = (
            now - timedelta(days=rng.random() * span_days, seconds=rng.randint(0, 86399))
            if span_minutes is None
            else now - timedelta(seconds=rng.random() * span_minutes * 60)
        )
        sessions.append(_ga4_session(rng, occurred, known, now))
    sessions.sort(key=lambda row: row["occurred_at"])
    return sessions


def _ga4_session(rng: random.Random, occurred: datetime, known: list, now: datetime) -> dict:
    source, medium = _pick(rng, GA4_SOURCES)
    session_number = rng.choices([1, 2, 3], weights=[62, 24, 14])[0]
    engagement = rng.choices(
        [rng.randint(0, 800), rng.randint(800, 20000), rng.randint(20000, 900000)],
        weights=[46, 38, 16],
    )[0]
    converted = rng.random() < (0.021 if session_number == 1 else 0.004)
    return {
        "session_id": f"{rng.getrandbits(64):016x}",
        "occurred_at": _messy_timestamp(occurred, rng),
        "country": _pick(rng, CARD_COUNTRIES),
        "device_category": _pick(rng, [("desktop", 0.58), ("mobile", 0.38),
                                       ("tablet", 0.04)]),
        "traffic_source": source,
        "source_medium": f"{source} / {medium}",
        "campaign": (
            f"pmax-{rng.choice(['brand', 'retargeting', 'lookalike', 'spring'])}"
            if medium == "paid_social" or (source == "google" and medium == "cpc")
            else "(not set)"
        ),
        "session_number": str(session_number),
        "engagement_time_msec": str(engagement),
        "is_bounce": "1" if engagement < 800 else "0",
        "_converted": "1" if converted else "0",
        "_signup_after": (
            sorted(known)[rng.randrange(len(sorted(known)))]
            if converted and known else None
        ),
    }


def ga4_rows(rows: list[dict]) -> list[tuple]:
    return [(r["session_id"], r["occurred_at"], r["country"], r["device_category"],
             r["traffic_source"], r["source_medium"], r["campaign"],
             r["session_number"], r["engagement_time_msec"], r["is_bounce"])
            for r in rows]


# ---------------------------------------------------------------------------
# Acquisition: Meta Ads, Google Ads, Search Console
# ---------------------------------------------------------------------------

META_CAMPAIGNS = [
    ("pmax-brand", "Prospecting | Broad | LAL 1%", 0.26),
    ("pmax-retargeting", "Retargeting | 7d cart", 0.19),
    ("catalog-sales", "Advantage+ Catalogue", 0.21),
    ("pmax-spring", "Spring Launch | Video", 0.15),
    ("retargeting-dynamic", "Dynamic Retargeting", 0.12),
    ("brand-awareness", "Brand Awareness | Reach", 0.07),
]

META_ADSETS = [
    ("Broad 25-54", 0.34), ("Lookalike 1%", 0.22), ("Retarget 14d", 0.18),
    ("Cart abandoners", 0.14), ("Engaged 30d", 0.12),
]

GOOGLE_CAMPAIGNS = [
    ("brand", "Brand | Exact", 0.18),
    ("nonbrand-search", "Nonbrand | Generic", 0.26),
    ("competitor", "Competitor | conquest", 0.07),
    ("pmax", "Performance Max", 0.21),
    ("youtube", "YouTube | In-stream", 0.12),
    ("pmax-spring", "Performance Max | Spring", 0.10),
    ("display", "Display | Remarketing", 0.06),
]

SEARCH_QUERIES = [
    "data observability", "data stack tool", "open source data ui",
    "connect airflow dbt", "data lineage tool", "duckdb dashboard",
    "internal analytics platform", "data catalog open source",
    "monitor data pipelines", "sql workspace", "data plugin sdk",
    "developer data portal", "single pane of glass data",
    "data stack cost", "self hosted analytics", "synthetic data platform",
]

SEARCH_PAGES = [
    ("/", 0.24), ("/pricing", 0.19), ("/product/lineage", 0.14),
    ("/product/agent", 0.11), ("/docs/quickstart", 0.10),
    ("/docs/adapter-sdk", 0.08), ("/signup", 0.08), ("/blog/state-of-data", 0.06),
]

SEARCH_APPEARANCE = [("BLUE_LINK", 0.52), ("SITELINK", 0.18), ("FAQ", 0.09),
                     ("PROMOTION", 0.05), ("VIDEO", 0.16)]

GSC_DEVICES = [("DESKTOP", 0.54), ("MOBILE", 0.42), ("TABLET", 0.04)]


def build_acquisition(rng: random.Random, now: datetime, span_days: int,
                      burst_schedule: dict):
    """Meta Ads, Google Ads and Search Console from one acquisition model.

    Spend is the input; impressions, clicks, sessions and signups follow from it
    through CPC and CTR. Generating the three reports independently would look
    plausible and reconcile perfectly, which is the opposite of the point.

    Returns the reports plus the per-day traffic index, so GA4 sessions and the
    subscription timeline inherit the same shape.
    """
    meta_rows, google_rows, gsc_rows = [], [], []
    daily_index: dict[str, dict] = {}
    meta_currency, google_currency = "EUR", "EUR"

    # Baseline unit economics, so the reports are internally consistent.
    meta_cpc = rng.uniform(0.42, 0.72)
    meta_ctr = rng.uniform(0.011, 0.021)
    google_cpc_search = rng.uniform(1.35, 2.60)
    google_cpc_pmax = rng.uniform(0.55, 1.05)
    google_ctr_search = rng.uniform(0.028, 0.055)
    google_ctr_display = rng.uniform(0.004, 0.011)

    for offset in range(span_days):
        day = now - timedelta(days=offset)
        key = day.strftime("%Y-%m-%d")
        burst = burst_schedule.get(key, 1.0)
        weekday = 0.86 if day.weekday() >= 5 else 1.0
        trend = 0.65 + 0.7 * (1 - offset / max(1, span_days))
        noise = rng.uniform(0.78, 1.28)
        seasonal = [0.94, 0.88, 1.02, 1.26][(day.month - 1) // 3]
        scale = trend * weekday * noise * seasonal * burst

        meta_spend = 180.0 * scale
        meta_clicks = int(meta_spend / meta_cpc)

        google_spend = 240.0 * scale
        google_search_share = rng.uniform(0.55, 0.7)
        google_search_clicks = int(
            (google_spend * google_search_share) / google_cpc_search
        )
        google_rest_spend = google_spend * (1 - google_search_share)
        google_rest_clicks = int(google_rest_spend / google_cpc_pmax)

        organic_clicks = int(38.0 * scale)

        daily_index[key] = {
            "meta_clicks": meta_clicks,
            "google_search_clicks": google_search_clicks,
            "google_rest_clicks": google_rest_clicks,
            "organic_clicks": organic_clicks,
            "meta_spend": meta_spend,
            "google_spend": google_spend,
            "burst": burst,
            "weekday": day.weekday(),
        }

        for name, adset_label, share in META_CAMPAIGNS:
            # A campaign that is not running spends nothing, the way a paused one
            # reports a row of zeros rather than no row at all.
            if rng.random() < 0.08:
                continue
            spend = meta_spend * share * rng.uniform(0.85, 1.15)
            clicks = int(spend / meta_cpc)
            impressions = int(clicks / meta_ctr)
            reach = int(impressions * rng.uniform(0.55, 0.78))
            adset_name = rng.choice(META_ADSETS)[0]
            conversions = {
                "purchase": round(clicks * rng.uniform(0.012, 0.031), 2),
                "lead": round(clicks * rng.uniform(0.004, 0.014), 2),
                "add_to_cart": round(clicks * rng.uniform(0.02, 0.06), 2),
            }
            meta_rows.append({
                "date": key,
                "campaign_id": str(rng.getrandbits(40)),
                "campaign_name": name,
                "adset_id": str(rng.getrandbits(40)),
                "adset_name": adset_name,
                "impressions": str(impressions),
                "reach": str(reach),
                "clicks": str(clicks),
                # Meta reports spend as a decimal string, not a number.
                "spend": f"{spend:.2f}",
                "cpc": f"{spend / clicks:.2f}" if clicks else "0.00",
                "cpm": f"{spend / impressions * 1000:.2f}" if impressions else "0.00",
                "ctr": f"{clicks / impressions:.4f}" if impressions else "0.0000",
                "currency": meta_currency,
                # The nested action array is what a Meta report actually is.
                "actions": _json([
                    {"action_type": "purchase", "value": str(conversions["purchase"])},
                    {"action_type": "lead", "value": str(conversions["lead"])},
                    {"action_type": "add_to_cart",
                     "value": str(conversions["add_to_cart"])},
                ]),
                "_adset_label": adset_label,
            })

        for name, _label, share in GOOGLE_CAMPAIGNS:
            if rng.random() < 0.06:
                continue
            if name in ("pmax", "pmax-spring"):
                spend = google_rest_spend * share * rng.uniform(0.8, 1.2)
                clicks = int(spend / google_cpc_pmax)
                impressions = int(clicks / google_ctr_display * 1.4)
            elif name == "display":
                spend = google_rest_spend * share * rng.uniform(0.8, 1.2)
                clicks = int(spend / google_cpc_pmax)
                impressions = int(clicks / google_ctr_display)
            else:
                spend = google_spend * share * rng.uniform(0.85, 1.15)
                clicks = int(spend / google_cpc_search)
                impressions = int(clicks / google_ctr_search)
            conversions = round(clicks * rng.uniform(0.021, 0.048), 2)
            value = round(conversions * rng.uniform(80, 260), 2)
            all_conversions = round(conversions * rng.uniform(1.05, 1.4), 2)
            # Cost is in micros: millionths of the account currency unit.
            micros = int(round(spend * 1_000_000))
            google_rows.append({
                "date": key,
                "campaign_id": str(rng.getrandbits(40)),
                "campaign_name": name,
                "impressions": str(impressions),
                "clicks": str(clicks),
                "cost_micros": str(micros),
                "conversions": str(conversions),
                "conversions_value": f"{value:.2f}",
                "ctr": f"{clicks / impressions:.4f}" if impressions else "0.0000",
                "average_cpc": f"{spend / clicks:.2f}" if clicks else "0.00",
                "average_cpm": f"{spend / impressions * 1000:.2f}" if impressions else "0.00",
                "all_conversions": str(all_conversions),
                "cost_per_conversion": f"{spend / conversions:.2f}" if conversions else "0.00",
                "currency": google_currency,
                "_micros": micros,
            })

        # Search Console returns one row per dimension combination, keyed by an
        # array, and position is a fractional average over the whole range.
        remaining = organic_clicks
        queries = rng.sample(SEARCH_QUERIES, k=min(len(SEARCH_QUERIES),
                                                    rng.randint(9, 16)))
        weights = [rng.uniform(0.4, 2.6) for _ in queries]
        total_weight = sum(weights)
        for index, query in enumerate(queries):
            is_last = index == len(queries) - 1
            clicks = remaining if is_last else int(organic_clicks * weights[index] / total_weight)
            remaining -= clicks
            if clicks <= 0:
                continue
            # Click position decides impressions: rank one gets far more of them.
            position = min(60.0, max(1.05, rng.lognormvariate(1.7, 0.52)))
            impressions = int(clicks / rng.uniform(0.04, 0.26))
            page = _pick(rng, SEARCH_PAGES)
            gsc_rows.append({
                "date": key,
                "query": query,
                "page": page,
                "country": _pick(rng, CARD_COUNTRIES),
                "device": _pick(rng, GSC_DEVICES),
                "search_appearance": _pick(rng, SEARCH_APPEARANCE),
                "clicks": str(clicks),
                "impressions": str(impressions),
                "ctr": f"{clicks / impressions:.3f}" if impressions else "0.000",
                "position": f"{position:.2f}",
                "_keys": [query, page],
            })

    return {
        "meta_ads_daily": meta_rows,
        "google_ads_daily": google_rows,
        "gsc_daily": gsc_rows,
        "_daily_index": daily_index,
    }


def meta_rows_to_tuples(rows: list[dict]) -> list[tuple]:
    return [(r["date"], r["campaign_id"], r["campaign_name"], r["adset_id"],
             r["adset_name"], r["impressions"], r["reach"], r["clicks"], r["spend"],
             r["cpc"], r["cpm"], r["ctr"], r["currency"], r["actions"])
            for r in rows]


def google_rows_to_tuples(rows: list[dict]) -> list[tuple]:
    return [(r["date"], r["campaign_id"], r["campaign_name"], r["impressions"],
             r["clicks"], r["cost_micros"], r["conversions"], r["conversions_value"],
             r["ctr"], r["average_cpc"], r["average_cpm"], r["all_conversions"],
             r["cost_per_conversion"], r["currency"])
            for r in rows]


def gsc_rows_to_tuples(rows: list[dict]) -> list[tuple]:
    return [(r["date"], r["query"], r["page"], r["country"], r["device"],
             r["search_appearance"], r["clicks"], r["impressions"], r["ctr"],
             r["position"])
            for r in rows]
