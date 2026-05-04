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
| 1a | 拆出 `core/` + `hosts/` 骨架 + git init | ✅ 当前 |
| 1b | Claude Code plugin（`.claude-plugin/` + `/ccpal` 命令 + Stop hook） | ⏳ |
| 1c | `install.sh`（替代 HTML 安装器，curl 一行装） | ⏳ |
| 2  | Codex MCP server（`open_ui` / `search` / `stats` tools） | ⏳ |
| 3  | OpenCode plugin（slash 命令 + 共享 MCP） | ⏳ |

---

## 当前可用方式（Phase 0，沿用旧版）

把 `installer/legacy/请安装这个项目CCPal-install v4.1.html` 给 Claude Code，说"装一下"。Claude 会做环境预检，确认后一次跑完 11 步部署，启动 `http://127.0.0.1:8765`。

详见该 HTML 文件顶部的 `CCPAL_INSTALL_INSTRUCTIONS` 块。

---

## 平台

**macOS only**。依赖 `launchd`、`~/Library/LaunchAgents/`、`bash`、`rsync`、`open` 等 macOS 原生设施。Windows/Linux 不在当前 scope。
