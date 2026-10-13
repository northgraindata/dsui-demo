# dsui-demo

A public, always-on DSUI instance. Anyone can open it and click through a real
stack — no signup, no login, no setup. This is the "see it work" surface behind
the marketing site.

The demo tells one story about one dataset: a synthetic e-commerce SaaS, from raw
files in object storage through an orchestrated load, a dbt transformation, into a
warehouse you can query, with a local DuckDB file alongside it for comparison.

## Everything here is fake and public

This instance is open to the internet. Every credential in it is synthetic and
disclosed on purpose:

| Where | What |
| --- | --- |
| `.env` | Not committed. Holds `DSUI_MASTER_KEY` and `DEMO_ADMIN_SECRET`. |
| `compose.yaml` | Reads everything from the environment. No literal secrets. |
| `dsui.yaml` | Interpolates the dedicated reader credentials from the environment. |
| PostgreSQL, MinIO, Airflow | Published defaults in `.env.example`. They protect nothing real. |

Do not copy this credential handling into anything that matters. The point of the
demo is that its data is worthless, so disclosure costs nothing.

## Running it

On Linux:

```sh
python3 scripts/setup-env.py
docker compose up -d --build
docker compose logs -f airflow dsui
```

The setup script fills missing runtime secrets and preserves existing ones.
On macOS use Apple Containers with `container-compose`.
The helper requires PyYAML (included in `requirements-dev.txt`).
It renders configuration, resolves container addresses, isolates the process environment and uses shared host directories for exports.

```sh
python3 scripts/setup-env.py
python3 scripts/start-apple.py --build
```

For subsequent starts omit `--build`.
Local Apple state lives in the ignored `.state/` directory.
Run `container logs dsui-demo-airflow` or `container logs dsui-demo-dsui` to inspect startup.
The first build downloads pinned DSUI and MinIO source archives and compiles the runtime.
Allow several minutes for image builds, the initial seed and the first dbt build.

```sh
docker compose exec dsui dsui doctor --check-adapters
```

## How it is wired

Only DSUI publishes a host port.
PostgreSQL, Airflow and MinIO stay on the internal network.
Airflow 2.10.5 uses its supported Basic API authentication and a provisioned user.
Its healthcheck verifies the running webserver, metadata database and scheduler.
DSUI connects to PostgreSQL as a dedicated reader with no write grants and a 30-second statement timeout.
Provisioning, ingestion and Airflow metadata use separate roles.

DSUI, SDKs and adapters are built together from the immutable source commit and lockfile in `Dockerfile`.
The old published DSUI release predates the plugin APIs this demo needs.
The public instance is served below `/demo/`; the DSUI web bundle and runtime plugin URLs use that same prefix.
MinIO is built from a pinned, checksum-verified source archive because the old official image is unavailable.

The generator marks the initial seed ready only after database writes and file exports finish.
Airflow extracts a consistent PostgreSQL transaction, builds a fresh DuckDB snapshot, uploads CSV and Parquet to MinIO, then atomically publishes the snapshot.
A failed build preserves the previous published database.
Landing data is materialized inside DuckDB so that published snapshots remain readable after the Parquet files change.

## Layout

```
.
├── compose.yaml          # DSUI + backing services
├── dsui.yaml             # adapters, services, plugins
├── .env.example
├── data-generator/       # Python: seeds and serves the synthetic dataset
├── dbt/                  # transformation project
├── airflow/dags/         # orchestration
├── airflow/               # orchestration: extract, dbt, publish
├── plugins/
│   ├── demo-auth/        # anonymous operator, secret-holder owner
│   └── demo-guide/       # developer investigation with contextual overlays
└── scripts/
    └── reset.sh          # reseed the dataset
```

## Access

OSS DSUI has no identity provider. With no authentication plugin installed the
server assigns `localPrincipalMiddleware()`, which is `owner` to every request —
correct for the single-operator install OSS targets, and completely wrong for an
instance on the public internet.

`plugins/demo-auth` supplies the missing half, because identity is a plugin
concern and here nobody signs in:

| Visitor | Role | Can |
| --- | --- | --- |
| browser with a `dsui_demo_visitor` cookie | `operator` | browse everything; run source queries and trigger DAGs (10 per visitor, 30 total per minute) |
| caller without a valid visitor cookie | `operator` | a fresh conversation identity for each request; same allowlist and global limit |
| any visitor, `allowExecution: false` | `viewer` | read only |
| maintainer with the admin secret | `owner` | all capabilities |

The demo agent is configured with `OPENROUTER_API_KEY` in the DSUI container.
Without the key, the agent shows setup instructions and cannot send prompts. It
uses OpenRouter's free-model router by default, keeps each
visitor's conversation under that browser's isolated principal, and cannot
execute actions. Agent requests are limited to five per visitor and 30 total per
minute, with at most eight concurrent turns per server process. Public deployments should also apply an IP-based
Cloudflare rate limits to `POST /demo/api/v1/plugins/ai-agent/procedures/send`
and `POST /demo/api/v1/services/*/actions/*` (or the same paths without `/demo`
when the proxy strips the prefix);
browser cookies can be cleared, so application identity limits are not a
replacement for an edge limit.

`operator` withholds `manage`, so a stranger cannot create or delete a service
or change configuration. Those grants are a hard ceiling in the host's
`auth.ts`, so no plugin can widen them back. The secret is compared in constant
time after hashing, and an unset secret matches nothing.

The web bundle initializes a random, first-party `dsui_demo_visitor` cookie
before the DSUI app starts. The auth plugin hashes it into the visitor's
principal ID, which namespaces agent conversations per browser. The cookie
contains no account or personal information; clearing it starts a fresh chat
history. Requests without a valid cookie receive a one-request identity rather
than sharing a fallback conversation namespace.

The plugin declares `security: true` and is configured `critical: true`, so the
host refuses to install it rather than starting the server without it. Failing
closed is the point: the alternative is silently serving the demo as `owner` to
everyone.

```sh
cd plugins/demo-auth && bun test && bun run typecheck
```

## The dataset

One synthetic subscription business feeds the whole demo, so a visitor never sees
two unrelated worlds. The product is a scale-up SaaS: accounts on plans from
Starter to Enterprise, billed monthly, with some churn.

`data-generator` writes it to PostgreSQL and exports a landing zone of CSV and
Parquet. It deliberately does **not** produce a `.duckdb` file. DuckDB allows a
single writing process, so a generator holding that file would lock out the very
dbt run the landing zone exists to feed. DuckDB is dbt's engine and its output,
not the generator's.

The raw tables are malformed on purpose, because cleaning them is the story:

- Timestamps arrive in five formats: ISO, `DD/MM/YYYY`, ISO with `Z`, bare date,
  and epoch seconds.
- Money arrives as a number, as `$1,234.56`, as `12.00 EUR`, and with a decimal
  comma.
- Status casing is inconsistent.
- Around one percent of customers are duplicated, two percent have no email, and
  a few order items reference orders that do not exist.

Everything the generator writes, it also has to read back, so `parse_money` and
`parse_timestamp` sit next to the functions that produce the mess. dbt gets
equivalent macros later.

### Sources

| Source | Tables | Fidelity notes |
| --- | --- | --- |
| Stripe | customers, subscriptions, invoices, charges, refunds, balance transactions | Integer minor units, epoch timestamps, lowercased ISO currency, positive balance amounts on charges and negative on refunds, `net = amount - fee`, and refunds update `amount_refunded` on the parent charge |
| PostHog | people, events | `event` / `distinct_id` / `timestamp` envelope, `$set` and `$set_once` person properties, `$current_url`, `$referrer`, `$browser`, `$os`, and `$feature_flag_called` with a variant |
| GA4 | sessions | Anonymous `session_id`, `source` / `medium` / `campaign`, `engagement_time_msec`, bounce flag |
| Meta Ads | meta_ads_daily | Spend as a decimal string, and `actions` as the nested action-type/value array a Meta report actually is |
| Google Ads | google_ads_daily | Cost in `cost_micros`, millionths of the account currency unit |
| Search Console | gsc_daily | One row per dimension combination with a fractional average `position` between 1 and 100 |
| Accounts | accounts | The product's own dimension, and the join key the other sources resolve to |

Landed the way the vendors actually hand data over: Stripe as synthetic API object snapshots in `payload`, with export index columns alongside them.
The modeled Stripe API schema is `2024-06-20`; these are object snapshots, not `event.data.object` webhook envelopes.
PostHog retains its event envelope and person-property exports.
GA4, ad platforms and Search Console are modeled report exports, not verbatim vendor API responses.
See [source fidelity](docs/source-fidelity.md) for scope and limitations.

### One acquisition model, not six random walks

Paid and organic reports drive everything downstream. Spend sets impressions and
clicks through a per-platform CPC and CTR, clicks set GA4 sessions, and a campaign
burst lifts spend, sessions and new subscriptions together over a few days. The
generated correlation between daily ad spend and daily sessions is around 0.8.

That is the point of the whole dataset. Six sources that agreed with each other
would teach nothing; these agree in shape and disagree in number, the way real
ones do, and the reconciliation model has something real to explain. A site
advertising its own demo does not need the sources to reconcile perfectly.

A/B experiments are out. Feature flags stay: one extra property on an event, and
enough to show which variant an account saw. A real experiment needs assignment
consistency and a significance model, which is a separate piece of work.

### Running continuously

The container seeds once, then serves: each tick emits a shaped amount of
activity and sleeps for a jittered interval. Volume follows a diurnal and weekly
shape rather than a uniform one, and roughly one burst a week lifts spend,
sessions and charges together, so the data contains an event instead of only
noise.

It reseeds itself when the event table passes `DEMO_ROW_CAP` or the seed reaches
`DEMO_MAX_AGE_DAYS`. The cap is enforced in-process on purpose: a cron that
misses a window leaves the demo quietly oversized. `scripts/reset.sh` is for a
manual or scheduled reset, and is a convenience rather than the mechanism that
keeps the database bounded. A cap below the seeded size can never be satisfied,
so it is reported and the process exits instead of looping.

```sh
docker compose exec data-generator python generate.py verify
scripts/reset.sh                       # reseed now
scripts/reset.sh 2026-01-31T00:00:00   # reseed at a fixed anchor
```

Reproducible builds need an anchor, because the wall clock moves the window:

```sh
scripts/reset.sh 2026-01-31T00:00:00
```

### Checks

CI generates all 21 landing files with a fixed `2026-01-31` anchor and runs a real DuckDB `dbt build`.
Model contracts enforce documented column names and types.
`dbt_utils` checks composite grains and accounting expressions; `dbt_expectations` checks nonempty tables and value ranges.
Singular SQL tests reconcile marts to raw acquisition reports and the Stripe ledger, validate refund totals and exercise the cleaning macros.
Python tests cover Stripe identities, object links, billing periods, full refunds, live customer identity, and CSV/Parquet round trips.
The intentional orphan order items emit a warning; other failures stop the build before publication.
A static CI job uses [northgraindata/dbt-doctor](https://github.com/northgraindata/dbt-doctor), pinned to a commit, with native static rules and an error gate.
A runtime CI job builds and starts the complete stack from fresh volumes.
`scripts/smoke.py` verifies anonymous/owner roles, management and SQL write denial, all five adapters, execution of both DAGs, object-storage refresh and preservation of a published snapshot after a failed dbt build.
CI uploads the dbt manifest, results, catalog and runtime logs for review.

```sh
python scripts/smoke.py
# macOS, after starting with the Apple helper:
python scripts/smoke.py --url http://localhost:4192/demo
```

Run the same data checks locally without backing services:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m pyflakes data-generator/*.py airflow/dags/*.py tests/*.py
python data-generator/test_tables.py
python -m unittest discover -s tests -p 'test_*.py'
export DEMO_LANDING_DIR="$PWD/.ci/landing"
export DEMO_DUCKDB_NEXT="$PWD/.ci/next/demo.duckdb"
python tests/create_landing.py --output "$DEMO_LANDING_DIR"
dbt deps --project-dir dbt --profiles-dir dbt
dbt/entrypoint.sh dbt build --project-dir dbt --profiles-dir dbt
dbt docs generate --project-dir dbt --profiles-dir dbt
npx dbt-doctor@0.3.4 dbt --offline --fail-on error
```

Use `--customers 5000 --orders 60000 --accounts 1200` with `tests/create_landing.py` to exercise the deployment defaults.
The generator's default `DEMO_ROW_CAP=1000000` caps PostHog events, not the total warehouse row count.
The 1200-account seed alone produces roughly 720,000 PostHog events, so the earlier 400,000 cap could never be satisfied.

## The transformation layer

`dbt/` reads the landing zone and produces marts. Staging is a view layer, marts
are tables, and the published database shows all three schemas side by side:

```
landing   21 tables   raw exports, all text
staging   21 views   typed, documented, one row per declared grain
marts      3 tables  the numbers a person actually reads
```

`macros/clean.sql` holds `parse_timestamp`, `parse_money`, `parse_integer` and
`normalize_status`: the SQL counterparts of the generator's own parsing helpers.
The generator writes the mess and then has to read its own writing back, and so
does dbt.

`fct_revenue_reconciliation` is the model the whole dataset exists to support.
A subscription business has several defensible answers to "how much revenue last
month", and a workspace that shows only one is hiding something, so the mart
keeps every answer side by side and names the gap:

| What | Where |
| --- | --- |
| Revenue gross, refunded, fees, net | `fct_revenue_daily`, built from the Stripe balance ledger |
| Active accounts, MRR, churn | the product database |
| Active, canceled and past-due subscriptions, invoice counts | Stripe billing records |
| Spend, clicks, sessions, average position | the acquisition reports |
| Active users, feature flag exposure | PostHog |
| `active_account_gap`, `effective_fee_pct`, `largest_discrepancy` | the differences |

`largest_discrepancy` reports the first applicable diagnostic, prioritizing account differences before open invoices.
It does not numerically rank metrics with different units.
Account and subscription counts are current statuses grouped by creation month.
Their MRR is current cohort MRR, while revenue and activity are monthly flows; this is an illustrative comparison, not historical month-end MRR.
Cash marts include settled ledger entries, preserve currency grain and subtract refunds and fees.

The build writes to `next/demo.duckdb` and never to the published file, because
DuckDB allows a single writing process. Airflow renames it into place only after
a successful build, so a visitor reading the previous snapshot never sees a
half-built one. The build target is deleted first each run, because dbt does not
drop schemas it no longer manages and a reused file accumulates stale duplicates.

## What a visitor sees

Five services, all fed by the same synthetic business:

| Service | What it is |
| --- | --- |
| `landing` | MinIO, seeded from the same CSVs the pipeline reads, so object storage and the warehouse describe one company |
| `analytics` | PostgreSQL raw layer, accessed by a read-only role with a statement timeout |
| `snapshot` | One DuckDB file holding landing, staging and marts, replaced atomically after each build |
| `orchestration` | Airflow, reached over the compose network with Basic auth and never published |
| `transformations` | dbt project, including source SQL, compiled models and build artifacts |

`demo-guide` is a 6–8 minute developer investigation launched from the sidebar.
It first introduces the workspace UI, then follows a missing-orders report from
DuckDB to PostgreSQL, the dbt filter, Airflow and the MinIO input artifact. The
panel stays in one viewport corner and highlights the actual editor, results and
model source. Query steps advance after the visitor runs the prepared SQL.

The regression uses nine deterministic orders in `raw.demo_tour_orders`, separate
from generated commerce data. The source changes from `paid` to `completed` while
`marts.fct_tour_orders` intentionally retains the old filter. Airflow extracts and
publishes `demo_tour_orders.parquet` with the normal landing artifacts. The guide's
repair action builds only its own corrected dbt project, tests nine orders and
900 revenue, then removes its disposable database. It preserves the original
regression so each visitor can reproduce the investigation.

The tour ends with the code-repository plugin and a Plugin SDK contribution
example. Product code provides generic slots, positioning, named targets and
interaction notifications; the story and repair code live in `plugins/demo-guide`.

The demo image pins DSUI commit `5dd9161d5592e0c9ab3fd28d5af99370a0202062`,
which includes the SDK overlay contracts, host changes and the dbt browser
component fix in [DSUI PR #74](https://github.com/northgraindata/dsui/pull/74).
Deploy this revision after that product PR has been reviewed. Configuration and
PostgreSQL bootstrap scripts are baked into their images, so remote deployments
do not depend on runtime bind mounts from the source checkout.

## Status

- [x] Compose with DSUI and PostgreSQL, one adapter, resource limits, healthcheck
- [x] `demo-auth` two-tier plugin
- [x] Data generator: e-commerce, Stripe, PostHog, GA4, accounts
- [x] Meta Ads, Google Ads, Search Console daily reports, sharing one acquisition model
- [x] dbt project: staging, marts, reconciliation
- [x] Airflow: Postgres to Parquet to dbt to DuckDB, published by atomic rename
- [x] MinIO, seeded from the same landing zone the pipeline reads
- [x] DuckDB snapshot service, read-only
- [x] `demo-guide` tour plugin
- [x] Airflow exposed as a service, so DAG runs are visible in the demo
- [x] `code-repository`, pointed at this repository's DAG folder
- [ ] `monitoring`, landing page CTA

## Known issues

See [project review](docs/project-review.md) for remaining deployment checks and modeling limits.


The AI agent is absent because the pinned runtime has no AI agent plugin implementation.
Historical MRR and month-end subscriber counts require state history; current cohort metrics are labeled in the model documentation.
