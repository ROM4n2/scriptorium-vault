#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""No-side-effect gate for every `verification_command` in CAPABILITY-MATRIX.md.

Why this file exists
--------------------
`scripts/capability-check.py` runs each declared `verification_command` and calls
the capability `verified` when it exits 0. Nothing checked whether those commands
were *read-only*. "A verification command must not mutate the vault" was a
convention with no enforcement, and it was already violated in production:
`vault-knowledge-graph.py --json` unconditionally rewrote
`00-MOC/知识图谱白板（自动生成）` (+4662 / -173 lines) until commit d3b4950 gated
the write behind `--write`. Had that command been promoted into the matrix first,
every `capability-check.py` run would have silently dirtied the worktree and the
breakage would have surfaced somewhere unrelated (CI hermeticity, or the
`updated:` staleness gate, which derives its dirty set from `git status`).

This module turns the convention into a gate: it executes *every* command the
matrix declares and asserts `git status --porcelain=v1 --untracked-files=all` is
byte-identical before and after.

Dirty worktrees are fine
------------------------
The gate compares a before/after snapshot rather than requiring a clean start, so
it stays usable mid-development. The flip side: a *concurrent* writer (another
agent, an editor autosave, Obsidian) during the ~25s run shows up as a failure.
The failure message therefore prints the exact added/removed porcelain lines so a
human can tell "the command wrote this" from "something else touched that".

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §2 Occurrence precheck — measured with `len(re.findall(pattern, slice))` before
  being asserted, each pinning exactly one match:
  - `r"timeout=(\\d+)"` in `scripts/capability-check.py` -> 1
  - `r"(?m)^\\| <name> \\|"` in `05-Tools/CAPABILITY-MATRIX.md` -> 1 per capability
    (asserted mechanically for all 17 rows in
    `test_each_capability_row_appears_exactly_once`)
* §4 Fixture coherence — a "nothing was written" assertion is vacuously green in
  three ways, all of which are closed here:
  1. the matrix parsed to zero commands ->
     `test_matrix_declares_at_least_one_verification_command`
  2. `git status` itself failed, making both snapshots equally empty ->
     `_git_status` raises on a non-zero git exit instead of returning b""
  3. the command crashed on startup and so had no chance to write ->
     `test_every_verification_command_exits_zero`
* §1 Inversion / mutation — executed, not merely claimed. A `mutation-probe` row
  running `vault-knowledge-graph.py --write --output 05-Tools/_mutation-probe.canvas`
  was temporarily added to the matrix. `test_no_verification_command_dirties_the_worktree`
  went red naming the offender and the exact porcelain line::

      mutation-probe: `python scripts/vault-knowledge-graph.py --write --output
      05-Tools/_mutation-probe.canvas` changed the worktree
      -> appeared: ?? 05-Tools/_mutation-probe.canvas

  while `test_no_verification_command_exceeds_the_check_timeout` and
  `test_every_verification_command_exits_zero` stayed green — the red came from
  the side effect, not from a slowdown or a crash. A throwaway `--output` was used
  rather than the default `00-MOC/知识图谱白板（自动生成）` so the probe could be
  undone with `rm` plus a `cp` restore of the matrix; reverting a rewrite of the
  real canvas would have needed `git checkout --`, which TESTING-PATTERNS §2
  forbids. `git diff` afterwards showed no `mutation-probe` residue.
"""
import importlib.util
import pathlib
import re
import subprocess
import sys
import time
import unittest

# Prevent Windows GBK stdout/stderr trap (Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
VAULT_ROOT = _SCRIPTS_DIR.parent
CAPABILITY_CHECK_PATH = _SCRIPTS_DIR / "capability-check.py"
MATRIX_PATH = VAULT_ROOT / "05-Tools" / "CAPABILITY-MATRIX.md"

# Reuse the production parser. A second matrix parser here would be a copy of the
# implementation, and a copy passes even when the real parser regresses
# (TESTING-PATTERNS §3 "probe the real source").
_spec = importlib.util.spec_from_file_location("capability_check", CAPABILITY_CHECK_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_CAPABILITY_CHECK_SOURCE = CAPABILITY_CHECK_PATH.read_text(encoding="utf-8")

# The per-command budget is read out of capability-check.py rather than restated,
# so raising the real timeout cannot leave a stale number asserted here.
_TIMEOUT_PATTERN = r"timeout=(\d+)"
_TIMEOUT_MATCHES = re.findall(_TIMEOUT_PATTERN, _CAPABILITY_CHECK_SOURCE)
CHECK_TIMEOUT_SECONDS = int(_TIMEOUT_MATCHES[0]) if _TIMEOUT_MATCHES else 30

# Deliberately larger than CHECK_TIMEOUT_SECONDS: a command that overruns the real
# budget must be reported by the runtime test as a measured number, not truncated
# into an indistinguishable "TimeoutExpired".
_RUN_TIMEOUT_SECONDS = CHECK_TIMEOUT_SECONDS * 3

GIT_STATUS_ARGV = ["git", "status", "--porcelain=v1", "--untracked-files=all"]


def _git_status() -> bytes:
    """Snapshot the worktree. Raises on git failure — never a silent empty snapshot.

    Returning b"" on error would make every before/after comparison trivially
    equal, i.e. a permanently green gate (TESTING-PATTERNS §4).
    """
    proc = subprocess.run(
        GIT_STATUS_ARGV, cwd=str(VAULT_ROOT), capture_output=True, timeout=60
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git status failed (exit {proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')}"
        )
    return proc.stdout


def _porcelain_delta(before: bytes, after: bytes) -> str:
    """Human-readable added/removed porcelain lines, for the failure message."""
    b = before.decode("utf-8", "replace").splitlines()
    a = after.decode("utf-8", "replace").splitlines()
    added = [line for line in a if line not in b]
    removed = [line for line in b if line not in a]
    parts = []
    if added:
        parts.append("appeared: " + " | ".join(added))
    if removed:
        parts.append("disappeared: " + " | ".join(removed))
    return "; ".join(parts) or "(identical line sets but different bytes/order)"


def _declared_commands() -> list:
    """[(capability_name, command)] for every capability that declares one."""
    return [
        (cap["name"], cap["verification_command"])
        for cap in _mod.parse_matrix(MATRIX_PATH)
        if cap["verification_command"]
    ]


class TestScriptCapabilityCoverage(unittest.TestCase):
    """Static, cheap: a `script` capability with no command can never be verified.

    `check_capability` returns `configured` whenever the command is None. For a
    script — something that is, by definition, runnable from the shell — that is a
    permanent terminal state dressed up as a pending one. Scripts are held to
    "declare how you are verified"; `mcp` and `skill` capabilities are not, they
    need a different probe mechanism (out of scope here).
    """

    @classmethod
    def setUpClass(cls):
        cls.matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
        cls.caps = _mod.parse_matrix(MATRIX_PATH)

    def test_matrix_parses_to_distinct_named_capabilities(self):
        """Fixture coherence (§4): duplicate/absent names would mis-target the rows."""
        names = [c["name"] for c in self.caps]
        self.assertGreater(len(names), 0, f"nothing parsed from {MATRIX_PATH}")
        self.assertEqual(len(names), len(set(names)), f"duplicate capability names: {names}")

    def test_each_capability_row_appears_exactly_once(self):
        """Occurrence precheck (§2), asserted mechanically for every row."""
        multi = []
        for cap in self.caps:
            pattern = r"(?m)^\| " + re.escape(cap["name"]) + r" \|"
            hits = len(re.findall(pattern, self.matrix_text))
            if hits != 1:
                multi.append(f"{cap['name']}: {hits} rows")
        self.assertEqual([], multi, "row anchors must be unique:\n" + "\n".join(multi))

    def test_every_script_capability_has_a_verification_command(self):
        """A `script` row without a command is stuck at `configured` forever."""
        missing = [
            c["name"] for c in self.caps
            if c["type"] == "script" and not c["verification_command"]
        ]
        self.assertEqual(
            [], missing,
            f"{len(missing)} script capabilities declare no verification_command and "
            f"can therefore never be promoted past `configured`: {missing}",
        )


class TestVerificationCommandsAreSideEffectFree(unittest.TestCase):
    """Every matrix verification command must be read-only, by measurement.

    The commands are executed once in `setUpClass` (the full sweep costs ~25s) and
    the individual tests assert over the recorded results.
    """

    runs = []
    setup_error = None

    @classmethod
    def setUpClass(cls):
        try:
            _git_status()
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise unittest.SkipTest(f"git unusable in {VAULT_ROOT}: {exc}")

        cls.commands = _declared_commands()
        cls.runs = []
        for name, cmd in cls.commands:
            before = _git_status()
            started = time.monotonic()
            timed_out = False
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,          # mirrors capability-check.check_capability
                    cwd=str(VAULT_ROOT),
                    capture_output=True,
                    timeout=_RUN_TIMEOUT_SECONDS,
                )
                returncode = proc.returncode
                stderr = proc.stderr.decode("utf-8", "replace")
            except subprocess.TimeoutExpired:
                returncode = None
                timed_out = True
                stderr = f"timed out after {_RUN_TIMEOUT_SECONDS}s"
            duration = time.monotonic() - started
            after = _git_status()
            cls.runs.append({
                "name": name,
                "command": cmd,
                "returncode": returncode,
                "timed_out": timed_out,
                "stderr": stderr[-800:],
                "duration": duration,
                "before": before,
                "after": after,
            })

    def test_matrix_declares_at_least_one_verification_command(self):
        """Anti-vacuous guard: an empty sweep would make every test below green."""
        self.assertGreater(
            len(self.runs), 0,
            f"no verification_command parsed from {MATRIX_PATH}; the side-effect "
            "gate below would be inspecting nothing",
        )

    def test_capability_check_declares_exactly_one_timeout(self):
        """Occurrence precheck (§2) for the budget this file reads out of the source."""
        self.assertEqual(
            len(_TIMEOUT_MATCHES), 1,
            f"{_TIMEOUT_PATTERN!r} matched {len(_TIMEOUT_MATCHES)} sites in "
            f"capability-check.py ({_TIMEOUT_MATCHES}); CHECK_TIMEOUT_SECONDS is "
            "no longer pinned to a single known site",
        )

    def test_every_verification_command_exits_zero(self):
        """Anti-vacuous guard: a command that crashed proves nothing about writes.

        This is also the same condition `capability-check.py` turns into
        `degraded`, so a failure here is a real broken capability, not test noise.
        """
        broken = [
            f"{r['name']}: `{r['command']}` -> "
            f"{'TIMEOUT' if r['timed_out'] else 'exit ' + str(r['returncode'])}"
            f" | stderr: {r['stderr'].strip()[:200]}"
            for r in self.runs
            if r["timed_out"] or r["returncode"] != 0
        ]
        self.assertEqual([], broken, "verification command(s) did not succeed:\n" + "\n".join(broken))

    def test_no_verification_command_dirties_the_worktree(self):
        """THE GATE: `git status` must be byte-identical before and after each command."""
        offenders = [
            f"{r['name']}: `{r['command']}` changed the worktree -> "
            f"{_porcelain_delta(r['before'], r['after'])}"
            for r in self.runs
            if r["before"] != r["after"]
        ]
        self.assertEqual(
            [], offenders,
            "verification commands MUST be read-only; a matrix command that writes "
            "makes every `capability-check.py` run dirty the vault:\n" + "\n".join(offenders),
        )

    def test_no_verification_command_exceeds_the_check_timeout(self):
        """A command slower than capability-check's own budget is reported `degraded`."""
        slow = [
            f"{r['name']}: {r['duration']:.1f}s"
            for r in self.runs
            if r["timed_out"] or r["duration"] >= CHECK_TIMEOUT_SECONDS
        ]
        self.assertEqual(
            [], slow,
            f"command(s) at/over capability-check.py's timeout={CHECK_TIMEOUT_SECONDS}s "
            "would be scored `degraded`; raise the timeout or make the tool faster "
            "— do not drop the command:\n" + "\n".join(slow),
        )


if __name__ == "__main__":
    unittest.main()
