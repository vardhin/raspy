#!/usr/bin/env bash
# build-and-serve.sh — compile the SvelteKit frontend, then serve the fresh build.
#
# The frontend uses @sveltejs/adapter-static, so `bun run build` emits a plain
# static bundle to frontend/build/. We serve it with `vite preview`, which honors
# the SPA fallback (index.html) needed for client-side routes like /a/[name].
#
# In production the spine (backend FastAPI) serves these same files — this script
# is for local dev/preview. Use serve.sh to skip the build and serve what's there.
#
# Usage:
#   scripts/build-and-serve.sh                # build, then preview on default host/port
#   PORT=8080 scripts/build-and-serve.sh      # override port
#   HOST=0.0.0.0 scripts/build-and-serve.sh   # expose on the network (e.g. for the Pi/phone)
set -euo pipefail

# Resolve the frontend dir relative to this script, so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

HOST="${HOST:-localhost}"
PORT="${PORT:-4173}"

cd "$FRONTEND_DIR"

# Install deps if node_modules is missing (fresh checkout).
if [ ! -d node_modules ]; then
  echo "==> node_modules missing — installing dependencies with bun"
  bun install
fi

echo "==> Building frontend (bun run build)"
bun run build

echo "==> Serving build at http://$HOST:$PORT"
exec bun run preview -- --host "$HOST" --port "$PORT"
