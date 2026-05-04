#!/usr/bin/env bash
# CCPal Codex integration · install (Phase 2.2)
#
# Codex Desktop only honors MCP servers registered via its `codex mcp add`
# CLI — hand-edited [mcp_servers.X] / [marketplaces.X] blocks in
# ~/.codex/config.toml are silently ignored by the desktop loader. Earlier
# phases tried both and were dead code.
#
# This script:
#   0. cleans up Phase 2.0 / 2.1 leftovers (old marketplace tree + config blocks)
#   1. pip install --user mcp
#   2. deploys core/scripts/ccpal-mcp.py to ~/.claude/scripts/
#   3. (re)registers via `codex mcp add ccpal -- python3 <deployed-script>`
#
# Idempotent. After install, Cmd+Q Codex Desktop and reopen.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CORE_MCP="$REPO/core/scripts/ccpal-mcp.py"
DEPLOY_MCP="$HOME/.claude/scripts/ccpal-mcp.py"
CONFIG="$HOME/.codex/config.toml"

# ── locate the codex binary ────────────────────────────────────────────────
CODEX_BIN=""
for cand in \
  "/Applications/Codex.app/Contents/Resources/codex" \
  "$(command -v codex 2>/dev/null || true)"
do
  if [ -n "$cand" ] && [ -x "$cand" ]; then
    CODEX_BIN="$cand"
    break
  fi
done
if [ -z "$CODEX_BIN" ]; then
  echo "ERROR: codex binary not found." >&2
  echo "  Tried /Applications/Codex.app/Contents/Resources/codex and \$PATH." >&2
  exit 1
fi

# ── sanity ─────────────────────────────────────────────────────────────────
[ -f "$CORE_MCP" ] || { echo "ERROR: missing $CORE_MCP" >&2; exit 1; }
[ -x "$HOME/.claude/scripts/start-history.sh" ] || {
  echo "ERROR: CCPal core not installed yet."
  echo "  Run first: bash $REPO/hosts/claude-code/scripts/install.sh"
  exit 1
}

echo "▸ codex binary: $CODEX_BIN"

# ── 0. clean up Phase 2.0 / 2.1 leftovers ──────────────────────────────────
if [ -d "$HOME/.codex/marketplaces/ccpal" ]; then
  rm -rf "$HOME/.codex/marketplaces/ccpal"
  echo "▸ removed ~/.codex/marketplaces/ccpal/ (Phase 2.1 dead tree)"
fi
if [ -f "$CONFIG" ] && grep -qE '^\[(marketplaces\.ccpal-marketplace|plugins\."ccpal@ccpal-marketplace")\]' "$CONFIG"; then
  python3 - "$CONFIG" <<'PY'
import re, pathlib, sys
p = pathlib.Path(sys.argv[1])
lines = p.read_text().splitlines(True)
out, skip = [], False
HEADER = re.compile(r'^\[[\w".@\-]+\]\s*$')
TARGET = re.compile(r'^\[(marketplaces\.ccpal-marketplace|plugins\."ccpal@ccpal-marketplace")\]\s*$')
for line in lines:
    if HEADER.match(line):
        skip = bool(TARGET.match(line))
        if not skip:
            out.append(line)
        continue
    if not skip:
        out.append(line)
p.write_text(re.sub(r"\n{3,}", "\n\n", "".join(out)))
PY
  echo "▸ removed Phase 2.1 [marketplaces.*] / [plugins.*] blocks from $CONFIG"
fi

# ── 1. python deps ─────────────────────────────────────────────────────────
echo "▸ pip install mcp (--user)"
python3 -m pip install --user --quiet --upgrade -r "$HERE/requirements.txt"

# ── 2. deploy MCP script ───────────────────────────────────────────────────
mkdir -p "$(dirname "$DEPLOY_MCP")"
cp -f "$CORE_MCP" "$DEPLOY_MCP"
chmod +x "$DEPLOY_MCP"
echo "▸ deployed: $DEPLOY_MCP"

# ── 3. (re)register via codex mcp add ──────────────────────────────────────
"$CODEX_BIN" mcp remove ccpal >/dev/null 2>&1 || true
"$CODEX_BIN" mcp add ccpal -- python3 "$DEPLOY_MCP" >/dev/null
echo "▸ codex mcp add ccpal -- python3 $DEPLOY_MCP"

# ── 4. verify ──────────────────────────────────────────────────────────────
if "$CODEX_BIN" mcp list 2>/dev/null | grep -qE '^ccpal[[:space:]]'; then
  echo "▸ codex mcp list: ccpal present"
else
  echo "✗ codex mcp list does not show ccpal" >&2
  exit 1
fi

if python3 -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
  echo "▸ mcp package OK"
else
  echo "✗ mcp package import failed" >&2
  exit 1
fi

# end-to-end: spawn the deployed script and complete an MCP initialize handshake
if python3 - <<'PY' 2>/dev/null
import json, os, subprocess, sys
p = subprocess.Popen(
    ["python3", os.path.expanduser("~/.claude/scripts/ccpal-mcp.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, bufsize=1,
)
p.stdin.write(json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "smoke", "version": "0"}}
}) + "\n")
p.stdin.flush()
line = p.stdout.readline()
p.stdin.close()
p.wait(timeout=3)
sys.exit(0 if line and "result" in line else 1)
PY
then
  echo "▸ ccpal-mcp.py initialize handshake OK"
else
  echo "✗ ccpal-mcp.py failed handshake test" >&2
  exit 1
fi

echo ""
echo "✅ CCPal Codex bridge installed."
echo "   Cmd+Q Codex Desktop, then reopen — model will see 5 mcp__ccpal__* tools."
