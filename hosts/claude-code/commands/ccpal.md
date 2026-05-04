---
description: Open the local CCPal history browser, search past conversations, or run diagnostics
argument-hint: [open|search|doctor|install|status] [query...]
allowed-tools: Bash
---

You are handling the `/ccpal` slash command for CCPal — the local Claude Code history browser & backup tool.

**Subcommand:** `$1` (defaults to `open` if empty)
**Full args:** `$ARGUMENTS`

Dispatch table:

| Subcommand | What to run |
|---|---|
| `open` (default) | `bash ~/.claude/scripts/start-history.sh` — starts server if needed, opens http://127.0.0.1:8765 in browser |
| `search` | `bash ~/.claude/scripts/search-chats.sh <rest of $ARGUMENTS>` — full-text search past chats |
| `doctor` | `bash ~/.claude/scripts/ccpal-doctor.sh` — 23-item self-check + idempotent fix |
| `install` | `bash ${CLAUDE_PLUGIN_ROOT}/scripts/install.sh` — deploy/re-deploy CCPal core to ~/.claude/scripts/ and load launchd jobs |
| `status` | `curl -s -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:8765/api/index` — quick health probe |

**Pre-flight:** if `~/.claude/scripts/start-history.sh` does not exist (i.e. CCPal has never been installed), tell the user to run `/ccpal install` first and STOP — don't try to run the other subcommands.

**Reporting:** keep output tight. For `open`, just confirm the URL. For `search`, pass through the script's output. For `doctor`, summarize OK/FIX/WARN/ERR counts and only show ERR lines verbatim. For `install`, surface the final ✅/⚠ line.
