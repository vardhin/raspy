#!/usr/bin/env bash
# release.sh — cut a Raspy release: bump the version, tag, push, and kick off the
# GitHub Actions build that publishes the per-platform binaries.
#
#   scripts/release.sh 1.2.3        # set version to 1.2.3, tag v1.2.3, push
#   scripts/release.sh patch        # bump the patch component (x.y.Z+1)
#   scripts/release.sh minor        # bump minor (x.Y+1.0)
#   scripts/release.sh major        # bump major (X+1.0.0)
#   scripts/release.sh --dispatch   # don't tag; just trigger the workflow manually
#
# The single source of truth for the version is backend/raspy/__init__.py
# (__version__); pyproject reads it dynamically. This script rewrites that line,
# commits it, tags vX.Y.Z, and pushes the tag — which is what release.yml triggers
# on. The build then publishes raspy-<os>-<arch>, SHA256SUMS, and latest.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INIT="$ROOT/backend/raspy/__init__.py"

current() { grep -oE '__version__ = "[^"]+"' "$INIT" | sed -E 's/.*"([^"]+)".*/\1/'; }

bump() { # bump <major|minor|patch> <cur>
  IFS=. read -r MA MI PA <<<"$2"
  case "$1" in
    major) echo "$((MA+1)).0.0" ;;
    minor) echo "$MA.$((MI+1)).0" ;;
    patch) echo "$MA.$MI.$((PA+1))" ;;
  esac
}

# --dispatch: trigger the workflow without tagging (uses workflow_dispatch).
if [ "${1:-}" = "--dispatch" ]; then
  command -v gh >/dev/null || { echo "need the GitHub CLI (gh) for --dispatch" >&2; exit 1; }
  echo "==> triggering release workflow (workflow_dispatch) on the current branch"
  gh workflow run release.yml
  echo "==> watch: gh run watch \$(gh run list --workflow=release.yml -L1 --json databaseId -q '.[0].databaseId')"
  exit 0
fi

[ $# -ge 1 ] || { echo "usage: release.sh <version|patch|minor|major|--dispatch>" >&2; exit 1; }

CUR="$(current)"
case "$1" in
  major|minor|patch) NEW="$(bump "$1" "$CUR")" ;;
  *) NEW="${1#v}" ;;   # explicit version, tolerate a leading v
esac

echo "==> version: $CUR -> $NEW"

# Refuse to tag a dirty tree (other than the version bump we're about to make).
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then
  echo "working tree is dirty — commit or stash first (this script makes its own version-bump commit)" >&2
  exit 1
fi

# Rewrite __version__.
tmp="$(mktemp)"
sed -E "s/__version__ = \"[^\"]+\"/__version__ = \"$NEW\"/" "$INIT" > "$tmp" && mv "$tmp" "$INIT"

git -C "$ROOT" add "$INIT"
git -C "$ROOT" commit -m "release: v$NEW"
git -C "$ROOT" tag -a "v$NEW" -m "Raspy v$NEW"

echo "==> pushing commit + tag v$NEW"
git -C "$ROOT" push origin HEAD
git -C "$ROOT" push origin "v$NEW"

echo "==> done. Release workflow will build + publish binaries for v$NEW."
if command -v gh >/dev/null; then
  echo "    watch:  gh run watch \$(gh run list --workflow=release.yml -L1 --json databaseId -q '.[0].databaseId')"
fi
