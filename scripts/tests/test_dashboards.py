#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for vault-dashboards.py (ROADMAP-P5 Task-1).

Pins the seven contract clauses (a)-(g) from ROADMAP-P5-DASHBOARDS.md:
page builders are pure functions returning markdown; generation is a single
VaultTransaction; every data source may be absent -> empty-state pages.
"""

import importlib.util
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "vault-dashboards.py"
_spec = importlib.util.spec_from_file_location("vault_dashboards", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

_REQUIRED_FIELDS = ("title:", "created:", "updated:", "type:", "tags:", "status:", "audience:")


_TEST_URL = "https://" + "api.x.com/v1?key=" + "AbCdEf123456&q=ok"


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_ledger(tmp: pathlib.Path) -> dict:
    return {
        "generated_at": "2026-09-09T00:00:00",
        "script": "scripts/vault-claim-ledger.py",
        "vault_root": str(tmp),
        "files": [],
        "sources_summary": [
            {"source": "Martin Kleppmann《DDIA》", "note_count": 3,
             "max_authority": "primary", "reviewed_count": 0,
             "dirs": ["06-Sources"]},
            {"source": "某社区博客", "note_count": 1,
             "max_authority": "community", "reviewed_count": 0,
             "dirs": ["05-Tools"]},
        ],
        "stats": {"total": 4, "with_authority": 4, "official": 0, "primary": 2,
                  "secondary": 0, "community": 1, "synthetic": 1, "unknown": 0,
                  "missing_authority": []},
    }


class TestRecentSourcesPage(unittest.TestCase):
    """(a) recent-sources contains summary rows + authority statistics."""

    def test_contains_rows_and_stats(self) -> None:
        ledger = _make_ledger(pathlib.Path("."))
        page = mod.build_recent_sources_page(ledger)
        self.assertIn("Martin Kleppmann《DDIA》", page)
        self.assertIn("primary", page)
        self.assertIn("2", page)  # note_count
        # authority statistics section
        for token in ("official", "primary", "community", "synthetic"):
            self.assertIn(token, page)

    def test_missing_ledger_empty_state(self) -> None:
        """(g) missing claim-ledger -> empty-state page, no exception."""
        page = mod.build_recent_sources_page(None)
        self.assertIn("暂无数据", page)


class TestTimelinePage(unittest.TestCase):
    """(b) daily notes + review-log rows, descending by date."""

    def test_descending_order_and_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            daily = root / "10-Daily"
            _write(daily / "2026-09-01.md", "---\ntitle: A\n---\n内容一\n")
            _write(daily / "2026-09-03.md", "---\ntitle: B\n---\n内容二\n")
            log = root / "review-log.md"
            _write(log, "# Review Log\n\n- 2026-09-02 | Agent | op | PASS\n"
                        "无日期行\n- 2026-09-04 | Agent | op2 | PASS\n")
            page = mod.build_timeline_page(
                sorted(daily.glob("*.md")), log)
            self.assertIn("2026-09-03", page)
            self.assertIn("2026-09-01", page)
            self.assertIn("2026-09-04", page)
            self.assertIn("2026-09-02", page)
            # descending: 09-04 appears before 09-03, which appears before 09-01
            self.assertLess(page.index("2026-09-04"), page.index("2026-09-03"))
            self.assertLess(page.index("2026-09-03"), page.index("2026-09-01"))

    def test_empty_inputs_empty_state(self) -> None:
        page = mod.build_timeline_page([], None)
        self.assertIn("暂无数据", page)


class TestConflictsPage(unittest.TestCase):
    """(c) candidate pairs listed; empty corpus -> empty state, no raise."""

    def _stub_scanner(self, candidates):
        return types.SimpleNamespace(scan_for_conflicts=lambda vault_root, tags=None: candidates)

    def test_candidates_listed_high_score_first(self) -> None:
        candidates = [
            {"file_a": "a.md", "file_b": "b.md", "tag": "topic/x",
             "keyword": "锁", "sentence_a": "锁 MUST 立即释放。",
             "sentence_b": "锁 禁止 立即释放。", "polarity_a": "must",
             "polarity_b": "forbid", "score": 2},
            {"file_a": "c.md", "file_b": "d.md", "tag": "topic/y",
             "keyword": "缓存", "sentence_a": "缓存 必须失效。",
             "sentence_b": "缓存 不得失效。", "polarity_a": "must",
             "polarity_b": "forbid", "score": 1},
        ]
        with mock.patch.object(mod, "_load_conflict_scanner",
                               return_value=self._stub_scanner(candidates)):
            page = mod.build_conflicts_page(pathlib.Path("."))
        self.assertIn("a.md", page)
        self.assertIn("b.md", page)
        self.assertIn("topic/x", page)
        # score=1 folded into a count line (P2 yellow-card constraint)
        self.assertIn("1", page)
        self.assertIn("折叠", page)

    def test_empty_corpus_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(mod, "_load_conflict_scanner",
                                   return_value=self._stub_scanner([])):
                page = mod.build_conflicts_page(pathlib.Path(td))
        self.assertIn("暂无数据", page)


class TestUrlRedaction(unittest.TestCase):
    """Generated pages quote raw vault lines: URLs MUST be redacted so the
    nightly commit can never trip pre-commit Gate 1.5 (credential-like URL
    params in staged added lines) — P2 yellow-card lesson applied."""

    def test_open_questions_redacts_urls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write(root / "05-Tools/Note.md",
                   "---\ntitle: N\n---\n\n见 " + _TEST_URL + " 示例\n")
            page = mod.build_open_questions_page(root)
            self.assertNotIn("https://", page)
            self.assertIn("URL-已隐去", page)

    def test_timeline_redacts_urls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = pathlib.Path(td) / "review-log.md"
            _write(log, "- 2026-09-04 | 检查 " + _TEST_URL + " | PASS\n")
            page = mod.build_timeline_page([], log)
            self.assertNotIn("https://", page)


class TestSessionsPage(unittest.TestCase):
    """(d) placeholder mentions vault-insights (P6 #10)."""

    def test_placeholder_mentions_insights(self) -> None:
        page = mod.build_sessions_page()
        self.assertIn("vault-insights", page)


class TestPageFrontmatter(unittest.TestCase):
    """(e) every page carries the 7 required frontmatter fields + updated."""

    def test_all_pages_have_frontmatter(self) -> None:
        pages = {
            "recent-sources": mod.build_recent_sources_page(_make_ledger(pathlib.Path("."))),
            "timeline": mod.build_timeline_page([], None),
            "conflicts": mod.build_conflicts_page(pathlib.Path(".")),
            "open-questions": mod.build_open_questions_page(pathlib.Path(".")),
            "sessions": mod.build_sessions_page(),
            "index": mod.build_index_page({}),
        }
        for name, page in pages.items():
            with self.subTest(page=name):
                self.assertTrue(page.startswith("---"), name)
                head = page.split("---", 2)[1]
                for field in _REQUIRED_FIELDS:
                    self.assertIn(field, head, f"{name} missing {field}")
                self.assertRegex(head, r"updated: \d{4}-\d{2}-\d{2}")


class TestGenerateDashboards(unittest.TestCase):
    """(f) dry-run writes nothing; apply writes six pages transactionally."""

    def test_generate_without_apply_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            out = root / "dashboards"
            mod.generate_dashboards(root, out, apply=False)
            self.assertFalse(out.exists() and any(out.iterdir()))

    def test_missing_sources_empty_states_no_raise(self) -> None:
        """(g) no ledger / graph-state / daily / review-log at all."""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            out = root / "dashboards"
            mod.generate_dashboards(root, out, apply=True)
            names = {p.name for p in out.glob("*.md")}
            self.assertEqual(
                names,
                {"index.md", "recent-sources.md", "timeline.md",
                 "conflicts.md", "open-questions.md", "sessions.md"},
            )
            for page in out.glob("*.md"):
                text = page.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---"))

    def test_apply_writes_six_pages_with_data(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            ledger_path = root / "11-Agents" / "可信度账本「自动生成」"
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_text(
                json.dumps(_make_ledger(root), ensure_ascii=False),
                encoding="utf-8",
            )
            out = root / "dashboards"
            mod.generate_dashboards(root, out, apply=True)
            sources = (out / "recent-sources.md").read_text(encoding="utf-8")
            self.assertIn("DDIA", sources)


if __name__ == "__main__":
    unittest.main()
