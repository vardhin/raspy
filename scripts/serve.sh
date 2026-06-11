#!/usr/bin/env bash
# serve.sh — serve the EXISTING frontend build without recompiling.
#
# Serves frontend/build/ as-is via `vite preview` (SPA fallback intact for routes
# like /a/[name]). If you've changed source, run build-and-serve.sh instead — this
# script does NOT rebuild.
#
# Usage:
#   scripts/serve.sh                # serve existing build on default host/port
#   PORT=8080 scripts/serve.sh      # override port
#   HOST=0.0.0.0 scripts/serve.sh   # expose on the network
set -euo pipefail

# Resolve the frontend dir relative to this script, so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

HOST="${HOST:-localhost}"
PORT="${PORT:-4173}"

cd "$FRONTEND_DIR"

if [ ! -f build/index.html ]; then
  echo "error: no build found at frontend/build/ — run scripts/build-and-serve.sh first" >&2
  exit 1
fi

echo "==> Serving existing build at http://$HOST:$PORT"
exec bun run preview -- --host "$HOST" --port "$PORT"
