#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Session Insights for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P6 Task-4 (#10 会话洞察) — aggregates the vault's own audit month
logs (`11-Agents/logs/{YYYY-MM}.md`) plus the corrections ledger
(`11-Agents/corrections.md`, schema per CROSS-AGENT-MEMORY §2.5) into the
REAL `dashboards/sessions.md`, replacing the P5 placeholder page.

Interfaces:
* parse_corrections(path) -> list[dict]: ledger table rows
  {date, original, category, status, distillation}; missing file -> [].
* aggregate(log_paths, corrections) -> dict:
  {correction_events, by_day, by_week, corrections}
  — a monthly-log row counts as a correction event when the row text
  contains `CORRECTION` (the event keyword pinned by the protocol).
* build_sessions_page(agg) -> str: full page (7-field frontmatter,
  updated = today, heat lines by day, category distribution, open rows,
  empty-state 「暂无数据」 when no corpus).
* CLI: --apply writes dashboards/sessions.md (single transaction);
  --dry-run (default) read-only; --json prints the aggregate.

Failure semantics: unreadable files reported on stderr and skipped — zero
silent swallowing. UTF-8 reconfigure per vault convention.
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import json
import pathlib
import re
from typing import Any, Dict, List, Optional, Union

from vault_transaction import VaultTransaction

_SCRIPT_NAME = "scripts/vault-insights.py"
_LOGS_DIR_REL = "11-Agents/logs"
_CORRECTIONS_REL = "11-Agents/corrections.md"
_SESSIONS_PAGE_REL = "dashboards/sessions.md"
_CORRECTION_KEYWORD = "CORRECTION"
_EMPTY_MARK = "暂无数据"
_ROW_DATE_RE = re.compile(r"^\|\s*(\d{4}-\d{2}-\d{2})")


def _safe_read(path: pathlib.Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(f"{_SCRIPT_NAME}: cannot read {path}: {exc}", file=sys.stderr)
        return ""


def _iso_week(date_str: str) -> str:
    return f"{datetime.date.fromisoformat(date_str).isocalendar()[0]}-W" \
           f"{datetime.date.fromisoformat(date_str).isocalendar()[1]:02d}"


def parse_corrections(path: Union[str, pathlib.Path]) -> List[Dict[str, str]]:
    """Parse corrections.md ledger rows; missing file -> empty list."""
    rows: List[Dict[str, str]] = []
    for line in _safe_read(pathlib.Path(path)).splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not _ROW_DATE_RE.match(line):
            continue  # header / separator / malformed rows skipped
        rows.append({
            "date": cells[0],
            "original": cells[1],
            "category": cells[2],
            "status": cells[3],
            "distillation": cells[4],
        })
    return rows


def aggregate(
    log_paths: List[pathlib.Path], corrections: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Aggregate correction events from monthly logs + ledger rows."""
    by_day: Dict[str, int] = {}
    by_week: Dict[str, int] = {}
    events = 0
    for log_path in log_paths:
        for line in _safe_read(log_path).splitlines():
            if _CORRECTION_KEYWORD not in line:
                continue
            match = re.match(r"^\|\s*(\d{4}-\d{2}-\d{2})", line)
            if match is None:
                continue
            date = match.group(1)
            events += 1
            by_day[date] = by_day.get(date, 0) + 1
            week = _iso_week(date)
            by_week[week] = by_week.get(week, 0) + 1
    return {
        "correction_events": events,
        "by_day": dict(sorted(by_day.items(), reverse=True)),
        "by_week": dict(sorted(by_week.items(), reverse=True)),
        "corrections": corrections,
    }


def _default_log_paths(vault_root: pathlib.Path) -> List[pathlib.Path]:
    logs_dir = vault_root / _LOGS_DIR_REL
    if not logs_dir.is_dir():
        return []
    return sorted(logs_dir.glob("*.md"))


def build_sessions_page(agg: Dict[str, Any]) -> str:
    """Full sessions page (7-field frontmatter) replacing the P5 placeholder."""
    today = datetime.date.today().isoformat()
    frontmatter = (
        f"---\n"
        f"title: \"会话洞察 (Session Insights)\"\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"type: notes\n"
        f"tags:\n  - category/dashboard\n  - topic/memory\n  - topic/multi-agent\n"
        f"status: active\n"
        f"audience: both\n"
        f"---\n\n"
        f"# 会话洞察 (Session Insights)\n\n"
    )
    corrections: List[Dict[str, str]] = agg.get("corrections", [])
    if not agg.get("correction_events") and not corrections:
        return frontmatter + (
            f"## 纠正洞察\n\n"
            f"{_EMPTY_MARK}。纠正语料随使用积累（CORRECTION 事件与 "
            f"`{_CORRECTIONS_REL}` 账本行），本页由 nightly `vault-insights.py` 自动刷新。\n"
        )
    heat_lines = [
        f"- {date}: {count} 次" for date, count in list(agg["by_day"].items())[:15]
    ]
    week_lines = [
        f"- {week}: {count} 次" for week, count in list(agg["by_week"].items())[:8]
    ]
    open_rows = [c for c in corrections if c.get("status") == "open"]
    category_counts: Dict[str, int] = {}
    for row in corrections:
        category_counts[row.get("category", "-")] = \
            category_counts.get(row.get("category", "-"), 0) + 1
    category_lines = [
        f"- {category}: {count}" for category, count in
        sorted(category_counts.items(), key=lambda kv: -kv[1])
    ]
    open_lines = [
        f"- {row['date']} | {row['original']}（{row['category']}）"
        for row in open_rows[:10]
    ]
    body = (
        "## 纠正热力（按日）\n\n" + ("\n".join(heat_lines) + "\n" if heat_lines else "")
        + "\n## 纠正趋势（按周）\n\n" + ("\n".join(week_lines) + "\n" if week_lines else "")
        + f"\n## 类别分布\n\n账本共 {len(corrections)} 条：\n\n"
        + ("\n".join(category_lines) + "\n" if category_lines else "")
        + f"\n## 待解决 open（{len(open_rows)} 条）\n\n"
        + ("\n".join(open_lines) + "\n" if open_lines else f"- {_EMPTY_MARK}\n")
        + "\n来源：审计月日志 CORRECTION 事件行 + 纠正账本（协议 [[01-Rules/CROSS-AGENT-MEMORY]] §2.5）；本页 nightly 自动刷新。\n"
    )
    return frontmatter + body


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P6 Task-4: aggregate corrections into dashboards/sessions.md."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write the sessions page (default: read-only dry-run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="explicit read-only preview (default behavior, kept for CLI symmetry)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the aggregate as JSON",
    )
    parser.add_argument(
        "--vault-root", default=None,
        help="vault root (default: parent of the scripts/ directory)",
    )
    parser.add_argument(
        "--corrections-dir", default=None,
        help="extra dir to scan for project corrections ledgers (optional)",
    )
    args = parser.parse_args(argv)
    vault_root = (
        pathlib.Path(args.vault_root)
        if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    corrections = parse_corrections(vault_root / _CORRECTIONS_REL)
    if args.corrections_dir:
        for ledger in sorted(pathlib.Path(args.corrections_dir).glob(
                "*/WORKMEMORY/corrections.md")):
            corrections.extend(parse_corrections(ledger))
    agg = aggregate(_default_log_paths(vault_root), corrections)
    if args.json:
        print(json.dumps(agg, ensure_ascii=False, indent=2))
        return 0
    page = build_sessions_page(agg)
    if not args.apply:
        print(f"dry-run: sessions page {len(page.splitlines())} lines, "
              f"{agg['correction_events']} correction events, "
              f"{sum(1 for c in agg['corrections'] if c['status'] == 'open')} open")
        return 0
    out = vault_root / _SESSIONS_PAGE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    with VaultTransaction(vault_root, tx_id=f"tx-insights-{today}") as tx:
        tx.stage(out, new_text=page)
    print(f"applied: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
