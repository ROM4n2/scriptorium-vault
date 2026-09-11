#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP stdio handshake probe — headless verifier for JSON-RPC MCP servers.

Usage:
    python scripts/mcp_probe.py <path/to/server.py> [--expect-tools N] [--timeout SECONDS]

Performs the stdio JSON-RPC handshake a real MCP client would perform:
    1. initialize
    2. notifications/initialized  (a notification: no response expected)
    3. tools/list

Exit codes (this is the contract consumed by scripts/capability-check.py):
    0 — handshake succeeded (and, with --expect-tools N, the tool count matched)
    1 — verification failed, with a human-readable reason on stderr
    2 — usage error (argparse convention: bad/unknown flag, negative --expect-tools)
        capability-check.py treats any non-zero as `degraded`, so 1 vs 2 only matters
        to a human reading the log.

Design notes:
  - The three messages are written to the child's stdin in one batch. The servers in
    this vault read stdin line-by-line (`for line in sys.stdin`) and answer in order,
    and responses are matched by JSON-RPC `id`, not by line position — so batching is
    safe and removes the need for per-read timeouts (which need threads on Windows).
  - subprocess.run(timeout=...) is the timeout AND the reaper: on TimeoutExpired it
    kills the child and drains it before re-raising, so no orphan python process
    survives a hung server. Never wait on a child's stdout without a bound.
  - Nothing is swallowed: every failure path routes through ProbeError to stderr,
    carrying the child's own stdout/stderr excerpt so the reason is actionable.
"""

import sys

# Prevent Windows GBK stdout/stderr trap (RFC / Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import pathlib
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

# Well under capability-check.py's 30s per-command budget, and configurable.
DEFAULT_TIMEOUT = 10.0
EXCERPT_LINES = 20

INIT_ID = 1
TOOLS_ID = 2

CLIENT_INFO = {"name": "mcp-probe", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"


class ProbeError(Exception):
    """A handshake failure with a human-readable reason. Never swallowed."""


def build_handshake() -> str:
    """Return the three newline-delimited JSON-RPC messages sent to the server."""
    messages: List[Dict[str, Any]] = [
        {
            "jsonrpc": "2.0",
            "id": INIT_ID,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": TOOLS_ID, "method": "tools/list", "params": {}},
    ]
    return "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)


def _excerpt(stream: str, label: str) -> str:
    """Format the tail of a child stream for inclusion in a failure reason."""
    lines = [line for line in (stream or "").splitlines() if line.strip()]
    if not lines:
        return ""
    tail = lines[-EXCERPT_LINES:]
    body = "\n".join("    " + line for line in tail)
    return f"\n  --- server {label} (last {len(tail)} line(s)) ---\n{body}"


def run_handshake(server: pathlib.Path, timeout: float) -> Tuple[str, str, int]:
    """Spawn the server, drive the handshake, return (stdout, stderr, returncode).

    Raises ProbeError on timeout. The child is always reaped: subprocess.run kills and
    drains it on TimeoutExpired, and closes its pipes on every other path.
    """
    try:
        proc = subprocess.run(
            [sys.executable, str(server)],
            input=build_handshake(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        detail = _excerpt(exc.stderr if isinstance(exc.stderr, str) else "", "stderr")
        raise ProbeError(
            f"handshake timed out after {timeout:g}s "
            f"(server never completed the exchange; killed){detail}"
        ) from exc
    except OSError as exc:
        raise ProbeError(f"cannot start server process: {exc}") from exc

    return proc.stdout, proc.stderr, proc.returncode


def parse_responses(stdout: str) -> Dict[Any, Dict[str, Any]]:
    """Index JSON-RPC responses by id. Non-JSON stdout noise is skipped, not fatal here.

    Skipping is not swallowing: if the responses we need are absent, the caller raises
    ProbeError and prints the raw stdout excerpt, so garbage stays visible.
    """
    responses: Dict[Any, Dict[str, Any]] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "id" in obj:
            responses[obj["id"]] = obj
    return responses


def require_result(
    responses: Dict[Any, Dict[str, Any]],
    resp_id: Any,
    method: str,
    context: str,
) -> Dict[str, Any]:
    """Return the `result` object for one request, or raise a ProbeError explaining why not."""
    resp = responses.get(resp_id)
    if resp is None:
        raise ProbeError(f"no response to {method!r}{context}")

    error = resp.get("error")
    if error is not None:
        raise ProbeError(f"server returned an error for {method!r}: {error}")

    result = resp.get("result")
    if not isinstance(result, dict):
        raise ProbeError(f"malformed response to {method!r}: missing 'result' object")

    return result


def probe(server: pathlib.Path, expect_tools: Optional[int], timeout: float) -> str:
    """Run the full handshake. Returns a success summary, or raises ProbeError."""
    if not server.is_file():
        raise ProbeError(f"server script not found: {server}")

    started = time.monotonic()
    stdout, stderr, returncode = run_handshake(server, timeout)
    elapsed = time.monotonic() - started

    # Context appended only to "no response" failures: that is where the child's own
    # crash output is the actionable part.
    context = (
        f" (server exit code {returncode})"
        + _excerpt(stderr, "stderr")
        + _excerpt(stdout, "stdout")
    )

    responses = parse_responses(stdout)
    init_result = require_result(responses, INIT_ID, "initialize", context)
    tools_result = require_result(responses, TOOLS_ID, "tools/list", context)

    tools = tools_result.get("tools")
    if not isinstance(tools, list):
        raise ProbeError("malformed 'tools/list' result: 'tools' is not a list")

    count = len(tools)
    if expect_tools is not None and count != expect_tools:
        raise ProbeError(f"tool count mismatch: expected {expect_tools}, got {count}")

    protocol = init_result.get("protocolVersion", "?")
    name = init_result.get("serverInfo", {}).get("name", server.name)
    return f"{name} — protocol {protocol}, {count} tools, {elapsed:.2f}s"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an MCP server's stdio JSON-RPC handshake.",
    )
    parser.add_argument("server", help="path to the MCP server script")
    parser.add_argument(
        "--expect-tools",
        type=int,
        default=None,
        metavar="N",
        help="fail unless tools/list returns exactly N tools",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"abort and fail if the handshake exceeds this (default: {DEFAULT_TIMEOUT:g}s)",
    )
    args = parser.parse_args()

    # A negative N would otherwise silently degrade this verification into a smoke
    # test — the exact failure mode --expect-tools exists to prevent.
    if args.expect_tools is not None and args.expect_tools < 0:
        parser.error(f"--expect-tools must be >= 0, got {args.expect_tools}")

    server = pathlib.Path(args.server)
    try:
        summary = probe(server, args.expect_tools, args.timeout)
    except ProbeError as exc:
        print(f"mcp_probe: FAIL {server.name} — {exc}", file=sys.stderr)
        return 1

    print(f"mcp_probe: OK {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
