#!/usr/bin/env bash
# CCPal Claude Code plugin · bootstrap installer
# Deploys core/ to ~/.claude/scripts/ + ~/Library/LaunchAgents/, merges settings,
# loads launchd jobs, starts the web UI, and runs the doctor.
# Idempotent: safe to re-run.
set -euo pipefail

# ── locate core/ ────────────────────────────────────────────────────────────
# Try plugin-local copy first (Phase 1c will bundle it), then dev layout where
# the plugin lives at <repo>/hosts/claude-code/ and core is at <repo>/core/.
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "${CLAUDE_PLUGIN_ROOT}/core" ]; then
  CORE="${CLAUDE_PLUGIN_ROOT}/core"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "${CLAUDE_PLUGIN_ROOT}/../../core" ]; then
  CORE="$(cd "${CLAUDE_PLUGIN_ROOT}/../../core" && pwd)"
else
  # Fallback: this script lives at <repo>/hosts/claude-code/scripts/install.sh
  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -d "$HERE/../../../core" ]; then
    CORE="$(cd "$HERE/../../../core" && pwd)"
  else
    echo "ERROR: cannot locate CCPal core/ directory" >&2
    echo "  CLAUDE_PLUGIN_ROOT=${CLAUDE_PLUGIN_ROOT:-<unset>}" >&2
    exit 1
  fi
fi

echo "▸ core source:  $CORE"
echo "▸ install root: $HOME/.claude"

# ── 1. directories ──────────────────────────────────────────────────────────
mkdir -p \
  "$HOME/.claude/scripts" \
  "$HOME/.claude/logs" \
  "$HOME/Library/LaunchAgents" \
  "$HOME/CCPal-Backup"

# ── 2. scripts (shell + python + html + md, all flat under scripts/) ────────
cp -f "$CORE"/scripts/* "$HOME/.claude/scripts/"
chmod +x "$HOME"/.claude/scripts/*.sh
echo "▸ deployed $(ls "$CORE/scripts" | wc -l | tr -d ' ') files → ~/.claude/scripts/"

# ── 3. launchd plists ───────────────────────────────────────────────────────
cp -f "$CORE"/LaunchAgents/*.plist "$HOME/Library/LaunchAgents/"

# ── 4. merge settings.json (don't replace) ──────────────────────────────────
SETTINGS="$HOME/.claude/settings.json"
[ -f "$SETTINGS" ] || echo "{}" > "$SETTINGS"
if command -v jq >/dev/null 2>&1; then
  TMP=$(mktemp)
  jq '. + {
    "cleanupPeriodDays": 9007199254740991,
    "fileCheckpointingEnabled": true,
    "showMessageTimestamps": true,
    "showTurnDuration": true,
    "autoMemoryEnabled": true,
    "autoCompactEnabled": true,
    "viewMode": "verbose",
    "defaultView": "transcript"
  }' "$SETTINGS" > "$TMP" && mv "$TMP" "$SETTINGS"
  echo "▸ merged settings.json"
else
  echo "⚠  jq not installed — skipped settings.json merge"
  echo "   install with: brew install jq, then re-run /ccpal install"
fi

# ── 5. init git in projects/ (if user has used Claude Code before) ──────────
if [ -d "$HOME/.claude/projects" ] && [ ! -d "$HOME/.claude/projects/.git" ]; then
  (cd "$HOME/.claude/projects" \
    && git init -q \
    && git config user.email "claude-snapshot@local" \
    && git config user.name "Claude Snapshot")
  echo "▸ git init ~/.claude/projects"
fi

# ── 6. (re)load launchd ─────────────────────────────────────────────────────
for plist in \
  "$HOME/Library/LaunchAgents/com.claude.daily-snapshot.plist" \
  "$HOME/Library/LaunchAgents/com.claude.backup-mirror.plist"
do
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load   "$plist"
done
echo "▸ loaded launchd jobs"

# ── 7. first snapshot + mirror (background) ────────────────────────────────
[ -d "$HOME/.claude/projects/.git" ] && \
  bash "$HOME/.claude/scripts/daily-snapshot.sh" >/dev/null 2>&1 || true
bash "$HOME/.claude/scripts/backup-mirror.sh" >/dev/null 2>&1 &

# ── 8. start web UI ─────────────────────────────────────────────────────────
bash "$HOME/.claude/scripts/start-history.sh"

# ── 9. doctor ───────────────────────────────────────────────────────────────
echo ""
bash "$HOME/.claude/scripts/ccpal-doctor.sh"

echo ""
echo "✅ CCPal installed. Open: http://127.0.0.1:8765"
echo "   Re-run anytime:  /ccpal install"
echo "   Self-check:      /ccpal doctor"
