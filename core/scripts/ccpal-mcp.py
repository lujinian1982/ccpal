#!/usr/bin/env python3
"""CCPal MCP server.

Exposes Claude Code conversation history (browser UI + search + per-session
text + usage stats) to any MCP-aware host (Codex CLI today; OpenCode next).

Talks to the local history-server.py over HTTP at 127.0.0.1:8765 and
auto-starts it via ~/.claude/scripts/start-history.sh if it isn't running.

stdio JSON-RPC discipline: nothing is ever printed to stdout from this
file — all diagnostics go to stderr via _log().
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

CCPAL_PORT = int(os.environ.get("CCPAL_PORT", "8765"))
CCPAL_BASE = f"http://127.0.0.1:{CCPAL_PORT}"
START_SCRIPT = Path.home() / ".claude" / "scripts" / "start-history.sh"


def _log(msg: str) -> None:
    print(f"[ccpal-mcp] {msg}", file=sys.stderr, flush=True)


def _http_json(path: str, timeout: float = 5.0):
    with urllib.request.urlopen(f"{CCPAL_BASE}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _http_text(path: str, timeout: float = 15.0) -> str:
    with urllib.request.urlopen(f"{CCPAL_BASE}{path}", timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _ensure_server() -> bool:
    """Return True iff history-server is reachable. Bootstraps it on demand."""
    try:
        _http_json("/api/index", timeout=1.0)
        return True
    except Exception:
        pass

    if not START_SCRIPT.exists():
        _log(f"start script missing: {START_SCRIPT} — run /ccpal install first")
        return False

    try:
        subprocess.run(
            ["bash", str(START_SCRIPT)],
            timeout=30,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        _log(f"start-history.sh failed: {e}")
        return False

    for _ in range(20):
        try:
            _http_json("/api/index", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.3)
    _log("history-server did not come up within ~6s")
    return False


def _slim(s: dict) -> dict:
    return {
        "title": s.get("title", ""),
        "cwd": s.get("cwd", ""),
        "path": s.get("path", ""),
        "msg_count": s.get("msg_count", 0),
        "mtime": s.get("mtime", 0),
        "tokens_in": s.get("tokens_in", 0),
        "tokens_out": s.get("tokens_out", 0),
    }


mcp = FastMCP("ccpal")


@mcp.tool()
def open_ui() -> str:
    """Ensure the CCPal history browser is running locally and return its URL.

    Use this when the user wants to visually browse, search, or read their
    full Claude Code conversation history. The URL is local-only
    (http://127.0.0.1:8765), no data leaves the machine.
    """
    if not _ensure_server():
        return (
            "ERROR: CCPal is not installed. From Claude Code run "
            "`/ccpal install`, or run "
            "`bash ~/Documents/workspace/claudcode/mem/hosts/claude-code/scripts/install.sh`."
        )
    return f"CCPal UI is running: {CCPAL_BASE}"


@mcp.tool()
def recent_sessions(limit: int = 10) -> list[dict]:
    """Return the most recently active Claude Code sessions, newest first.

    Each entry: title (first user message excerpt), cwd (project path),
    path (relative jsonl path used by other ccpal tools), msg_count,
    mtime (unix seconds), tokens_in, tokens_out.

    Use the `path` field as input to `get_session_text` to read the full
    conversation.
    """
    if not _ensure_server():
        return [{"error": "ccpal server unavailable"}]
    idx = _http_json("/api/index")
    n = max(1, min(int(limit), 100))
    return [_slim(s) for s in idx[:n]]


@mcp.tool()
def search_sessions(query: str, limit: int = 20) -> list[dict]:
    """Find past Claude Code sessions whose title or project path contains the query.

    Case-insensitive substring match against the first user-message excerpt
    (title) and the working directory (cwd). Sorted by recency. For
    full-message-body search, use the CLI: `~/.claude/scripts/search-chats.sh
    <query>`.

    Use the returned `path` with `get_session_text` to read a full match.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    if not _ensure_server():
        return [{"error": "ccpal server unavailable"}]
    idx = _http_json("/api/index")
    n = max(1, min(int(limit), 100))
    hits = [
        _slim(s)
        for s in idx
        if q in (s.get("title") or "").lower() or q in (s.get("cwd") or "").lower()
    ]
    return hits[:n]


@mcp.tool()
def get_session_text(path: str) -> str:
    """Return a full Claude Code session as markdown.

    `path` must be the relative jsonl path returned by recent_sessions or
    search_sessions (e.g. "-Users-you-project/abc-uuid.jsonl"). Output
    contains user/assistant turns, project context, and the attachments
    list — suitable for the model to read directly.
    """
    if not path:
        return "ERROR: path required"
    if not _ensure_server():
        return "ERROR: ccpal server unavailable"
    try:
        return _http_text(f"/api/export?path={urllib.parse.quote(path)}")
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def stats() -> dict:
    """Return summary stats about Claude Code usage.

    Includes totals (sessions, messages, tokens in/out, cache read/create),
    active_days, daily breakdown for the recent window, hourly distribution,
    project ranking, and generated_at timestamp. Source: ~/.claude/projects/.
    """
    if not _ensure_server():
        return {"error": "ccpal server unavailable"}
    return _http_json("/api/stats")


if __name__ == "__main__":
    mcp.run()
