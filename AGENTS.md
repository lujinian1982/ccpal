# AGENTS.md

> Operating manual for AI assistants working on this repo. Read this **first**
> before making changes. The patterns and gotchas here were learned the hard
> way (multiple wasted reverse-engineering passes); honoring them saves hours.

---

## 1. Mission

**CCPal** makes the user's local Claude Code conversation history
(`~/.claude/projects/*.jsonl`) **permanent + browsable + searchable**, with
**zero cloud**. It bundles:

- a Python `history-server.py` serving a local web UI at
  `http://127.0.0.1:8765` (browse / search / stats / health / budget /
  data-safety pages)
- two **launchd** jobs that auto-snapshot the jsonl tree and rsync-mirror it
  off-disk daily
- a CLI `search-chats.sh` for terminal-side full-text search
- an idempotent `ccpal-doctor.sh` that self-checks 23 invariants

The product goal is to expose the same browser/search surface from **three
host CLIs** — Claude Code, Codex, OpenCode — so the user's history is
reachable wherever they're working. Each host gets a thin plugin in
`hosts/<name>/`; the heavy logic lives in shared `core/`.

**Scope locks (do not relitigate):**
- **macOS-only.** launchd, `~/Library/LaunchAgents`, `open(1)`, `rsync`,
  hard-coded `~/Library` paths. Cross-platform was explicitly considered
  and declined. Don't propose Linux/Windows ports.
- **Single data source = `~/.claude/projects/`.** Do not write Codex /
  OpenCode session-format adapters. The user wants their *Claude Code*
  history reachable from the other CLIs, not unified history across all
  tools.

---

## 2. Current state

```
phase     status   notes
────────  ──────   ─────────────────────────────────────────────────────────
1a        ✅       repo skeleton, git init
1b        ✅       Claude Code plugin (commands/ccpal.md + Stop hook + install.sh)
1c        ✅       core/ bundled into hosts/claude-code/core/ (self-contained)
1d        ⏳       publish to GitHub + verify marketplace flow (needs CC CLI, not Desktop)
2         ✅       Codex MCP server (5 tools), end-to-end verified by user 2026-05-04
2.1       🪦       (dead-end) tried plugin/marketplace registration — Codex Desktop won't mount user marketplaces
2.2       ✅       install.sh stripped to 3 steps using `codex mcp add`
2.3       ⏳       credential scrubbing in MCP tool outputs
3         ⏳       OpenCode plugin (TBD — likely MCP-via-opencode.json)
```

The single most consequential learning: **Codex Desktop ignores hand-edited
`[mcp_servers.*]` and `[marketplaces.*]` blocks**. See §6.

---

## 3. Architecture

```
.
├── AGENTS.md                              ← you are here
├── README.md                              ← user-facing roadmap
│
├── .claude-plugin/marketplace.json        ← Claude Code marketplace, lists `ccpal`
│
├── core/                                  ← single source of truth, host-agnostic
│   ├── scripts/
│   │   ├── history-server.py              ← localhost:8765 HTTP server (~1100 lines)
│   │   ├── history-{ui,stats,health,budget,safety}.html  ← 6 web UI pages
│   │   ├── start-history.sh               ← spawns history-server in background
│   │   ├── daily-snapshot.sh              ← `git commit ~/.claude/projects` (launchd 03:00)
│   │   ├── backup-mirror.sh               ← rsync + git mirror (launchd 03:30)
│   │   ├── search-chats.sh                ← CLI grep over jsonl
│   │   ├── ccpal-doctor.sh                ← 23-item self-check + idempotent fix
│   │   ├── ccpal-mcp.py                   ← FastMCP server (5 tools, proxies to history-server)
│   │   └── PREREQ.md                      ← end-user system requirements doc
│   └── LaunchAgents/
│       ├── com.claude.daily-snapshot.plist
│       └── com.claude.backup-mirror.plist
│
├── hosts/
│   ├── claude-code/                       ← Claude Code plugin (Phase 1b/1c done)
│   │   ├── .claude-plugin/plugin.json
│   │   ├── commands/ccpal.md              ← /ccpal [open|search|doctor|install|status]
│   │   ├── hooks/hooks.json               ← Stop hook → daily-snapshot.sh background
│   │   ├── scripts/install.sh             ← deploy core/ → ~/.claude/scripts + launchd
│   │   └── core/                          ← bundled copy of /core (kept in sync by dev/sync-core.sh)
│   │
│   ├── codex/                             ← Codex Desktop integration (Phase 2.2 done)
│   │   ├── install.sh                     ← 3-step: pip + cp + `codex mcp add`
│   │   └── requirements.txt               ← mcp>=1.0
│   │
│   └── opencode/                          ← Phase 3 placeholder, currently empty
│
├── dev/
│   └── sync-core.sh                       ← copy core/ into each hosts/<x>/core/ that has plugin.json
│
└── installer/
    └── legacy/                            ← original "give to AI to install" HTML installer
        ├── 请安装这个项目CCPal-install v4.1.html
        └── extract.py                     ← parses 14 base64 blocks back into source
```

---

## 4. Dev workflow

`core/` is the **single source of truth**. Each host plugin's `core/`
subdirectory (e.g. `hosts/claude-code/core/`) is a **bundled copy** so the
plugin is self-contained when distributed (git-subdir / tarball /
marketplace).

```bash
# 1. edit anything in core/
$EDITOR core/scripts/history-server.py

# 2. propagate to every host plugin's core/ bundle
bash dev/sync-core.sh

# 3. commit both source-of-truth and bundles
git add core hosts/*/core
git commit -m "..."
```

**Never edit `hosts/<x>/core/` directly** — the next `sync-core.sh` will
overwrite. The script intentionally only syncs into hosts that already have
`.claude-plugin/plugin.json` (Codex / OpenCode placeholder dirs are
skipped).

---

## 5. How to add a new host (Phase 3 recipe)

Use this when adding OpenCode or any future host. Steps in order:

1. **Investigate the host's MCP/plugin surface.** Where is its config file?
   Does it support `[mcp_servers.X]`-style stdio MCP servers? Is there a
   CLI subcommand for registration (like Codex's `codex mcp add`)? Read
   the host's docs **and** spot-check by reading its actual binary/source
   — docs lie, code doesn't (see §6 for why).
2. **Create `hosts/<name>/`** with at minimum:
   - `install.sh` — idempotent. Pre-req check that `~/.claude/scripts/start-history.sh`
     exists (i.e. CCPal core is already deployed). Use `core/scripts/ccpal-mcp.py`
     (don't duplicate it).
   - `requirements.txt` if pip deps needed (currently just `mcp>=1.0`).
   - `.claude-plugin/plugin.json` only if this host has a Claude-Code-style
     plugin manifest (Codex doesn't; OpenCode TBD).
3. **Reuse `core/scripts/ccpal-mcp.py` as-is.** The 5 tools are
   host-agnostic. If a host only allows MCP-as-a-plugin (vs. raw stdio
   server), add a thin wrapper script *inside the plugin dir* and have it
   `exec python3 /path/to/ccpal-mcp.py`. See the deleted Phase 2.1
   `run-ccpal.sh` in git history for the pattern (don't recreate the
   marketplace tree — Codex Desktop didn't honor it; check what your
   target host actually does).
4. **Smoke test.** End-to-end MCP `initialize` + `tools/list` handshake
   against the deployed script. The Phase 2.2 `install.sh` has a working
   inline Python harness — copy that pattern.
5. **Have the user verify in their actual host UI.** The model in the host
   should see `mcp__ccpal__open_ui` etc. and auto-invoke them on prompts
   like "what were my last 5 Claude Code sessions?".

---

## 6. Critical empirical knowledge

These are facts that cost hours to discover. Trust them; don't relitigate
without strong evidence.

### 6.1 Codex Desktop user MCP registration

**Codex Desktop silently drops hand-edited `[mcp_servers.X]` and
`[marketplaces.X]` blocks** from `~/.codex/config.toml`. The Electron layer
(`app.asar`'s `BundledPluginsMarketplace`) only mounts the hardcoded
`openai-bundled` marketplace into the Rust core. The Rust core
(`/Applications/Codex.app/Contents/Resources/codex`) parses
`[marketplaces.X]` but its loader (`core-plugins/src/loader.rs`) only
enumerates curated and non-curated remote-catalog marketplaces — there is
no code path that mounts a `local` user marketplace into `plugin/list`.

**The only working path is the CLI:**
```bash
/Applications/Codex.app/Contents/Resources/codex mcp add ccpal -- python3 ~/.claude/scripts/ccpal-mcp.py
```

The CLI writes the same `[mcp_servers.ccpal]` block to `config.toml` you'd
write by hand, but **also** registers internal state via
`config/mcpServer/reload`. Without that internal state, the same block is
invisible to the desktop. Verified 2026-05-04.

If a future Codex change exposes a UI for user MCPs or starts honoring
`[mcp_servers.X]` directly, this gotcha may go away — re-test before
trusting docs.

### 6.2 Claude Code Desktop has no `/plugin` command

The user runs the **macOS Claude Desktop app**
(`__CFBundleIdentifier=com.anthropic.claudefordesktop`,
`CLAUDE_CODE_ENTRYPOINT=claude-desktop`). The desktop variant doesn't
expose `/plugin marketplace add`, `/plugin install`, etc. — those are only
on the standalone CLI (`npm i -g @anthropic-ai/claude-code`). Test plugin
features by direct script invocation, not via slash commands.

### 6.3 macOS-only constraints

- launchd plists at `~/Library/LaunchAgents/com.claude.{daily-snapshot,backup-mirror}.plist`
- `open(1)` to launch URLs / reveal in Finder
- `rsync` for backup mirror
- bash 3.2 (default macOS) — don't use bash 4+ features
- `python3` resolved via `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` on this machine; assume 3.7+ generally

### 6.4 The Stats UI bug pattern

`history-stats.html` originally called `$('generated').textContent = ...`
on a non-existent DOM element, throwing `Cannot set properties of null` and
aborting `load()` before `#content` got populated — the page rendered
blank with only a red error. Fixed by adding `<span id="generated">`. If
similar errors appear on other pages, check the JS for `$()` references to
elements that don't exist.

### 6.5 Embedded git repos are not your friend

`git add -A` from this repo root will pick up `.claude/worktrees/<...>`
(Claude Code's internal worktrees, which are themselves git repos) as
submodule pointers. `.gitignore` has `.claude/worktrees/` for this reason.
Don't remove it.

---

## 7. The 5 MCP tools

Defined in `core/scripts/ccpal-mcp.py`. All proxy to `history-server.py`'s
HTTP API and auto-bootstrap the server via
`~/.claude/scripts/start-history.sh` on first call. Logs go to **stderr**
(stdout is reserved for JSON-RPC).

| Tool | Args | Returns | Backend |
|---|---|---|---|
| `open_ui` | — | `"CCPal UI is running: http://127.0.0.1:8765"` | starts server, no browser open |
| `recent_sessions` | `limit: int = 10` (1..100) | list of `{title, cwd, path, msg_count, mtime, tokens_in, tokens_out}` | `/api/index` |
| `search_sessions` | `query: str, limit: int = 20` | substring match on title + cwd, same shape as recent | `/api/index` filtered |
| `get_session_text` | `path: str` (relative jsonl path from above) | full conversation as markdown | `/api/export?path=...` |
| `stats` | — | `{totals, active_days, daily, hourly, projects, generated_at}` | `/api/stats` |

Codex/OpenCode model sees these as `mcp__ccpal__<tool>`.

---

## 8. `history-server.py` HTTP API

For any future tool that needs to talk to it directly. All endpoints are
on `http://127.0.0.1:8765`.

| Method | Path | Returns |
|---|---|---|
| GET | `/`, `/index.html` | main UI HTML |
| GET | `/{stats,health,budget,safety}` | sub-page HTML |
| GET | `/api/index` | array of session metadata `{path, cwd, raw_cwd, is_worktree, title, msg_count, mtime, ctime, size, tokens_in, ...}` sorted by mtime desc |
| GET | `/api/stats` | `{totals, active_days, daily[], hourly[], projects[], generated_at}` |
| GET | `/api/usage` | rolling 5h-session and 7d-weekly token windows |
| GET | `/api/export?path=...&download=1&fn=...` | session as markdown (Content-Type `text/markdown`); `download=1` adds Content-Disposition |
| GET | `/api/session?path=...` | `{cwd, messages[]}` |
| GET | `/api/open?path=...&mode=file\|reveal` | runs `open` to launch a file or reveal in Finder |
| POST | `/api/rebuild` | rebuild in-memory index, returns `{ok, count}` |

Path safety: relative paths are resolved against `ROOT = ~/.claude/projects`
and validated to stay inside (via `Path.resolve().relative_to(ROOT)`).

---

## 9. Validation patterns

**End-to-end MCP handshake test** (use this when adding a new host or
debugging):

```python
import json, subprocess, sys, os
p = subprocess.Popen(
    ["python3", os.path.expanduser("~/.claude/scripts/ccpal-mcp.py")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, bufsize=1,
)
p.stdin.write(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize",
    "params":{"protocolVersion":"2024-11-05","capabilities":{},
              "clientInfo":{"name":"smoke","version":"0"}}}) + "\n")
p.stdin.flush()
line = p.stdout.readline()
sys.exit(0 if line and "result" in line else 1)
```

**Doctor**: `bash ~/.claude/scripts/ccpal-doctor.sh` — should print
`✓ 正常 23  ⚙ 自动修复 0  ⚠ 警告 0  ✗ 错误 0`. If anything is non-zero,
investigate before proceeding.

**Server up?** `curl -s http://127.0.0.1:8765/api/index | head -c 200`.

**Codex tools visible?** `/Applications/Codex.app/Contents/Resources/codex mcp list`
should show `ccpal` with `Status: enabled`.

---

## 10. Known issues / open items

- **Phase 2.3 (credentials in tool output)**: `recent_sessions` and
  `search_sessions` return `title` (= first user-message excerpt) verbatim.
  If the user typed a password / API key into a Claude Code session, it
  gets surfaced to *every* MCP client (including Codex, future OpenCode,
  any other agent that can talk MCP). The user already has one such leak
  in their history (an SSH credential). Plan: add a regex scrubber for
  well-known secret shapes (`password=`, `Authorization: Bearer`,
  `AKIA[0-9A-Z]{16}`, `xox[baprs]-`, OpenAI `sk-...`, `ghp_...`,
  `BEGIN ... PRIVATE KEY`, etc.) at the MCP boundary. `get_session_text`
  is the explicit-fetch tool, leave it un-scrubbed (user opted in).

- **Stats page**: there's likely more `$()` references to undeclared IDs
  in the other UI pages — only `history-stats.html` was audited. If users
  report blank pages, audit the others with the same grep pattern.

- **Phase 1d (publish marketplace)**: blocked on user installing the
  standalone Claude Code CLI to actually run `/plugin marketplace add`
  against a real GitHub URL. Not worth doing speculatively.

---

## 11. What NOT to do

- Don't propose Linux/Windows support.
- Don't write session-format adapters for Codex / OpenCode chat history.
- Don't edit `hosts/<x>/core/` directly — edit `core/` and run
  `bash dev/sync-core.sh`.
- Don't recreate `hosts/codex/marketplace/` — it's documented dead code in
  git history (commit `4b0862a`).
- Don't propose `[mcp_servers.X]` or `[marketplaces.X]` config edits to
  Codex Desktop — they don't work. Use `codex mcp add`.
- Don't bypass the `~/.claude/scripts/start-history.sh` pre-req check in
  any host's `install.sh` — running a host integration without core
  deployed leaves a broken state.
- Don't add `--no-verify` / `--no-gpg-sign` to git commands.
- Don't write multi-paragraph docstrings or speculative future-proofing in
  shell scripts. Keep them tight.

---

## 12. Where to learn more

- **Original installer with full design intent**:
  `installer/legacy/请安装这个项目CCPal-install v4.1.html` — the v4.1 HTML
  has a banner block (`CCPAL_INSTALL_INSTRUCTIONS`) describing the 11-step
  bootstrap and FIX table for missing deps.
- **Commit history**: `git log --oneline` — each commit message documents
  *why*, not just *what*. Especially:
  - `4b0862a` — explains the Codex Desktop registration dead-end and the
    real fix
  - `c4cdc0c` — Phase 1c bundle workflow rationale
  - `c91ff69` → `af3895a` → `4b0862a` — the full Codex Phase 2 evolution
- **`core/scripts/PREREQ.md`** — end-user-facing system requirements,
  install steps, uninstall.
- **`README.md`** — human-facing roadmap (this file is the AI-facing one).
