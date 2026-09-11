#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nightly Automated Vault Maintenance & Memory Compactor Daemon
============================================================
Runs at 03:00 AM daily (or on demand) to:
1. Run memory compactor on 99-Inbox/ drafts
2. Regenerate 00-MOC/知识图谱白板（自动生成） (bare invocation = write)
3. Derive 11-Agents/可信度账本「自动生成」 from frontmatter truth (P4 Task-5;
   bare invocation = write, keeps the ledger perpetually fresh)
4. Regenerate dashboards/ multi-page set (P5 Task-2, --apply)
5. Refresh dashboards/sessions.md via vault-insights (P6 Task-4, --apply)
6. Run strict quality check
7. Commit and push updates to GitHub remote repository
8. Record audit entry in 11-Agents/logs/{YYYY-MM}.md (month-sharded)

Step-driven design (P1 Task-6): `build_nightly_steps()` is a pure function
returning the ordered pipeline as (step_name, argv) pairs; `main()` walks it.
Error semantics per step:
  - memory-compactor / canvas-regen: best-effort, never abort the run
    (compactor parity); canvas passes both stdout and stderr through to
    the nightly log.
  - quality-check: strict gate — a non-zero returncode (or an exception)
    exits the whole run with code 1, before git-sync can fire.
  - git-sync: best-effort, failures reported but non-fatal.

Import safety: loading this module via importlib (hyphenated filename — see
scripts/tests/test_nightly_steps.py) has no side effects beyond stream
reconfiguration; execution only happens under `if __name__ == "__main__"`.
"""

import sys
import subprocess
import datetime
from typing import Callable, Optional

# Shared audit-log writer (single source of truth for 11-Agents/logs/{YYYY-MM}.md appends)
from vault_audit import append_audit_row

# Portability contract (Release Plan Task 3): CLI > $VAULT_ROOT > scripts/ parent
from vault_paths import resolve_vault_root

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VAULT = resolve_vault_root()


def build_nightly_steps() -> list[tuple[str, list[str]]]:
    """Return the ordered nightly pipeline as (step_name, argv) tuples.

    Pure function: no I/O, no subprocess calls. Each argv is executed by
    `main()` with cwd=VAULT (the vault root). Order is load-bearing:
    compactor rewrites drafts -> canvas regenerates from the vault ->
    strict quality gate -> git sync publishes everything only if the
    gate passed.

    The canvas step is the *bare* invocation of vault-knowledge-graph.py:
    bare = write is the documented compatibility contract (README.md,
    scripts/README.md, AGENTS.md); a `--json` flag here would silently
    turn the nightly graph step read-only.
    """
    return [
        ("memory-compactor",
         [sys.executable, str(VAULT / "scripts" / "vault-memory-compactor.py")]),
        ("canvas-regen",
         [sys.executable, str(VAULT / "scripts" / "vault-knowledge-graph.py")]),
        ("claim-ledger",
         [sys.executable, str(VAULT / "scripts" / "vault-claim-ledger.py")]),
        ("dashboards",
         [sys.executable, str(VAULT / "scripts" / "vault-dashboards.py"),
          "--apply"]),
        ("insights",
         [sys.executable, str(VAULT / "scripts" / "vault-insights.py"),
          "--apply"]),
        ("quality-check",
         [sys.executable, str(VAULT / "scripts" / "vault-quality-check.py"), "--strict"]),
        ("git-sync",
         ["git", "status", "--porcelain"]),
    ]


def _run_best_effort(name: str, argv: list[str]) -> None:
    """Run a non-gating step: failures are reported, never fatal.

    Both child streams are passed through to the nightly log (canvas-regen
    prints its own success banner on stdout and diagnostics on stderr).
    """
    try:
        res = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", cwd=str(VAULT),
            timeout=600,  # 无人值守链路必须有时限，否则挂起即静默停摆（2026-09-11 二评）
        )
        if res.stdout:
            print(res.stdout)
        if res.stderr:
            print(res.stderr)
    except subprocess.TimeoutExpired as e:
        print(f"⚠️ {name} timed out after {e.timeout}s (killed; treated as best-effort failure)")
    except Exception as e:
        print(f"⚠️ {name} error: {e}")


def _run_quality_gate(argv: list[str]) -> int:
    """Run the strict quality check; any failure exits the nightly run (1)."""
    try:
        res_qc = subprocess.run(
            argv, capture_output=True, text=True,
            encoding="utf-8", errors="replace", cwd=str(VAULT),
            timeout=600,
        )
        if res_qc.returncode != 0:
            print("❌ Quality check failed, skipping git push:")
            print(res_qc.stdout)
            return 1
        print("✅ Quality check passed (100/100)!")
        return 0
    except Exception as e:
        print(f"⚠️ Quality check error: {e}")
        return 1


def _current_branch() -> str:
    """当前分支名（detached HEAD 等异常时回退 master）。

    硬编码 master 会让默认分支为 main 的库（接收者常见情形）夜间推送静默失败。
    """
    try:
        res = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(VAULT), timeout=30,
        )
        branch = res.stdout.strip()
        return branch or "master"
    except Exception:
        return "master"


def _run_git_sync(status_argv: list[str]) -> None:
    """Commit & push when the working tree is dirty; best-effort, non-fatal."""
    try:
        # Check if dirty (the step's argv IS the dirty probe)
        st_res = subprocess.run(status_argv, capture_output=True, text=True, cwd=str(VAULT), timeout=60)
        if st_res.stdout.strip():
            subprocess.run(["git", "add", "-A"], cwd=str(VAULT), check=True, timeout=60)
            today = datetime.date.today().strftime("%Y-%m-%d")
            subprocess.run(["git", "commit", "-m", f"chore(nightly): automated memory compaction & healthcheck [{today}]"], cwd=str(VAULT), check=True, timeout=60)
            branch = _current_branch()
            # timeout 是无人值守场景的关键防线：未配凭据助手的全新机器上
            # git push 会永久挂起（2026-09-11 二评）
            subprocess.run(["git", "push", "origin", branch], cwd=str(VAULT), check=True, timeout=120)
            print(f"🎉 Nightly changes committed and pushed to remote {branch}!")
        else:
            print("ℹ️ Working tree clean, no commit needed.")
    except Exception as e:
        print(f"⚠️ Git push error: {e}")


def _default_executor(name: str, argv: list[str]) -> int:
    """Dispatch one step by name (the production executor)."""
    if name == "quality-check":
        return _run_quality_gate(argv)
    if name == "git-sync":
        _run_git_sync(argv)
        return 0
    # memory-compactor / canvas-regen / claim-ledger / dashboards /
    # insights: best-effort parity (module docstring); a sensor failure
    # must not block the quality gate.
    _run_best_effort(name, argv)
    return 0


def run_pipeline(
    steps: list[tuple[str, list[str]]],
    executor: Optional[Callable[[str, list[str]], int]] = None,
) -> int:
    """Walk the pipeline; returns 1 if the quality gate fails, else 0.

    Injectable `executor` (P1 yellow card #3) so the dispatch semantics are
    testable without subprocesses: a failing/raising quality-check aborts
    the run before git-sync, any other step failure is best-effort.
    """
    ex = executor or _default_executor
    total = len(steps)
    for idx, (name, argv) in enumerate(steps, start=1):
        print(f"\n▶ [{idx}/{total}] step: {name}")
        try:
            rc = ex(name, argv)
        except Exception as e:
            if name == "quality-check":
                print(f"⚠️ Quality check error: {e}")
                return 1
            print(f"⚠️ {name} raised: {e}")
            continue
        if name == "quality-check" and rc != 0:
            return 1
    return 0


def main() -> int:
    """Execute the nightly pipeline step by step; returns the exit code."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== [Coding Vault Nightly Maintenance] Started at {now_str} ===")

    # 审计行先于管线落盘：管线末尾的 git-sync 才能把当夜的审计行一并提交
    # （原时序 append 在 push 之后 → 审计行永远等下一次夜跑才入库，工作区每夜必脏）。
    ok, msg = append_audit_row(VAULT, "Nightly-Daemon", "Scheduled Maintenance",
                               "COMPACT+CANVAS+HEALTH+SYNC", "STARTED", timestamp=now_str)
    print(msg)

    if run_pipeline(build_nightly_steps()) != 0:
        return 1

    print("=== [Coding Vault Nightly Maintenance] Finished successfully ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
