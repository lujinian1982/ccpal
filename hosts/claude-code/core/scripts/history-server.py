#!/usr/bin/env python3
"""
Claude Code 本地历史浏览器
启动后访问 http://127.0.0.1:8765
"""
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
HTML_FILE = Path(__file__).parent / "history-ui.html"
STATS_HTML_FILE = Path(__file__).parent / "history-stats.html"
SAFETY_HTML_FILE = Path(__file__).parent / "history-safety.html"
PATH_RE = re.compile(r'@([~/\.][^\s\)\]\,\;]+)')
PORT = 8765
HOST = "127.0.0.1"

# 内存索引
_INDEX = []
_STATS = {}
_INDEX_TIME = 0
_INDEX_LOCK = threading.Lock()


def normalize_cwd(cwd):
    """worktree 路径规范化回真实项目根
    /xxx/项目/.claude/worktrees/yyy  ->  /xxx/项目
    """
    if not cwd:
        return cwd, False
    parts = cwd.split("/")
    try:
        idx = parts.index(".claude")
        if idx + 1 < len(parts) and parts[idx + 1] == "worktrees":
            return "/".join(parts[:idx]), True
    except ValueError:
        pass
    return cwd, False


def smart_title(text, maxlen=90):
    """从首条用户消息提取一个像标题的短句
    优先在 标点/换行 截断
    """
    if not text:
        return ""
    t = text.strip()
    # 跳过 @file 引用,找真正提问开头
    if t.startswith("@") and " " in t:
        t = t[t.find(" ") + 1:].strip()

    # 优先在标点/换行处截断
    cut = len(t)
    for sep in ["\n", "。", "？", "?", "！", "!", "。", "；", ";"]:
        i = t.find(sep)
        if 5 < i < maxlen and i < cut:
            cut = i
    if cut < len(t):
        return t[:cut].strip()
    return t[:maxlen].strip()


def extract_attachments(content):
    """从消息内容里提取被引用的文件路径
    - user message 里 @path 引用
    - tool_use input 里的 file_path / path / notebook_path / files
    返回去重后的 list
    """
    paths = set()

    def visit(block):
        if isinstance(block, str):
            for m in PATH_RE.finditer(block):
                p = m.group(1).rstrip('.,;:')
                if len(p) > 2:
                    paths.add(p)
        elif isinstance(block, list):
            for b in block:
                visit(b)
        elif isinstance(block, dict):
            t = block.get("type")
            if t == "text":
                txt = block.get("text", "")
                if isinstance(txt, str):
                    visit(txt)
            elif t == "tool_use":
                inp = block.get("input") or {}
                if isinstance(inp, dict):
                    for k in ("file_path", "path", "notebook_path", "edit_file_path", "filename"):
                        v = inp.get(k)
                        if isinstance(v, str) and len(v) > 2:
                            paths.add(v)
                    files = inp.get("files") or inp.get("paths")
                    if isinstance(files, list):
                        for x in files:
                            if isinstance(x, str) and len(x) > 2:
                                paths.add(x)

    visit(content)
    return sorted(paths)


def extract_blocks(content):
    """返回结构化 blocks: text / tool_use / tool_result / thinking"""
    blocks = []
    if content is None:
        return blocks
    if isinstance(content, str):
        if content.strip():
            blocks.append({"type": "text", "text": content})
        return blocks
    if isinstance(content, dict):
        return extract_blocks(content.get("content"))
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            t = b.get("type")
            if t == "text" and "text" in b:
                blocks.append({"type": "text", "text": b["text"]})
            elif t == "tool_use":
                blocks.append({
                    "type": "tool_use",
                    "name": b.get("name", "tool"),
                    "input": b.get("input") or {},
                })
            elif t == "tool_result":
                inner = b.get("content")
                if isinstance(inner, str):
                    txt = inner
                elif isinstance(inner, list):
                    parts = []
                    for x in inner:
                        if isinstance(x, dict) and x.get("type") == "text":
                            parts.append(x.get("text", ""))
                        elif isinstance(x, str):
                            parts.append(x)
                    txt = "\n".join(parts)
                else:
                    txt = str(inner) if inner else ""
                blocks.append({
                    "type": "tool_result",
                    "text": txt,
                    "is_error": bool(b.get("is_error", False)),
                })
            elif t == "thinking":
                blocks.append({
                    "type": "thinking",
                    "text": b.get("thinking", "") or b.get("text", ""),
                })
    return blocks


def extract_text(content):
    """合并为纯文本(给 search_blob 和 title 用)"""
    parts = []
    for b in extract_blocks(content):
        if b["type"] == "text":
            parts.append(b["text"])
        elif b["type"] == "tool_use":
            parts.append(f"[{b['name']}]")
        elif b["type"] == "tool_result":
            parts.append(b["text"])
        elif b["type"] == "thinking":
            parts.append(b["text"])
    return "\n".join(parts)


def parse_jsonl(path, with_tokens=False):
    """读 jsonl, 返回 (messages, cwd, first_user_text, raw_text, tokens)
    tokens = { in, out, cache_read, cache_create, by_day: {date: {in,out,read,create}} }
    """
    messages = []
    cwd = ""
    first_user_text = ""
    raw_chunks = []
    tokens = {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0, "by_day": {}, "by_hour": [0]*24, "events": []}

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not cwd and obj.get("cwd"):
                    cwd = obj["cwd"]

                msg = obj.get("message")
                role = None
                text = ""
                usage = None

                if isinstance(msg, dict):
                    role = msg.get("role")
                    text = extract_text(msg.get("content"))
                    usage = msg.get("usage")
                elif obj.get("type") in ("user", "assistant"):
                    role = obj["type"]
                    text = extract_text(obj.get("content"))

                if role and text:
                    ts = obj.get("timestamp", "")
                    raw_content = msg.get("content") if isinstance(msg, dict) else obj.get("content")
                    atts = extract_attachments(raw_content)
                    blocks = extract_blocks(raw_content)
                    messages.append({
                        "role": role,
                        "text": text,
                        "ts": ts,
                        "blocks": blocks,
                        "attachments": atts,
                    })
                    if role == "user" and not first_user_text:
                        first_user_text = text[:200]
                    raw_chunks.append(text)

                # 累积 token (只 assistant 消息有 usage)
                if with_tokens and usage and isinstance(usage, dict):
                    inp = int(usage.get("input_tokens", 0) or 0)
                    out = int(usage.get("output_tokens", 0) or 0)
                    cread = int(usage.get("cache_read_input_tokens", 0) or 0)
                    ccreate = int(usage.get("cache_creation_input_tokens", 0) or 0)
                    tokens["in"] += inp
                    tokens["out"] += out
                    tokens["cache_read"] += cread
                    tokens["cache_create"] += ccreate

                    ts_str = obj.get("timestamp", "")
                    if ts_str:
                        try:
                            # ISO 格式: 2026-05-02T08:30:31.397Z
                            day = ts_str[:10]
                            hour = int(ts_str[11:13])
                            d = tokens["by_day"].setdefault(day, {"in":0,"out":0,"read":0,"create":0,"msgs":0})
                            d["in"] += inp; d["out"] += out
                            d["read"] += cread; d["create"] += ccreate
                            d["msgs"] += 1
                            if 0 <= hour < 24:
                                tokens["by_hour"][hour] += 1
                            # 精确事件(unix ts) 给滚动窗口算
                            from datetime import datetime
                            t_unix = datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()
                            tokens["events"].append((t_unix, inp, out, cread, ccreate))
                        except (ValueError, IndexError):
                            pass

    except Exception:
        return [], "", "", "", tokens

    return messages, cwd, first_user_text, "\n".join(raw_chunks), tokens


def build_index():
    """扫描全部 jsonl, 建索引 + 统计"""
    global _INDEX, _INDEX_TIME, _STATS
    print("[index] building...", flush=True)
    t0 = time.time()
    items = []

    daily = {}  # day -> {sessions, msgs, in, out, read, create}
    hourly = [0]*24
    project_agg = {}  # cwd -> {sessions, msgs, in, out}
    totals = {"sessions": 0, "msgs": 0, "in": 0, "out": 0, "cache_read": 0, "cache_create": 0}
    all_events = []  # (ts_unix, in, out, read, create)

    for p in ROOT.rglob("*.jsonl"):
        try:
            stat = p.stat()
        except OSError:
            continue
        messages, cwd, first_user, raw, tokens = parse_jsonl(p, with_tokens=True)
        if not messages:
            continue

        norm_cwd, is_worktree = normalize_cwd(cwd or "")
        items.append({
            "path": str(p.relative_to(ROOT)),
            "cwd": norm_cwd or "(未记录)",
            "raw_cwd": cwd or "",
            "is_worktree": is_worktree,
            "title": smart_title(first_user) or "(无文本)",
            "msg_count": len(messages),
            "mtime": stat.st_mtime,
            "ctime": stat.st_ctime,
            "size": stat.st_size,
            "tokens_in": tokens["in"],
            "tokens_out": tokens["out"],
            "tokens_cache_read": tokens["cache_read"],
            "search_blob": raw.lower(),
        })

        # 全局聚合
        totals["sessions"] += 1
        totals["msgs"] += len(messages)
        totals["in"] += tokens["in"]
        totals["out"] += tokens["out"]
        totals["cache_read"] += tokens["cache_read"]
        totals["cache_create"] += tokens["cache_create"]

        for h in range(24):
            hourly[h] += tokens["by_hour"][h]

        # 收集精确事件给滚动窗口
        all_events.extend(tokens["events"])

        for day, d in tokens["by_day"].items():
            agg = daily.setdefault(day, {"sessions": set(), "msgs": 0, "in": 0, "out": 0, "read": 0, "create": 0})
            agg["sessions"].add(str(p))
            agg["msgs"] += d["msgs"]
            agg["in"] += d["in"]; agg["out"] += d["out"]
            agg["read"] += d["read"]; agg["create"] += d["create"]

        # 项目聚合用规范化后的 cwd (worktree 合并到真实项目)
        ckey = norm_cwd or "(未记录)"
        pa = project_agg.setdefault(ckey, {"sessions": 0, "msgs": 0, "in": 0, "out": 0})
        pa["sessions"] += 1
        pa["msgs"] += len(messages)
        pa["in"] += tokens["in"]
        pa["out"] += tokens["out"]

    # 计算每日工作时长 (10 min 切段 → 累加段长 = work_seconds)
    from collections import defaultdict
    events_by_day = defaultdict(list)
    for ev in all_events:
        ts = ev[0]
        day_key = time.strftime('%Y-%m-%d', time.localtime(ts))
        events_by_day[day_key].append(ts)

    work_sec_by_day = {}
    SEG_GAP = 600  # 10 分钟
    for day_key, ts_list in events_by_day.items():
        ts_list.sort()
        if not ts_list:
            continue
        seg_start = ts_list[0]
        last = ts_list[0]
        total = 0
        for t in ts_list[1:]:
            if t - last > SEG_GAP:
                total += last - seg_start
                seg_start = t
            last = t
        total += last - seg_start
        # 每段额外加 +60 秒(单条消息也算 1 分钟基础)
        if total == 0:
            total = 60
        work_sec_by_day[day_key] = total

    # daily 转可序列化
    daily_list = []
    for day in sorted(daily.keys()):
        d = daily[day]
        daily_list.append({
            "day": day,
            "sessions": len(d["sessions"]),
            "msgs": d["msgs"],
            "in": d["in"], "out": d["out"],
            "cache_read": d["read"], "cache_create": d["create"],
            "work_seconds": work_sec_by_day.get(day, 0),
        })

    # 项目排行
    projects_top = sorted(
        [{"cwd": k, **v} for k, v in project_agg.items()],
        key=lambda x: x["msgs"], reverse=True
    )

    # 活跃天数
    active_days = len(daily)

    items.sort(key=lambda x: x["mtime"], reverse=True)

    # 滚动窗口预聚合 (只保留 7 天内的事件)
    now = time.time()
    cutoff = now - 7 * 86400
    recent_events = [e for e in all_events if e[0] >= cutoff]
    recent_events.sort(key=lambda e: e[0])

    with _INDEX_LOCK:
        _INDEX = items
        _STATS = {
            "totals": totals,
            "active_days": active_days,
            "daily": daily_list,
            "hourly": hourly,
            "projects": projects_top,
            "events_7d": recent_events,
            "generated_at": time.time(),
        }
        _INDEX_TIME = time.time()
    print(f"[index] {len(items)} sessions, {active_days} active days, "
          f"{totals['in']+totals['out']:,} non-cache tokens in {time.time()-t0:.1f}s", flush=True)


def get_index():
    if not _INDEX:
        build_index()
    return _INDEX


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Claude Code 历史浏览器</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
    background: #f7f8fa;
    color: #111827;
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }

  /* 顶部 */
  header {
    background: #fff;
    border-bottom: 1px solid #e5e7eb;
    padding: 14px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  header h1 {
    font-size: 15px;
    font-weight: 600;
    margin-right: 12px;
  }
  header .stat {
    font-size: 12px;
    color: #6b7280;
  }
  input, select {
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    font-family: inherit;
    color: #111827;
    background: #fff;
  }
  input:focus, select:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37,99,235,.1);
  }
  #q { flex: 1; min-width: 200px; }
  button {
    border: 1px solid #d1d5db;
    background: #fff;
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 13px;
    cursor: pointer;
    color: #374151;
  }
  button:hover { background: #f9fafb; }

  /* 主体 */
  main {
    display: grid;
    grid-template-columns: 380px 1fr;
    height: calc(100vh - 56px);
  }

  /* 列表 */
  .list {
    background: #fff;
    border-right: 1px solid #e5e7eb;
    overflow-y: auto;
  }
  .item {
    padding: 12px 16px;
    border-bottom: 1px solid #f3f4f6;
    cursor: pointer;
    transition: background 0.1s;
  }
  .item:hover { background: #f9fafb; }
  .item.active {
    background: #eff6ff;
    border-left: 3px solid #2563eb;
    padding-left: 13px;
  }
  .item .row1 {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: #6b7280;
    margin-bottom: 4px;
  }
  .item .row1 .date { font-weight: 500; }
  .item .row1 .count { background: #f3f4f6; padding: 1px 6px; border-radius: 8px; }
  .item .title {
    font-size: 13px;
    color: #111827;
    line-height: 1.45;
    margin-bottom: 4px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .item .cwd {
    font-size: 11px;
    color: #9ca3af;
    font-family: ui-monospace, Menlo, monospace;
    direction: rtl;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .item mark {
    background: #fef3c7;
    color: #b45309;
    padding: 0 2px;
    border-radius: 2px;
  }

  /* 详情 */
  .detail {
    overflow-y: auto;
    padding: 28px 32px;
  }
  .detail .meta {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 20px;
  }
  .detail .meta .field {
    display: grid;
    grid-template-columns: 60px 1fr;
    gap: 16px;
    font-size: 13px;
    padding: 4px 0;
  }
  .detail .meta .field b {
    color: #6b7280;
    font-weight: 500;
  }
  .detail .meta .field span {
    color: #111827;
    font-family: ui-monospace, Menlo, monospace;
    font-size: 12px;
    word-break: break-all;
  }

  .msg {
    margin-bottom: 16px;
    padding: 14px 18px;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    background: #fff;
  }
  .msg.user {
    background: #eff6ff;
    border-color: #dbeafe;
  }
  .msg.assistant {
    background: #fff;
  }
  .msg .role {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .msg.user .role { color: #2563eb; }
  .msg .text {
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 13.5px;
    line-height: 1.7;
    color: #1f2937;
  }
  .msg .ts {
    font-size: 11px;
    color: #9ca3af;
    margin-top: 8px;
    font-family: ui-monospace, Menlo, monospace;
  }
  .msg mark { background: #fef3c7; padding: 0 3px; border-radius: 2px; }

  .empty {
    color: #9ca3af;
    text-align: center;
    padding: 80px 20px;
    font-size: 14px;
  }
  .loading { padding: 20px; text-align: center; color: #9ca3af; }
</style>
</head>
<body>

<header>
  <h1>Claude Code 历史</h1>
  <input id="q" type="search" placeholder="搜索关键词(同时搜索标题和对话内容)…" autofocus>
  <select id="proj"><option value="">全部项目</option></select>
  <select id="range">
    <option value="">不限时间</option>
    <option value="1">近 1 天</option>
    <option value="7">近 7 天</option>
    <option value="30">近 30 天</option>
    <option value="90">近 90 天</option>
  </select>
  <button id="refresh">重建索引</button>
  <span class="stat" id="stat"></span>
</header>

<main>
  <div class="list" id="list"><div class="loading">加载中…</div></div>
  <div class="detail" id="detail"><div class="empty">从左侧选择一个会话查看完整对话</div></div>
</main>

<script>
let ALL = [];
let FILTERED = [];
let CURRENT = null;

const $q = document.getElementById('q');
const $proj = document.getElementById('proj');
const $range = document.getElementById('range');
const $list = document.getElementById('list');
const $detail = document.getElementById('detail');
const $stat = document.getElementById('stat');

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[m]));
}

function highlight(text, q) {
  if (!q) return escapeHtml(text);
  const safe = escapeHtml(text);
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  return safe.replace(re, m => `<mark>${m}</mark>`);
}

async function loadIndex() {
  $list.innerHTML = '<div class="loading">索引加载中…</div>';
  const r = await fetch('/api/index');
  ALL = await r.json();
  // 填充项目下拉
  const projects = [...new Set(ALL.map(s => s.cwd))].sort();
  $proj.innerHTML = '<option value="">全部项目 (' + projects.length + ')</option>' +
    projects.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
  applyFilter();
}

function applyFilter() {
  const q = $q.value.trim().toLowerCase();
  const proj = $proj.value;
  const range = parseInt($range.value, 10);
  const cutoff = range ? (Date.now()/1000 - range*86400) : 0;

  FILTERED = ALL.filter(s => {
    if (proj && s.cwd !== proj) return false;
    if (cutoff && s.mtime < cutoff) return false;
    if (q && !s.search_blob.includes(q) && !s.title.toLowerCase().includes(q)) return false;
    return true;
  });

  $stat.textContent = `${FILTERED.length} / ${ALL.length} 个会话`;
  renderList();
}

function fmtDate(ts) {
  const d = new Date(ts * 1000);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderList() {
  if (!FILTERED.length) {
    $list.innerHTML = '<div class="loading">无匹配会话</div>';
    return;
  }
  const q = $q.value.trim();
  $list.innerHTML = FILTERED.slice(0, 500).map(s => `
    <div class="item ${CURRENT===s.path?'active':''}" data-path="${escapeHtml(s.path)}">
      <div class="row1"><span class="date">${fmtDate(s.mtime)}</span><span class="count">${s.msg_count} 条</span></div>
      <div class="title">${highlight(s.title, q)}</div>
      <div class="cwd">${escapeHtml(s.cwd)}</div>
    </div>
  `).join('');
  $list.querySelectorAll('.item').forEach(el => {
    el.addEventListener('click', () => openSession(el.dataset.path));
  });
}

async function openSession(path) {
  CURRENT = path;
  renderList();
  $detail.innerHTML = '<div class="loading">读取会话…</div>';
  const r = await fetch('/api/session?path=' + encodeURIComponent(path));
  const data = await r.json();
  const q = $q.value.trim();

  const meta = ALL.find(s => s.path === path) || {};
  let html = `<div class="meta">
    <div class="field"><b>项目</b><span>${escapeHtml(meta.cwd||'')}</span></div>
    <div class="field"><b>会话</b><span>${escapeHtml(path)}</span></div>
    <div class="field"><b>消息</b><span>${data.messages.length} 条</span></div>
  </div>`;

  html += data.messages.map(m => `
    <div class="msg ${m.role}">
      <div class="role">${m.role}</div>
      <div class="text">${highlight(m.text, q)}</div>
      ${m.ts ? `<div class="ts">${escapeHtml(m.ts)}</div>` : ''}
    </div>
  `).join('');

  $detail.innerHTML = html;

  // 自动滚动到第一个高亮
  if (q) {
    const first = $detail.querySelector('mark');
    if (first) first.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

let debounce;
$q.addEventListener('input', () => {
  clearTimeout(debounce);
  debounce = setTimeout(applyFilter, 200);
});
$proj.addEventListener('change', applyFilter);
$range.addEventListener('change', applyFilter);
document.getElementById('refresh').addEventListener('click', async () => {
  $stat.textContent = '重建中…';
  await fetch('/api/rebuild', { method: 'POST' });
  await loadIndex();
});

loadIndex();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 让 Chrome/Safari 正确处理大文件下载(否则 HTTP/1.0 关连接被判网络错误)
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # 静默,避免刷屏
        pass

    def _no_cache(self):
        # 防浏览器缓存旧版 — 升级后用户不必硬刷新
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        # HTTP/1.1 下显式声明 close,避免 Chrome 等 keep-alive 超时
        self.send_header("Connection", "close")

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._no_cache()
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._no_cache()
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        if path == "/" or path == "/index.html":
            try:
                return self._html(HTML_FILE.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._html("<h1>UI 文件缺失</h1><p>history-ui.html 不存在</p>")

        if path == "/api/index":
            idx = get_index()
            return self._json(idx)

        if path == "/api/stats":
            if not _STATS:
                build_index()
            # events_7d 太大,/api/stats 不带它
            return self._json({k: v for k, v in _STATS.items() if k != "events_7d"})

        if path == "/api/usage":
            if not _STATS:
                build_index()
            events = _STATS.get("events_7d", [])
            now = time.time()

            # 5h session 滚动窗口,按 15 分钟分桶 = 20 桶
            sess_start = now - 5 * 3600
            sess_buckets = [[0,0,0,0] for _ in range(20)]
            sess_total = [0,0,0,0]
            for ts, ti, to, tr, tc in events:
                if ts < sess_start: continue
                idx = min(19, int((ts - sess_start) // 900))
                sess_buckets[idx][0] += ti; sess_buckets[idx][1] += to
                sess_buckets[idx][2] += tr; sess_buckets[idx][3] += tc
                sess_total[0] += ti; sess_total[1] += to
                sess_total[2] += tr; sess_total[3] += tc

            # 7d weekly 滚动窗口,按小时分桶 = 168 桶
            week_start = now - 7 * 86400
            week_buckets = [[0,0,0,0] for _ in range(168)]
            week_total = [0,0,0,0]
            for ts, ti, to, tr, tc in events:
                if ts < week_start: continue
                idx = min(167, int((ts - week_start) // 3600))
                week_buckets[idx][0] += ti; week_buckets[idx][1] += to
                week_buckets[idx][2] += tr; week_buckets[idx][3] += tc
                week_total[0] += ti; week_total[1] += to
                week_total[2] += tr; week_total[3] += tc

            def keys(totals):
                return {"in": totals[0], "out": totals[1], "read": totals[2], "create": totals[3]}

            return self._json({
                "now": now,
                "session_5h": {
                    "window_seconds": 5*3600,
                    "bucket_seconds": 900,
                    "buckets": [keys(b) for b in sess_buckets],
                    "total": keys(sess_total),
                },
                "weekly_7d": {
                    "window_seconds": 7*86400,
                    "bucket_seconds": 3600,
                    "buckets": [keys(b) for b in week_buckets],
                    "total": keys(week_total),
                },
            })

        if path == "/stats" or path == "/stats.html":
            try:
                return self._html(STATS_HTML_FILE.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._html("<h1>Stats UI 缺失</h1>")

        if path == "/safety" or path == "/safety.html":
            try:
                return self._html(SAFETY_HTML_FILE.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._html("<h1>Safety UI 缺失</h1>")

        if path == "/health" or path == "/health.html":
            try:
                return self._html((Path(__file__).parent / "history-health.html").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._html("<h1>Health UI 缺失</h1>")

        if path == "/budget" or path == "/budget.html":
            try:
                return self._html((Path(__file__).parent / "history-budget.html").read_text(encoding="utf-8"))
            except FileNotFoundError:
                return self._html("<h1>Budget UI 缺失</h1>")

        if path == "/api/export":
            rel = qs.get("path", [""])[0]
            if not rel:
                return self._json({"error": "path required"}, 400)
            full = ROOT / rel
            try:
                full.resolve().relative_to(ROOT.resolve())
            except ValueError:
                return self._json({"error": "invalid path"}, 400)
            if not full.exists():
                return self._json({"error": "not found"}, 404)

            messages, cwd, first_user, _, _ = parse_jsonl(full)
            sid = full.stem
            atts = set()
            for m in messages:
                for a in m.get("attachments") or []:
                    atts.add(a)

            lines = []
            title = (first_user or "(会话)").split("\n")[0][:80]
            lines.append(f"# {title}")
            lines.append("")
            lines.append(f"- 项目: `{cwd}`")
            lines.append(f"- 会话 ID: `{sid}`")
            lines.append(f"- 消息数: {len(messages)}")
            lines.append(f"- jsonl: `~/.claude/projects/{rel}`")
            lines.append("")

            if atts:
                lines.append(f"## 涉及文件 ({len(atts)})")
                lines.append("")
                for a in sorted(atts):
                    lines.append(f"- `{a}`")
                lines.append("")

            lines.append("## 对话内容")
            lines.append("")
            lines.append("> 注: **🧑 用户** 是用户消息(原 UI 中蓝色),**🤖 助手** 是 AI 回复(原 UI 中白底黑字)")
            lines.append("")

            for m in messages:
                role = m.get("role", "")
                text = (m.get("text") or "").strip()
                if not text:
                    continue
                ts = m.get("ts", "")
                ts_short = ts[:16].replace("T", " ") if ts else ""
                if role == "user":
                    lines.append(f"### 🧑 用户  {ts_short}")
                    lines.append("")
                    for ln in text.split("\n"):
                        lines.append(f"> {ln}")
                    lines.append("")
                elif role == "assistant":
                    lines.append(f"### 🤖 助手  {ts_short}")
                    lines.append("")
                    lines.append(text)
                    lines.append("")
                lines.append("---")
                lines.append("")

            body = ("\n".join(lines)).encode("utf-8")
            download = qs.get("download", [""])[0] == "1"
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if download:
                fn = qs.get("fn", [""])[0]
                if not fn:
                    fn = f"ccpal-{sid}.md"
                # 安全:仅允许常见字符
                fn = re.sub(r'[^\w一-龥\-\.\(\)]+', '-', fn)
                if not fn.endswith('.md'):
                    fn += '.md'
                # ASCII fallback + UTF-8 encoded for filename*
                ascii_fn = re.sub(r'[^\w\-\.]', '_', fn)
                from urllib.parse import quote as _q
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{ascii_fn}"; filename*=UTF-8\'\'{_q(fn)}'
                )
            self._no_cache()
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/open":
            target = qs.get("path", [""])[0]
            mode = qs.get("mode", ["file"])[0]  # "file" or "reveal"
            if not target:
                return self._json({"error": "path required"}, 400)
            try:
                p = Path(target).expanduser()
            except Exception:
                return self._json({"error": "bad path"}, 400)
            if not p.exists():
                return self._json({"error": "not found", "path": str(p)}, 404)
            try:
                if mode == "reveal":
                    subprocess.run(["open", "-R", str(p)], check=False)
                else:
                    subprocess.run(["open", str(p)], check=False)
                return self._json({"ok": True, "path": str(p)})
            except Exception as e:
                return self._json({"error": str(e)}, 500)

        if path == "/api/session":
            rel = qs.get("path", [""])[0]
            if not rel:
                return self._json({"error": "path required"}, 400)
            full = ROOT / rel
            try:
                full.resolve().relative_to(ROOT.resolve())
            except ValueError:
                return self._json({"error": "invalid path"}, 400)
            if not full.exists():
                return self._json({"error": "not found"}, 404)
            messages, cwd, _, _, _ = parse_jsonl(full)
            return self._json({"cwd": cwd, "messages": messages})

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/rebuild":
            build_index()
            return self._json({"ok": True, "count": len(_INDEX)})
        self.send_response(404)
        self.end_headers()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    print(f"[boot] indexing {ROOT}...", flush=True)
    build_index()
    with Server((HOST, PORT), Handler) as srv:
        url = f"http://{HOST}:{PORT}"
        print(f"[boot] http {url}  ({len(_INDEX)} sessions)", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[bye]")


if __name__ == "__main__":
    main()
