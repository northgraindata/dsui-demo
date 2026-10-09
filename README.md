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
are reachable only on the compose network. Memory and CPU limits are set on every
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
├── plugins/
│   ├── demo-auth/        # anonymous operator, secret-holder owner
│   └── demo-guide/       # guided tour
└── scripts/
    └── reset.sh          # reseed the dataset
```

## Access

Anonymous visitors get role `operator`: they can browse everything and run
actions, but not create or delete services and not change configuration, because
`manage` is not in the role's grants.

`demo-auth` adds a second tier — presenting `DEMO_ADMIN_SECRET` grants `owner`.
That plugin is not written yet.

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
| Accounts | accounts | The product's own dimension, and the join key the other sources resolve to |

Landed the way the vendors actually hand data over: Stripe as verbatim webhook
JSON in a `payload` column with only `created_at` promoted, PostHog as an event
envelope. Nothing is flattened into a convenient shape on the way in.

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

`data-generator/test_tables.py` asserts the shape of every weighted-choice table
and country code, and runs during the image build. Three tables were wrong in the
first draft, as flat lists and `(source, medium, weight)` triples, and none of
them failed where they were defined. They failed later, on whichever code path
happened to reach them.

## Status

- [x] Compose with DSUI and PostgreSQL, one adapter, resource limits, healthcheck
- [ ] `demo-auth` two-tier plugin
- [x] Data generator: e-commerce, Stripe, PostHog, GA4, accounts
- [ ] Meta Ads, Google Ads, Search Console daily reports
- [ ] Airflow: Postgres to Parquet to dbt to DuckDB, published by atomic rename
- [ ] dbt project, seeded and built
- [ ] MinIO, `code-repository`, monitoring
- [ ] `demo-guide` tour plugin, landing page CTA

## Known issues

`adapters[].source: git` does not currently accept a tag. The refinement in
`packages/server/src/config.ts` implements an exclusive-or where its own message
describes "both or neither", so it rejects `ref` + `path` and `commit` +
`integrity` while accepting a `commit` or an `integrity` on its own. Until that is
fixed, an adapter cannot be pointed at a tag. `dsui.yaml` here is written in the
intended form and will work as soon as the predicate matches its message.

The AI agent is deliberately absent: `packages/plugin-ai-agent` has no source, so
there is nothing to mount. The demo does not promise it.
