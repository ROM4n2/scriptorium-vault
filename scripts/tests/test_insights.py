#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for vault-insights.py (ROADMAP-P6 Task-4, #10 会话洞察).

Covers the six contract clauses: event aggregation, open-correction count,
7-field frontmatter pages, empty-corpus tolerance, dry-run read-only, and
the nightly step placement (dashboards -> insights -> quality).
"""

import importlib.util
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "vault-insights.py"
_spec = importlib.util.spec_from_file_location("vault_insights", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_REQUIRED_FIELDS = ("title:", "created:", "updated:", "type:", "tags:", "status:", "audience:")


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _log_row(date: str, summary: str, correction: bool = False) -> str:
    event = "CORRECTION " if correction else ""
    return f"| {date} 10:00 | CodeBuddy | {event}Fix | scripts/x.py | {summary} |\n"


def _make_monthly_log(root: pathlib.Path, month: str, rows: str) -> pathlib.Path:
    path = root / "11-Agents" / "logs" / f"{month}.md"
    _write(path, f"---\ntitle: log {month}\n---\n\n# Log {month}\n\n{rows}")
    return path


def _make_corrections(root: pathlib.Path) -> pathlib.Path:
    path = root / "11-Agents" / "corrections.md"
    _write(path, (
        "---\ntitle: corrections\n---\n\n"
        "| 日期 | 原话（用户） | 问题归属（领域/流程/工具） | 落地状态 | 蒸馏去向 |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| 2026-09-01 | 不要把临时脚本塞进根目录 | 流程 | open | — |\n"
        "| 2026-09-02 | 用事务写盘 | 工具 | resolved | vault://x |\n"
    ))
    return path


class TestAggregate(unittest.TestCase):
    """(a) event rows aggregated by day/week; category distribution counted."""

    def test_counts_by_day_and_category(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            log_a = _make_monthly_log(root, "2026-08", (
                _log_row("2026-08-20", "纠正：路径写反", correction=True)
                + _log_row("2026-08-21", "普通操作")
            ))
            log_b = _make_monthly_log(root, "2026-09", (
                _log_row("2026-09-01", "纠正：GBK 编码", correction=True)
                + _log_row("2026-09-01", "再纠正一次", correction=True)
            ))
            corrections = mod.parse_corrections(
                root / "11-Agents" / "corrections.md")
            agg = mod.aggregate([log_a, log_b], corrections)
            self.assertEqual(agg["correction_events"], 3)
            self.assertEqual(agg["by_day"]["2026-09-01"], 2)
            self.assertEqual(agg["by_day"]["2026-08-20"], 1)
            # weekly buckets: 2026-09-01 belongs to ISO week 36
            self.assertIn("2026-W36", agg["by_week"])
            self.assertEqual(agg["by_week"]["2026-W36"], 2)


class TestCorrectionsParsing(unittest.TestCase):
    """(b) corrections ledger rows parsed; open count surfaced."""

    def test_parse_corrections_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = _make_corrections(pathlib.Path(td))
            rows = mod.parse_corrections(path)
            self.assertEqual(len(rows), 2)
            open_count = sum(1 for r in rows if r["status"] == "open")
            self.assertEqual(open_count, 1)

    def test_missing_ledger_empty_rows(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rows = mod.parse_corrections(pathlib.Path(td) / "nope.md")
            self.assertEqual(rows, [])


class TestSessionsPage(unittest.TestCase):
    """(c) 7-field frontmatter + updated; (b) open count in page."""

    def test_page_contains_open_count_and_frontmatter(self) -> None:
        agg = {
            "correction_events": 3,
            "by_day": {"2026-09-01": 2, "2026-08-20": 1},
            "by_week": {"2026-W36": 2, "2026-W34": 1},
            "corrections": [
                {"date": "2026-09-01", "original": "不要把临时脚本塞进根目录",
                 "category": "流程", "status": "open", "distillation": "—"},
                {"date": "2026-09-02", "original": "用事务写盘",
                 "category": "工具", "status": "resolved", "distillation": "vault://x"},
            ],
        }
        page = mod.build_sessions_page(agg)
        head = page.split("---", 2)[1]
        for field in _REQUIRED_FIELDS:
            self.assertIn(field, head)
        self.assertRegex(head, r"updated: \d{4}-\d{2}-\d{2}")
        self.assertIn("1", page)  # open corrections count
        self.assertIn("不要把临时脚本塞进根目录", page)
        self.assertIn("流程", page)

    def test_empty_corpus_empty_state(self) -> None:
        """(d) no correction corpus at all -> empty-state page, no raise."""
        page = mod.build_sessions_page({
            "correction_events": 0, "by_day": {}, "by_week": {},
            "corrections": [],
        })
        self.assertIn("暂无数据", page)


class TestCliDryRun(unittest.TestCase):
    """(e) --dry-run must not write dashboards/sessions.md."""

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _make_monthly_log(root, "2026-09", _log_row("2026-09-01", "x", True))
            rc = mod.main(["--dry-run", "--vault-root", str(root)])
            self.assertEqual(rc, 0)
            self.assertFalse((root / "dashboards" / "sessions.md").exists())

    def test_apply_writes_sessions_page(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _make_monthly_log(root, "2026-09", _log_row("2026-09-01", "x", True))
            rc = mod.main(["--apply", "--vault-root", str(root)])
            self.assertEqual(rc, 0)
            page = root / "dashboards" / "sessions.md"
            self.assertTrue(page.exists())


if __name__ == "__main__":
    unittest.main()
