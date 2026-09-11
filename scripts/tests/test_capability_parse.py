"""Tests for CAPABILITY-MATRIX verification_command parsing (Task 2).

Bug under test: the markdown cell wraps the command in backticks. Passing that
raw cell to `subprocess.run(..., shell=True)` makes bash treat the backticks as
command substitution, so every backtick-wrapped capability falsely reports
`degraded`.
"""
import importlib.util
import pathlib
import re
import tempfile
import unittest

# Import capability-check.py (hyphenated name needs importlib)
_cc_path = pathlib.Path(__file__).resolve().parent.parent / "capability-check.py"
_spec = importlib.util.spec_from_file_location("capability_check", _cc_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Table fragment mirroring the "Scripts" table of 05-Tools/CAPABILITY-MATRIX.md.
# Row 1: backtick-wrapped command (the bug).
# Row 2: em-dash placeholder (no verifier).
# Row 3: backticks plus padding whitespace inside them.
# Row 4: bare command, no backticks at all.
MATRIX_FRAGMENT = """\
| 能力 | 类型 | tier | verification_command | 状态 |
| --- | --- | --- | --- | --- |
| vault-quality-check | script | core | `python scripts/vault-quality-check.py --strict` | verified |
| vault-dedup | script | extension | — | configured |
| padded-cmd | script | core | `  python scripts/padded.py  ` | verified |
| bare-cmd | script | core | python scripts/bare.py | verified |
"""

EXPECTED_QUALITY_CHECK_CMD = "python scripts/vault-quality-check.py --strict"
EXPECTED_ROW_COUNT = 4


class TestCapabilityVerificationCommandParse(unittest.TestCase):
    """parse_matrix must hand subprocess a bare shell command, never markdown syntax."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        matrix = pathlib.Path(self.tmpdir.name) / "CAPABILITY-MATRIX.md"
        matrix.write_text(MATRIX_FRAGMENT, encoding="utf-8")
        self.caps = _mod.parse_matrix(matrix)
        self.by_name = {c["name"]: c for c in self.caps}

        # Fixture coherence (TESTING-PATTERNS §4): the header and separator rows
        # must be filtered out and every data row must parse to a distinct name,
        # otherwise the assertions below would be pinning the wrong row.
        self.assertEqual(len(self.caps), EXPECTED_ROW_COUNT,
                         f"fixture drifted, parsed rows: {[c['name'] for c in self.caps]}")
        self.assertEqual(len(self.by_name), EXPECTED_ROW_COUNT,
                         "duplicate capability names in fixture")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fixture_pins_exactly_one_backticked_row(self):
        """Occurrence precheck (TESTING-PATTERNS §2): the pinned row appears once."""
        pattern = r"^\| vault-quality-check \|.*\|$"
        hits = re.findall(pattern, MATRIX_FRAGMENT, re.MULTILINE)
        self.assertEqual(len(hits), 1, f"pattern matched {len(hits)} rows: {hits}")

    def test_backtick_wrapped_command_keeps_no_backtick(self):
        """A backtick in the parsed command becomes shell command substitution."""
        cmd = self.by_name["vault-quality-check"]["verification_command"]
        self.assertNotIn("`", cmd, f"backtick survived parsing: {cmd!r}")

    def test_backtick_wrapped_command_equals_bare_command(self):
        """The parsed command must be exactly the runnable command, nothing more."""
        cmd = self.by_name["vault-quality-check"]["verification_command"]
        self.assertEqual(cmd, EXPECTED_QUALITY_CHECK_CMD)

    def test_padded_backtick_cell_is_trimmed(self):
        """Whitespace inside the backticks must not leak into the command."""
        cmd = self.by_name["padded-cmd"]["verification_command"]
        self.assertEqual(cmd, "python scripts/padded.py")

    def test_bare_cell_without_backticks_is_unchanged(self):
        """Cells that were never backtick-wrapped must survive verbatim."""
        cmd = self.by_name["bare-cmd"]["verification_command"]
        self.assertEqual(cmd, "python scripts/bare.py")

    def test_em_dash_cell_yields_none(self):
        """The 'no verifier' placeholder must stay None, never become a command."""
        cmd = self.by_name["vault-dedup"]["verification_command"]
        self.assertIsNone(cmd)


if __name__ == "__main__":
    unittest.main()
