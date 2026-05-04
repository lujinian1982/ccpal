# CCPal

> **C**laude **C**ode **Pal** · macOS-only · 让你的 Claude Code 对话**永久保留 + 可视化检索 + 跨工具读取** · 全本地零云端

---

## TL;DR · 30 秒看懂

- **问题**:Claude Code 默认 30 天清理你的本地对话(`~/.claude/projects/*.jsonl`),清掉就再也回不来
- **CCPal 做的事**:
  1. 把保留期改成"永不清理"
  2. 每天 03:00 自动 `git commit` 一次,03:30 异地 `rsync` 镜像到 `~/CCPal-Backup/`
  3. 起一个本地浏览器(`http://127.0.0.1:8765`),让你用 markdown 可视化看每段对话、全文搜索、查统计/健康/Token 用量
  4. 把同样的能力做成 **MCP 工具**,让 **Codex / OpenCode / 其他 Claude Code 实例** 也能读到你的 Claude 历史
- **数据始终在你本机**,从不上传任何云

---

## 它解决的真实痛点

你大概遇到过这些场景:

| 场景 | 没 CCPal | 有 CCPal |
|---|---|---|
| 上周跟 Claude 讨论的 X 方案,具体怎么写来着 | 翻 IDE 历史,翻不到 | 浏览器搜 "X" 5 秒命中 |
| 打算换个 model / 换个对话续做,context 丢失 | 重新解释一遍,慢 | 一键导出 markdown,粘到新对话 |
| Claude Code 默认 30 天清理 | 老对话静默消失 | `cleanupPeriodDays = ∞`,永不清 |
| 笔记本硬盘出问题 | 全没了 | 异地镜像还在 `~/CCPal-Backup/` |
| 在 Codex 里干活,想引用之前 Claude Code 的讨论 | 来回切窗口翻 | Codex 里 model 直接调 `mcp__ccpal__search_sessions` 拿到 |
| 想知道我用 Claude Code 用了多少 Token / 多少天 | 没数 | `/stats` 页一眼看到:45 sessions · 13K msgs · 20 active days |

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   你跟 Claude Code 对话                                                   │
│         │                                                                │
│         ▼                                                                │
│   ① 原始 jsonl                                                          │
│   ~/.claude/projects/<project>/<session-uuid>.jsonl                     │
│   (Claude Code 实时追加写,每条 user/assistant 一行 JSON)                │
│         │                                                                │
│         ├──── CCPal 改 settings.json: cleanupPeriodDays = ∞ ────►  永不清理 │
│         │                                                                │
│         ├──── ② 03:00 launchd → daily-snapshot.sh ────►  git commit      │
│         │     ~/.claude/projects/.git/  (同盘版本史)                      │
│         │                                                                │
│         └──── ③ 03:30 launchd → backup-mirror.sh ────►  rsync + git mirror │
│               ~/CCPal-Backup/  (异地全量副本)                             │
│                                                                          │
│   读取/浏览/搜索 通道:                                                    │
│         │                                                                │
│         ├──── history-server.py 读 ~/.claude/projects/                  │
│         │     → http://127.0.0.1:8765   (浏览器 6 个页面)                │
│         │                                                                │
│         └──── ccpal-mcp.py(5 个 MCP tool)                              │
│               → Claude Code · Codex · OpenCode (Phase 3)                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 三层备份的物理位置

| 层级 | 物理路径 | 数据 | 谁写 | 频率 |
|---|---|---|---|---|
| ① **原文件** | `~/.claude/projects/` | jsonl 全集(用户对话原文) | Claude Code 自己 | 实时(每条对话即时落盘) |
| ② **同盘 git** | `~/.claude/projects/.git/` | 累积 commit 历史 | CCPal `daily-snapshot.sh` | 每天 03:00 |
| ③ **异地镜像** | `~/CCPal-Backup/` | rsync 副本 + git --mirror + manifest.json | CCPal `backup-mirror.sh` | 每天 03:30 |

`~/CCPal-Backup/manifest.json` 长这样,可以拿来确认上次备份何时跑、跑了多少:

```json
{
  "last_run": "2026-05-04T05:09:48-07:00",
  "source": "/Users/<you>/.claude/projects",
  "destination": "/Users/<you>/CCPal-Backup",
  "jsonl_count": 46,
  "total_size": "107M",
  "policy": "rsync incremental, no delete on dest; git-mirror full history"
}
```

> **想再加一层云端备份**?把 `~/CCPal-Backup/` 放进 iCloud Drive / Dropbox / Time Machine / 你的 NAS 都行。CCPal 不强制走云,留给你自己选。

---

## 跨工具读取(MCP)

同一份 Claude Code 数据,通过 `core/scripts/ccpal-mcp.py`(基于 [FastMCP](https://github.com/modelcontextprotocol/python-sdk))暴露成 5 个 MCP 工具:

| Tool | 干嘛 | 在 Claude Code/Codex/OpenCode 里看到的工具名 |
|---|---|---|
| `open_ui` | 启动本地 server,返回 URL | `mcp__ccpal__open_ui` |
| `recent_sessions(limit)` | 最近 N 个会话(标题/项目/消息数) | `mcp__ccpal__recent_sessions` |
| `search_sessions(query, limit)` | 按标题 + 项目路径子串搜索 | `mcp__ccpal__search_sessions` |
| `get_session_text(path)` | 整段对话 markdown(model 可直接读) | `mcp__ccpal__get_session_text` |
| `stats()` | 用量摘要(sessions / messages / tokens / 活跃天数) | `mcp__ccpal__stats` |

**典型 model 自动调用场景**(无需用户主动 `@`):

> 在 Codex 里你说: *"我之前跟 Claude Code 聊过 polymarket 套利,把那段找出来给我"*
>
> Codex model 自动:
> 1. 调 `mcp__ccpal__search_sessions(query="polymarket")` → 拿到匹配列表
> 2. 调 `mcp__ccpal__get_session_text(path=...)` → 拿到完整对话
> 3. 总结/引用给你

每次第一次调用某 tool,host 会弹权限确认("allow ccpal to call X?"),允许一次或永久允许。

---

## 安装

### 前置要求

- macOS(用了 launchd / `~/Library/LaunchAgents/` / `open(1)` / `rsync`)
- Python 3.7+
- git
- bash + curl + launchctl(macOS 自带)

不需要的:Homebrew(可选,缺 `jq` 时 settings.json 合并会跳过,有也行)、Node、任何包管理器、任何云账号。

### 一键装(推荐 · Phase 1b/2.2)

把这个仓库 clone 下来:

```bash
git clone https://github.com/lujinian1982/ccpal.git
cd ccpal

# Step 1: 装 core(history-server + 6 个 UI 页面 + 2 个 launchd 任务)
bash hosts/claude-code/scripts/install.sh

# Step 2(可选,要让 Codex 也能读你的 Claude 历史):装 Codex 桥
bash hosts/codex/install.sh
# 然后 Cmd+Q Codex Desktop 完全退出再重开
```

装完会自动:
- `mkdir -p ~/.claude/scripts ~/.claude/logs ~/Library/LaunchAgents ~/CCPal-Backup`
- 部署 13 个文件到 `~/.claude/scripts/`(脚本 + 6 个 UI HTML + Python MCP server)
- 部署 2 个 plist 到 `~/Library/LaunchAgents/` 并 `launchctl load`(03:00 / 03:30 自动跑)
- 合并 `~/.claude/settings.json`(只加 8 个键,不动其他配置)
- 在 `~/.claude/projects/` 跑 `git init`(如果还不是 git 仓)
- 跑一次 `daily-snapshot.sh` 做首次 commit
- 后台跑 `backup-mirror.sh` 做首次镜像
- 启动 `http://127.0.0.1:8765` 并自动 `open` 浏览器
- 跑 23 项自检 `ccpal-doctor.sh`,期望输出 `✓ 正常 23  ⚙ 自动修复 0  ⚠ 警告 0  ✗ 错误 0`

### 旧版"丢 HTML 给 AI 装"(也仍然可用)

`installer/legacy/请安装这个项目CCPal-install v4.1.html` 是 v4.1 时代的安装包 —— 把这个 HTML 丢给 Claude Code 说一句"装一下",Claude 会读文件顶部的 `CCPAL_INSTALL_INSTRUCTIONS` 指令,做环境预检,确认后跑完 11 步部署。功能跟一键装等价,只是不需要 clone repo。

---

## 日常使用

### 1. 浏览器 UI

打开 **http://127.0.0.1:8765**,6 个页面:

| 页面 | 干啥 |
|---|---|
| **主页** `/` | 项目层级浏览 / 全局搜索 / 附件清单 / 完整 markdown 渲染对话 / 一键 "导入到新对话"(下载 md + 复制提示语) |
| **统计** `/stats` | 总 sessions/messages/tokens · 30 天趋势图 · 项目排行 |
| **健康** `/health` | 工作节律图(每日消息数 + 工作时长 10 分钟切段) + 共情提醒 |
| **套餐** `/budget` | 5h session 滚动窗口 + 7d weekly 滚动 Token 用量 |
| **数据安全** `/safety` | 三层备份路径清单 + 防删机制说明 + 复制方法 |

### 2. CLI 终端搜索

```bash
# 在所有 jsonl 里 grep
~/.claude/scripts/search-chats.sh "polymarket"

# 输出按时间倒序,每条带:时间 / 项目路径 / 标题 / 命中片段
```

### 3. MCP(Codex / OpenCode)

装完 `hosts/codex/install.sh` 后,在 Codex 任意对话里直接说自然语言即可,如:

```
"列出我最近 5 次 Claude Code 对话"
"找一下我跟 Claude Code 讨论过 Polymarket 的对话"
"打开我的 Claude Code 历史浏览器"
"我用 Claude Code 多少天了?"
```

Model 自动选合适的 `mcp__ccpal__*` 工具调。

### 4. 自检 / 修复

什么时候用:升级了 macOS / 觉得哪里不对劲 / launchd 没跑 / 想确认 server 还活着:

```bash
bash ~/.claude/scripts/ccpal-doctor.sh
```

23 项自动检查 + 缺啥自动补啥(创建目录、chmod、reload launchd、启动 server、git init projects 等)。完整输出会告诉你 ✓ 正常 / ⚙ 自动修复 / ⚠ 警告 / ✗ 错误 各多少。

---

## 安装后会动到的所有东西(完整清单)

| 路径 | 干啥 | 删除方法(完整卸载) |
|---|---|---|
| `~/.claude/scripts/{daily-snapshot,backup-mirror,search-chats,start-history,ccpal-doctor}.sh` | shell 脚本 | `rm` 这些文件 |
| `~/.claude/scripts/history-server.py` | Web UI 服务器 | `rm` |
| `~/.claude/scripts/history-{ui,stats,health,budget,safety}.html` | 6 个 UI 页面 | `rm` |
| `~/.claude/scripts/ccpal-mcp.py` | MCP server(Phase 2 新增) | `rm` |
| `~/.claude/scripts/PREREQ.md` | 给最终用户的说明 | `rm` |
| `~/.claude/logs/*.log` | server / snapshot / mirror 的日志 | `rm` |
| `~/Library/LaunchAgents/com.claude.{daily-snapshot,backup-mirror}.plist` | launchd 任务 | `launchctl unload <plist>; rm <plist>` |
| `~/.claude/projects/.git/` | 同盘 git 版本史 | `rm -rf ~/.claude/projects/.git`(jsonl 不动) |
| `~/.claude/settings.json` 增加 8 个键 | `cleanupPeriodDays` 等 | 用编辑器删那 8 行(其他配置保留) |
| `~/CCPal-Backup/` | 异地镜像目录 | `rm -rf ~/CCPal-Backup` |
| `~/.codex/config.toml` 末尾 5 行 `[mcp_servers.ccpal]` | Codex MCP 注册(可选) | `/Applications/Codex.app/Contents/Resources/codex mcp remove ccpal` |

**永远不会动**的东西:`~/.claude/projects/<project>/*.jsonl`(对话原文)、Claude Code 应用本身、其他 `~/.claude/` 子目录的内容(`backups/`, `plans/`, `sessions/`, `telemetry/` 等)。

---

## 数据安全 / 隐私

- **零云端**:CCPal 不调任何外部 API,不上传任何数据。所有进程都跑在 `127.0.0.1`(回环地址,网络外面访问不到)。
- **server 只 listen `127.0.0.1:8765`**,在 `history-server.py` 里硬编码,不能从局域网访问。
- **路径白名单**:web API 严格校验所有 `path` 参数必须在 `~/.claude/projects/` 下,无法越界读其他文件。
- **MCP tool 通过同一个 server**,继承同样的路径检查。
- **launchd 任务以你自己的用户身份跑**,无 sudo / root。

⚠ **已知风险**([Phase 2.3](#路线图--开发状态) 待修):`recent_sessions` 和 `search_sessions` 当前返回的 `title` 字段是会话第一条 user message 的截断 —— 如果你曾经在 Claude Code 里**直接打过密码 / API key / SSH 凭证**,这些会被当作普通文本暴露给所有连接 ccpal 的 MCP client。计划加正则脱敏层。在那之前,**别在 Claude Code 里直接贴敏感凭证**,或者卸载 Codex 那条桥。

---

## 路线图 / 开发状态

| Phase | 内容 | 状态 |
|---|---|---|
| 1a | 拆出 `core/` + `hosts/` 骨架 + git init | ✅ |
| 1b | Claude Code plugin(`/ccpal` 命令 + Stop hook + bootstrap install.sh) | ✅ |
| 1c | 把 `core/` bundle 进 plugin(让 plugin 自洽分发) | ✅ |
| 1d | 推 GitHub + 真实环境验证 marketplace 流程(需要 Claude Code CLI 而非 Desktop) | ⏳ |
| 2  | Codex MCP server(5 tool · `codex mcp add` 注册) | ✅ |
| 2.1 | (废弃)尝试用 plugin/marketplace 注册 — Codex Desktop 不读用户 marketplace | 🪦 |
| 2.2 | install.sh 砍到 3 步,走 `codex mcp add` | ✅ |
| 2.3 | 给 search_sessions / recent_sessions 加凭证脱敏 | ⏳ |
| 3  | OpenCode plugin(slash 命令 + 共享 MCP) | ⏳ |
| 4  | 多源 ingestion(同时读 Codex `~/.codex/sessions/` 和 OpenCode 的会话文件) | ⏳(用户表达过需求) |

---

## 仓库结构

```
.
├── README.md                              ← 本文件(给人看)
├── AGENTS.md                              ← 给 AI 看的操作手册(跨工具约定)
├── .claude-plugin/marketplace.json        ← Claude Code marketplace 入口
│
├── core/                                  ← 单一来源,与宿主无关
│   ├── scripts/
│   │   ├── history-server.py              # localhost:8765 HTTP server
│   │   ├── history-{ui,stats,health,budget,safety}.html
│   │   ├── start-history.sh
│   │   ├── daily-snapshot.sh              # launchd 03:00 跑
│   │   ├── backup-mirror.sh               # launchd 03:30 跑
│   │   ├── search-chats.sh                # CLI 搜索
│   │   ├── ccpal-doctor.sh                # 23 项自检
│   │   ├── ccpal-mcp.py                   # 5 个 MCP tool
│   │   └── PREREQ.md
│   └── LaunchAgents/
│       ├── com.claude.daily-snapshot.plist
│       └── com.claude.backup-mirror.plist
│
├── hosts/
│   ├── claude-code/                       ✅ Phase 1b/1c 完整
│   │   ├── .claude-plugin/plugin.json
│   │   ├── commands/ccpal.md              # /ccpal [open|search|doctor|install|status]
│   │   ├── hooks/hooks.json               # Stop hook → daily-snapshot.sh
│   │   ├── scripts/install.sh             # core 部署器
│   │   └── core/                          # bundled 副本(由 dev/sync-core.sh 维护)
│   │
│   ├── codex/                             ✅ Phase 2.2 完整
│   │   ├── install.sh                     # pip + cp + codex mcp add
│   │   └── requirements.txt               # mcp>=1.0
│   │
│   └── opencode/                          ⏳ Phase 3 占位
│
├── dev/sync-core.sh                       ← 编辑 core/ 后必跑
│
└── installer/legacy/                      ← v4.1 HTML 安装器(沿用至今仍可用)
    ├── 请安装这个项目CCPal-install v4.1.html
    └── extract.py
```

---

## 二次开发

### Dev workflow

`core/` 是单一来源。每个 host plugin 的 `core/` 子目录是 bundled 副本(让 plugin 通过 marketplace / git-subdir / 压缩包分发时自洽)。改完 core 之后**必须 sync**:

```bash
# 1. 编辑 core/ 下任何文件
$EDITOR core/scripts/history-server.py

# 2. 同步到所有 hosts/<name>/core/
bash dev/sync-core.sh

# 3. git add 双方都提交
git add core hosts/*/core
git commit -m "..."
```

不要直接编辑 `hosts/<name>/core/` —— 下次 sync 会被覆盖。`dev/sync-core.sh` 只往**已经有 `.claude-plugin/plugin.json`** 的 host 里同步,所以 codex/ 和 opencode/ 占位目录会被自动跳过。

### 添加一个新 host plugin

`AGENTS.md §5` 有完整 recipe。简短版:

1. 调研目标 host 的 MCP / plugin 注册路径(读它的源码,**别只信文档**)
2. 在 `hosts/<name>/` 下放 `install.sh` + 必要的 manifest
3. 复用 `core/scripts/ccpal-mcp.py` 不要重写,需要包装就在 plugin dir 里加个 wrapper shell 调它
4. 端到端 MCP `initialize` + `tools/list` 握手测试
5. 在真实 host 里让 model 自动调一次工具

---

## 设计/取舍说明

- **macOS only**:依赖 launchd。Linux 要换 systemd / cron,Windows 要换 Task Scheduler + PowerShell —— 工程预算不值得(~5% 用户),也会让 Claude Code 用户最关心的"03:00 自动备份"在那两个平台上做得不完整反而被吐槽。
- **数据源只锁 Claude Code**:不读 Codex / OpenCode 自己的会话文件(它们格式各异,各自有官方 UI 看)。**反方向**(Claude Code 里读 Codex 历史)等 Phase 4 决定。
- **不做云同步**:本地优先。备份目录 `~/CCPal-Backup/` 你想云就自己挂 iCloud / Dropbox / NAS,工具不替你决定。
- **不写新 jsonl**:CCPal 是只读 + 备份,绝不修改 Claude Code 的对话原文。`~/.claude/projects/` 下面唯一 CCPal 加的东西是 `.git/` 子目录。

---

## 致谢

CCPal 是 [@lujinian](https://github.com/lujinian1982) 的个人工具,日常吃自己的狗粮。

如果你也在用,issue / PR 欢迎,但不承诺响应速度 —— 工程预算优先用在让自己更顺手的地方。

---

## License

MIT
