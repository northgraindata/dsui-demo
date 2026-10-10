FROM postgres:16-alpine

# Keep the recurring role reconciliation script available without a source
# checkout bind mount in remote Compose deployments.
COPY postgres-init/02-ensure-roles.sql /docker-entrypoint-initdb.d/02-ensure-roles.sql
