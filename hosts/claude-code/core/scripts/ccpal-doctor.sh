#!/usr/bin/env bash
# CCPal 自检 + 幂等修复
# 重复跑无副作用,缺啥补啥,不删任何东西
set +e

SCRIPTS=$HOME/.claude/scripts
LOGS=$HOME/.claude/logs
PROJECTS=$HOME/.claude/projects
LAUNCH=$HOME/Library/LaunchAgents
BACKUP=$HOME/CCPal-Backup
PORT=8765

OK=0; FIX=0; WARN=0; ERR=0

ok()   { echo "  ✓ $1"; OK=$((OK+1)); }
fix()  { echo "  ⚙ $1"; FIX=$((FIX+1)); }
warn() { echo "  ⚠ $1"; WARN=$((WARN+1)); }
err()  { echo "  ✗ $1"; ERR=$((ERR+1)); }

check() {
  local name="$1" test="$2" fixcmd="$3"
  if eval "$test" >/dev/null 2>&1; then
    ok "$name"
  else
    if [ -n "$fixcmd" ]; then
      if eval "$fixcmd" >/dev/null 2>&1; then
        fix "$name → 已修复"
      else
        err "$name → 自动修复失败"
      fi
    else
      err "$name (缺失,需要重跑 install.html)"
    fi
  fi
}

echo "═══ CCPal Doctor · $(date '+%Y-%m-%d %H:%M') ═══"

echo
echo "▸ 目录"
check "scripts 目录"   "[ -d $SCRIPTS ]"  "mkdir -p $SCRIPTS"
check "logs 目录"      "[ -d $LOGS ]"     "mkdir -p $LOGS"
check "LaunchAgents"   "[ -d $LAUNCH ]"   "mkdir -p $LAUNCH"
check "CCPal-Backup"   "[ -d $BACKUP ]"   "mkdir -p $BACKUP"

echo
echo "▸ Shell 脚本"
for f in daily-snapshot.sh backup-mirror.sh search-chats.sh start-history.sh ccpal-doctor.sh; do
  if [ -f "$SCRIPTS/$f" ]; then
    if [ -x "$SCRIPTS/$f" ]; then ok "$f"
    else chmod +x "$SCRIPTS/$f" && fix "$f → chmod +x"; fi
  else err "$f"; fi
done

echo
echo "▸ Python + HTML"
[ -f "$SCRIPTS/history-server.py" ] && ok "history-server.py" || err "history-server.py"
for h in ui stats health budget safety; do
  [ -f "$SCRIPTS/history-$h.html" ] && ok "history-$h.html" || err "history-$h.html"
done

echo
echo "▸ launchd"
for p in daily-snapshot backup-mirror; do
  pf="$LAUNCH/com.claude.$p.plist"
  if [ -f "$pf" ]; then
    ok "com.claude.$p.plist 文件"
    if launchctl list | grep -q "com.claude.$p" 2>/dev/null; then
      ok "com.claude.$p 已加载"
    else
      launchctl load "$pf" 2>/dev/null && fix "com.claude.$p → 已加载" || err "com.claude.$p 加载失败"
    fi
  else err "com.claude.$p.plist 缺失"; fi
done

echo
echo "▸ Git 仓"
if [ -d "$PROJECTS" ]; then
  if [ -d "$PROJECTS/.git" ]; then
    ok "~/.claude/projects/.git 已初始化"
    last_commit=$(cd "$PROJECTS" && git log -1 --format='%h %s' 2>/dev/null)
    [ -n "$last_commit" ] && echo "    最近 commit: $last_commit"
  else
    (cd "$PROJECTS" && git init -q && git config user.email claude-snapshot@local && git config user.name 'Claude Snapshot') && fix "git init projects" || err "git init 失败"
  fi
else
  warn "~/.claude/projects 还不存在 (用户尚未用过 Claude Code)"
fi

echo
echo "▸ settings.json"
if [ -f "$HOME/.claude/settings.json" ]; then
  if grep -q 'cleanupPeriodDays' "$HOME/.claude/settings.json" 2>/dev/null; then
    ok "settings.json 含 cleanupPeriodDays"
  else
    warn "settings.json 缺 cleanupPeriodDays (transcripts 30 天会被清,建议重跑 install.html 第 5 步)"
  fi
else
  warn "settings.json 不存在"
fi

echo
echo "▸ Web 服务"
if curl -s -o /dev/null -m 2 "http://127.0.0.1:$PORT/api/index" 2>/dev/null; then
  ok "history-server 已运行 (http://127.0.0.1:$PORT)"
else
  if [ -f "$SCRIPTS/start-history.sh" ]; then
    bash "$SCRIPTS/start-history.sh" >/dev/null 2>&1 && fix "history-server → 已启动" || err "history-server 启动失败"
  else err "start-history.sh 缺失"; fi
fi

echo
echo "▸ 镜像备份"
if [ -f "$BACKUP/manifest.json" ]; then
  jc=$(grep -o '"jsonl_count": *[0-9]*' "$BACKUP/manifest.json" | grep -o '[0-9]*')
  sz=$(grep -o '"total_size": *"[^"]*"' "$BACKUP/manifest.json" | sed 's/.*"\([^"]*\)"$/\1/')
  ok "镜像备份: $jc 个 jsonl, $sz"
else
  warn "镜像备份未跑过 (运行 bash $SCRIPTS/backup-mirror.sh 触发,首次约 1-3 分钟)"
fi

echo
echo "═══════════════════════════"
echo "✓ 正常 $OK   ⚙ 自动修复 $FIX   ⚠ 警告 $WARN   ✗ 错误 $ERR"
echo "═══════════════════════════"
[ $ERR -eq 0 ] && echo "🎉 CCPal 状态健康。打开 http://127.0.0.1:$PORT" || echo "⚠ 有未修复项目,建议重跑 install.html"
exit 0
