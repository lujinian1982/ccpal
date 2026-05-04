#!/usr/bin/env bash
# CCPal Codex integration · install
#   1. install the `mcp` Python package (pip --user)
#   2. deploy ccpal-mcp.py to ~/.claude/scripts/ (alongside other CCPal artifacts)
#   3. append [mcp_servers.ccpal] to ~/.codex/config.toml (idempotent)
#
# Idempotent. Safe to re-run.
#
# Pre-req: CCPal core must already be installed (run the Claude Code plugin's
# install.sh first, or `bash hosts/claude-code/scripts/install.sh`). This
# script only adds the Codex bridge on top of an existing core.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$HOME/.claude/scripts"
MCP_SCRIPT="$DEPLOY_DIR/ccpal-mcp.py"
CONFIG="$HOME/.codex/config.toml"

# ── 0. sanity: core installed? ──────────────────────────────────────────────
if [ ! -x "$HOME/.claude/scripts/start-history.sh" ]; then
  echo "ERROR: CCPal core not installed yet."
  echo "  Run first: bash <repo>/hosts/claude-code/scripts/install.sh"
  exit 1
fi

# ── 1. python deps ──────────────────────────────────────────────────────────
echo "▸ pip install mcp (--user)"
python3 -m pip install --user --quiet --upgrade -r "$HERE/requirements.txt"

# ── 2. deploy MCP script ────────────────────────────────────────────────────
mkdir -p "$DEPLOY_DIR"
cp -f "$HERE/ccpal-mcp.py" "$MCP_SCRIPT"
chmod +x "$MCP_SCRIPT"
echo "▸ deployed: $MCP_SCRIPT"

# ── 3. register in ~/.codex/config.toml ─────────────────────────────────────
mkdir -p "$(dirname "$CONFIG")"
touch "$CONFIG"

if grep -q '^\[mcp_servers\.ccpal\]' "$CONFIG"; then
  echo "▸ ~/.codex/config.toml already has [mcp_servers.ccpal] — leaving as-is"
else
  cat >> "$CONFIG" <<EOF

[mcp_servers.ccpal]
command = "python3"
args = ["$MCP_SCRIPT"]
startup_timeout_sec = 20
EOF
  echo "▸ appended [mcp_servers.ccpal] to $CONFIG"
fi

# ── 4. quick smoke test ────────────────────────────────────────────────────
if python3 -c "from mcp.server.fastmcp import FastMCP" 2>/dev/null; then
  echo "▸ mcp package import OK"
else
  echo "⚠  mcp package import failed — check 'python3 -m pip show mcp'"
fi

if python3 -c "import ast; ast.parse(open('$MCP_SCRIPT').read())" 2>/dev/null; then
  echo "▸ ccpal-mcp.py syntax OK"
else
  echo "✗ ccpal-mcp.py has a syntax error"
  exit 1
fi

echo ""
echo "✅ CCPal Codex bridge installed."
echo "   Restart Codex (or 'codex restart') to pick up the new MCP server."
echo "   Then in Codex, the model can call: ccpal.open_ui, ccpal.recent_sessions,"
echo "                                       ccpal.search_sessions, ccpal.get_session_text,"
echo "                                       ccpal.stats"
