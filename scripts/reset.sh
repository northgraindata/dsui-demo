#!/usr/bin/env bash
# Reseeds the demo dataset.
#
# The generator already reseeds itself when it passes its cap or its max age,
# so this script is a convenience rather than the mechanism that keeps the
# database bounded. Use it for a manual reset, or wire it into a Coolify cron
# when you want a guaranteed clean window at a fixed hour.
#
#   scripts/reset.sh                       # reseed at the current time
#   scripts/reset.sh 2026-01-31T00:00:00   # reseed at a fixed anchor

set -euo pipefail

cd "$(dirname "$0")/.."

CUSTOMERS="${DEMO_CUSTOMERS:-5000}"
ORDERS="${DEMO_ORDERS:-60000}"
ACCOUNTS="${DEMO_ACCOUNTS:-1200}"
ANCHOR="${1:-}"

if [ -n "$ANCHOR" ]; then
  exec docker compose run --rm data-generator \
    python generate.py reset --customers "$CUSTOMERS" --orders "$ORDERS" \
      --accounts "$ACCOUNTS" --as-of "$ANCHOR"
fi

exec docker compose run --rm data-generator \
  python generate.py reset --customers "$CUSTOMERS" --orders "$ORDERS" \
    --accounts "$ACCOUNTS"
