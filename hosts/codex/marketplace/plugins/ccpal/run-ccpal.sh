#!/usr/bin/env bash
# Wrapper invoked by Codex Desktop. Lives inside the plugin directory so
# Codex's localPluginPath gate accepts it; delegates to the real Python
# MCP server which is shipped alongside.
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/ccpal-mcp.py"
