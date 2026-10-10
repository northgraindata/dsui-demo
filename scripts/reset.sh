#!/usr/bin/env bash
# Reset through the running generator so its configured dataset sizes apply.
set -euo pipefail
cd "$(dirname "$0")/.."
args=(sh -c 'exec python generate.py reset --customers "${DEMO_CUSTOMERS:-5000}" --orders "${DEMO_ORDERS:-60000}" --accounts "${DEMO_ACCOUNTS:-1200}" "$@"' reset)
if [ -n "${1:-}" ]; then args+=(--as-of "$1"); fi
if [ "$(uname -s)" = Darwin ]; then
  exec container exec dsui-demo-data-generator "${args[@]}"
fi
exec docker compose exec -T data-generator "${args[@]}"
