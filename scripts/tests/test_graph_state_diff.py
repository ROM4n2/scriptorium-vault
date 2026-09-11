"""Tests for the graph-state snapshot (``.graph-state.json``) + ``--diff`` mode.

Problem
-------
``vault-knowledge-graph.py`` used to return only counts — no node/edge inventory
and no historical state — so nothing could answer "what changed in the knowledge
graph since the last regeneration?" (ROADMAP-P2 Task-1, audit sensor #5: the
nightly ``--json --diff`` run and the P5 dashboard both need a persisted
baseline to diff against).

Contract pinned here
--------------------
``save_graph_state`` schema — exactly the contracted keys, none missing, no
extras (5 top-level keys; ``counts`` contributes the 2 leaf keys ``nodes`` /
``edges`` — the "6 键" of the task card counted flattened)::

    {
      "generated_at": "<UTC ISO-8601 timestamp>",
      "vault_root":   "<resolved vault root, POSIX slashes>",
      "node_ids":     [sorted ids of *file* nodes only — groups excluded],
      "edges":        [sorted "src_id→tgt_id" strings],
      "counts":       {"nodes": <int>, "edges": <int>}
    }

CLI matrix (extends the one pinned in ``test_graph_nowrite.py``)::

    invocation             canvas   state   diff report
    ---------------------  -------  ------  ---------------------------
    bare / --write         write    write   only printed with --diff
    --json / --dry-run     no       no      only printed with --diff
    --json --diff          no       no      merged as payload["diff"]
    --diff (any mode)      -        -       missing baseline => first run:
                                            everything counts as added,
                                            exit 0, hint printed

The read-only hermeticity contract extends to the *state* file: ``--json``
(with or without ``--diff``) must leave an existing ``.graph-state.json``
byte-identical and create none when absent — otherwise the nightly diff runner
would rewrite the very baseline it is supposed to compare against (and every
capability-matrix verification run would dirty the worktree).

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §4 Fixture coherence: the temp vault cross-links two notes, so node/edge
  inventories are non-empty (and exactly 2/2) before any "diff is empty" claim
  is trusted.
* Determinism (task card (e)): two identical read-only diff runs must produce
  identical diff payloads. This doubles as the guard against an implementation
  that refreshes the state file on read-only runs — the second run would then
  diff against the refreshed baseline and report an empty diff.
* Expected node/edge ids are derived via the module's own ``make_node_id``
  rather than hard-coded, so the real id scheme is probed (§3).
* Occurrence prechecks (§2): the human diff section prints the removed-edge id,
  the ``移除链接`` header and the ``First run`` hint exactly once each — pinned
  mechanically with ``len(re.findall(...))``, not via ``assertIn``.
"""
import contextlib
import datetime
import importlib.util
import io
import json
import pathlib
import re
import sys
import tempfile
import unittest

# Import vault-knowledge-graph.py (hyphenated name needs importlib)
_vkg_path = pathlib.Path(__file__).resolve().parent.parent / "vault-knowledge-graph.py"
_spec = importlib.util.spec_from_file_location("vault_knowledge_graph", _vkg_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _note(title: str, body: str) -> str:
    return (
        "---\n"
        f'title: "{title}"\n'
        "created: 2026-03-01\n"
        "updated: 2026-03-01\n"
        "type: rules\n"
        "---\n"
        "\n"
        f"# {title}\n"
        "\n"
        f"{body}\n"
    )


class _GraphStateCase(unittest.TestCase):
    """Temp vault + the same `main()` seam as test_graph_nowrite's _GraphCliCase."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "01-Rules").mkdir()
        (self.vault / "00-MOC").mkdir()
        # Two cross-linked notes: node/edge inventories are non-empty AND the
        # baseline graph is exactly 2 nodes / 2 edges (TESTING-PATTERNS §4).
        (self.vault / "01-Rules" / "alpha.md").write_text(
            _note("Alpha", "Links to [[01-Rules/beta]]."), encoding="utf-8"
        )
        (self.vault / "01-Rules" / "beta.md").write_text(
            _note("Beta", "Links back to [[01-Rules/alpha]]."), encoding="utf-8"
        )
        self.canvas = self.vault / "00-MOC" / "知识图谱白板（自动生成）"
        # The DEFAULT state location (used whenever --state-path is omitted).
        self.state = self.vault / "00-MOC" / ".graph-state.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_cli(self, *flags):
        """Invoke `main()` through argv, returning (exit_code, stdout, stderr)."""
        argv = [
            "vault-knowledge-graph.py",
            "--vault-path", str(self.vault),
            "--output", str(self.canvas),
            *flags,
        ]
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

    def seed_baseline_state(self):
        """Lay down the baseline snapshot with an explicit `--write` run."""
        code, _, err = self.run_cli("--write", "--state-path", str(self.state))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.state.exists(), "seeding must create the baseline state")

    def assert_no_state_side_effects(self, state_path: pathlib.Path) -> None:
        tmp = state_path.parent / (state_path.name + ".tmp")
        self.assertFalse(tmp.exists(), f"no .tmp stray expected next to {state_path}")


class TestStateSnapshot(_GraphStateCase):
    """Task card (a): `--write` persists a normalized, atomic state snapshot."""

    def test_write_with_explicit_state_path_produces_normalized_state(self):
        state = self.vault / "00-MOC" / "nested" / "graph-state.json"
        code, _, err = self.run_cli("--write", "--state-path", str(state))

        self.assertEqual(code, 0, err)
        self.assertTrue(state.exists(), f"--write must create {state}")
        raw = json.loads(state.read_text(encoding="utf-8"))

        # Schema: exactly the 6 contracted leaf keys (5 top-level + counts' 2).
        self.assertEqual(
            set(raw), {"generated_at", "vault_root", "node_ids", "edges", "counts"}
        )
        self.assertEqual(set(raw["counts"]), {"nodes", "edges"})

        alpha = _mod.make_node_id("01-Rules/alpha.md")
        beta = _mod.make_node_id("01-Rules/beta.md")
        # node_ids: file nodes only (group nodes excluded), sorted, complete.
        self.assertEqual(raw["node_ids"], [alpha, beta])
        # edges: sorted "src→tgt" strings, complete for the cross-linked fixture.
        self.assertEqual(raw["edges"], [f"{alpha}→{beta}", f"{beta}→{alpha}"])
        # counts are coherent with the lists.
        self.assertEqual(raw["counts"], {"nodes": 2, "edges": 2})
        # vault_root is recorded POSIX-normalized.
        self.assertEqual(
            raw["vault_root"],
            str(pathlib.Path(self.vault).resolve()).replace("\\", "/"),
        )
        # generated_at is a parseable ISO-8601 timestamp.
        datetime.datetime.fromisoformat(raw["generated_at"])
        # Atomic write: no .tmp stray survives a successful write.
        self.assert_no_state_side_effects(state)

    def test_write_without_state_path_uses_the_default_location(self):
        code, _, err = self.run_cli("--write")

        self.assertEqual(code, 0, err)
        self.assertTrue(
            self.state.exists(),
            f"bare --write must persist the default {self.state}",
        )


class TestDiffMode(_GraphStateCase):
    """Task cards (b)(c)(e)(f): `--diff` reports set differences, read-only safe."""

    def test_json_diff_reports_added_nodes_without_touching_state(self):
        self.seed_baseline_state()
        (self.vault / "01-Rules" / "gamma.md").write_text(
            _note("Gamma", "Also links to [[01-Rules/alpha]]."), encoding="utf-8"
        )
        before = self.state.read_bytes()

        code, out, err = self.run_cli(
            "--json", "--diff", "--state-path", str(self.state)
        )

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertIn("diff", payload, "--json --diff must merge the diff report")
        diff = payload["diff"]
        gamma = _mod.make_node_id("01-Rules/gamma.md")
        alpha = _mod.make_node_id("01-Rules/alpha.md")
        self.assertEqual(diff["added_nodes"], [gamma])
        self.assertEqual(diff["added_edges"], [f"{gamma}→{alpha}"])
        self.assertEqual(diff["removed_nodes"], [])
        self.assertEqual(diff["removed_edges"], [])
        self.assertIs(diff["first_run"], False)
        # Read-only contract: the pre-existing state stays byte-identical and no
        # new baseline is written by a --json run (hermeticity iron law).
        self.assertEqual(
            self.state.read_bytes(), before,
            "--json --diff must not rewrite the state file",
        )
        self.assert_no_state_side_effects(self.state)

    def test_diff_reports_removed_edges_after_link_deletion(self):
        self.seed_baseline_state()
        (self.vault / "01-Rules" / "beta.md").write_text(
            _note("Beta", "Standalone note now, no links left."), encoding="utf-8"
        )
        removed_pair = (
            f'{_mod.make_node_id("01-Rules/beta.md")}→'
            f'{_mod.make_node_id("01-Rules/alpha.md")}'
        )

        code, out, err = self.run_cli("--diff", "--state-path", str(self.state))

        self.assertEqual(code, 0, err)
        # Human-readable listing: the removed edge appears exactly once (§2).
        self.assertEqual(len(re.findall(re.escape(removed_pair), out)), 1, out)
        self.assertEqual(len(re.findall(r"移除链接", out)), 1, out)
        # A write run refreshes the snapshot: removed edge gone, nodes intact.
        refreshed = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertNotIn(removed_pair, refreshed["edges"])
        self.assertEqual(refreshed["counts"], {"nodes": 2, "edges": 1})

    def test_identical_inputs_yield_identical_diff_reports(self):
        self.seed_baseline_state()
        (self.vault / "01-Rules" / "gamma.md").write_text(
            _note("Gamma", "Deterministic link to [[01-Rules/beta]]."),
            encoding="utf-8",
        )

        _, out1, err1 = self.run_cli(
            "--json", "--diff", "--state-path", str(self.state)
        )
        _, out2, err2 = self.run_cli(
            "--json", "--diff", "--state-path", str(self.state)
        )

        self.assertEqual(err1, "", err1)
        self.assertEqual(err2, "", err2)
        d1 = json.loads(out1)["diff"]
        d2 = json.loads(out2)["diff"]
        self.assertEqual(d1, d2, "same input must produce the same diff twice")
        # Both runs diff against the SAME baseline (read-only runs never refresh
        # it), so the second run must still report gamma as added.
        self.assertEqual(d1["added_nodes"], [_mod.make_node_id("01-Rules/gamma.md")])

    def test_missing_previous_state_is_a_first_run_not_an_error(self):
        code, out, err = self.run_cli(
            "--json", "--diff", "--state-path", str(self.state)
        )

        self.assertEqual(code, 0, err)
        diff = json.loads(out)["diff"]
        alpha = _mod.make_node_id("01-Rules/alpha.md")
        beta = _mod.make_node_id("01-Rules/beta.md")
        self.assertIs(diff["first_run"], True)
        # First run = full graph counts as added.
        self.assertEqual(diff["added_nodes"], [alpha, beta])
        self.assertEqual(diff["added_edges"], [f"{alpha}→{beta}", f"{beta}→{alpha}"])
        self.assertEqual(diff["removed_nodes"], [])
        self.assertEqual(diff["removed_edges"], [])
        # Read-only: the first run must not lay down the baseline either.
        self.assertFalse(self.state.exists())
        # Human mode reports the first-run hint too, still exit 0, still no state.
        code, out2, err2 = self.run_cli(
            "--dry-run", "--diff", "--state-path", str(self.state)
        )
        self.assertEqual(code, 0, err2)
        self.assertEqual(len(re.findall(r"First run", out2)), 1, out2)
        self.assertFalse(self.state.exists())


class TestReadOnlyStateHermeticity(_GraphStateCase):
    """Task card (d): `--json`/`--dry-run` are byte-zero side effects on state."""

    def test_json_creates_no_state_file(self):
        code, out, err = self.run_cli("--json")

        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertGreater(payload["file_nodes_count"], 0, payload)  # §4 coherence
        self.assertNotIn("diff", payload, "--json alone must not add a diff key")
        self.assertFalse(self.state.exists(), "--json must not create the state file")
        self.assertEqual(list(self.state.parent.glob("*.tmp")), [])

        code, _, err = self.run_cli("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertFalse(
            self.state.exists(), "--dry-run must not create the state file"
        )

    def test_json_leaves_an_existing_state_byte_identical(self):
        self.seed_baseline_state()
        before = self.state.read_bytes()

        code, _, err = self.run_cli("--json")

        self.assertEqual(code, 0, err)
        self.assertEqual(
            self.state.read_bytes(), before,
            "--json must leave an existing state file byte-identical",
        )
        self.assert_no_state_side_effects(self.state)


class TestDiffGraphStates(unittest.TestCase):
    """Pure function contract: sorted set difference, defensive on missing keys."""

    def test_sorted_set_difference(self):
        diff = _mod.diff_graph_states(
            {"node_ids": ["n_b", "n_a"], "edges": ["n_a→n_b", "n_x→n_y"]},
            {"node_ids": ["n_a", "n_c"], "edges": ["n_c→n_a"]},
        )
        self.assertEqual(diff, {
            "added_nodes": ["n_c"],
            "removed_nodes": ["n_b"],
            "added_edges": ["n_c→n_a"],
            "removed_edges": ["n_a→n_b", "n_x→n_y"],
        })

    def test_empty_previous_state_counts_everything_as_added(self):
        diff = _mod.diff_graph_states(
            {}, {"node_ids": ["n_a"], "edges": ["n_b→n_a"]}
        )
        self.assertEqual(diff["added_nodes"], ["n_a"])
        self.assertEqual(diff["added_edges"], ["n_b→n_a"])
        self.assertEqual(diff["removed_nodes"], [])
        self.assertEqual(diff["removed_edges"], [])


if __name__ == "__main__":
    unittest.main()
