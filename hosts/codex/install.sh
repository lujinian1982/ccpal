#!/usr/bin/env bash
# CCPal Codex integration · install (Phase 2.1, Codex-Desktop-correct)
#
# Codex Desktop silently drops user-added [mcp_servers.*] entries whose
# `command` isn't under a known localPluginPath. The supported path is the
# plugin/marketplace system used by computer-use, gmail, github, etc.
#
# This script:
#   1. removes the stale [mcp_servers.ccpal] block our v1 install added
#   2. installs the `mcp` Python package (--user)
#   3. deploys hosts/codex/marketplace/ → ~/.codex/marketplaces/ccpal/
#      (plus copies core/scripts/ccpal-mcp.py into the plugin dir)
#   4. idempotently appends [marketplaces.ccpal-marketplace] and
#      [plugins."ccpal@ccpal-marketplace"] to ~/.codex/config.toml
#
# Idempotent. Safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && cd .. && pwd)"
SOURCE_MARKET="$HERE/marketplace"
DEPLOY_MARKET="$HOME/.codex/marketplaces/ccpal"
DEPLOY_PLUGIN="$DEPLOY_MARKET/plugins/ccpal"
CORE_MCP="$REPO/core/scripts/ccpal-mcp.py"
CONFIG="$HOME/.codex/config.toml"

# ── 0. sanity ──────────────────────────────────────────────────────────────
[ -d "$SOURCE_MARKET" ]   || { echo "ERROR: source marketplace missing: $SOURCE_MARKET" >&2; exit 1; }
[ -f "$CORE_MCP" ]        || { echo "ERROR: core MCP script missing: $CORE_MCP" >&2; exit 1; }
[ -x "$HOME/.claude/scripts/start-history.sh" ] || {
  echo "ERROR: CCPal core not installed yet."
  echo "  Run first: bash $REPO/hosts/claude-code/scripts/install.sh"
  exit 1
}

# ── 1. remove stale [mcp_servers.ccpal] block (idempotent) ─────────────────
# Line-based parser: a "section header" is a line matching ^\[name\]$ at col 0.
# This avoids miscounting [ inside `args = [...]` as a section break.
if [ -f "$CONFIG" ] && grep -q '^\[mcp_servers\.ccpal\]' "$CONFIG"; then
  python3 - "$CONFIG" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
lines = p.read_text().splitlines(True)
out, skip = [], False
HEADER = re.compile(r'^\[[\w".@\-]+\]\s*$')
for line in lines:
    if HEADER.match(line):
        skip = (line.strip() == "[mcp_servers.ccpal]")
        if not skip:
            out.append(line)
        continue
    if not skip:
        out.append(line)
text = re.sub(r"\n{3,}", "\n\n", "".join(out))
p.write_text(text)
PY
  echo "▸ removed stale [mcp_servers.ccpal] from $CONFIG"
fi

# ── 2. python deps ─────────────────────────────────────────────────────────
echo "▸ pip install mcp (--user)"
python3 -m pip install --user --quiet --upgrade -r "$HERE/requirements.txt"

# ── 3. deploy marketplace tree ─────────────────────────────────────────────
mkdir -p "$DEPLOY_MARKET"
# rsync without --delete to be conservative; --delete-after only on plugin dir
rsync -a --delete-after \
  --exclude '.DS_Store' \
  "$SOURCE_MARKET"/ "$DEPLOY_MARKET"/
cp -f "$CORE_MCP" "$DEPLOY_PLUGIN/ccpal-mcp.py"
chmod +x "$DEPLOY_PLUGIN/run-ccpal.sh" "$DEPLOY_PLUGIN/ccpal-mcp.py"
echo "▸ deployed marketplace → $DEPLOY_MARKET"

# ── 4. register in ~/.codex/config.toml (idempotent) ───────────────────────
mkdir -p "$(dirname "$CONFIG")"
touch "$CONFIG"

if grep -q '^\[marketplaces\.ccpal-marketplace\]' "$CONFIG"; then
  echo "▸ [marketplaces.ccpal-marketplace] already in config — skipped"
else
  cat >> "$CONFIG" <<EOF

[marketplaces.ccpal-marketplace]
source_type = "local"
source = "$DEPLOY_MARKET"
EOF
  echo "▸ appended [marketplaces.ccpal-marketplace]"
fi

if grep -q '^\[plugins\."ccpal@ccpal-marketplace"\]' "$CONFIG"; then
  echo "▸ [plugins.\"ccpal@ccpal-marketplace\"] already in config — skipped"
else
  cat >> "$CONFIG" <<'EOF'

[plugins."ccpal@ccpal-marketplace"]
enabled = true
EOF
  echo "▸ appended [plugins.\"ccpal@ccpal-marketplace\"]"
fi

# ── 5. smoke test ──────────────────────────────────────────────────────────
if python3 -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
  echo "▸ mcp package OK"
else
  echo "⚠  mcp package import failed"
fi

if python3 -c "import ast; ast.parse(open('$DEPLOY_PLUGIN/ccpal-mcp.py').read())" 2>/dev/null; then
  echo "▸ deployed ccpal-mcp.py syntax OK"
else
  echo "✗ deployed ccpal-mcp.py has syntax error"
  exit 1
fi

# verify the wrapper actually launches the MCP server (initialize handshake)
if python3 - <<'PY' 2>/dev/null
import json, subprocess, sys, os
WRAP = os.path.expanduser("~/.codex/marketplaces/ccpal/plugins/ccpal/run-ccpal.sh")
p = subprocess.Popen([WRAP], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
p.stdin.write(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}})+"\n"); p.stdin.flush()
line = p.stdout.readline()
p.stdin.close(); p.wait(timeout=3)
sys.exit(0 if "result" in line else 1)
PY
then
  echo "▸ run-ccpal.sh wrapper end-to-end OK"
else
  echo "✗ run-ccpal.sh wrapper failed to initialize MCP"
  exit 1
fi

echo ""
echo "✅ CCPal Codex bridge installed (plugin path)."
echo ""
echo "   1. Cmd+Q Codex Desktop completely, then reopen"
echo "   2. Look in Codex Settings → Plugins/Tools — 'CCPal' should appear"
echo "   3. Or ask the model: 'list all available MCP tools'"
echo ""
echo "   Tools the model can call:"
echo "     mcp__ccpal__open_ui"
echo "     mcp__ccpal__recent_sessions"
echo "     mcp__ccpal__search_sessions"
echo "     mcp__ccpal__get_session_text"
echo "     mcp__ccpal__stats"
