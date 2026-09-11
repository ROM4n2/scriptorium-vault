"""Tests for _resolve_wikilink table pipe escape handling (Task 1.1)."""
import importlib.util
import pathlib
import tempfile
import unittest
import sys

# Import vault-quality-check.py (hyphenated name needs importlib)
_vqc_path = pathlib.Path(__file__).resolve().parent.parent / "vault-quality-check.py"
_spec = importlib.util.spec_from_file_location("vault_quality_check", _vqc_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
QualityChecker = _mod.VaultQualityChecker


class TestResolveWikilinkEscapedPipe(unittest.TestCase):
    """Test that escaped pipe (\|) in wikilinks is handled correctly."""

    def setUp(self):
        """Create a minimal vault structure for testing."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)

        # Create target files
        (self.vault / "docs").mkdir()
        (self.vault / "docs" / "示例项目-V4.8-ARCHITECTURE.md").write_text("# Title\n")
        (self.vault / "docs" / "POST-MORTEM-V5.0.1.md").write_text("# Title\n")
        (self.vault / "docs" / "simple.md").write_text("# Simple\n")
        (self.vault / "Templates").mkdir()
        (self.vault / "Templates" / "tpl-test.md").write_text("# Template\n")

        self.checker = QualityChecker(self.vault)
        # Manually populate all_files_rel so _resolve_wikilink can find targets
        self.checker.all_files_rel = set()
        for f in self.vault.rglob("*.md"):
            rel = str(f.relative_to(self.vault)).replace("\\", "/")
            self.checker.all_files_rel.add(rel)
            stem = f.stem
            if stem not in self.checker.all_stems:
                self.checker.all_stems[stem] = []
            self.checker.all_stems[stem].append(f)

        self.source = self.vault / "docs" / "test-note.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_escaped_pipe_in_table_resolves(self):
        """[[path\|alias]] should resolve to the file, not treat \| as separator."""
        link = "docs/示例项目-V4.8-ARCHITECTURE\\|V4.8-ARCHITECTURE"
        exists, desc = self.checker._resolve_wikilink(self.source, link)
        self.assertTrue(exists, f"Escaped pipe link should resolve: {desc}")

    def test_normal_pipe_alias_resolves(self):
        """[[path|alias]] should still work (normal alias)."""
        link = "docs/simple|Simple Note"
        exists, desc = self.checker._resolve_wikilink(self.source, link)
        self.assertTrue(exists, f"Normal pipe link should resolve: {desc}")

    def test_heading_anchor_resolves(self):
        """[[path#heading]] should resolve with anchor."""
        link = "docs/simple#Title"
        exists, desc = self.checker._resolve_wikilink(self.source, link)
        self.assertTrue(exists, f"Heading link should resolve: {desc}")

    def test_escaped_pipe_with_dots_resolves(self):
        """The intersection bug: [[path.with.dots\|alias]] should resolve."""
        link = "docs/POST-MORTEM-V5.0.1\\|POST-MORTEM"
        exists, desc = self.checker._resolve_wikilink(self.source, link)
        self.assertTrue(exists, f"Dots + escaped pipe should resolve: {desc}")

    def test_nonexistent_file_returns_false(self):
        """A link to a nonexistent file should return False."""
        link = "docs/DOES-NOT-EXIST"
        exists, desc = self.checker._resolve_wikilink(self.source, link)
        self.assertFalse(exists)


if __name__ == "__main__":
    unittest.main()
