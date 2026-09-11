#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contract tests: capabilities.json is the single source of truth (P3 Task-1).

Spec: 08-Projects/项目档案/ROADMAP-P3-CONFIG-CONTRACTS.md Task 1
      + ADR-0001 §4 #7 ("capabilities.json 唯一真值源 + 反查漂移 + 渲染").

Five contract clauses (mirrors the plan's TDD step list):

(a) Schema load — ``load_capabilities()`` returns 17 capabilities, every schema
    field present, scope pinned to "read-only", ``confirmation_required`` True
    exactly when no automatic verifier exists, and any capability without a
    ``verification_command`` declares ``configured`` (never a fake "verified").
(b) ``--check-drift`` — JSON vs Markdown set comparison keyed on
    (name, type, tier, verification_command); a deleted matrix row exits 1,
    the restored matrix exits 0.
(c) ``--render-matrix`` — regenerating the marker-wrapped tables
    (``<!-- MATRIX:BEGIN -->`` / ``<!-- MATRIX:END -->``) from JSON is
    idempotent: two consecutive renders leave an identical marker block,
    and the rendered rows parse back with zero drift against the JSON.
(d) Unknown ``declared_status`` raises ValueError (no silent enum drift).
(e) Static clause — the live-verification path consumes the JSON loader
    (``capabilities = load_capabilities(...)``); ``parse_matrix`` stays as the
    Markdown side of the drift cross-check only.

RED-first note: every test here failed before Task-1 landed — no
capabilities.json existed and capability-check.py had neither --check-drift
nor --render-matrix. The legacy script silently ignored unknown argv and ran
the full live verification instead, so the CLI tests fail on their exit-code
and marker-block assertions, which is the intended red.
"""
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

# Prevent Windows GBK stdout/stderr trap (Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
VAULT_ROOT = _SCRIPTS_DIR.parent
CAPABILITY_CHECK_PATH = _SCRIPTS_DIR / "capability-check.py"
CAPABILITIES_PATH = VAULT_ROOT / "05-Tools" / "capabilities.json"
MATRIX_PATH = VAULT_ROOT / "05-Tools" / "CAPABILITY-MATRIX.md"

MATRIX_BEGIN = "<!-- MATRIX:BEGIN -->"
MATRIX_END = "<!-- MATRIX:END -->"

EXPECTED_CAPABILITY_COUNT = 17
# The three-section layout migrated verbatim from the committed matrix.
EXPECTED_SECTION_COUNTS = {"scripts": 11, "mcp": 4, "skills": 2}
REQUIRED_FIELDS = (
    "name", "type", "tier", "verification_command",
    "declared_status", "section", "scope", "confirmation_required",
)
LEGAL_STATUS = {"verified", "configured", "degraded"}

# Reuse the production module (hyphenated filename needs importlib).
_spec = importlib.util.spec_from_file_location("capability_check", CAPABILITY_CHECK_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_SOURCE = CAPABILITY_CHECK_PATH.read_text(encoding="utf-8")


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run capability-check.py in the real vault (same interpreter as pytest)."""
    return subprocess.run(
        [sys.executable, str(CAPABILITY_CHECK_PATH), *args],
        cwd=str(VAULT_ROOT), capture_output=True, timeout=300,
    )


def _stdout(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout.decode("utf-8", "replace")


def _marker_block(text: str) -> str:
    """The exact text from <!-- MATRIX:BEGIN --> through <!-- MATRIX:END -->."""
    begin = text.index(MATRIX_BEGIN)
    end = text.index(MATRIX_END)
    return text[begin:end + len(MATRIX_END)]


class TestLoadCapabilitiesSchema(unittest.TestCase):
    """Clause (a): the JSON contract, loaded through the production loader."""

    @classmethod
    def setUpClass(cls):
        cls.caps = _mod.load_capabilities(CAPABILITIES_PATH)

    def test_json_source_exists(self):
        self.assertTrue(CAPABILITIES_PATH.exists(), f"missing {CAPABILITIES_PATH}")

    def test_schema_version_and_tooling(self):
        data = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["generated_tooling"], "capability-check.py")

    def test_loads_seventeen_capabilities(self):
        self.assertEqual(len(self.caps), EXPECTED_CAPABILITY_COUNT)

    def test_every_capability_has_all_schema_fields(self):
        for cap in self.caps:
            missing = [field for field in REQUIRED_FIELDS if field not in cap]
            self.assertEqual(missing, [], f"{cap.get('name')}: missing fields {missing}")

    def test_section_counts_match_the_migrated_matrix(self):
        counts = {}
        for cap in self.caps:
            counts[cap["section"]] = counts.get(cap["section"], 0) + 1
        self.assertEqual(counts, EXPECTED_SECTION_COUNTS)

    def test_scope_is_read_only_everywhere(self):
        offenders = [c["name"] for c in self.caps if c["scope"] != "read-only"]
        self.assertEqual(offenders, [])

    def test_confirmation_required_is_bool_and_tracks_the_verifier(self):
        for cap in self.caps:
            self.assertIsInstance(cap["confirmation_required"], bool, cap["name"])
            self.assertEqual(
                cap["confirmation_required"], cap["verification_command"] is None,
                f"{cap['name']}: confirmation_required must be True exactly when "
                "no automatic verifier exists",
            )

    def test_no_verifier_implies_configured(self):
        offenders = [
            c["name"] for c in self.caps
            if c["verification_command"] is None and c["declared_status"] != "configured"
        ]
        self.assertEqual(offenders, [])

    def test_declared_status_within_legal_enum(self):
        offenders = [
            c["name"] for c in self.caps if c["declared_status"] not in LEGAL_STATUS
        ]
        self.assertEqual(offenders, [])

    def test_unknown_declared_status_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
            data["capabilities"][0]["declared_status"] = "bogus-status"
            bad = pathlib.Path(tmp) / "bad.json"
            bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                _mod.load_capabilities(bad)

    def test_missing_field_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
            del data["capabilities"][0]["scope"]
            bad = pathlib.Path(tmp) / "bad.json"
            bad.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                _mod.load_capabilities(bad)


class TestCheckDrift(unittest.TestCase):
    """Clause (b): JSON vs Markdown alignment on the 4-field drift key."""

    def test_drift_report_empty_for_the_committed_pair(self):
        report = _mod.drift_report(
            _mod.load_capabilities(CAPABILITIES_PATH),
            _mod.parse_matrix(MATRIX_PATH),
        )
        self.assertEqual(report, [])

    def test_drift_report_names_a_deleted_matrix_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = MATRIX_PATH.read_text(encoding="utf-8")
            lines = [ln for ln in text.split("\n") if not ln.startswith("| vault-tools |")]
            self.assertEqual(
                len(text.split("\n")) - len(lines), 1,
                "occurrence precheck: expected exactly one vault-tools row",
            )
            reduced = pathlib.Path(tmp) / "CAPABILITY-MATRIX.md"
            reduced.write_text("\n".join(lines), encoding="utf-8", newline="")
            report = _mod.drift_report(
                _mod.load_capabilities(CAPABILITIES_PATH),
                _mod.parse_matrix(reduced),
            )
        self.assertEqual(len(report), 1, report)
        self.assertIn("vault-tools", report[0])

    def test_cli_check_drift_exits_one_on_deleted_row_and_zero_after_restore(self):
        original = MATRIX_PATH.read_bytes()
        try:
            text = original.decode("utf-8")
            kept = [ln for ln in text.split("\n") if not ln.startswith("| vault-tools |")]
            self.assertEqual(
                len(text.split("\n")) - len(kept), 1,
                "occurrence precheck: expected exactly one vault-tools row",
            )
            MATRIX_PATH.write_bytes("\n".join(kept).encode("utf-8"))
            proc = _run_cli("--check-drift")
            self.assertEqual(
                proc.returncode, 1,
                f"expected drift exit 1, stdout:\n{_stdout(proc)}",
            )
            self.assertIn("vault-tools", _stdout(proc))
        finally:
            MATRIX_PATH.write_bytes(original)
        restored = _run_cli("--check-drift")
        self.assertEqual(restored.returncode, 0, _stdout(restored))


class TestRenderMatrixIdempotent(unittest.TestCase):
    """Clause (c): JSON → marker block render is deterministic and drift-free."""

    def test_render_twice_leaves_identical_marker_block(self):
        first = _run_cli("--render-matrix")
        self.assertEqual(first.returncode, 0, _stdout(first))
        block1 = _marker_block(MATRIX_PATH.read_text(encoding="utf-8"))
        second = _run_cli("--render-matrix")
        self.assertEqual(second.returncode, 0, _stdout(second))
        block2 = _marker_block(MATRIX_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            block1, block2,
            "marker block changed between consecutive renders — render is not deterministic",
        )

    def test_rendered_block_has_zero_drift_against_json(self):
        report = _mod.drift_report(
            _mod.parse_matrix(MATRIX_PATH),
            _mod.load_capabilities(CAPABILITIES_PATH),
        )
        self.assertEqual(report, [])

    def test_rendered_block_contains_all_three_sections(self):
        block = _marker_block(MATRIX_PATH.read_text(encoding="utf-8"))
        for title in (
            "### Scripts（脚本）",
            "### MCP Services（MCP 服务）",
            "### Skills（技能，清理后）",
        ):
            self.assertIn(title, block)


class TestMainConsumesJsonSource(unittest.TestCase):
    """Clause (e): the live-verification path reads JSON, not the markdown parser."""

    def test_main_uses_load_capabilities_exactly_once(self):
        hits = re.findall(r"capabilities = load_capabilities\(", _SOURCE)
        self.assertEqual(len(hits), 1, hits)


if __name__ == "__main__":
    unittest.main()
