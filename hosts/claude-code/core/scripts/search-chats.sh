#!/usr/bin/env bash
# 在所有 Claude Code 历史会话里搜索关键词
# 用法: search-chats.sh <关键词>
set -euo pipefail

if [ $# -eq 0 ]; then
  cat <<EOF
用法: claude-search <关键词>

示例:
  claude-search 阅读卡片
  claude-search "Vercel 部署"
  claude-search 仁珍千宝

输出: 时间 · 项目路径 · 会话标题 · 命中片段
按时间倒序。
EOF
  exit 0
fi

QUERY="$*"
ROOT="$HOME/.claude/projects"
cd "$ROOT"

MATCHES=$(find . -name "*.jsonl" -type f -exec grep -l -i -F "$QUERY" {} \; 2>/dev/null)

if [ -z "$MATCHES" ]; then
  echo "未命中: $QUERY"
  exit 0
fi

# (mtime, file) 倒序
RESULTS=$(while IFS= read -r f; do
  ts=$(stat -f '%m' "$f")
  echo "$ts|$f"
done <<< "$MATCHES" | sort -rn)

COUNT=$(echo "$RESULTS" | wc -l | tr -d ' ')
echo "═══ 命中 $COUNT 个会话 · 关键词: $QUERY ═══"
echo

echo "$RESULTS" | while IFS='|' read -r ts f; do
  session=$(basename "$f" .jsonl)
  date=$(date -r "$ts" '+%Y-%m-%d %H:%M')

  # 真实 cwd 路径
  cwd=$(jq -r 'select(.cwd != null) | .cwd' "$f" 2>/dev/null | head -1)
  [ -z "$cwd" ] && cwd="(未知路径)"

  # 标题:第一条 user message 文本
  title=$(jq -r '
    select(.type=="user" or (.message.role=="user")) |
    (.message.content // .content) |
    if type=="string" then .
    elif type=="array" then (.[]? | select(.type=="text") | .text) // ""
    else ""
    end' "$f" 2>/dev/null \
    | grep -v '^$' | head -1 | tr -s '\n ' ' ' | head -c 90)
  [ -z "$title" ] && title="(无文本)"

  # 命中片段:在所有可读文本里找
  hit=$(jq -r '
    (.message.content // .content // .lastPrompt // "") |
    if type=="string" then .
    elif type=="array" then (map(select(.type=="text") | .text) | join(" "))
    else ""
    end' "$f" 2>/dev/null \
    | grep -i -F -m 1 "$QUERY" | tr -s '\n ' ' ' | head -c 160)
  [ -z "$hit" ] && hit="(命中位置在元数据中)"

  echo "▸ $date  $session"
  echo "  路径   $cwd"
  echo "  标题   $title"
  echo "  命中   …$hit…"
  echo
done
