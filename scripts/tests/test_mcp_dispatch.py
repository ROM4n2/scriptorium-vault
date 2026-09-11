"""Tests for MCP tool dispatch completeness (Task 3.1)."""
import importlib.util
import pathlib
import unittest
import sys

# Import vault_search_mcp.py (hyphenated name needs importlib)
_vsm_path = pathlib.Path(__file__).resolve().parent.parent / "vault_search_mcp.py"
_spec = importlib.util.spec_from_file_location("vault_search_mcp", _vsm_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


class TestMCPDispatchCompleteness(unittest.TestCase):
    """Verify that every tool declared in TOOLS_DEFINITION has a dispatch handler."""

    def test_all_declared_tools_have_handlers(self):
        """TOOLS_DEFINITION names must equal TOOL_HANDLERS keys."""
        # Extract declared tool names from TOOLS_DEFINITION
        declared = set()
        for tool in _mod.TOOLS_DEFINITION:
            declared.add(tool["name"])

        # Extract handler names from the if-elif chain by scanning source
        # We use a simpler approach: just call the dispatch function with each tool name
        # and verify it doesn't return "❌ 未知工具"
        # But since we can't easily mock the JSON-RPC, we check the source directly
        source = _vsm_path.read_text(encoding="utf-8")

        # Find all tool names referenced in the if-elif chain
        import re
        handler_names = set(re.findall(r'tool_name == "(\w+)"', source))

        # Also check for the dict-based dispatch (if refactored)
        dict_matches = re.findall(r'"(\w+)":\s*tool_', source)
        handler_names.update(dict_matches)

        missing = declared - handler_names
        self.assertEqual(
            missing, set(),
            f"Tools declared in TOOLS_DEFINITION but missing from dispatch: {missing}"
        )

    def test_get_rule_snippet_is_dispatched(self):
        """get_rule_snippet specifically must be reachable."""
        source = _vsm_path.read_text(encoding="utf-8")
        self.assertIn('tool_name == "get_rule_snippet"', source,
                       "get_rule_snippet missing from if-elif dispatch chain")


if __name__ == "__main__":
    unittest.main()
