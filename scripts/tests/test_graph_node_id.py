"""Tests for `make_node_id` hash preservation (YELLOW-1) + `.codebuddy` exclusion (YELLOW-4).

Problem
-------
``make_node_id`` built ``f"node_{clean}_{h}"[:40]`` — for any path whose sanitized
form reached 35+ chars before the md5 tail, the ``[:40]`` slice chopped the
6-char md5 off the end. Distinct paths sharing a long sanitized prefix (e.g. the
seven ROADMAP-P*.md notes) then collapsed onto ONE node id: the persisted
graph-state ``node_ids`` held 149 entries with only ~135 unique values, and the
canvas silently merged distinct notes into a single node.

Contract pinned here
--------------------
1. Hash tail (YELLOW-1 core): the id ALWAYS ends with ``_<md5[:6]>`` — the
   collision guard is never truncated away, for any path length.
2. Bounded: the id is never longer than 40 chars (canvas id hygiene).
3. Injectivity: two paths differing only in their tail map to different ids.
4. Backward shape: short paths keep the exact ``node_<clean>_<h>`` form, so
   already-published ids for short paths do not churn.
5. (YELLOW-4) ``.codebuddy`` is excluded from the vault walk, aligned with
   vault-quality-check's exclusion policy.
"""
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest

# Import vault-knowledge-graph.py (hyphenated name needs importlib)
_vkg_path = pathlib.Path(__file__).resolve().parent.parent / "vault-knowledge-graph.py"
_spec = importlib.util.spec_from_file_location("vault_knowledge_graph", _vkg_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _expected_hash(rel_path: str) -> str:
    return hashlib.md5(rel_path.encode("utf-8")).hexdigest()[:6]


class TestMakeNodeIdHashPreservation(unittest.TestCase):
    """YELLOW-1: the md5 tail must survive the 40-char length cap."""

    # Both paths sanitize to a 48-char clean string whose first 34 chars are
    # identical — precisely the shape that made the old [:40] slice drop the
    # hash suffix and collide the two ids onto one node.
    LONG_TAIL_A = "01-Rules/ROADMAP-P1-very-long-name-aaaaaaaaaa.md"
    LONG_TAIL_B = "01-Rules/ROADMAP-P1-very-long-name-bbbbbbbbbb.md"

    def test_long_paths_differing_only_in_tail_get_distinct_ids(self):
        id_a = _mod.make_node_id(self.LONG_TAIL_A)
        id_b = _mod.make_node_id(self.LONG_TAIL_B)
        self.assertNotEqual(
            id_a, id_b, "distinct paths must never share a node id"
        )

    def test_id_always_ends_with_hash_tail(self):
        for rel_path in (self.LONG_TAIL_A, self.LONG_TAIL_B, "01-Rules/alpha.md"):
            with self.subTest(rel_path=rel_path):
                self.assertTrue(
                    _mod.make_node_id(rel_path).endswith("_" + _expected_hash(rel_path)),
                    f"id for {rel_path!r} lost its md5 tail",
                )

    def test_id_never_exceeds_40_chars(self):
        long_paths = [
            self.LONG_TAIL_A,
            self.LONG_TAIL_B,
            "a" * 200 + ".md",
            "00-MOC/" + "x-y_" * 30 + ".md",
        ]
        for rel_path in long_paths:
            with self.subTest(rel_path=rel_path):
                self.assertLessEqual(len(_mod.make_node_id(rel_path)), 40)

    def test_short_path_keeps_exact_shape(self):
        # clean("01-Rules/alpha.md") = "01_rules_alpha_md" (17 chars) — short
        # enough that the new cap must NOT change the previously published id.
        self.assertEqual(
            _mod.make_node_id("01-Rules/alpha.md"),
            "node_01_rules_alpha_md_" + _expected_hash("01-Rules/alpha.md"),
        )

    def test_ids_remain_deterministic(self):
        self.assertEqual(
            _mod.make_node_id(self.LONG_TAIL_A),
            _mod.make_node_id(self.LONG_TAIL_A),
        )


class TestCodebuddyExclusion(unittest.TestCase):
    """YELLOW-4: .codebuddy must be excluded, aligned with quality-check policy."""

    def test_codebuddy_in_excluded_dirs(self):
        self.assertIn(".codebuddy", _mod.EXCLUDED_DIRS)

    def test_generate_canvas_skips_codebuddy_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = pathlib.Path(tmp)
            (vault / "01-Rules").mkdir()
            (vault / "00-MOC").mkdir()
            (vault / "01-Rules" / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
            buddy_dir = vault / ".codebuddy"
            buddy_dir.mkdir()
            (buddy_dir / "internal.md").write_text("# Internal\n", encoding="utf-8")

            res = _mod.generate_canvas(
                vault, vault / "00-MOC" / "k.canvas", write=False
            )

            node_files = [
                n["file"] for n in res["_canvas_nodes"] if n.get("type") == "file"
            ]
            # Sanity (TESTING-PATTERNS §4): the walk itself works before any
            # "nothing leaked" claim is trusted.
            self.assertIn("01-Rules/alpha.md", node_files)
            self.assertFalse(
                [f for f in node_files if f.startswith(".codebuddy")],
                ".codebuddy notes leaked into the canvas",
            )


if __name__ == "__main__":
    unittest.main()
