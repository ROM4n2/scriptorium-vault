"""Tests for the step-driven nightly pipeline (P1 Task-6).

Problem
-------
``nightly-maintenance.py`` was a linear script: top-level statements ran
compactor -> quality-check -> git push with hardcoded "[1/3]" numbering, and
importing the module executed the whole pipeline (subprocesses, git
commit/push). Extending it with the canvas regeneration step
(``vault-knowledge-graph.py``) meant another copy-pasted try/except block and
more drift in error-handling semantics.

Contract pinned here
--------------------
``build_nightly_steps()`` is a pure function returning the ordered nightly
pipeline as ``(step_name, argv)`` tuples, executed by the main loop with
``cwd`` = vault root:

=====================  ======================================================
step                   argv contract
=====================  ======================================================
memory-compactor       [sys.executable, <scripts>/vault-memory-compactor.py]
canvas-regen           [sys.executable, <scripts>/vault-knowledge-graph.py]
                       — bare, no flags: bare = write is the documented
                       compatibility contract (README.md, scripts/README.md,
                       AGENTS.md); a ``--json`` flag here would silently turn
                       the nightly graph step read-only.
quality-check          [sys.executable, <scripts>/vault-quality-check.py,
                       "--strict"]
git-sync               starts with system "git" (not sys.executable)
=====================  ======================================================

Import safety: the module must load via importlib (hyphenated filename) with
ZERO side effects — no subprocess, no git, no console output — because all
execution lives behind ``if __name__ == "__main__"``. This is what makes the
module testable at all; cf. ``test_stderr_protection.py``, which had to fall
back to static source assertions on the old execute-on-import version.

Path assertions compare against ``_mod.VAULT`` — the resolved vault root the
module itself computed (honoring ``$VAULT_ROOT``) — not this file's
``_SCRIPTS_DIR``, so the suite holds in any vault-root environment.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* The import-safety claim is asserted mechanically (captured import-time
  stdout/stderr must be empty), not assumed.
* ``test_canvas_regen_is_bare_invocation`` pins the *absence* of read-only
  flags, not just the script path — a regression to ``--json`` here would
  keep every path assertion green while silently no-op'ing the graph step.

Red-first evidence: against the pre-refactor script (linear top-level logic,
no ``build_nightly_steps``) every ``TestBuildNightlySteps`` case fails with
``AttributeError: ... object has no attribute 'build_nightly_steps'``.
"""
import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

# nightly-maintenance.py does `from vault_audit import append_audit_row`;
# make scripts/ importable regardless of how pytest assembled sys.path.
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Hyphenated filename -> importlib, never `import nightly_maintenance`.
# Import-time output is captured and pinned empty by TestImportSafety: the
# pipeline may only run under `if __name__ == "__main__"`.
_out, _err = io.StringIO(), io.StringIO()
try:
    with contextlib.redirect_stdout(_out), contextlib.redirect_stderr(_err):
        _spec = importlib.util.spec_from_file_location(
            "nightly_maintenance", _SCRIPTS_DIR / "nightly-maintenance.py"
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
except FileNotFoundError as _import_error:
    # $VAULT_ROOT pointing at a nonexistent directory makes the module's
    # own resolve_vault_root() reject the import at load time. Skip the
    # whole module with an explicit reason instead of crashing collection.
    pytest.skip(
        f"nightly-maintenance.py not importable under this VAULT_ROOT: "
        f"{_import_error}",
        allow_module_level=True,
    )
_LOAD_STDOUT = _out.getvalue()
_LOAD_STDERR = _err.getvalue()

EXPECTED_STEP_ORDER = [
    "memory-compactor", "canvas-regen", "claim-ledger", "dashboards",
    "insights", "quality-check", "git-sync",
]


class TestImportSafety(unittest.TestCase):
    """Loading the module must have zero side effects; execution only under __main__."""

    def test_import_prints_nothing(self):
        self.assertEqual(_LOAD_STDOUT, "", "module printed to stdout at import time")
        self.assertEqual(_LOAD_STDERR, "", "module printed to stderr at import time")


class TestBuildNightlySteps(unittest.TestCase):
    """`build_nightly_steps()` is the single source of the pipeline order."""

    def setUp(self):
        self.steps = _mod.build_nightly_steps()
        self.by_name = dict(self.steps)

    def test_step_names_in_canonical_order(self):
        self.assertEqual(
            [name for name, _ in self.steps], EXPECTED_STEP_ORDER
        )

    def test_step_names_are_unique(self):
        names = [name for name, _ in self.steps]
        self.assertEqual(len(set(names)), len(names), names)

    def test_steps_are_name_argv_tuples_of_strings(self):
        for name, argv in self.steps:
            self.assertIsInstance(name, str)
            self.assertIsInstance(argv, list)
            for token in argv:
                self.assertIsInstance(token, str)

    def test_python_steps_use_sys_executable(self):
        for name in ("memory-compactor", "canvas-regen", "claim-ledger",
                     "dashboards", "quality-check"):
            self.assertEqual(self.by_name[name][0], sys.executable, name)

    def test_dashboards_targets_the_real_script_apply(self):
        """Dashboards step MUST be the bare apply invocation (write mode)."""
        argv = self.by_name["dashboards"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-dashboards.py").resolve(),
        )
        self.assertIn("--apply", argv)

    def test_insights_targets_the_real_script_apply(self):
        """Insights step refreshes dashboards/sessions.md after dashboards."""
        argv = self.by_name["insights"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-insights.py").resolve(),
        )
        self.assertIn("--apply", argv)

    def test_claim_ledger_targets_the_real_script_bare(self):
        """Default mode of vault-claim-ledger.py is the ONLY writing mode."""
        argv = self.by_name["claim-ledger"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-claim-ledger.py").resolve(),
        )
        for forbidden in ("--json", "--dry-run", "--check"):
            self.assertNotIn(forbidden, argv)

    def test_memory_compactor_targets_the_real_script(self):
        argv = self.by_name["memory-compactor"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-memory-compactor.py").resolve(),
        )

    def test_canvas_regen_targets_the_real_script(self):
        argv = self.by_name["canvas-regen"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-knowledge-graph.py").resolve(),
        )

    def test_canvas_regen_is_bare_invocation(self):
        """bare = write (documented contract); --json would be read-only."""
        argv = self.by_name["canvas-regen"]
        self.assertEqual(len(argv), 2, argv)
        for forbidden in ("--json", "--dry-run", "--write", "--apply"):
            self.assertNotIn(forbidden, argv)

    def test_quality_check_is_strict(self):
        argv = self.by_name["quality-check"]
        self.assertEqual(
            pathlib.Path(argv[1]).resolve(),
            (_mod.VAULT / "scripts" / "vault-quality-check.py").resolve(),
        )
        self.assertIn("--strict", argv)

    def test_git_sync_uses_system_git(self):
        argv = self.by_name["git-sync"]
        self.assertEqual(argv[0], "git", argv)


if __name__ == "__main__":
    unittest.main()
