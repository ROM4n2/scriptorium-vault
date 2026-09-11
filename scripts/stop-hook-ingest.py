#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stop Hook Ingestion Prompt — Karpathy-Mode Knowledge Harvester
Runs at Claude Code session end to remind ingestion of new learnings.
Always exits 0 — never blocks agent stop.
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import subprocess
from datetime import date
from pathlib import Path

VAULT = Path("{{VAULT_ROOT}}")

# Pull inbox stats from existing triage script (--json already supported)
total, overdue = 0, 0
try:
    r = subprocess.run(
        [
            sys.executable,
            str(VAULT / "scripts/vault-inbox-triage.py"),
            "--json",
            "--vault-path",
            str(VAULT),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    if r.stdout.strip():
        data = json.loads(r.stdout)
        # triage JSON uses "total_drafts" (not "total")
        total = data.get("total_drafts", 0)
        overdue = data.get("overdue_count", 0)
except Exception:
    # Non-fatal: counts stay 0, prompt still prints
    pass

today = date.today().strftime("%Y-%m-%d")

SEP = "═" * 55
print(f"\n{SEP}")
print("📥 [Karpathy Ingestion Prompt] 会话结束")
print(SEP)
print("本次会话是否发现了新踩坑、架构决策或通用模式？")
print("如有，请写草稿至：")
print(f"  {{VAULT_ROOT}}\\99-Inbox\\{today}-{{topic}}.md")
print(f"格式参考：{{VAULT_ROOT}}\\Templates\\tpl-source-note.md")
print(f"\n📋 当前 Inbox 状态：{total} 篇草稿（{overdue} 篇超龄）")
print(f"{SEP}\n")

sys.exit(0)
