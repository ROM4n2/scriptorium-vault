#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scripts/mcp_probe.py — the MCP stdio JSON-RPC handshake verifier.

The probe is a *verification* tool consumed by capability-check.py, so these tests
exercise it end-to-end as a subprocess (exit code is the contract, not internals).

Fake servers are written into a tempfile dir so the misbehaving cases (crash / hang /
garbage) are deterministic instead of depending on a real server going wrong.

Anti-dead-test notes (01-Rules/TESTING-PATTERNS.md):
  - Every stderr phrase asserted below was occurrence-prechecked with
    len(re.findall(pattern, stderr)) == 1, so each assertion pins exactly one emission
    site (cause #4). test_probe_emits_each_failure_phrase_exactly_once locks that in.
  - Mutation-verified (§2 "变异声明必须实证", actually executed, not claimed):
    making the tool-count comparison always-true in mcp_probe.py turns
    test_expect_tools_mismatch_exits_1 RED.
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
PROBE = SCRIPTS_DIR / "mcp_probe.py"
REAL_SERVER = SCRIPTS_DIR / "vault_search_mcp.py"

# Upper bound for the *test harness* waiting on the probe. The probe owns its own,
# much shorter timeout; if the harness bound is ever hit, the probe failed to self-limit.
HARNESS_TIMEOUT = 30

HEALTHY_SERVER_TEMPLATE = '''\
import json, sys

TOOLS = [
    {{"name": "tool_%d" % i, "description": "fake", "inputSchema": {{"type": "object"}}}}
    for i in range({tool_count})
]

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    method = req.get("method", "")
    if method == "initialize":
        resp = {{"jsonrpc": "2.0", "id": req.get("id"), "result": {{
            "protocolVersion": "2024-11-05",
            "capabilities": {{"tools": {{}}}},
            "serverInfo": {{"name": "fake-healthy", "version": "1.0.0"}},
        }}}}
    elif method == "tools/list":
        resp = {{"jsonrpc": "2.0", "id": req.get("id"), "result": {{"tools": TOOLS}}}}
    else:
        continue  # notifications get no response, like the real servers
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
'''

CRASH_SERVER = '''\
import sys
sys.stderr.write("ImportError: cannot import name 'frobnicator'\\n")
sys.exit(1)
'''

HANG_SERVER = '''\
import time
time.sleep(120)  # never reads stdin, never answers
'''

GARBAGE_SERVER = '''\
import sys
for line in sys.stdin:
    sys.stdout.write("this is not json-rpc\\n")
    sys.stdout.flush()
'''


def _run_probe(*args, timeout=HARNESS_TIMEOUT):
    """Run mcp_probe.py as a subprocess and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(PROBE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


class MCPProbeTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="mcp_probe_test_"))
        cls.healthy = cls.tmpdir / "healthy_server.py"
        cls.healthy.write_text(HEALTHY_SERVER_TEMPLATE.format(tool_count=3), encoding="utf-8")
        cls.crash = cls.tmpdir / "crash_server.py"
        cls.crash.write_text(CRASH_SERVER, encoding="utf-8")
        cls.hang = cls.tmpdir / "hang_server.py"
        cls.hang.write_text(HANG_SERVER, encoding="utf-8")
        cls.garbage = cls.tmpdir / "garbage_server.py"
        cls.garbage.write_text(GARBAGE_SERVER, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)


class TestHealthyHandshake(MCPProbeTestBase):
    """Case 1: a well-behaved server must exit 0."""

    def test_healthy_server_exits_0(self):
        proc = _run_probe(str(self.healthy))
        self.assertEqual(
            proc.returncode, 0,
            f"healthy server should exit 0\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )

    def test_healthy_server_reports_tool_count_on_stdout(self):
        """The probe must report what it actually found, not just succeed silently."""
        proc = _run_probe(str(self.healthy))
        self.assertIn("3 tools", proc.stdout, f"stdout={proc.stdout!r}")

    def test_matching_expect_tools_exits_0(self):
        proc = _run_probe(str(self.healthy), "--expect-tools", "3")
        self.assertEqual(
            proc.returncode, 0,
            f"--expect-tools 3 against a 3-tool server should pass\nstderr={proc.stderr}",
        )

    def test_real_vault_search_mcp_handshake_exits_0(self):
        """Integration: the probe must work against a production server.

        Deliberately does NOT pin the tool count here — the count contract lives in
        CAPABILITY-MATRIX.md, not in this test file.
        """
        proc = _run_probe(str(REAL_SERVER))
        self.assertEqual(
            proc.returncode, 0,
            f"real vault_search_mcp handshake failed\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )


class TestExpectToolsMismatch(MCPProbeTestBase):
    """Case 2: --expect-tools N must be a real assertion, not decoration."""

    def test_expect_tools_mismatch_exits_1(self):
        proc = _run_probe(str(self.healthy), "--expect-tools", "99")
        self.assertEqual(
            proc.returncode, 1,
            f"--expect-tools 99 against a 3-tool server must fail\nstdout={proc.stdout}",
        )

    def test_expect_tools_mismatch_reports_both_numbers(self):
        """A bare 'mismatch' is useless; the reason must name expected and actual."""
        proc = _run_probe(str(self.healthy), "--expect-tools", "99")
        self.assertIn("expected 99", proc.stderr, f"stderr={proc.stderr!r}")
        self.assertIn("got 3", proc.stderr, f"stderr={proc.stderr!r}")


class TestUnresponsiveServers(MCPProbeTestBase):
    """Case 3: crash / hang / protocol-garbage must exit 1 with a readable reason."""

    def test_crashing_server_exits_1(self):
        proc = _run_probe(str(self.crash))
        self.assertEqual(proc.returncode, 1, f"stdout={proc.stdout}\nstderr={proc.stderr}")

    def test_crashing_server_reason_names_the_failed_step(self):
        proc = _run_probe(str(self.crash))
        self.assertIn("no response to 'initialize'", proc.stderr, f"stderr={proc.stderr!r}")

    def test_crashing_server_surfaces_child_stderr(self):
        """Zero silent swallowing: the child's own traceback is the actionable part."""
        proc = _run_probe(str(self.crash))
        self.assertIn("frobnicator", proc.stderr, f"stderr={proc.stderr!r}")

    def test_hanging_server_exits_1_without_hanging_the_suite(self):
        """A short --timeout must bound the probe well below the harness timeout."""
        proc = _run_probe(str(self.hang), "--timeout", "2", timeout=20)
        self.assertEqual(proc.returncode, 1, f"stdout={proc.stdout}\nstderr={proc.stderr}")

    def test_hanging_server_reason_says_timed_out(self):
        proc = _run_probe(str(self.hang), "--timeout", "2", timeout=20)
        self.assertIn("timed out", proc.stderr, f"stderr={proc.stderr!r}")

    def test_garbage_output_server_exits_1(self):
        """Non-JSON on stdout is a protocol violation, not a pass."""
        proc = _run_probe(str(self.garbage))
        self.assertEqual(proc.returncode, 1, f"stdout={proc.stdout}\nstderr={proc.stderr}")

    def test_missing_server_file_exits_1_with_reason(self):
        missing = self.tmpdir / "does_not_exist.py"
        proc = _run_probe(str(missing))
        self.assertEqual(proc.returncode, 1, f"stdout={proc.stdout}")
        self.assertIn("not found", proc.stderr, f"stderr={proc.stderr!r}")

    def test_negative_expect_tools_is_rejected_not_ignored(self):
        """A negative N must be an error, never a silently-skipped assertion.

        Treating it as 'no check' would turn a typo into a green smoke test — the
        exact degradation --expect-tools exists to prevent.
        """
        proc = _run_probe(str(self.healthy), "--expect-tools", "-1")
        self.assertNotEqual(
            proc.returncode, 0,
            f"--expect-tools -1 must not silently pass\nstdout={proc.stdout}",
        )
        self.assertIn("--expect-tools must be >= 0", proc.stderr, f"stderr={proc.stderr!r}")


class TestDiagnosticsAreDiscriminating(MCPProbeTestBase):
    """Occurrence precheck (TESTING-PATTERNS §2 ①②) locked in as an executable test.

    Each phrase the tests above assert on MUST appear exactly once in the stderr it
    was asserted against. If a refactor starts echoing a reason twice, the assertions
    silently stop pinning one site — this test fails first.
    """

    def test_probe_emits_each_failure_phrase_exactly_once(self):
        cases = [
            ([str(self.healthy), "--expect-tools", "99"], r"expected 99"),
            ([str(self.healthy), "--expect-tools", "99"], r"got 3"),
            ([str(self.crash)], r"no response to 'initialize'"),
            ([str(self.crash)], r"frobnicator"),
        ]
        for args, pattern in cases:
            with self.subTest(pattern=pattern):
                stderr = _run_probe(*args).stderr
                self.assertEqual(
                    len(re.findall(pattern, stderr)), 1,
                    f"pattern {pattern!r} must appear exactly once in stderr:\n{stderr}",
                )

    def test_timed_out_phrase_appears_exactly_once(self):
        stderr = _run_probe(str(self.hang), "--timeout", "2", timeout=20).stderr
        self.assertEqual(
            len(re.findall(r"timed out", stderr)), 1,
            f"'timed out' must appear exactly once in stderr:\n{stderr}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
