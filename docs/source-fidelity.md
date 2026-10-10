# Source fidelity

All data is synthetic and public.
The project models useful vendor concepts and object relationships rather than reproducing every endpoint or every field.
Each landing file has a source YAML and a staging SQL/YAML pair, with documented grain, column types, model contract and data tests.

| Source | Modeled scope | Deliberate limits |
| --- | --- | --- |
| Stripe | Customers, current subscription snapshots, monthly invoices, succeeded/failed charges, partial/full refunds, balance transactions | API object schema subset pinned to `2024-06-20`; 30-day synthetic billing periods; flat account pricing with quantity 1; no tax, coupons, disputes, payouts, Connect, PaymentIntent or payment-method object tables |
| Product | Current accounts, plans, seats, MRR, trial and churn dates | Current state, without a history of plan or seat changes; MRR is EUR |
| E-commerce | Customers, products, subscriptions, orders, lines, payments, refunds and events | Separate commerce example, not a purchase-level attribution link to the SaaS accounts; duplicate markers, missing emails and orphan lines are intentional |
| PostHog | Person-property exports and event envelopes, group account IDs on flag exposures, optional operation metrics | `$set` and `$set_once` preserve synthetic provenance; person exports are not verbatim responses from every PostHog endpoint; flag variants do not model experiments |
| GA4 | Anonymous sessions, source/medium/campaign and engagement duration | Synthetic session export, not the Data API or native BigQuery export; session IDs are globally unique here; bounce threshold is synthetic |
| Meta Ads | Daily campaign/adset report, decimal spend, nested action values | EUR only; exported CTR is normalized to a fraction, whereas native Meta CTR is a percentage; dimensions are illustrative |
| Google Ads | Daily campaign report, cost in micros, fractional attributed conversions | EUR only; no attribution windows or offline conversion adjustments |
| Search Console | Daily query/page/country/device/appearance combinations, clicks, impressions and fractional position | Simplified country and dimension representation; position is weighted by impressions in the daily mart |

## Stripe accounting and links

`payload` contains an API object snapshot, not a webhook event envelope.
Object creation timestamps are epoch seconds; promoted export timestamps preserve those values.
The SQL staging layer uses the object payload as its source of truth.
Charges have positive object amounts and positive balance impacts.
Refund objects have positive amounts, while their balance impacts are negative.
Ledger fees are positive costs and `net = amount - fee`.
Balance `source` points to the actual charge or refund object, and both objects point back to the same balance transaction.
The parent charge tracks cumulative `amount_refunded` and becomes `refunded = true` only after a full refund.
Paid invoices link to their charge and share the subscription's price identifier.
Failed charge export identifiers equal the identifiers in their payloads.
Live charges refer to existing customers and represent standalone account charges; they do not invent missing invoice records.

The settled-cash mart includes only `available` ledger entries.
Pending transactions remain visible in staging.
Availability is a synthetic snapshot state; it is not a settlement simulator or a bank payout ledger.
Gross, refunds, fees and net stay in integer minor units and retain currency grain.
Seeded billing and current live charges are EUR, matching product MRR and advertising spend.
The models do not invent exchange rates.

The modeled Stripe subset follows the [balance transaction object](https://docs.stripe.com/api/balance_transactions/object) and the [2024-06-20 subscription schema](https://docs.stripe.com/api/subscriptions/object?api-version=2024-06-20).
Updating the API version requires updating generator objects, staging contracts and regression tests together.

## Reading reconciliation

`fct_revenue_daily` represents settled cash movement, not accrual revenue.
`fct_acquisition_daily` has one row per day and does not multiply spend when reading Meta actions.
`fct_revenue_reconciliation` combines monthly cash/activity flows with current account and subscription status grouped by creation month.
Its product MRR is the current MRR of a creation cohort, not reconstructed historical month-end MRR.
An account gap can reflect signup/subscription timing and modeled lifecycle differences.
`largest_discrepancy` is an ordered diagnostic, not a ranking of percentages or monetary differences.
A real historical MRR reconciliation would need account/subscription snapshots or event history, including plan changes, cancellations and trials.

## Test policy

Model contracts fail on column or type drift.
Missing keys, duplicate grains, invalid accounting identities, broken Stripe links and mart/source mismatches fail the build.
`dbt_utils` provides composite uniqueness and expression tests.
The maintained `metaplane/dbt_expectations` package checks nonempty tables and metric ranges.
The intentional e-commerce orphan lines trigger a warning relationship test and remain available for inspection.
Missing customer emails are documented source defects and are not assigned misleading `not_null` constraints.
Historical business timestamps are not ingestion timestamps, so source freshness thresholds are not fabricated from them.
Freshness needs an explicit ingestion timestamp or extraction marker before it can become a meaningful gate.
