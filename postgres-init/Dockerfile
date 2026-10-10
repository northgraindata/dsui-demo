FROM postgres:16-alpine

# Keep bootstrap scripts in the image: remote Compose deployments cannot rely
# on the build checkout remaining available as a runtime bind mount.
COPY --chmod=755 postgres-init/01-roles.sh /docker-entrypoint-initdb.d/01-roles.sh
COPY postgres-init/02-ensure-roles.sql /docker-entrypoint-initdb.d/02-ensure-roles.sql
