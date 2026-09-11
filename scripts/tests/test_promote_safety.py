"""Tests for promote_inbox_draft path traversal and safety (Task 3.2)."""
import importlib.util
import pathlib
import tempfile
import unittest
import sys

# Import vault_search_mcp.py
_vsm_path = pathlib.Path(__file__).resolve().parent.parent / "vault_search_mcp.py"
_spec = importlib.util.spec_from_file_location("vault_search_mcp", _vsm_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestPromoteInboxDraftSafety(unittest.TestCase):
    """Test that promote_inbox_draft blocks path traversal and fuzzy match abuse."""

    def setUp(self):
        """Create a temporary vault with inbox and target dirs."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)

        # Override VAULT_ROOT in the module
        self._orig_vault_root = _mod.VAULT_ROOT
        _mod.VAULT_ROOT = self.vault

        # Create dirs
        (self.vault / "99-Inbox").mkdir()
        (self.vault / "01-Rules").mkdir()

        # Create a real draft
        (self.vault / "99-Inbox" / "my-draft.md").write_text(
            "---\ntitle: Test\ndraft\nstatus: draft\nupdated: 2026-01-01\n---\nContent\n"
        )

        # Create a file outside inbox (the target of traversal)
        (self.vault / "AGENTS.md").write_text("# Important\n")

    def tearDown(self):
        _mod.VAULT_ROOT = self._orig_vault_root
        self.tmpdir.cleanup()

    def test_path_traversal_blocked(self):
        """../AGENTS.md should be rejected, not deleted."""
        result = _mod.tool_promote_inbox_draft("../AGENTS.md", "01-Rules")
        self.assertIn("❌", result)
        self.assertIn("越界", result)
        self.assertTrue((self.vault / "AGENTS.md").exists(),
                        "AGENTS.md should NOT be deleted")

    def test_multi_match_rejected(self):
        """Multiple glob matches should be rejected with list of candidates."""
        # Create multiple similar drafts
        (self.vault / "99-Inbox" / "test-alpha.md").write_text("---\ntitle: A\n---\n")
        (self.vault / "99-Inbox" / "test-beta.md").write_text("---\ntitle: B\n---\n")
        result = _mod.tool_promote_inbox_draft("test", "01-Rules")
        self.assertIn("❌", result)
        self.assertIn("多个匹配", result)

    def test_normal_promote_works(self):
        """A valid draft in 99-Inbox should promote successfully."""
        result = _mod.tool_promote_inbox_draft("my-draft.md", "01-Rules")
        self.assertIn("🎉", result)
        self.assertFalse((self.vault / "99-Inbox" / "my-draft.md").exists(),
                         "Original draft should be deleted")
        self.assertTrue((self.vault / "01-Rules" / "my-draft.md").exists(),
                        "Promoted file should exist in target")

    def test_nonexistent_draft_rejected(self):
        """A draft that doesn't exist should return error."""
        result = _mod.tool_promote_inbox_draft("no-such-file.md", "01-Rules")
        self.assertIn("❌", result)
        self.assertIn("未在 99-Inbox", result)


if __name__ == "__main__":
    unittest.main()
