"""Tests for `vault-claim-ledger.py` — claim-ledger one-way deriver (#9+#16).

Contract pinned here (ROADMAP-P4 Task-2; normative truth source
08-Projects/README.md §1/§7)
----------------------------------------------------------------------
* scan_notes() walks every *.md (vault exclusion convention: EXCLUDED_DIRS +
  root infrastructure files, same as vault-conflict-scan.py) and parses the
  frontmatter: title/type/tags/source plus the three credibility fields.
  PyYAML is used when importable; the regex fallback MUST work without it.
* Default semantics (SCHEMA §1): authority missing -> "unknown" AND the note
  lands in stats.missing_authority; claim_risk missing -> "none";
  review_status missing -> "unreviewed". Explicit values are kept verbatim
  (illegal values stay visible so --check can flag them).
* derive_ledger(notes) emits {generated_at, script, vault_root, files,
  sources_summary, stats}; files[] entries carry exactly {rel, title, type,
  tags, authority, claim_risk, review_status, source, claims:[{line}]}.
* claims extraction: body lines (leading markdown list/quote/heading
  decorations stripped, fenced code blocks ignored) starting with
  必须|禁止|不得|应|推荐|MUST|SHOULD|NEVER|is |is not (case-sensitive per
  contract), capped at 20 lines per file.
* sources_summary (#16 并入): one entry per unique non-empty source with
  note_count, max_authority (rank official>primary>secondary>community>
  synthetic>unknown), reviewed_count and deduplicated dirs.
* CLI: --dry-run and --json are strictly read-only; --check exits 1 on (a)
  any illegal enum value or (b) an all-unknown vault (「全 unknown」 — ADR-0001
  #9 wording contrasts 全 unknown vs 有非法枚举 within one clause, and SCHEMA
  §2.2 declares unknown a legal deferred state, so PARTIAL unknown stays
  exit 0); default mode writes 11-Agents/可信度账本「自动生成」.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* Fixture coherence: the three-note fixture interleaves assertion lines with
  heading/quote/prose/inline-code/fenced lines, so a claims miner that ignored
  fences or prefixes cannot pass by accident; the cap test uses exactly 25
  assertion lines so an off-by-one limit flips the count.
* --check cases cover all four quadrants: all-unknown -> 1, all-annotated ->
  0, partial-unknown -> 0, illegal-enum -> 1.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest

# Import vault-claim-ledger.py (hyphenated name needs importlib)
_ledger_path = pathlib.Path(__file__).resolve().parent.parent / "vault-claim-ledger.py"
_spec = importlib.util.spec_from_file_location("vault_claim_ledger", _ledger_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


OFFICIAL_NOTE = """---
title: "Fixture Standards"
created: 2026-09-09
updated: 2026-09-09
type: standards
tags:
  - topic/fixture
source: "Fixture Source X"
authority: official
claim_risk: high
review_status: reviewed
---

## 并发规范

- 必须先申请锁再读写缓存。
* 禁止在持锁期间调用外部 IO。
1. 不得静默吞掉锁超时异常。
> 推荐为锁超时记录告警日志。
普通叙述行不算断言。
- 行内 `禁止` 标记不算断言行。

```bash
# 必须 export 变量后再验证
```
"""

UNKNOWN_NOTE = """---
title: "Fixture Unknown"
type: notes
tags:
  - topic/fixture
source: "Fixture Source Y"
---

这是一个来源不明的笔记，没有三字段标注。

- MUST 只在显式标注 authority 后作为决策依据。
should 小写不触发（前缀大小写敏感）。
is not 官方原文，仅为网络摘录。
"""

SYNTHETIC_NOTE = """---
title: "Fixture Project"
type: project
tags:
  - project/fixture
source: "Fixture Source X"
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

本库工程推导的项目约束。

- 应当在提交前运行质量门禁。
"""

EXPECTED_OFFICIAL_CLAIMS = [
    "必须先申请锁再读写缓存。",
    "禁止在持锁期间调用外部 IO。",
    "不得静默吞掉锁超时异常。",
    "推荐为锁超时记录告警日志。",
]
EXPECTED_UNKNOWN_CLAIMS = [
    "MUST 只在显式标注 authority 后作为决策依据。",
    "is not 官方原文，仅为网络摘录。",
]


def _write_note(vault: pathlib.Path, rel: str, content: str) -> None:
    target = vault / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _seed_main_fixture(vault: pathlib.Path) -> None:
    _write_note(vault, "01-Rules/standards-fixture.md", OFFICIAL_NOTE)
    _write_note(vault, "06-Sources/unknown-fixture.md", UNKNOWN_NOTE)
    _write_note(vault, "08-Projects/project-fixture.md", SYNTHETIC_NOTE)


def _snapshot(vault: pathlib.Path) -> dict:
    return {
        str(p): p.read_bytes()
        for p in sorted(vault.rglob("*"))
        if p.is_file()
    }


class TestScanNotes(unittest.TestCase):
    """API-level case (a): tmpdir vault, direct scan_notes."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        _seed_main_fixture(self.vault)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _by_rel(self) -> dict:
        records = _mod.scan_notes(self.vault)
        return {record["rel"]: record for record in records}

    # ---- case (a): three fields + source parsed; missing -> defaults ----
    def test_scan_parses_three_fields_and_source(self):
        records = self._by_rel()

        official = records["01-Rules/standards-fixture.md"]
        self.assertEqual(official["title"], "Fixture Standards")
        self.assertEqual(official["type"], "standards")
        self.assertEqual(official["tags"], ["topic/fixture"])
        self.assertEqual(official["source"], "Fixture Source X")
        self.assertEqual(official["authority"], "official")
        self.assertEqual(official["claim_risk"], "high")
        self.assertEqual(official["review_status"], "reviewed")
        self.assertFalse(official["authority_missing"])

        unknown = records["06-Sources/unknown-fixture.md"]
        self.assertEqual(unknown["source"], "Fixture Source Y")
        self.assertEqual(unknown["authority"], "unknown")  # SCHEMA §1 default
        self.assertTrue(unknown["authority_missing"])
        self.assertEqual(unknown["claim_risk"], "none")
        self.assertEqual(unknown["review_status"], "unreviewed")

        synthetic = records["08-Projects/project-fixture.md"]
        self.assertEqual(synthetic["authority"], "synthetic")
        self.assertEqual(synthetic["claim_risk"], "medium")
        self.assertEqual(synthetic["review_status"], "unreviewed")
        self.assertFalse(synthetic["authority_missing"])

        # Deterministic order: sorted by POSIX rel path.
        self.assertEqual(
            sorted(records),
            ["01-Rules/standards-fixture.md",
             "06-Sources/unknown-fixture.md",
             "08-Projects/project-fixture.md"],
        )

    # ---- case (d, part 1): claims = assertion lines only ----
    def test_claims_contain_only_assertion_lines(self):
        records = self._by_rel()
        self.assertEqual(
            [claim["line"] for claim in records["01-Rules/standards-fixture.md"]["claims"]],
            EXPECTED_OFFICIAL_CLAIMS,
        )
        self.assertEqual(
            [claim["line"] for claim in records["06-Sources/unknown-fixture.md"]["claims"]],
            EXPECTED_UNKNOWN_CLAIMS,
        )
        self.assertEqual(
            [claim["line"] for claim in records["08-Projects/project-fixture.md"]["claims"]],
            ["应当在提交前运行质量门禁。"],
        )

    # ---- case (d, part 2): per-file cap of 20 claim lines ----
    def test_claim_lines_capped_at_twenty(self):
        tmpdir = tempfile.TemporaryDirectory()
        try:
            vault = pathlib.Path(tmpdir.name)
            body = "\n".join(f"- 必须第{i:02d}条约束。" for i in range(1, 26))
            _write_note(vault, "03-Languages/cap-fixture.md",
                        "---\ntitle: cap\n---\n\n" + body + "\n")
            records = {r["rel"]: r for r in _mod.scan_notes(vault)}
            claims = records["03-Languages/cap-fixture.md"]["claims"]
            self.assertEqual(len(claims), 20, "claim cap must be 20 per file")
            self.assertEqual(claims[0]["line"], "必须第01条约束。")
            self.assertEqual(claims[-1]["line"], "必须第20条约束。")
        finally:
            tmpdir.cleanup()

    # ---- note without frontmatter: included with default semantics ----
    def test_frontmatter_less_note_gets_defaults(self):
        tmpdir = tempfile.TemporaryDirectory()
        try:
            vault = pathlib.Path(tmpdir.name)
            _write_note(vault, "10-Daily/plain-fixture.md",
                        "今天只是随手记录。\n- 不得遗忘这条无 frontmatter 的断言。\n")
            records = {r["rel"]: r for r in _mod.scan_notes(vault)}
            record = records["10-Daily/plain-fixture.md"]
            self.assertEqual(record["title"], "")
            self.assertEqual(record["type"], "")
            self.assertEqual(record["tags"], [])
            self.assertIsNone(record["source"])
            self.assertEqual(record["authority"], "unknown")
            self.assertTrue(record["authority_missing"])
            self.assertEqual(record["claim_risk"], "none")
            self.assertEqual(record["review_status"], "unreviewed")
            self.assertEqual(
                [claim["line"] for claim in record["claims"]],
                ["不得遗忘这条无 frontmatter 的断言。"],
            )
        finally:
            tmpdir.cleanup()

    # ---- contract: PyYAML missing -> regex fallback parses the fields ----
    def test_regex_fallback_parses_fields_without_yaml(self):
        fm_text = (
            'title: "Fixture Standards"\n'
            "created: 2026-09-09\n"
            "type: standards\n"
            "tags:\n"
            "  - topic/fixture\n"
            'source: "Fixture Source X"\n'
            "authority: official\n"
            "claim_risk: high\n"
            "review_status: reviewed\n"
        )
        original_yaml = _mod._yaml
        _mod._yaml = None  # simulate "PyYAML not installed"
        try:
            fields = _mod._parse_frontmatter(fm_text)
        finally:
            _mod._yaml = original_yaml
        self.assertEqual(fields["title"], "Fixture Standards")
        self.assertEqual(fields["type"], "standards")
        self.assertEqual(fields["tags"], ["topic/fixture"])
        self.assertEqual(fields["source"], "Fixture Source X")
        self.assertEqual(fields["authority"], "official")
        self.assertEqual(fields["claim_risk"], "high")
        self.assertEqual(fields["review_status"], "reviewed")


class TestDeriveLedger(unittest.TestCase):
    """API-level cases (b)/(c): stats + sources_summary over the main fixture."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        _seed_main_fixture(self.vault)
        self.notes = _mod.scan_notes(self.vault)
        self.ledger = _mod.derive_ledger(self.notes, vault_root=self.vault)

    def tearDown(self):
        self.tmpdir.cleanup()

    # ---- case (b): stats counts are exact ----
    def test_stats_counts(self):
        stats = self.ledger["stats"]
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["with_authority"], 2)
        self.assertEqual(stats["official"], 1)
        self.assertEqual(stats["primary"], 0)
        self.assertEqual(stats["secondary"], 0)
        self.assertEqual(stats["community"], 0)
        self.assertEqual(stats["synthetic"], 1)
        self.assertEqual(stats["unknown"], 1)
        self.assertEqual(
            stats["missing_authority"], ["06-Sources/unknown-fixture.md"]
        )

    # ---- case (c) + #16: sources_summary aggregation ----
    def test_sources_summary_aggregation(self):
        summary = self.ledger["sources_summary"]
        self.assertEqual(
            [entry["source"] for entry in summary],
            ["Fixture Source X", "Fixture Source Y"],  # unique, sorted
        )
        by_source = {entry["source"]: entry for entry in summary}

        shared = by_source["Fixture Source X"]
        self.assertEqual(shared["note_count"], 2)
        # official ranks above synthetic (official>primary>secondary>
        # community>synthetic>unknown)
        self.assertEqual(shared["max_authority"], "official")
        self.assertEqual(shared["reviewed_count"], 1)
        self.assertEqual(shared["dirs"], ["01-Rules", "08-Projects"])  # deduped

        solo = by_source["Fixture Source Y"]
        self.assertEqual(solo["note_count"], 1)
        self.assertEqual(solo["max_authority"], "unknown")
        self.assertEqual(solo["reviewed_count"], 0)
        self.assertEqual(solo["dirs"], ["06-Sources"])

    # ---- files[] schema: exact keys, internal flag not leaked ----
    def test_files_schema_exact_keys_and_ordering(self):
        files = self.ledger["files"]
        self.assertEqual(
            [entry["rel"] for entry in files],
            ["01-Rules/standards-fixture.md",
             "06-Sources/unknown-fixture.md",
             "08-Projects/project-fixture.md"],
        )
        for entry in files:
            self.assertEqual(
                set(entry),
                {"rel", "title", "type", "tags", "authority", "claim_risk",
                 "review_status", "source", "claims"},
                entry,
            )
        for entry in files:
            for claim in entry["claims"]:
                self.assertEqual(set(claim), {"line"}, claim)
        self.assertNotIn(
            "authority_missing", files[0], "internal flag must not leak"
        )

    # ---- brief signature: derive_ledger(notes) works without vault_root ----
    def test_derive_ledger_minimal_signature_and_metadata(self):
        ledger = _mod.derive_ledger(self.notes)
        self.assertEqual(ledger["vault_root"], "")
        self.assertEqual(ledger["script"], "scripts/vault-claim-ledger.py")
        # generated_at must be a parseable ISO timestamp.
        datetime_obj = _mod.datetime.datetime.fromisoformat(ledger["generated_at"])
        self.assertIsNotNone(datetime_obj)
        self.assertEqual(
            set(ledger),
            {"generated_at", "script", "vault_root", "files",
             "sources_summary", "stats"},
        )


class TestCli(unittest.TestCase):
    """CLI cases (e)/(f): --dry-run / --json / --check / default write."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_cli(self, *flags):
        """Invoke main() through argv, returning (exit_code, stdout, stderr)."""
        argv = ["vault-claim-ledger.py", "--vault-path", str(self.vault), *flags]
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

    # ---- case (e): --dry-run does not write the ledger ----
    def test_dry_run_leaves_vault_untouched(self):
        _seed_main_fixture(self.vault)
        before = _snapshot(self.vault)

        code, out, err = self.run_cli("--dry-run")

        self.assertEqual(code, 0, err)
        self.assertFalse((self.vault / "11-Agents").exists())
        self.assertFalse((self.vault / "11-Agents/可信度账本「自动生成」").exists())
        self.assertEqual(_snapshot(self.vault), before, "--dry-run must not write")
        # The report names the would-be output path.
        self.assertIn("11-Agents/可信度账本「自动生成」", out)

    # ---- case (e): --json stdout schema is legal and read-only ----
    def test_json_stdout_schema_and_readonly(self):
        _seed_main_fixture(self.vault)
        before = _snapshot(self.vault)

        code, out, err = self.run_cli("--json")

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(
            set(payload),
            {"generated_at", "script", "vault_root", "files",
             "sources_summary", "stats"},
            payload,
        )
        self.assertEqual(payload["vault_root"], str(self.vault).replace("\\", "/"))
        self.assertEqual(payload["script"], "scripts/vault-claim-ledger.py")
        self.assertEqual(payload["stats"]["total"], 3)
        self.assertEqual(len(payload["files"]), 3)
        first = payload["files"][0]
        self.assertEqual(
            set(first),
            {"rel", "title", "type", "tags", "authority", "claim_risk",
             "review_status", "source", "claims"},
            first,
        )
        self.assertEqual(set(first["claims"][0]), {"line"})
        self.assertEqual(
            set(payload["sources_summary"][0]),
            {"source", "note_count", "max_authority", "reviewed_count", "dirs"},
        )
        self.assertEqual(
            set(payload["stats"]),
            {"total", "with_authority", "official", "primary", "secondary",
             "community", "synthetic", "unknown", "missing_authority"},
        )
        # Read-only: --json must not write anything.
        self.assertFalse((self.vault / "11-Agents").exists())
        self.assertEqual(_snapshot(self.vault), before, "--json must not write")

    # ---- default mode is the ONLY writing mode ----
    def test_default_mode_writes_ledger_file(self):
        _seed_main_fixture(self.vault)
        before = _snapshot(self.vault)

        code, out, err = self.run_cli()

        self.assertEqual(code, 0, err)
        ledger_path = self.vault / "11-Agents" / "可信度账本「自动生成」"
        self.assertTrue(ledger_path.exists())
        added = set(_snapshot(self.vault)) - set(before)
        self.assertEqual(added, {str(ledger_path)}, "default mode writes only the ledger")
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["stats"]["total"], 3)
        self.assertEqual(payload["files"][0]["rel"], "01-Rules/standards-fixture.md")

    # ---- case (f): all unknown -> exit 1 (nothing judged yet) ----
    def test_check_all_unknown_exits_one(self):
        _write_note(self.vault, "06-Sources/solo-fixture.md", UNKNOWN_NOTE)

        code, out, err = self.run_cli("--check")

        self.assertEqual(code, 1)
        self.assertFalse((self.vault / "11-Agents").exists(), "--check is read-only")
        # missing 计数 must be reported on stdout.
        self.assertIn("missing=1", out)

    # ---- case (f): fully annotated -> exit 0 ----
    def test_check_all_annotated_exits_zero(self):
        _write_note(self.vault, "01-Rules/standards-fixture.md", OFFICIAL_NOTE)
        _write_note(self.vault, "08-Projects/project-fixture.md", SYNTHETIC_NOTE)

        code, out, err = self.run_cli("--check")

        self.assertEqual(code, 0, err)

    # ---- case (f), partial pin: mixed vault stays exit 0 ----
    def test_check_partial_annotation_exits_zero(self):
        # 「全 unknown → exit 1」 is literal (ADR-0001 #9 contrasts 全 unknown
        # vs 有非法枚举 in one clause); SCHEMA §2.2: unknown is a legal deferred
        # state, so a partially-annotated vault is not a check failure.
        _seed_main_fixture(self.vault)

        code, out, err = self.run_cli("--check")

        self.assertEqual(code, 0, err)

    # ---- case (f): illegal enum -> exit 1 ----
    def test_check_illegal_enum_exits_one(self):
        _write_note(
            self.vault,
            "06-Sources/bogus-fixture.md",
            UNKNOWN_NOTE.replace('title: "Fixture Unknown"', 'title: "Bogus"')
            .replace("---\n\n这是一个", "authority: bogus\n---\n\n这是一个"),
        )

        code, out, err = self.run_cli("--check")

        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
