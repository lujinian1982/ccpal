#!/usr/bin/env bash
# 启动 Claude Code 历史浏览器
set -e

PORT=8765
URL="http://127.0.0.1:$PORT"

# 已在跑就直接打开
if curl -s -o /dev/null -m 1 "$URL/api/index" 2>/dev/null; then
  echo "已在运行: $URL"
  open "$URL"
  exit 0
fi

# 启动后台服务
LOG="$HOME/.claude/logs/history-server.log"
mkdir -p "$(dirname "$LOG")"
nohup python3 "$HOME/.claude/scripts/history-server.py" >> "$LOG" 2>&1 &
PID=$!
echo "$PID" > "$HOME/.claude/logs/history-server.pid"

# 等服务起来
for i in $(seq 1 30); do
  if curl -s -o /dev/null -m 1 "$URL/api/index" 2>/dev/null; then
    echo "已启动: $URL  (pid $PID)"
    open "$URL"
    exit 0
  fi
  sleep 0.5
done

echo "启动超时,看日志: $LOG"
exit 1
