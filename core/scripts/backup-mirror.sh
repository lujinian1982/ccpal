#!/usr/bin/env bash
# 把 ~/.claude/projects 镜像到独立目录 (~/CCPal-Backup),
# 即使整个 ~/.claude 被清掉也不丢数据。
# rsync 默认增量、不删除目标多余文件。
set -euo pipefail

SRC="$HOME/.claude/projects"
DEST="$HOME/CCPal-Backup"
LOG="$HOME/.claude/logs/backup-mirror.log"

mkdir -p "$DEST/transcripts" "$(dirname "$LOG")"

# 1) rsync 增量同步全部 jsonl 和 .git
rsync -a \
  --exclude='*.lock' --exclude='*.tmp' --exclude='.DS_Store' \
  "$SRC/" "$DEST/transcripts/"

# 2) git --mirror 同步,保留完整 commit 历史 (可独立 clone 出来恢复任意一天)
if [ -d "$DEST/git-mirror/refs" ]; then
  (cd "$DEST/git-mirror" && git fetch --all -q 2>/dev/null) || true
else
  git clone --mirror "$SRC" "$DEST/git-mirror" -q || true
fi

# 3) manifest
COUNT=$(find "$DEST/transcripts" -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
SIZE=$(du -sh "$DEST" 2>/dev/null | awk '{print $1}')
NOW=$(date -Iseconds)

cat > "$DEST/manifest.json" <<EOF
{
  "last_run": "$NOW",
  "source": "$SRC",
  "destination": "$DEST",
  "jsonl_count": $COUNT,
  "total_size": "$SIZE",
  "policy": "rsync incremental, no delete on dest; git-mirror full history"
}
EOF

echo "[$(date '+%F %T')] mirrored $COUNT jsonl files, total $SIZE" >> "$LOG"
