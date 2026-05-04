# CCPal

> macOS-only · 让本机 Claude Code 对话**永久保留 + 浏览器可视化检索** · 三层备份 · 零云端

CCPal 把 Claude Code 的本地对话（`~/.claude/projects/*.jsonl`）做成可浏览、可搜索、可统计的 web UI，并通过 launchd 自动做 git snapshot + rsync 镜像，保证对话永远不丢。

未来目标是做成一个 plugin，让 **Claude Code、Codex、OpenCode** 三家 CLI 都能一键调出同一个历史浏览器。

---

## 目录结构

```
.
├── core/                            # 核心组件（与宿主无关）
│   ├── scripts/                     # 部署到 ~/.claude/scripts/
│   │   ├── history-server.py        # 本地 HTTP 服务（:8765）
│   │   ├── history-*.html           # 6 个 web UI 页面
│   │   ├── start-history.sh         # 启动 server
│   │   ├── daily-snapshot.sh        # git commit ~/.claude/projects
│   │   ├── backup-mirror.sh         # rsync + git mirror 到 ~/CCPal-Backup
│   │   ├── search-chats.sh          # CLI 全文搜索
│   │   ├── ccpal-doctor.sh          # 23 项自检 + 幂等修复
│   │   └── PREREQ.md                # 给最终用户看的说明
│   └── LaunchAgents/                # 部署到 ~/Library/LaunchAgents/
│       ├── com.claude.daily-snapshot.plist    # 每天 03:00
│       └── com.claude.backup-mirror.plist     # 每天 03:30
│
├── hosts/                           # 三家 CLI 的 plugin 入口（待开发）
│   ├── claude-code/                 # .claude-plugin/ + slash commands + hooks
│   ├── codex/                       # MCP server
│   └── opencode/                    # opencode plugin manifest + commands
│
└── installer/
    └── legacy/                      # 旧的"丢给 AI 装"HTML 安装器
        ├── 请安装这个项目CCPal-install v4.1.html
        └── extract.py               # 把 HTML 里的 base64 解出到 src/
```

---

## 路线图

| Phase | 内容 | 状态 |
|---|---|---|
| 1a | 拆出 `core/` + `hosts/` 骨架 + git init | ✅ |
| 1b | Claude Code plugin（`.claude-plugin/` + `/ccpal` 命令 + Stop hook + bootstrap install.sh） | ✅ |
| 1c | 把 `core/` bundle 进 plugin（解除 git-subdir 对父目录依赖） | ✅ |
| 1d | 推 GitHub + 真实环境验证 marketplace 流程（需要 Claude Code CLI 而非 Desktop） | ⏳ |
| 2  | Codex MCP server（`ccpal-mcp.py` 5 tool · `codex mcp add` 注册） | ✅ |
| 2.1 | （废弃）尝试用 plugin/marketplace 注册 — Codex Desktop 不读用户 marketplace | 🪦 |
| 2.2 | install.sh 砍到 3 步，走 `codex mcp add` | ✅ 当前 |
| 2.3 | 给 search_sessions / recent_sessions 加凭证脱敏（密码/API key 正则打码） | ⏳ |
| 3  | OpenCode plugin（slash 命令 + 共享 MCP） | ⏳ |

### Codex usage（已工作）

```bash
# 一键安装（前提：Claude Code plugin 的 install.sh 已跑过，core 已部署）
bash hosts/codex/install.sh

# Cmd+Q Codex Desktop 完全退出，重新打开
# 模型在 Codex 里自动看到 5 个 tool：
#   mcp__ccpal__open_ui
#   mcp__ccpal__recent_sessions
#   mcp__ccpal__search_sessions
#   mcp__ccpal__get_session_text
#   mcp__ccpal__stats
```

**关键发现**：Codex Desktop 完全忽略用户手写的 `[mcp_servers.X]` / `[marketplaces.X]` 块；唯一的注册路径是 CLI 子命令 `codex mcp add`。app.asar 反编译后确认 Electron 层只把 BundledPluginsMarketplace 喂给 Rust core，用户 marketplace 没有 mount 路径。

### Dev workflow

`core/` 是单一来源。每个 host plugin 的 `core/` 子目录是 bundle 副本（让 plugin 自洽分发）。改完 core 后**必须 sync**:

```bash
# 1. 编辑 core/ 下任何文件
vim core/scripts/history-server.py

# 2. 同步到所有 hosts/<name>/core/
bash dev/sync-core.sh

# 3. git add 两边
git add core hosts/*/core
git commit -m "..."
```

不要直接编辑 `hosts/<name>/core/` —— 下次 sync 会被覆盖。

### Claude Code plugin 用法（开发中）

```bash
# 在 Claude Code 里把仓库根当 marketplace 加进来
/plugin marketplace add /Users/lujinian/Documents/workspace/claudcode/mem

# 装上
/plugin install ccpal@ccpal-marketplace

# 用
/ccpal install      # 首次：把 core/ 部署到 ~/.claude/scripts/ + 加载 launchd
/ccpal              # 默认：打开 http://127.0.0.1:8765
/ccpal search 关键词
/ccpal doctor
/ccpal status
```

---

## 当前可用方式（Phase 0，沿用旧版）

把 `installer/legacy/请安装这个项目CCPal-install v4.1.html` 给 Claude Code，说"装一下"。Claude 会做环境预检，确认后一次跑完 11 步部署，启动 `http://127.0.0.1:8765`。

详见该 HTML 文件顶部的 `CCPAL_INSTALL_INSTRUCTIONS` 块。

---

## 平台

**macOS only**。依赖 `launchd`、`~/Library/LaunchAgents/`、`bash`、`rsync`、`open` 等 macOS 原生设施。Windows/Linux 不在当前 scope。
