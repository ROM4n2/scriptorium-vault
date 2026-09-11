"""Tests for `vault-knowledge-graph.py` read-only (`--json`) vs write (`--write`) modes.

Problem
-------
``generate_canvas`` used to end with an *unconditional*::

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(canvas_data, ...), encoding="utf-8")

No flag gated it, so ``--json`` — the only machine-readable mode, and therefore the
only sane candidate for a capability-matrix ``verification_command`` — rewrote
``00-MOC/知识图谱白板（自动生成）`` on every run (measured: +4662 / -173 lines).
That breaks two CI gates at once:

* the hermeticity gate (``git diff --exit-code`` after running the tool), and
* the ``updated:`` staleness gate, which derives its dirty set from ``git status``
  and would start judging notes the verification run itself had dirtied.

Contract pinned here
--------------------
=========================  ========  =================================
invocation                 writes?   why
=========================  ========  =================================
``(no flags)``             yes       backward compatibility — every doc
                                     (``README.md``, ``scripts/README.md``,
                                     ``AGENTS.md``) documents the bare form
                                     as *the* way to regenerate the canvas
``--json``                 **no**    read-only reporting mode
``--dry-run``              **no**    explicit read-only, human-readable report
``--write`` / ``--apply``  yes       explicit opt-in, overrides ``--json``
``--write --dry-run``      error     contradictory, must not be resolved silently
=========================  ========  =================================

Both directions are asserted deliberately. A one-directional suite ("``--json``
must not write") is satisfied by an implementation that deleted the write path
altogether, which would be a silent regression of the documented default.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §2 Occurrence Precheck: every textual assertion below was first measured with
  ``len(re.findall(pattern, slice))`` against real captured output and pins
  **exactly one** match; the counts are asserted mechanically rather than via
  ``assertIn``. Measured counts on the implementation as committed:
  ``"total_nodes"`` -> 1 in ``--json`` stdout; ``Canvas 全景可视化文件已成功生成``
  -> 1 in bare-invocation stdout and 0 in ``--dry-run`` stdout;
  ``--write and --dry-run`` -> 1 in the argparse error stderr.
* §4 Fixture coherence: the temp vault is asserted to produce a *non-empty*
  graph (``file_nodes_count`` and ``edges_count`` both > 0) before any
  "did not write" claim is trusted. A fixture that yielded zero nodes would make
  every negative assertion vacuously green.
* §1 Inversion / mutation — executed against a ``cp`` backup of the
  implementation (never ``git checkout --``), and these are the observed results:
  - M1 delete the ``if write:`` gate in ``generate_canvas``, i.e. restore the
    unconditional ``write_canvas(output_path, canvas_data)``
    -> 3 failed: ``test_json_mode_does_not_create_the_canvas``,
    ``test_json_mode_does_not_modify_an_existing_canvas`` and
    ``test_dry_run_does_not_write``. These three are the read-only guard.
  - M2 collapse ``resolve_should_write`` to ``return False``, i.e. the degenerate
    "never writes anything" implementation that a one-directional suite would
    happily accept -> 4 failed: all of ``TestWriteModes``. This is why both
    directions are pinned.
  - M1 notably did **not** fail ``test_json_mode_reports_that_it_did_not_write``:
    ``written`` mirrors the resolved *intent* flag, not an observed filesystem
    effect, so under M1 the payload says ``"written": false`` while the file was
    in fact rewritten. Recorded rather than quietly patched — the authority for
    "did it write?" is the ``self.canvas.exists()`` / ``read_bytes()``
    assertions above, and that assertion is documentation of the payload's
    contract, not a filesystem probe.
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
import unittest.mock

# Import vault-knowledge-graph.py (hyphenated name needs importlib)
_vkg_path = pathlib.Path(__file__).resolve().parent.parent / "vault-knowledge-graph.py"
_spec = importlib.util.spec_from_file_location("vault_knowledge_graph", _vkg_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_SENTINEL = '{"nodes": [], "edges": [], "sentinel": "untouched"}'


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


class _GraphCliCase(unittest.TestCase):
    """Shared temp vault + a seam that drives `main()` exactly as the shell does."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "01-Rules").mkdir()
        (self.vault / "00-MOC").mkdir()
        # Two cross-linked notes: guarantees nodes > 0 AND edges > 0, so a
        # "nothing was written" assertion can never be green just because the
        # generator had nothing to say (TESTING-PATTERNS §4).
        (self.vault / "01-Rules" / "alpha.md").write_text(
            _note("Alpha", "Links to [[01-Rules/beta]]."), encoding="utf-8"
        )
        (self.vault / "01-Rules" / "beta.md").write_text(
            _note("Beta", "Links back to [[01-Rules/alpha]]."), encoding="utf-8"
        )
        self.canvas = self.vault / "00-MOC" / "知识图谱白板（自动生成）"

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

    def assert_graph_is_not_empty(self, payload):
        """Guard against a vacuously-green negative test (TESTING-PATTERNS §4)."""
        self.assertGreater(payload["file_nodes_count"], 0, payload)
        self.assertGreater(payload["edges_count"], 0, payload)


class TestJsonModeIsReadOnly(_GraphCliCase):
    """`--json` is a reporting mode: it MUST leave the filesystem alone."""

    def test_json_mode_does_not_create_the_canvas(self):
        code, out, err = self.run_cli("--json")

        self.assertEqual(code, 0, err)
        # Occurrence precheck (§2): exactly one JSON document on stdout.
        self.assertEqual(len(re.findall(r'"total_nodes"', out)), 1, out)
        payload = json.loads(out)
        self.assert_graph_is_not_empty(payload)
        self.assertFalse(
            self.canvas.exists(),
            f"--json must not create {self.canvas}; stdout was: {out}",
        )

    def test_json_mode_does_not_modify_an_existing_canvas(self):
        """Stronger than 'not created': an existing canvas must be byte-identical."""
        self.canvas.write_text(_SENTINEL, encoding="utf-8")
        before = self.canvas.read_bytes()

        code, out, _ = self.run_cli("--json")

        self.assertEqual(code, 0)
        self.assert_graph_is_not_empty(json.loads(out))
        self.assertEqual(
            self.canvas.read_bytes(), before, "--json rewrote an existing canvas"
        )

    def test_json_mode_reports_that_it_did_not_write(self):
        """The machine-readable payload must not claim an output it never produced."""
        _, out, _ = self.run_cli("--json")

        self.assertIs(json.loads(out)["written"], False)

    def test_dry_run_does_not_write(self):
        """`--dry-run` is the human-readable read-only mode."""
        code, out, err = self.run_cli("--dry-run")

        self.assertEqual(code, 0, err)
        self.assertFalse(self.canvas.exists(), out)
        # Occurrence precheck (§2): the success banner is absent, not merely rare.
        self.assertEqual(
            len(re.findall(r"Canvas 全景可视化文件已成功生成", out)), 0, out
        )


class TestWriteModes(_GraphCliCase):
    """The write path must survive; a never-writing implementation is a regression."""

    def test_write_flag_creates_the_canvas(self):
        code, out, err = self.run_cli("--write")

        self.assertEqual(code, 0, err)
        self.assertTrue(self.canvas.exists(), f"--write must create {self.canvas}")
        written = json.loads(self.canvas.read_text(encoding="utf-8"))
        self.assertGreater(len(written["nodes"]), 0, written)
        self.assertGreater(len(written["edges"]), 0, written)

    def test_apply_is_an_alias_for_write(self):
        code, _, err = self.run_cli("--apply")

        self.assertEqual(code, 0, err)
        self.assertTrue(self.canvas.exists(), "--apply must behave like --write")

    def test_bare_invocation_still_writes(self):
        """Backward compatibility: every doc says the bare form regenerates the canvas."""
        code, out, err = self.run_cli()

        self.assertEqual(code, 0, err)
        self.assertTrue(self.canvas.exists(), f"bare run must create {self.canvas}")
        # Occurrence precheck (§2): the success banner is printed exactly once.
        self.assertEqual(
            len(re.findall(r"Canvas 全景可视化文件已成功生成", out)), 1, out
        )

    def test_write_overrides_json_read_only_default(self):
        """`--json --write` is the explicit 'report AND persist' combination."""
        code, out, err = self.run_cli("--json", "--write")

        self.assertEqual(code, 0, err)
        self.assertEqual(len(re.findall(r'"total_nodes"', out)), 1, out)
        self.assertIs(json.loads(out)["written"], True)
        self.assertTrue(self.canvas.exists())


class TestContradictoryFlags(_GraphCliCase):
    """A contradiction must be refused loudly, never resolved by silent precedence."""

    def test_write_with_dry_run_is_rejected(self):
        code, _, err = self.run_cli("--write", "--dry-run")

        self.assertEqual(code, 2, err)
        # Occurrence precheck (§2): argparse prints the reason exactly once.
        self.assertEqual(len(re.findall(r"--write and --dry-run", err)), 1, err)
        self.assertFalse(self.canvas.exists(), "a rejected invocation must not write")


class TestAtomicWrite(_GraphCliCase):
    """The write path must be atomic: `.tmp` sibling + `os.replace`.

    Pinned contract (P1 Task-5):

    * A failing ``os.replace`` must (1) propagate the ``OSError`` — never be
      swallowed or retried-until-success — and (2) leave the previous canvas
      byte-identical. A torn write would leave a half JSON canvas that Obsidian
      silently fails to open.
    * A successful write must leave no ``.tmp`` sibling behind.

    Injection point note: the module is loaded via ``spec_from_file_location``
    (hyphenated filename), so there is no importable package attribute path.
    Patching ``_mod.os.replace`` works regardless of the load mechanism because
    ``os`` is a shared singleton module object in the loader's namespace.
    """

    def test_replace_failure_keeps_old_canvas_bytes_and_propagates(self):
        self.canvas.write_text(_SENTINEL, encoding="utf-8")
        before = self.canvas.read_bytes()
        boom = OSError(5, "simulated os.replace failure")

        # side_effect list: FIRST call raises, later calls (if any — i.e. a
        # swallow-and-retry implementation) return normally, so a retry that
        # succeeds would flip the canvas and be caught by the bytes assertion.
        with unittest.mock.patch.object(
            _mod.os, "replace", side_effect=[boom]
        ) as fake_replace:
            with self.assertRaises(OSError) as raised:
                self.run_cli("--write")

        self.assertIs(raised.exception, boom)
        # Exactly one replace attempt at exactly the injection point: proves the
        # mock is wired (not vacuously passing via an unrelated error) and that
        # the failure surfaces at the atomic-replace step.
        fake_replace.assert_called_once()
        self.assertEqual(
            self.canvas.read_bytes(),
            before,
            "a failed os.replace must leave the previous canvas untouched",
        )

    def test_successful_write_leaves_no_tmp_sibling(self):
        code, out, err = self.run_cli("--write")

        self.assertEqual(code, 0, err)
        # Sanity (TESTING-PATTERNS §4): the write really happened and is valid
        # JSON with a non-empty graph before any "no leftovers" claim is trusted.
        written = json.loads(self.canvas.read_text(encoding="utf-8"))
        self.assertGreater(len(written["nodes"]), 0, written)
        self.assertGreater(len(written["edges"]), 0, written)
        tmp = self.canvas.parent / (self.canvas.name + ".tmp")
        self.assertFalse(tmp.exists(), f"successful write must clean up {tmp}")
        siblings = sorted(self.canvas.parent.glob(self.canvas.name + "*"))
        self.assertEqual(
            siblings, [self.canvas], f"unexpected siblings in 00-MOC: {siblings}"
        )


if __name__ == "__main__":
    unittest.main()
