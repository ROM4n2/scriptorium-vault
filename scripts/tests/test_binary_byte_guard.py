"""Tests for the raw-byte NUL (0x00) guard in vault-quality-check.py (Task 5).

Regression context
------------------
``03-Languages/C/C-STANDARDS.md`` line 78 carried 3 literal 0x00 bytes: the author
typed the two-character escape ``\\0`` as an actual NUL byte while writing a
``strncpy`` example. Consequence: ``file`` classified the note as ``data`` and
grep/ripgrep skipped it as binary, so ``search-vault.py`` (BM25),
``vault-quality-check.py``, ``vault-dedup.py`` and ``vault-auto-linker.py`` all
silently skipped a real knowledge asset — gate green, asset unreachable.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §2 Occurrence Precheck: every assertion below pins **exactly one** match; the
  counts are asserted mechanically (``assertEqual(len(...), 1)``) rather than by
  ``assertTrue(any(...))``, which would stay green if the guard fired twice or
  for the wrong reason.
* §1 Inversion / mutation — all claims below were actually run and observed:
  - M1 delete the ``_check_binary_bytes`` call in ``run_check`` -> 4 failed, 2 passed.
  - M2 make the guard fire unconditionally -> ``test_clean_file_emits_no_encoding_issue``
    and ``test_encoding_error_names_the_byte_and_line`` go red, so the negative
    case is alive rather than vacuously green.
  - M3a move the guard behind a strict ``decode('utf-8')`` that skips undecodable
    files -> only ``test_guard_reads_raw_bytes_not_decoded_text`` goes red.
  - M3b move the guard behind a lenient ``decode('utf-8', errors='ignore')``
    -> **all 6 still pass**. Honest limitation: 0x00 survives a lenient UTF-8
    decode as U+0000, so this suite does *not* discriminate that variant. The
    raw-byte read is still the mandated form because it cannot be defeated by a
    failing decode (M3a) or a future codec swap (UTF-16 text consumes 0x00 into
    characters and a post-decode check would see none).
"""
import importlib.util
import pathlib
import re
import tempfile
import unittest

# Import vault-quality-check.py (hyphenated name needs importlib)
_vqc_path = pathlib.Path(__file__).resolve().parent.parent / "vault-quality-check.py"
_spec = importlib.util.spec_from_file_location("vault_quality_check", _vqc_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
QualityChecker = _mod.VaultQualityChecker

# Valid frontmatter so the fixture's only ERROR can be the encoding one.
# Line layout is load-bearing: lines 1-10 are frontmatter, so the body line
# carrying the NUL byte is line 14 (see _write_note).
_FRONTMATTER = (
    "---\n"
    'title: "NUL guard fixture"\n'
    "created: 2026-09-08\n"
    "updated: 2026-09-08\n"
    "type: notes\n"
    "tags:\n"
    "  - category/rules\n"
    "status: stable\n"
    "audience: both\n"
    "---\n"
)

_NUL_LINE_NUMBER = 14


class TestBinaryByteGuard(unittest.TestCase):
    """A .md file containing literal 0x00 bytes MUST raise an ERROR/ENCODING issue."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "notes").mkdir()
        self.rel = "notes/nul-note.md"
        self.target = self.vault / "notes" / "nul-note.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_note(self, body_bytes: bytes) -> None:
        """Write the fixture with byte-level I/O so 0x00 survives verbatim."""
        payload = (
            _FRONTMATTER.encode("utf-8")          # lines 1-10
            + b"\n"                               # line 11 (blank)
            + b"# NUL Guard Fixture\n"            # line 12
            + b"\n"                               # line 13
            + body_bytes                          # line 14
            + b"\nTrailing prose.\n"              # line 15+
        )
        self.target.write_bytes(payload)

    def _run_checker(self):
        checker = QualityChecker(self.vault)
        summary = checker.run_check()
        return checker, summary

    def _encoding_errors(self, checker):
        return [
            i
            for i in checker.results.get(self.rel, [])
            if i.level == "ERROR" and i.category == "ENCODING"
        ]

    # ------------------------------------------------------------------ RED case

    def test_nul_byte_emits_encoding_error(self):
        """3 literal NUL bytes -> exactly one ERROR-severity ENCODING issue."""
        self._write_note(b"Use `strncpy`, then write `\x00` (`buf[n - 1] = '\x00'`) to \x00-terminate.")

        # Fixture self-coherence (TESTING-PATTERNS §4): the bytes really are on disk.
        self.assertEqual(self.target.read_bytes().count(b"\x00"), 3)

        checker, _ = self._run_checker()
        found = self._encoding_errors(checker)

        # Occurrence precheck (§2): exactly one issue pins this defect.
        self.assertEqual(
            len(found),
            1,
            f"expected exactly 1 ERROR/ENCODING issue, got {len(found)}: "
            f"{[(i.level, i.category, i.message) for i in checker.results.get(self.rel, [])]}",
        )

    def test_encoding_error_names_the_byte_and_line(self):
        """The message must identify the offending byte; the issue must carry its line."""
        self._write_note(b"Use `strncpy`, then write `\x00` (`buf[n - 1] = '\x00'`) to \x00-terminate.")
        checker, _ = self._run_checker()
        issue = self._encoding_errors(checker)[0]

        # Occurrence precheck (§2): 'NUL (0x00)' appears exactly once in the message,
        # so this assertion pins one phrase, not a family of them.
        self.assertEqual(len(re.findall(r"NUL \(0x00\)", issue.message)), 1, issue.message)
        self.assertEqual(len(re.findall(r"\b3\b", issue.message)), 1, issue.message)
        self.assertEqual(issue.line, _NUL_LINE_NUMBER)

    def test_nul_byte_trips_the_strict_gate(self):
        """The issue must reach stats['total_errors'] so --strict exits 1."""
        self._write_note(b"Use `strncpy`, then write `\x00` (`buf[n - 1] = '\x00'`) to \x00-terminate.")
        _, summary = self._run_checker()
        self.assertEqual(summary["stats"]["total_errors"], 1)
        self.assertEqual(summary["stats"]["files_with_errors"], 1)

    def test_guard_reads_raw_bytes_not_decoded_text(self):
        """A NUL sitting next to undecodable bytes must still fire.

        Verified kill (M3a): moving the guard behind a strict ``decode('utf-8')``
        that skips files raising UnicodeDecodeError turns *only this test* red —
        the other fixtures are valid UTF-8. Does NOT kill a lenient
        ``errors='ignore'`` decode (see module docstring, M3b).
        """
        self._write_note(b"broken \xff\xfe utf-8 with a \x00 byte")
        checker, _ = self._run_checker()
        self.assertEqual(len(self._encoding_errors(checker)), 1)

    # -------------------------------------------------------- anti-dead-test case

    def test_clean_file_emits_no_encoding_issue(self):
        """A clean note MUST NOT produce an ENCODING issue (guards a dead test)."""
        self._write_note(b"Use `strncpy`, then write `\\0` (`buf[n - 1] = '\\0'`) to NUL-terminate.")

        self.assertEqual(self.target.read_bytes().count(b"\x00"), 0)

        checker, summary = self._run_checker()
        encoding_issues = [
            i for i in checker.results.get(self.rel, []) if i.category == "ENCODING"
        ]
        self.assertEqual(
            len(encoding_issues),
            0,
            f"clean file must not be flagged: {[i.message for i in encoding_issues]}",
        )
        self.assertEqual(summary["stats"]["total_errors"], 0)

    def test_clean_file_is_actually_scanned(self):
        """The negative case must not be green because the fixture was skipped."""
        self._write_note(b"Use `strncpy`, then write `\\0` to NUL-terminate.")
        _, summary = self._run_checker()
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)


if __name__ == "__main__":
    unittest.main()
