# syntax=docker/dockerfile:1.7
# Build an immutable DSUI source revision that includes plugin overlays and the
# installed-plugin browserBundle support needed by the code-repository plugin.
FROM oven/bun:1.3.12 AS build
WORKDIR /src
ARG DSUI_REF=7fe8a6692050de10e10ecd6c7b7d811935d92440
ADD https://codeload.github.com/northgraindata/dsui/tar.gz/${DSUI_REF} /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
RUN bun install --frozen-lockfile --ignore-scripts
COPY plugins /src/packages/demo-plugins
COPY dbt /src/demo-dbt
RUN ln -s /src/packages/server/node_modules /src/packages/demo-plugins/node_modules && \
    bun build /src/packages/demo-plugins/demo-auth/src/index.ts --bundle --target bun --format esm --outfile /out/plugins/demo-auth.mjs && \
    bun build /src/packages/demo-plugins/demo-guide/src/index.ts --bundle --target bun --format esm --outfile /out/plugins/demo-guide.mjs
RUN bun test /src/packages/demo-plugins/demo-auth/src /src/packages/demo-plugins/demo-guide/src
RUN bun run --filter @northgraindata/dsui-web build
RUN mkdir -p /out/data /out/plugins && \
    bun build packages/server/src/main.ts --bundle --target bun --minify --outfile /out/server.mjs && \
    bun build packages/plugin-code-repository/src/plugin.ts --bundle --target bun --format esm --outfile /out/plugins/code-repository.mjs && \
    bun build packages/plugin-code-repository/src/browser.tsx --bundle --target browser --format esm --outfile /out/plugins/code-repository.browser.mjs && \
    bun -e "import { prepareSdk } from './packages/server/src/adapters/sdk.ts'; await prepareSdk('packages', '/app/sdk', '0.1.1');"

RUN for name in postgresql duckdb s3 airflow dbt; do \
      mkdir -p /out/adapters/adapter-$name; \
      tar --exclude=node_modules -C /src/packages/adapter-$name -cf - . | tar -C /out/adapters/adapter-$name -xf -; \
    done

FROM oven/bun:1.3.12-slim
WORKDIR /app
COPY --from=build --chown=bun:bun /out/server.mjs /app/server.mjs
RUN printf '#!/bin/sh\nexec bun /app/server.mjs "$@"\n' > /usr/local/bin/dsui && chmod +x /usr/local/bin/dsui
COPY --from=build --chown=bun:bun /out/data /data
COPY --from=build --chown=bun:bun /out/plugins /app/plugins
COPY --chown=bun:bun plugins/demo-guide/lab /app/plugins/demo-guide/lab
COPY --from=build --chown=bun:bun /out/plugins/code-repository.browser.mjs /app/plugins/code-repository.browser.mjs
RUN chown bun:bun /app/plugins/code-repository.browser.mjs
COPY --from=build --chown=bun:bun /app/sdk /app/sdk
COPY --from=build --chown=bun:bun /src/apps/web/dist /app/web
COPY --from=build --chown=bun:bun /out/adapters /app/source/packages
COPY --from=build --chown=bun:bun /src/demo-dbt /opt/demo-dbt
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv && \
    python3 -m venv /opt/dbt && \
    /opt/dbt/bin/pip install --no-cache-dir dbt-core==1.9.10 dbt-duckdb==1.9.2 duckdb==1.2.2 && \
    /opt/dbt/bin/dbt deps --project-dir /opt/demo-dbt --profiles-dir /opt/demo-dbt && \
    /opt/dbt/bin/dbt parse --project-dir /opt/demo-dbt --profiles-dir /opt/demo-dbt && \
    chown -R bun:bun /opt/dbt /opt/demo-dbt && \
    rm -rf /var/lib/apt/lists/*
ENV DSUI_HOST=0.0.0.0 DSUI_PORT=4192 DSUI_DATA_DIR=/data \
    DSUI_WEB_ROOT=/app/web DSUI_RUNTIME_PLUGINS=/app/plugins \
    DSUI_SDK_ROOT=/app/sdk DSUI_VERSION=0.1.1 \
    BUN_INSTALL_CACHE_DIR=/data/.bun-cache \
    DEMO_LANDING_DIR=/out/landing DEMO_DUCKDB_NEXT=/out/manual/demo.duckdb \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
USER bun
EXPOSE 4192
ENTRYPOINT ["/usr/local/bin/dsui"]
CMD ["start"]
