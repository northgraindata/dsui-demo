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
├── data-generator/       # Python: seeds and refreshes the synthetic dataset
├── dbt/                  # transformation project
├── airflow/dags/         # orchestration
├── plugins/
│   ├── demo-auth/        # anonymous operator, secret-holder owner
│   └── demo-guide/       # guided tour
└── scripts/demo.sh       # up / reset / doctor
```

## Access

Anonymous visitors get role `operator`: they can browse everything and run
actions, but not create or delete services and not change configuration, because
`manage` is not in the role's grants.

`demo-auth` adds a second tier — presenting `DEMO_ADMIN_SECRET` grants `owner`.
That plugin is not written yet.

## Status

- [x] Compose with DSUI and PostgreSQL, one adapter, resource limits, healthcheck
- [ ] `demo-auth` two-tier plugin
- [x] Data generator and raw schema
- [ ] dbt project, seeded and built
- [ ] Airflow with DAGs and backfilled history
- [ ] MinIO, DuckDB, `code-repository`, monitoring
- [ ] `demo-guide` tour plugin, reset procedure, landing page CTA

## The dataset

One synthetic e-commerce SaaS feeds the whole demo, so a visitor never sees two
unrelated worlds. `data-generator` writes it to PostgreSQL, exports CSVs for
object storage, and produces a local DuckDB file.

The raw tables are deliberately malformed, because cleaning them is the story:

- Timestamps arrive in five formats — ISO, `DD/MM/YYYY`, ISO with `Z`, bare
  date, and epoch seconds.
- Money arrives as a number, as `$1,234.56`, as `12.00 EUR`, and with a decimal
  comma.
- Status casing is inconsistent across all fourteen visible variants.
- Around one percent of customers are duplicated, two percent have no email, and
  a few order items reference orders that do not exist.

Reproducible builds need an anchor, because the wall clock moves the window:

```sh
docker compose run --rm data-generator python generate.py seed --as-of 2026-01-31T00:00:00
docker compose run --rm data-generator python generate.py verify
```

The container seeds on boot and then appends a trickle of activity every five
minutes, so charts and lineage do not look frozen. Appending is idempotent
against the seeded dimensions: it reads the existing customers and products
rather than inventing new ones, so recent rows stay referentially coherent.

## Known issues

`adapters[].source: git` does not currently accept a tag. The refinement in
`packages/server/src/config.ts` implements an exclusive-or where its own message
describes "both or neither", so it rejects `ref` + `path` and `commit` +
`integrity` while accepting a `commit` or an `integrity` on its own. Until that is
fixed, an adapter cannot be pointed at a tag. `dsui.yaml` here is written in the
intended form and will work as soon as the predicate matches its message.

The AI agent is deliberately absent: `packages/plugin-ai-agent` has no source, so
there is nothing to mount. The demo does not promise it.
