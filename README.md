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
| `dsui.yaml` | Interpolates `${POSTGRES_USER}` / `${POSTGRES_PASSWORD}` from the environment. |
| PostgreSQL, MinIO, Airflow | Published defaults in `.env.example`. They protect nothing real. |

Do not copy this credential handling into anything that matters. The point of the
demo is that its data is worthless, so disclosure costs nothing.

## Running it

```sh
cp .env.example .env
# Generate the two secrets:
#   DSUI_MASTER_KEY   ->  openssl rand -base64 32   (must decode to exactly 32 bytes)
#   DEMO_ADMIN_SECRET ->  openssl rand -hex 24
docker compose up -d
docker compose logs -f dsui
```

First boot is slow on purpose. Adapters are compiled from source, which takes
minutes; the healthcheck allows a ten-minute grace period so the container does
not restart-loop during that build. `/data` is a volume, so the package-manager
cache survives restarts and later boots are quick.

Then:

```sh
docker compose run --rm dsui doctor --check-adapters
```

## How it is wired

Only DSUI is ever published. PostgreSQL, Airflow and MinIO carry no `ports` and
are reachable only on the compose network. Airflow's stable REST API sits behind
the simple auth manager, so even a visitor who found the container would still
need a password, and the only way in is through DSUI. Memory and CPU limits are set on every
container as the primary defence against a visitor asking for something expensive,
ahead of any application-level rate limiting.

Nothing floats on a branch. Every `ref` in `dsui.yaml` is pinned to a tag, so a
push to a repository can never change or break the public demo; fixing the demo is
a deliberate tag bump.

Two details in `dsui.yaml` that are easy to get wrong:

- An adapter's `repository` must be a full `git+https://github.com/owner/name`
  URL. A plugin's is a bare `owner/name`.
- `ref` is a tag, never `main`.

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
│   └── demo-guide/       # guided tour, five stops
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
| anonymous | `operator` | browse everything, run queries, trigger DAGs and dbt |
| anonymous, `allowExecution: false` | `viewer` | read only |
| presents `DEMO_ADMIN_SECRET` as the `x-demo-admin` header or the `dsui_demo_admin` cookie | `owner` | everything, including service management |

`operator` withholds `manage`, so a stranger cannot create or delete a service
or change configuration. Those grants are a hard ceiling in the host's
`auth.ts`, so no plugin can widen them back. The secret is compared in constant
time after hashing, and an unset secret matches nothing.

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
| Stripe | customers, subscriptions, invoices, charges, refunds, balance transactions | Integer minor units, epoch timestamps, lowercased ISO currency, negative amounts on charges and positive on refunds, `net = amount - fee`, and refunds update `amount_refunded` on the parent charge |
| PostHog | people, events | `event` / `distinct_id` / `timestamp` envelope, `$set` and `$set_once` person properties, `$current_url`, `$referrer`, `$browser`, `$os`, and `$feature_flag_called` with a variant |
| GA4 | sessions | Anonymous `session_id`, `source` / `medium` / `campaign`, `engagement_time_msec`, bounce flag |
| Meta Ads | meta_ads_daily | Spend as a decimal string, and `actions` as the nested action-type/value array a Meta report actually is |
| Google Ads | google_ads_daily | Cost in `cost_micros`, millionths of the account currency unit |
| Search Console | gsc_daily | One row per dimension combination with a fractional average `position` between 1 and 100 |
| Accounts | accounts | The product's own dimension, and the join key the other sources resolve to |

Landed the way the vendors actually hand data over: Stripe as verbatim webhook
JSON in a `payload` column with only `created_at` promoted, PostHog as an event
envelope. Nothing is flattened into a convenient shape on the way in.

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
docker compose run --rm data-generator python generate.py verify
scripts/reset.sh                       # reseed now
scripts/reset.sh 2026-01-31T00:00:00   # reseed at a fixed anchor
```

Reproducible builds need an anchor, because the wall clock moves the window:

```sh
docker compose run --rm data-generator python generate.py seed --as-of 2026-01-31T00:00:00
```

### Checks

Two static gates run during the image build. `pyflakes` catches shape errors.
`test_tables.py` asserts the shape of every weighted-choice table, that country
codes are two letters, that the acquisition builders run end to end, and that
GA4 volume actually follows the acquisition index.

Both exist because those bugs were here. Three weighted-choice tables were
malformed as flat lists and `(source, medium, weight)` triples. Three separate
places subscripted or unpacked the result of a helper that already returns a
value, which produced a truncated country code `"D"` and two unpack errors. None
of them failed where they were defined; they failed later, on whichever code path
happened to reach them, which in a generator means a crash or a silent data
defect that only some seeds ever hit.

## The transformation layer

`dbt/` reads the landing zone and produces marts. Staging is a view layer, marts
are tables, and the published database shows all three schemas side by side:

```
landing   21 views   the malformed raw tables, all text
staging    9 views   typed, deduplicated, one row per grain
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

`largest_discrepancy` names the biggest disagreement in plain language, and all
three of its branches fire on the generated data rather than being decoration.

The build writes to `next/demo.duckdb` and never to the published file, because
DuckDB allows a single writing process. Airflow renames it into place only after
a successful build, so a visitor reading the previous snapshot never sees a
half-built one. The build target is deleted first each run, because dbt does not
drop schemas it no longer manages and a reused file accumulates stale duplicates.

## What a visitor sees

Three services, all fed by the same synthetic business:

| Service | What it is |
| --- | --- |
| `landing` | MinIO, seeded from the same CSVs the pipeline reads, so object storage and the warehouse describe one company |
| `analytics` | PostgreSQL, raw layer and marts side by side, with a statement timeout |
| `snapshot` | One DuckDB file holding landing, staging and marts, replaced atomically after each build |
| `orchestration` | Airflow, reached over the compose network with Basic auth and never published |

`demo-guide` walks five stops through them in the order the data flows, and
contributes a sidebar widget so it is reachable from anywhere. It does not
autoplay: someone who opened a public demo has already decided to look.

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

`adapters[].source: git` does not currently accept a tag. The refinement in
`packages/server/src/config.ts` implements an exclusive-or where its own message
describes "both or neither", so it rejects `ref` + `path` and `commit` +
`integrity` while accepting a `commit` or an `integrity` on its own. Until that is
fixed, an adapter cannot be pointed at a tag. `dsui.yaml` here is written in the
intended form and will work as soon as the predicate matches its message.

The AI agent is deliberately absent: `packages/plugin-ai-agent` has no source, so
there is nothing to mount. The demo does not promise it.
