#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Dashboards Generator for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P5 Task-1 (#12 知识仪表盘多页) — generates `dashboards/` with six
pages from the P2/P4 sensor outputs so 00-MOC navigation stops being
hand-maintained:

    index.md            navigation over the five content pages
    recent-sources.md   <- 11-Agents/可信度账本「自动生成」 sources_summary (#16)
    timeline.md         <- 10-Daily/*.md + 11-Agents/review-log.md rows
    conflicts.md        <- vault-conflict-scan.scan_for_conflicts (live scan)
    open-questions.md   <- vault-wide `?`/TODO/待定 line survey (light regex)
    sessions.md         <- PLACEHOLDER until P6 #10 vault-insights.py lands

Design contracts:
* Page builders are pure functions returning markdown strings (unit-testable).
* `generate_dashboards(vault_root, out_dir, apply=False)` writes all six pages
  in ONE P1 VaultTransaction when apply=True; dry-run (default) is read-only.
* Every page carries the 7 required frontmatter fields with `updated` set to
  the generation date (prevents staleness false positives when the nightly
  pipeline commits regenerated pages).
* Every data source may be absent: missing inputs render 「暂无数据」
  empty-state sections — generation never fails on an empty corpus.
* conflicts page honors the P2 yellow-card constraint: score>=2 candidates
  are listed in full, score==1 candidates are folded into a single count
  line (low-signal noise must not flood the page).
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import importlib.util
import json
import pathlib
import re
from typing import Any, Dict, List, Optional

from vault_transaction import VaultTransaction

_SCRIPT_NAME = "scripts/vault-dashboards.py"
_EMPTY_MARK = "暂无数据"
_LEDGER_REL = "11-Agents/可信度账本「自动生成」"
_REVIEW_LOG_REL = "11-Agents/review-log.md"
_DAILY_DIR = "10-Daily"
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TODO_RE = re.compile(r"TODO|待定|\?")
_FENCE_TOKENS = ("```", "~~~")
_OPEN_QUESTION_CAP = 50
_SOURCE_ROWS_CAP = 20
_TIMELINE_CAP = 30
# Generated pages quote raw vault lines. URLs are redacted so the nightly
# commit can never trip pre-commit Gate 1.5 (credential-like URL params in
# staged added lines) — P2 yellow-card lesson, applied at the generator.
_URL_RE = re.compile(r"https?://\S+")
_URL_PLACEHOLDER = "〈URL-已隐去〉"


def _redact_urls(text: str) -> str:
    return _URL_RE.sub(_URL_PLACEHOLDER, text)

_LEDGER_MODULE: Optional[Any] = None


def _ledger_module() -> Any:
    """Load vault-claim-ledger.py once (hyphenated filename) to reuse its
    vault walk and frontmatter splitting for the open-questions survey."""
    global _LEDGER_MODULE
    if _LEDGER_MODULE is None:
        path = pathlib.Path(__file__).resolve().parent / "vault-claim-ledger.py"
        spec = importlib.util.spec_from_file_location("vault_claim_ledger", path)
        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:  # pragma: no cover - defensive
            raise ImportError(f"cannot load ledger module from {path}")
        spec.loader.exec_module(module)
        _LEDGER_MODULE = module
    return _LEDGER_MODULE


def _load_conflict_scanner() -> Any:
    """Load vault-conflict-scan.py (hyphenated filename, P2 sensor)."""
    path = pathlib.Path(__file__).resolve().parent / "vault-conflict-scan.py"
    spec = importlib.util.spec_from_file_location("vault_conflict_scan", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load conflict scanner from {path}")
    spec.loader.exec_module(module)
    return module


def _page(title: str, tags: List[str], body: str) -> str:
    """Wrap a page body with the 7-field frontmatter (updated = today)."""
    today = datetime.date.today().isoformat()
    tags_block = "\n".join(f"  - {tag}" for tag in tags)
    return (
        f"---\n"
        f"title: \"{title}\"\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        f"type: notes\n"
        f"tags:\n{tags_block}\n"
        f"status: active\n"
        f"audience: both\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body}"
    )


def build_recent_sources_page(ledger: Optional[Dict[str, Any]]) -> str:
    """recent-sources <- claim-ledger sources_summary + authority stats."""
    rows: List[str] = []
    if ledger and ledger.get("sources_summary"):
        for item in ledger["sources_summary"][:_SOURCE_ROWS_CAP]:
            dirs = "、".join(item.get("dirs", [])) or "-"
            rows.append(
                f"| {item.get('source', '-')} | {item.get('note_count', 0)} "
                f"| {item.get('max_authority', '-')} "
                f"| {item.get('reviewed_count', 0)} | {dirs} |"
            )
    stats_section = ""
    if ledger and ledger.get("stats"):
        stats = ledger["stats"]
        lines = [
            f"- {name}: {stats.get(name, 0)}"
            for name in ("official", "primary", "secondary", "community",
                         "synthetic", "unknown")
        ]
        stats_section = (
            "## 权威度统计\n\n"
            f"总笔记 {stats.get('total', 0)} 篇，已标注 "
            f"{stats.get('with_authority', 0)} 篇。\n\n" + "\n".join(lines) + "\n"
        )
    if not rows:
        body = f"## 最近来源\n\n{_EMPTY_MARK}（claim-ledger 尚未生成或无来源记录）。\n"
    else:
        body = (
            "## 最近来源\n\n"
            "| 来源 | 笔记数 | 最高权威 | 已复核 | 覆盖目录 |\n"
            "|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n"
        )
    return _page("最近来源", ["category/dashboard", "topic/sources"], body + stats_section)


def _extract_date(text: str) -> Optional[str]:
    match = _DATE_RE.search(text)
    return match.group(0) if match else None


def build_timeline_page(
    daily_files: List[pathlib.Path], review_log_path: Optional[pathlib.Path]
) -> str:
    """timeline <- 10-Daily notes + review-log rows, descending by date."""
    entries: List[tuple[str, str]] = []
    for path in daily_files or []:
        date = _extract_date(path.name) or _extract_date(
            _safe_read(path) or "")
        if date:
            entries.append((date, f"📝 日志：{path.stem}"))
    if review_log_path is not None:
        for line in _safe_read(review_log_path).splitlines():
            date = _extract_date(line)
            if date and line.strip():
                entries.append((date, f"🔎 复核：{_redact_urls(line.strip())}"))
    if not entries:
        body = f"## 时间线\n\n{_EMPTY_MARK}（10-Daily 与 review-log 均无条目）。\n"
    else:
        entries.sort(key=lambda item: item[0], reverse=True)
        lines = [f"- {date} — {text}" for date, text in entries[:_TIMELINE_CAP]]
        body = "## 时间线\n\n" + "\n".join(lines) + "\n"
    return _page("时间线", ["category/dashboard", "topic/timeline"], body)


def build_conflicts_page(vault_root: pathlib.Path) -> str:
    """conflicts <- live conflict scan; score>=2 listed, score=1 folded."""
    scanner = _load_conflict_scanner()
    candidates = scanner.scan_for_conflicts(vault_root)
    high = [c for c in candidates if c.get("score", 0) >= 2]
    low_count = len(candidates) - len(high)
    if not candidates:
        body = f"## 矛盾候选\n\n{_EMPTY_MARK}（未检出对立断言候选对）。\n"
    else:
        rows = [
            f"| {c.get('file_a', '-')} ↔ {c.get('file_b', '-')} "
            f"| {c.get('tag', '-')} | {c.get('keyword', '-')} "
            f"| {c.get('score', 0)} |"
            for c in high
        ]
        body = (
            "## 矛盾候选\n\n"
            "| 文件对 | 共享 tag | 关键词 | score |\n"
            "|---|---|---|---|\n"
            + ("\n".join(rows) + "\n" if rows else "")
        )
        if low_count:
            body += f"\n另有 {low_count} 条 score=1 低信号候选（已折叠，勿全量灌页）。\n"
        body += "\n候选仅为人工复核线索，非错误（vault-conflict-scan 契约）。\n"
    return _page("矛盾候选", ["category/dashboard", "topic/consistency"], body)


def build_open_questions_page(vault_root: pathlib.Path) -> str:
    """open-questions <- vault-wide `?`/TODO/待定 line survey (cap 50)."""
    ledger = _ledger_module()
    hits: List[str] = []
    for path in ledger._iter_markdown_files(vault_root):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue  # reported by the ledger walker convention; skip here
        fm_text, body = ledger._split_frontmatter(text)
        del fm_text  # survey the body only
        in_fence = False
        rel_posix = str(path.relative_to(vault_root)).replace("\\", "/")
        for line in body.splitlines():
            if any(token in line for token in _FENCE_TOKENS):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if _TODO_RE.search(line):
                hits.append(f"- `{rel_posix}`：{_redact_urls(line.strip())}")
                if len(hits) >= _OPEN_QUESTION_CAP:
                    break
        if len(hits) >= _OPEN_QUESTION_CAP:
            break
    if not hits:
        body = f"## 开放问题\n\n{_EMPTY_MARK}（未检出问句 / TODO / 待定标记）。\n"
    else:
        body = (
            f"## 开放问题\n\n共 {len(hits)} 条（上限 {_OPEN_QUESTION_CAP}）：\n\n"
            + "\n".join(hits) + "\n"
        )
    return _page("开放问题", ["category/dashboard", "topic/open-questions"], body)


def build_sessions_page() -> str:
    """sessions placeholder — P6 #10 vault-insights.py will fill this page."""
    body = (
        "## 会话洞察（占位）\n\n"
        f"{_EMPTY_MARK}。本页由 P6 #10 的 `vault-insights.py` 补实"
        "（corrections.md + review-log + work.log → 纠正热力图/时间线/趋势），"
        "骨架先行、空态可容忍（ADR-0001 #10 终裁）。\n"
    )
    return _page("会话洞察", ["category/dashboard", "topic/sessions"], body)


def build_index_page(pages: Dict[str, str]) -> str:
    """index <- links over the five content pages ({filename: title})."""
    if not pages:
        links = f"- {_EMPTY_MARK}\n"
    else:
        links = "\n".join(
            f"- [[dashboards/{name}|{title}]]" for name, title in pages.items()
        )
    body = (
        "## 知识仪表盘\n\n"
        "由 `scripts/vault-dashboards.py` nightly 自动再生成，请勿手动编辑页面内容。\n\n"
        + links + "\n"
    )
    return _page("知识仪表盘索引", ["category/dashboard", "category/moc"], body)


def _safe_read(path: Optional[pathlib.Path]) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        print(f"{_SCRIPT_NAME}: cannot read {path}: {exc}", file=sys.stderr)
        return ""


def _collect_daily(vault_root: pathlib.Path) -> List[pathlib.Path]:
    daily = vault_root / _DAILY_DIR
    if not daily.is_dir():
        return []
    return sorted(daily.glob("*.md"))


def _build_all_pages(vault_root: pathlib.Path) -> Dict[str, str]:
    """Assemble the six pages; every source may be absent (empty states)."""
    ledger: Optional[Dict[str, Any]] = None
    ledger_path = vault_root / _LEDGER_REL
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"{_SCRIPT_NAME}: claim-ledger unreadable ({exc}); "
                  "recent-sources falls back to empty state", file=sys.stderr)
    pages = {
        "recent-sources.md": build_recent_sources_page(ledger),
        "timeline.md": build_timeline_page(
            _collect_daily(vault_root), vault_root / _REVIEW_LOG_REL
        ),
        "conflicts.md": build_conflicts_page(vault_root),
        "open-questions.md": build_open_questions_page(vault_root),
        "sessions.md": build_sessions_page(),
    }
    titles = {
        "recent-sources.md": "最近来源",
        "timeline.md": "时间线",
        "conflicts.md": "矛盾候选",
        "open-questions.md": "开放问题",
        "sessions.md": "会话洞察",
    }
    pages["index.md"] = build_index_page(titles)
    return pages


def generate_dashboards(
    vault_root: pathlib.Path, out_dir: pathlib.Path, apply: bool = False
) -> Dict[str, int]:
    """Build all six pages; apply=True writes them in ONE VaultTransaction.

    Returns per-page line counts (both modes) for dry-run reporting.
    """
    pages = _build_all_pages(vault_root)
    stats = {name: len(text.splitlines()) for name, text in pages.items()}
    if not apply:
        return stats
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    with VaultTransaction(vault_root, tx_id=f"tx-dashboards-{today}") as tx:
        for name, text in pages.items():
            tx.stage(out_dir / name, new_text=text)
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P5 Task-1: generate the dashboards/ multi-page set."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write pages via VaultTransaction (default: read-only dry-run)",
    )
    parser.add_argument(
        "--vault-root", default=None,
        help="vault root (default: parent of the scripts/ directory)",
    )
    args = parser.parse_args(argv)
    vault_root = (
        pathlib.Path(args.vault_root)
        if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    out_dir = vault_root / "dashboards"
    stats = generate_dashboards(vault_root, out_dir, apply=args.apply)
    mode = "applied" if args.apply else "dry-run"
    for name, lines in stats.items():
        print(f"  {name}: {lines} lines")
    print(f"{mode}: out_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
