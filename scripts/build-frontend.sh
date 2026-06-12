#!/usr/bin/env bash
# build-frontend.sh — compile the SvelteKit frontend for the spine to serve.
#
# Produces the static bundle at frontend/build/ via @sveltejs/adapter-static.
# In production the spine (FastAPI) serves this dir in place at the root path —
# no Node/vite-preview server. See backend/raspy/core/static.py and
# plan/50-deployment.md §4.
#
# Run this as part of deploy, BEFORE (re)starting the spine:
#   scripts/build-frontend.sh && systemctl restart raspy
#
# PUBLIC_API_BASE must be EMPTY for a spine-hosted build so the UI talks to its
# own origin (/api/...). The frontend .env sets it to app.vardhin.com for local
# dev; this script forces it empty for the build to avoid baking a cross-origin
# base into the production bundle. Override by exporting PUBLIC_API_BASE yourself.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

cd "$FRONTEND_DIR"

if [ ! -d node_modules ]; then
  echo "==> node_modules missing — installing dependencies with bun"
  bun install
fi

# Same-origin by default for a spine-hosted bundle (see header).
export PUBLIC_API_BASE="${PUBLIC_API_BASE:-}"

echo "==> Building frontend (PUBLIC_API_BASE='${PUBLIC_API_BASE}')"
bun run build

echo "==> Done. Bundle at: $FRONTEND_DIR/build"
echo "    The spine serves it in place; restart the spine to pick up changes."
