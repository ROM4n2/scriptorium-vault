#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault-Exec Resilient State Machine & Ledger Manager ({{VAULT_ROOT}})

Provides persistent execution checkpoints and 1-second crash recovery for
multi-subagent development pipelines.

CLI Commands:
  python scripts/vault_exec_state.py init --plan-file <path> --tasks <t1,t2,t3>
  python scripts/vault_exec_state.py status
  python scripts/vault_exec_state.py start-task --task-id <id>
  python scripts/vault_exec_state.py complete-task --task-id <id> [--commit <hash>] [--reviewer <status>]
  python scripts/vault_exec_state.py resume
  python scripts/vault_exec_state.py reset
"""

import sys

# Prevent Windows GBK stdout trap (RFC / Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

LEDGER_FILENAME = ".vault-exec-ledger.json"


def get_ledger_path(workdir: Optional[pathlib.Path] = None) -> pathlib.Path:
    if workdir is None:
        workdir = pathlib.Path.cwd()
    return workdir / LEDGER_FILENAME


def load_ledger(workdir: Optional[pathlib.Path] = None) -> Optional[Dict[str, Any]]:
    l_path = get_ledger_path(workdir)
    if not l_path.is_file():
        return None
    try:
        data = json.loads(l_path.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        print(f"⚠️ [LEDGER_WARN] 读取状态机失败: {e}", file=sys.stderr)
        return None


def save_ledger(data: Dict[str, Any], workdir: Optional[pathlib.Path] = None) -> None:
    l_path = get_ledger_path(workdir)
    data["last_updated"] = datetime.datetime.now().isoformat()
    l_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    l_path = get_ledger_path(workdir)

    task_list = []
    if args.tasks:
        for t_item in args.tasks.split(","):
            t_clean = t_item.strip()
            if t_clean:
                task_list.append({
                    "id": t_clean,
                    "title": t_clean,
                    "status": "pending",
                    "implementer": args.role or "TDD",
                    "commit_hash": None,
                    "reviewer_verdict": None,
                    "started_at": None,
                    "completed_at": None
                })
    elif args.plan_file:
        p_path = pathlib.Path(args.plan_file)
        if p_path.is_file():
            content = p_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                m = re.match(r"^###\s+Task\s+(\d+):\s*(.+)$", line.strip())
                if m:
                    num = m.group(1)
                    t_name = m.group(2).strip()
                    role_m = re.search(r"\[Subagent:\s*([^\]]+)\]", t_name)
                    role = role_m.group(1).strip() if role_m else "TDD"
                    task_list.append({
                        "id": f"Task-{num}",
                        "title": t_name,
                        "status": "pending",
                        "implementer": role,
                        "commit_hash": None,
                        "reviewer_verdict": None,
                        "started_at": None,
                        "completed_at": None
                    })

    if not task_list:
        print("❌ 未提供任何有效任务，初始化失败。请使用 --tasks 或 --plan-file。")
        return 1

    ledger_data = {
        "version": "1.0.0",
        "plan_file": str(args.plan_file or "inline"),
        "created_at": datetime.datetime.now().isoformat(),
        "last_updated": datetime.datetime.now().isoformat(),
        "total_tasks": len(task_list),
        "completed_count": 0,
        "active_task_id": None,
        "tasks": task_list
    }

    save_ledger(ledger_data, workdir)
    print(f"🎉 成功初始化执行状态机！已登记 {len(task_list)} 个任务到 `{l_path.name}`。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    data = load_ledger(workdir)

    if not data:
        if args.json:
            print(json.dumps({"active": False}))
        else:
            print(f"ℹ️ 当前目录 `{workdir}` 无进行中的执行状态机 (.vault-exec-ledger.json)。")
        return 0

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    total = data.get("total_tasks", 0)
    completed = data.get("completed_count", 0)
    active_id = data.get("active_task_id")
    pct = (completed / total * 100) if total > 0 else 0.0

    print("=" * 70)
    print(f"📊 [VAULT-EXEC LEDGER] 执行状态流水线 (完成度: {completed}/{total} - {pct:.1f}%)")
    print("=" * 70)
    print(f"  📁 对应计划: {data.get('plan_file')}")
    print(f"  ⏰ 最近更新: {data.get('last_updated')}")
    print("-" * 70)

    for idx, t in enumerate(data.get("tasks", []), 1):
        s = t.get("status")
        t_id = t.get("id")
        t_title = t.get("title")
        role = t.get("implementer", "TDD")
        c_hash = t.get("commit_hash") or "-"
        verdict = t.get("reviewer_verdict") or "-"

        if s == "completed":
            icon = "✅"
            status_text = f"COMPLETED [Commit: {c_hash} | Review: {verdict}]"
        elif s == "in_progress":
            icon = "⏳"
            status_text = f"IN PROGRESS [Subagent: {role}]"
        else:
            icon = "⚪"
            status_text = f"PENDING    [Subagent: {role}]"

        print(f"  {icon} {t_id:8} | {status_text:45} | {t_title}")

    print("=" * 70)
    return 0


def cmd_start_task(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    data = load_ledger(workdir)

    if not data:
        print("❌ 未找到执行状态机，请先运行 init。")
        return 1

    target_id = args.task_id.strip()
    found = False
    for t in data.get("tasks", []):
        if t.get("id").lower() == target_id.lower():
            t["status"] = "in_progress"
            t["started_at"] = datetime.datetime.now().isoformat()
            data["active_task_id"] = t.get("id")
            found = True
            break

    if not found:
        print(f"❌ 未找到任务 ID: {target_id}")
        return 1

    save_ledger(data, workdir)
    print(f"🚀 任务 `{target_id}` 已标记为进行中 (IN_PROGRESS)！")
    return 0


def cmd_complete_task(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    data = load_ledger(workdir)

    if not data:
        print("❌ 未找到执行状态机，请先运行 init。")
        return 1

    target_id = args.task_id.strip()
    found = False
    for t in data.get("tasks", []):
        if t.get("id").lower() == target_id.lower():
            t["status"] = "completed"
            t["completed_at"] = datetime.datetime.now().isoformat()
            if args.commit:
                t["commit_hash"] = args.commit.strip()
            if args.reviewer:
                t["reviewer_verdict"] = args.reviewer.strip()
            found = True
            break

    if not found:
        print(f"❌ 未找到任务 ID: {target_id}")
        return 1

    completed_count = sum(1 for t in data.get("tasks", []) if t.get("status") == "completed")
    data["completed_count"] = completed_count
    data["active_task_id"] = None

    save_ledger(data, workdir)
    print(f"🎉 任务 `{target_id}` 已标记为完成 (COMPLETED)！[已完成: {completed_count}/{data.get('total_tasks')}]")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    data = load_ledger(workdir)

    if not data:
        print("ℹ️ 无未完状态机。")
        return 0

    next_task = None
    for t in data.get("tasks", []):
        if t.get("status") in ("pending", "in_progress"):
            next_task = t
            break

    if not next_task:
        print("🎉 恭喜！当前计划中的所有任务已全部完成！")
        return 0

    if args.json:
        print(json.dumps(next_task, ensure_ascii=False, indent=2))
    else:
        print(f"▶️ [RESUME_CHECKPOINT] 发现断点任务：`{next_task.get('id')}`")
        print(f"  - 任务标题: {next_task.get('title')}")
        print(f"  - 执行角色: {next_task.get('implementer')}")
        print(f"  - 当前状态: {next_task.get('status')}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    workdir = pathlib.Path(args.workdir) if args.workdir else pathlib.Path.cwd()
    l_path = get_ledger_path(workdir)
    if l_path.is_file():
        l_path.unlink()
        print(f"🧹 已清除执行状态机 `{l_path.name}`。")
    else:
        print("ℹ️ 状态机文件不存在，无需清除。")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Vault-Exec State Machine & Ledger Manager")
    parser.add_argument("--workdir", help="Target workspace root directory (defaults to current dir)")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # init
    p_init = subparsers.add_parser("init", help="Initialize new ledger")
    p_init.add_argument("--plan-file", help="Path to markdown implementation plan")
    p_init.add_argument("--tasks", help="Comma-separated task list (e.g. 'Task 1,Task 2')")
    p_init.add_argument("--role", help="Default implementer subagent role")

    # status
    p_status = subparsers.add_parser("status", help="Show ledger status")
    p_status.add_argument("--json", action="store_true", help="Output JSON")

    # start-task
    p_start = subparsers.add_parser("start-task", help="Start a task")
    p_start.add_argument("--task-id", required=True, help="Task ID (e.g. 'Task-1')")

    # complete-task
    p_comp = subparsers.add_parser("complete-task", help="Complete a task")
    p_comp.add_argument("--task-id", required=True, help="Task ID")
    p_comp.add_argument("--commit", help="Git commit hash")
    p_comp.add_argument("--reviewer", help="Task reviewer verdict (e.g. 'PASS')")

    # resume
    p_res = subparsers.add_parser("resume", help="Get next pending task for breakpoint recovery")
    p_res.add_argument("--json", action="store_true", help="Output JSON")

    # reset
    subparsers.add_parser("reset", help="Reset/delete ledger")

    args = parser.parse_args()
    if not args.action:
        return cmd_status(args)

    if args.action == "init":
        return cmd_init(args)
    elif args.action == "status":
        return cmd_status(args)
    elif args.action == "start-task":
        return cmd_start_task(args)
    elif args.action == "complete-task":
        return cmd_complete_task(args)
    elif args.action == "resume":
        return cmd_resume(args)
    elif args.action == "reset":
        return cmd_reset(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
