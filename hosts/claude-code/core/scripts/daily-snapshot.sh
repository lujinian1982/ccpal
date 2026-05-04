#!/usr/bin/env bash
# 每日给 ~/.claude/projects 做一次 git 快照
set -euo pipefail

REPO="$HOME/.claude/projects"
LOG="$HOME/.claude/logs/daily-snapshot.log"

cd "$REPO"

if [ ! -d .git ]; then
  git init -q
fi

git config user.email "claude-snapshot@local" 2>/dev/null
git config user.name "Claude Snapshot" 2>/dev/null

if git diff --quiet HEAD -- 2>/dev/null && git diff --cached --quiet 2>/dev/null && [ -z "$(git status --porcelain)" ]; then
  echo "[$(date '+%F %T')] no changes" >> "$LOG"
  exit 0
fi

git add -A

CHANGED=$(git diff --cached --shortstat | tr -s ' ')
DATE=$(date '+%Y-%m-%d %H:%M')

git commit -q -m "snapshot: $DATE — $CHANGED" || {
  echo "[$(date '+%F %T')] commit failed" >> "$LOG"
  exit 1
}

REV=$(git rev-parse --short HEAD)
echo "[$(date '+%F %T')] committed $REV — $CHANGED" >> "$LOG"
