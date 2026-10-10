# Demo project review

The transformation project now covers every landing file and builds successfully from a deterministic fixture and the deployment-sized dataset.
This validates the data layer, not the deployed DSUI, Airflow or object-storage services.
The full Compose stack has not been started as part of this review.

## Fixed in this change

- Added source-specific staging folders, one YAML per source file and model, and documented all source/model columns and types.
- Added the missing e-commerce and Stripe staging models, bringing staging to 21 models; marts consume staged Stripe billing objects.
- Enforced model contracts and added `dbt_utils`, maintained `metaplane/dbt_expectations`, relationship tests and independent SQL reconciliations.
- Corrected Stripe merchant ledger signs, refund source IDs, refund currencies, parent charge updates, charge identity, invoice links, flat-price quantity and subscription billing periods.
- Stopped live Stripe charges from inventing customers and invoice references.
- Corrected Meta action fan-out, impression-weighted Search Console position, currency-decorated money parsing, UTC conversion and whitespace in GA4 source names.
- Made CSV exports standards-compliant, so nested JSON survives CSV/Parquet round trips.
- Enlarged random commerce identifiers to 96 bits after uniqueness tests reproduced collisions in the old six/seven-digit identifiers.
- Raised the event cap to one million because the 1200-account seed already exceeds the old 400,000 cap; increased generator memory to 2 GiB.
- Added CI with deterministic data generation, Python checks, `dbt build`, catalog generation, artifacts and the pinned dbt-doctor action.
- Pinned dbt-core, dbt-duckdb and DuckDB consistently for local checks and both runtime images; added package dependency installation to dbt builds.
- Made the Airflow dbt task use the same fresh build-file entrypoint, so renamed models do not accumulate in reused snapshots.

## Runtime and deployment status

The runtime changes now provision separate Airflow/writer/reader roles, initialize
Airflow 2 authentication and migrations, wait for a complete seed, execute real
DAG tasks, publish refreshed landing artifacts, and atomically replace the
warehouse only after a successful build. The reader is read-only. Health checks
verify the running scheduler/API rather than just installed binaries.

Local integration used Apple Containers. The exact pinned Docker Compose images
still need the fresh-stack CI job and remote deployment checks. CI exercises API
permissions, SQL reads/write denial, scheduler execution, S3 publication and
preservation of the published database after a failed build.

DSUI is pinned to the merged overlay implementation. Demo plugins own their
scenario and repair project; the product provides generic extension contracts.

## Modeling limits

The synthetic source shapes are documented in [source fidelity](source-fidelity.md).
Current account/subscription creation cohorts are not historical month-end subscriber counts.
Historical MRR needs state history rather than a sum of current MRR grouped by signup month.
Campaign dimension identifiers are illustrative rather than a stable vendor dimension history.
Pending balances and flag exposures are synthetic states, not settlement or experiment models.
These distinctions should stay visible in the demo tour and query examples.
