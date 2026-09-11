"""Static contract: every script/stream pair survives the Windows GBK console.

Problem
-------
On Windows the default console encoding is the legacy ANSI codepage (GBK on
zh-CN machines). Any Python script that prints Unicode (box-drawing, CJK,
emoji) to ``sys.stdout`` — or writes a traceback / warning to ``sys.stderr`` —
raises ``UnicodeEncodeError`` instead of doing its job. The vault standard
(cf. ``scripts/vault-knowledge-graph.py``:33-37, ``01-Rules`` RFC MUST) is to
``reconfigure`` **both** streams with ``encoding="utf-8", errors="replace"``
behind a ``hasattr`` guard (guard needed because ``sys.stdout`` can be a
non-``TextIOWrapper`` — e.g. pytest capture or a redirected pipe — that lacks
``reconfigure``).

A sweep found 8 CLI scripts that configured ``stdout`` but forgot the
``stderr`` twin, plus one shared module that had neither:

* the 8 scripts are CLIs whose stderr carries warnings, tracebacks and
  hook-failure diagnostics — exactly the output you cannot afford to lose to
  a codec error *while reporting an error*;
* ``vault_linkrules.py`` is **imported** (not executed) by
  ``vault-quality-check.py`` and ``vault-healthcheck.py``, so it must
  configure both streams itself at import time, before its importers print
  anything. It had no ``import sys`` at all.

Adjacency rule (≤3 lines between the ``sys.stdout.reconfigure(...)`` call and
the ``sys.stderr.reconfigure(...)`` call): the pair is one idiom, copied
file-to-file. Distance is what reviewers eyeball to see the twin was not
dropped; letting the two blocks drift apart in an import-heavy header is how
the 8 regressions happened in the first place.

Test shape
----------
Pure static source assertions (house style, cf. ``TestRuleIsNotDuplicated`` in
``test_template_placeholder_links.py``): these scripts talk to the console on
import (``stop-hook-ingest.py``) or need the real vault (``vault_audit.py``),
so importing them here would execute side effects. Occurrence precheck
(TESTING-PATTERNS §2): each ``reconfigure`` pattern is pinned to **exactly
one** match per file so a duplicated or half-copied block also fails.

Red-first evidence: before the fix all tests below failed — the 8 CLI scripts
matched 0 stderr patterns and ``vault_linkrules.py`` matched 0 for all three
of ``import sys`` / stdout / stderr.
"""
import pathlib
import re
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

# The 8 CLI scripts: stdout configured, stderr missing at the time of the sweep.
CLI_SCRIPTS = [
    "arxiv_paper_mcp.py",
    "nightly-maintenance.py",
    "sqlite_inspector_mcp.py",
    "stop-hook-ingest.py",
    "system_monitor_mcp.py",
    "vault_audit.py",
    "vault-inbox-consolidate.py",
    "vault-memory-compactor.py",
]

# The shared, imported module: both streams were missing.
SHARED_MODULE = "vault_linkrules.py"

ALL_TARGETS = CLI_SCRIPTS + [SHARED_MODULE]

# Exactly the canonical invocation — guards encoding drift, not just presence.
_STDOUT_RECONFIG = re.compile(
    r'^\s*sys\.stdout\.reconfigure\(encoding="utf-8", errors="replace"\)',
    re.MULTILINE,
)
_STDERR_RECONFIG = re.compile(
    r'^\s*sys\.stderr\.reconfigure\(encoding="utf-8", errors="replace"\)',
    re.MULTILINE,
)

_STDOUT_GUARD = 'if hasattr(sys.stdout, "reconfigure"):'
_STDERR_GUARD = 'if hasattr(sys.stderr, "reconfigure"):'

# Vault standard MUST: the stderr twin sits ≤3 lines from its stdout twin.
_MAX_ADJACENCY = 3


def _read(rel: str) -> str:
    return (_SCRIPTS_DIR / rel).read_text(encoding="utf-8")


def _line_numbers(src: str, pattern: re.Pattern) -> list:
    """1-based line numbers of the reconfigure call lines matching *pattern*."""
    return [
        lineno
        for lineno, line in enumerate(src.splitlines(), start=1)
        if pattern.match(line)
    ]


def _assert_adjacent(testcase: unittest.TestCase, rel: str) -> None:
    """Both streams configured exactly once and within _MAX_ADJACENCY lines."""
    src = _read(rel)
    out = _line_numbers(src, _STDOUT_RECONFIG)
    err = _line_numbers(src, _STDERR_RECONFIG)
    testcase.assertEqual(
        len(out), 1, f"{rel}: expected exactly one stdout.reconfigure call, saw {out}"
    )
    testcase.assertEqual(
        len(err), 1, f"{rel}: expected exactly one stderr.reconfigure call, saw {err}"
    )
    testcase.assertLessEqual(
        abs(err[0] - out[0]),
        _MAX_ADJACENCY,
        f"{rel}: stderr.reconfigure (line {err[0]}) drifted "
        f"{abs(err[0] - out[0])} lines from stdout.reconfigure (line {out[0]})",
    )


class TestCliScriptsHaveStderrTwin(unittest.TestCase):
    """The 8 sweep targets: stderr must catch up with stdout."""

    def test_each_cli_script_has_exactly_one_stderr_reconfigure(self):
        for rel in CLI_SCRIPTS:
            with self.subTest(script=rel):
                src = _read(rel)
                self.assertEqual(
                    len(_STDERR_RECONFIG.findall(src)),
                    1,
                    f"{rel}: missing canonical stderr.reconfigure line",
                )

    def test_stderr_call_is_adjacent_to_stdout_call(self):
        for rel in CLI_SCRIPTS:
            with self.subTest(script=rel):
                _assert_adjacent(self, rel)

    def test_both_streams_are_hasattr_guarded(self):
        for rel in CLI_SCRIPTS:
            with self.subTest(script=rel):
                src = _read(rel)
                self.assertIn(_STDOUT_GUARD, src, rel)
                self.assertIn(_STDERR_GUARD, src, rel)


class TestSharedModuleFullProtection(unittest.TestCase):
    """vault_linkrules.py: import-time protection for both streams."""

    def test_module_imports_sys(self):
        src = _read(SHARED_MODULE)
        self.assertEqual(
            len(re.findall(r"^import sys$", src, flags=re.MULTILINE)),
            1,
            f"{SHARED_MODULE}: missing (or duplicated) `import sys`",
        )

    def test_module_has_exactly_one_stdout_and_stderr_reconfigure(self):
        src = _read(SHARED_MODULE)
        self.assertEqual(
            len(_STDOUT_RECONFIG.findall(src)),
            1,
            f"{SHARED_MODULE}: missing canonical stdout.reconfigure line",
        )
        self.assertEqual(
            len(_STDERR_RECONFIG.findall(src)),
            1,
            f"{SHARED_MODULE}: missing canonical stderr.reconfigure line",
        )

    def test_streams_are_adjacent(self):
        _assert_adjacent(self, SHARED_MODULE)

    def test_streams_are_hasattr_guarded(self):
        src = _read(SHARED_MODULE)
        self.assertIn(_STDOUT_GUARD, src, SHARED_MODULE)
        self.assertIn(_STDERR_GUARD, src, SHARED_MODULE)


if __name__ == "__main__":
    unittest.main()
