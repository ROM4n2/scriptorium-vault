#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for nightly-maintenance dispatch semantics (P1 yellow card #3).

Problem: `main()` walked the pipeline with hardcoded if/elif, so the most
load-bearing behaviour — a failing quality gate MUST abort before git-sync,
while a best-effort sensor failure MUST NOT — was only observable by actually
running subprocesses. `run_pipeline(steps, executor)` makes the dispatch
injectable so the semantics are pinned by a fake executor.
"""

import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "nightly_maintenance_dispatch", _SCRIPTS_DIR / "nightly-maintenance.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class _FakeExecutor:
    """Records (name, argv) calls; returns a per-name result."""

    def __init__(self, results=None, raise_for=()):
        self.calls = []
        self._results = results or {}
        self._raise_for = set(raise_for)

    def __call__(self, name: str, argv: list) -> int:
        self.calls.append(name)
        if name in self._raise_for:
            raise RuntimeError(f"{name} boom")
        return self._results.get(name, 0)


class TestRunPipeline(unittest.TestCase):
    def setUp(self):
        self.steps = mod.build_nightly_steps()

    def _run(self, executor, steps=None):
        buf = io.StringIO()
        import contextlib
        pipeline = self.steps if steps is None else steps
        with contextlib.redirect_stdout(buf):
            rc = mod.run_pipeline(pipeline, executor)
        return rc, buf.getvalue()

    def test_all_steps_executed_in_order(self):
        ex = _FakeExecutor()
        rc, _ = self._run(ex)
        self.assertEqual(rc, 0)
        self.assertEqual(ex.calls, [name for name, _ in self.steps])

    def test_quality_gate_failure_aborts_before_git_sync(self):
        """The one fatal semantics: no git-sync after a failing gate."""
        ex = _FakeExecutor(results={"quality-check": 1})
        rc, _ = self._run(ex)
        self.assertEqual(rc, 1)
        self.assertIn("quality-check", ex.calls)
        self.assertNotIn("git-sync", ex.calls)

    def test_best_effort_failure_does_not_abort(self):
        """A sensor step raising must not stop the run (module docstring)."""
        ex = _FakeExecutor(raise_for={"canvas-regen"})
        rc, _ = self._run(ex)
        self.assertEqual(rc, 0)
        self.assertIn("git-sync", ex.calls)

    def test_empty_pipeline_returns_zero(self):
        ex = _FakeExecutor()
        rc, _ = self._run(ex, steps=[])
        self.assertEqual(rc, 0)
        self.assertEqual(ex.calls, [])


class TestDefaultExecutorWiring(unittest.TestCase):
    """run_pipeline must be what main() actually drives."""

    def test_main_uses_run_pipeline(self):
        with mock.patch.object(mod, "append_audit_row", return_value=(True, "ok")), \
             mock.patch.object(mod, "run_pipeline", return_value=0) as run:
            rc = mod.main()
        self.assertEqual(rc, 0)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
