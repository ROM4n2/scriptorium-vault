"""Tests for `vault-conflict-scan.py` — heuristic conflicting-assertion scanner.

Contract pinned here (ROADMAP-P2-AUDIT-SENSORS Task-2)
------------------------------------------------------
* Grouping key = shared frontmatter tag (>=1 intersection) + shared content
  keyword between the two assertion sentences (MVP strategy: core-word
  intersection of the two assertion sentences — see the implementation
  docstring for the exact tokenization heuristic).
* Only OPPOSITE-polarity sentence pairs become candidates:
  positive (必须/应当/一定要/推荐/正确/always/must/should) vs negative
  (不能/禁止/不得/不要/不应/切勿/否/never/must not). Same-direction pairs are
  NOT candidates (case b).
* Fenced code blocks and inline code are ignored (case d).
* Candidate schema: {file_a, file_b, tag, keyword, sentence_a, sentence_b,
  polarity_a, polarity_b, score} (case e).
* CLI: --json is machine-readable; exit stays 0 when candidates exist
  (candidates are results for human review, not errors); the scan is
  zero-write (hermeticity); --tag limits the scan domain.
* PyYAML is used when importable; the regex fallback MUST work without it.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §4 Fixture coherence: every "0 candidates" case shares a tag AND overlapping
  content words with its counterpart, so a scanner that ignored tags or
  keywords entirely could not pass by accident — only the polarity check
  (case b), the tag grouping (case c) or the code stripper (case d) explains
  the outcome:
  - case (b): same tag, same words, same direction -> 0 (pins polarity gate);
  - case (c): opposite polarity, same words, different tags -> 0 (pins tag join);
  - case (f): same tag, overlapping words, no assertion markers -> 0 (pins
    the assertion gate, i.e. the scanner does not fire on plain prose).
* The positive control (case a) differs from each negative case by exactly one
  field, so a mutation of the polarity table, the tag join or the code
  stripper is guaranteed to flip at least one test in this file.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

# Import vault-conflict-scan.py (hyphenated name needs importlib)
_conflict_path = pathlib.Path(__file__).resolve().parent.parent / "vault-conflict-scan.py"
_spec = importlib.util.spec_from_file_location("vault_conflict_scan", _conflict_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _note(tags: list, body: str) -> str:
    tag_block = "\n".join(f"  - {t}" for t in tags)
    return (
        "---\n"
        'title: "fixture"\n'
        "created: 2026-03-01\n"
        "updated: 2026-03-01\n"
        "type: rules\n"
        "tags:\n"
        f"{tag_block}\n"
        "---\n"
        "\n"
        f"{body}\n"
    )


class TestScanForConflicts(unittest.TestCase):
    """API-level cases (a)-(d), (f): tmpdir vault, direct scan_for_conflicts."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "01-Rules").mkdir()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, name: str, tags: list, body: str) -> None:
        (self.vault / "01-Rules" / name).write_text(_note(tags, body), encoding="utf-8")

    # ---- case (a): opposite assertions + same tag -> exactly 1 candidate ----
    def test_opposite_assertions_same_tag_detected(self):
        self._write(
            "alpha.md",
            ["topic/x"],
            "并发场景下必须对缓存加锁。",
        )
        self._write(
            "beta.md",
            ["topic/x"],
            "并发场景禁止无锁读写缓存。",
        )

        candidates = _mod.scan_for_conflicts(self.vault)

        self.assertEqual(len(candidates), 1, candidates)
        cand = candidates[0]
        self.assertEqual(cand["tag"], "topic/x")
        self.assertEqual(cand["file_a"], "01-Rules/alpha.md")
        self.assertEqual(cand["file_b"], "01-Rules/beta.md")
        # file_a is the lexicographically first note, so its sentence is the
        # positive one — pin both directions explicitly.
        self.assertEqual(cand["polarity_a"], "positive")
        self.assertEqual(cand["polarity_b"], "negative")
        self.assertIn("必须", cand["sentence_a"])
        self.assertIn("禁止", cand["sentence_b"])
        self.assertTrue(cand["keyword"], cand)
        self.assertGreaterEqual(cand["score"], 1, cand)

    # ---- case (b): same tag, same direction (必须 + 应当) -> 0 ----
    def test_same_direction_assertions_not_detected(self):
        self._write("alpha.md", ["topic/x"], "并发场景必须加锁。")
        self._write("beta.md", ["topic/x"], "并发场景应当加锁。")

        candidates = _mod.scan_for_conflicts(self.vault)

        self.assertEqual(candidates, [], candidates)

    # ---- case (c): opposite polarity but different tags -> 0 ----
    def test_different_tags_not_grouped(self):
        self._write("alpha.md", ["topic/x"], "并发必须加锁。")
        self._write("beta.md", ["topic/y"], "并发禁止无锁。")

        candidates = _mod.scan_for_conflicts(self.vault)

        self.assertEqual(candidates, [], candidates)

    # ---- case (d): assertion inside fenced block / inline code -> ignored ----
    def test_code_block_assertions_ignored(self):
        self._write("alpha.md", ["topic/x"], "并发场景必须加锁。")
        self._write(
            "beta.md",
            ["topic/x"],
            "```\n并发场景禁止无锁读写\n```\n行内 `禁止无锁` 也不算断言。",
        )

        candidates = _mod.scan_for_conflicts(self.vault)

        self.assertEqual(candidates, [], candidates)

    # ---- case (f): same tag, overlapping words, no assertion markers -> 0 ----
    def test_prose_without_assertions_yields_zero(self):
        self._write("alpha.md", ["topic/x"], "本篇整理并发的背景资料。")
        self._write("beta.md", ["topic/x"], "并发概念源自操作系统课程。")

        candidates = _mod.scan_for_conflicts(self.vault)

        self.assertEqual(candidates, [], candidates)

    # ---- contract: PyYAML missing -> regex fallback parses the tag list ----
    def test_regex_fallback_parses_tags_without_yaml(self):
        block_style = "title: t\ntags:\n  - topic/x\n  - topic/y\ntype: rules\n"
        inline_list = "tags: [topic/a, topic/b]\n"
        inline_comma = "tags: topic/a, topic/b\n"

        original_yaml = _mod._yaml
        _mod._yaml = None  # simulate "PyYAML not installed"
        try:
            self.assertEqual(_mod._parse_frontmatter_tags(block_style), ["topic/x", "topic/y"])
            self.assertEqual(_mod._parse_frontmatter_tags(inline_list), ["topic/a", "topic/b"])
            self.assertEqual(_mod._parse_frontmatter_tags(inline_comma), ["topic/a", "topic/b"])
        finally:
            _mod._yaml = original_yaml


class TestCliJsonMode(unittest.TestCase):
    """CLI cases: --json schema (e), zero-write hermeticity, --tag, exit 0."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "01-Rules").mkdir()
        (self.vault / "01-Rules" / "alpha.md").write_text(
            _note(["topic/x"], "并发场景下必须对缓存加锁。"), encoding="utf-8"
        )
        (self.vault / "01-Rules" / "beta.md").write_text(
            _note(["topic/x"], "并发场景禁止无锁读写缓存。"), encoding="utf-8"
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_cli(self, *flags):
        """Invoke main() through argv, returning (exit_code, stdout, stderr)."""
        argv = ["vault-conflict-scan.py", "--vault-path", str(self.vault), *flags]
        out, err = io.StringIO(), io.StringIO()
        original_argv = sys.argv
        sys.argv = argv
        code = None
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                _mod.main()
        except SystemExit as exc:
            code = exc.code
        finally:
            sys.argv = original_argv
        return code, out.getvalue(), err.getvalue()

    def _snapshot(self) -> dict:
        return {
            str(p): p.read_bytes()
            for p in sorted(self.vault.rglob("*"))
            if p.is_file()
        }

    # ---- case (e): --json schema + zero-write hermeticity + exit 0 ----
    def test_json_schema_hermeticity_and_exit_zero(self):
        before = self._snapshot()

        code, out, err = self.run_cli("--json")

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(
            set(payload), {"vault_root", "tags_filter", "count", "candidates"}, payload
        )
        self.assertIsNone(payload["tags_filter"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["candidates"]), 1)
        cand = payload["candidates"][0]
        self.assertEqual(
            set(cand),
            {
                "file_a",
                "file_b",
                "tag",
                "keyword",
                "sentence_a",
                "sentence_b",
                "polarity_a",
                "polarity_b",
                "score",
            },
            cand,
        )
        self.assertEqual(cand["tag"], "topic/x")
        self.assertIn(cand["polarity_a"], ("positive", "negative"))
        # Hermeticity: the scan is read-only — byte-identical tree afterwards.
        self.assertEqual(self._snapshot(), before, "--json must not write anything")

    def test_tag_flag_limits_scan_domain(self):
        code, out, err = self.run_cli("--json", "--tag", "topic/other")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["count"], 0)

        code, out, err = self.run_cli("--json", "--tag", "topic/x")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["count"], 1)

    def test_human_mode_lists_candidates_and_exits_zero(self):
        code, out, err = self.run_cli()

        self.assertEqual(code, 0, err)
        # Occurrence precheck (§2): the candidate banner appears exactly once.
        self.assertEqual(len(re.findall(r"检出候选对: 1 条", out)), 1, out)
        self.assertIn("人工复核", out)


if __name__ == "__main__":
    unittest.main()
