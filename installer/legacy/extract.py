#!/usr/bin/env python3
"""Extract all data-ccpal-file base64 blocks from the install HTML into ./src/."""
import base64
import os
import re
import sys
from html.parser import HTMLParser

HTML = os.path.join(os.path.dirname(__file__), "请安装这个项目CCPal-install v4.1.html")
OUT = os.path.join(os.path.dirname(__file__), "src")

class Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cur = None
        self.buf = []
        self.files = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        a = dict(attrs)
        if "data-ccpal-file" in a or a.get("data-ccpal-file") == "":
            self.cur = a
            self.buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self.cur is not None:
            self.files.append((self.cur, "".join(self.buf)))
            self.cur = None
            self.buf = []

    def handle_data(self, data):
        if self.cur is not None:
            self.buf.append(data)

with open(HTML, "r", encoding="utf-8") as f:
    html = f.read()

p = Extractor()
p.feed(html)

# Filter to only blocks that have data-ccpal-file attr (HTMLParser lower-cases attrs)
blocks = [(a, b) for a, b in p.files if any(k == "data-ccpal-file" for k in a.keys())]

print(f"Found {len(blocks)} embedded files")

written = []
for attrs, body in blocks:
    target = attrs.get("data-target", "")
    mode = attrs.get("data-mode", "0644")
    enc = attrs.get("data-encoding", "base64")
    fname = os.path.basename(target)
    if not fname:
        print(f"  ! skip: empty target", file=sys.stderr)
        continue

    # Mirror the original layout: scripts → src/scripts/, plists → src/LaunchAgents/
    if "/Library/LaunchAgents/" in target:
        sub = "LaunchAgents"
    elif "/.claude/scripts/" in target:
        sub = "scripts"
    else:
        sub = "other"
    out_dir = os.path.join(OUT, sub)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, fname)

    # Strip whitespace from base64 body
    b64 = re.sub(r"\s+", "", body)
    if enc != "base64":
        print(f"  ! unknown encoding {enc} for {fname}", file=sys.stderr)
        continue
    raw = base64.b64decode(b64)
    with open(out_path, "wb") as f:
        f.write(raw)
    os.chmod(out_path, int(mode, 8))
    written.append((sub, fname, len(raw), mode, target))
    print(f"  ✓ {sub}/{fname}  ({len(raw):,} B, mode {mode})")

print(f"\nWrote {len(written)} files to {OUT}")
