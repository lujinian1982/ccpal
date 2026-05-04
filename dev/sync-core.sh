#!/usr/bin/env bash
# Copy core/ into each host plugin's bundled core/, so plugins are
# self-contained when distributed (git-subdir, tarball, marketplace).
#
# Run this any time core/ changes:
#   bash dev/sync-core.sh
#
# Only hosts that have .claude-plugin/plugin.json get a bundle (skip empty
# placeholder dirs).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$REPO/core"

if [ ! -d "$CORE" ]; then
  echo "ERROR: $CORE not found" >&2
  exit 1
fi

count=0
for host_dir in "$REPO"/hosts/*/; do
  host="$(basename "$host_dir")"
  if [ ! -f "$host_dir/.claude-plugin/plugin.json" ]; then
    echo "▸ skip $host (no plugin.json yet)"
    continue
  fi
  echo "▸ sync core → hosts/$host/core/"
  rm -rf "$host_dir/core"
  cp -R "$CORE" "$host_dir/core"
  count=$((count + 1))
done

echo ""
echo "✓ synced core/ into $count host plugin(s)"
echo "  remember to: git add hosts/*/core && git commit"
