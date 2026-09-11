#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Vault Template Publisher — 一键重发布（导出 → 自检 → 提交 → 推送）

把 `vault-export-template.py` 的导出、包内自检、git 提交与推送串成一条
fail-closed 流水线，避免手工发布漏步骤：

    1. 导出：刷新包内容（keep / 空壳 / 骨架 / 去标识化 / 断链修复）
    2. 自检：包内 `pytest scripts/tests/` 与 `quality --strict` 必须全绿
       （任一失败即中止，不提交、不推送）
    3. 提交：`git add -A` + commit（无变更则跳过）
    4. 推送：`git push <remote> <branch>`

安全默认：**默认 dry-run**，必须 `--apply` 才真正执行写盘/提交/推送；
`export_fn` 与 `self_check_fn` 可注入，便于测试与定制。
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import importlib.util
import pathlib
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "master"


def _load_exporter(vault_root: pathlib.Path):
    """按路径加载连字符文件名的导出器。"""
    spec = importlib.util.spec_from_file_location(
        "vault_export_template", vault_root / "scripts" / "vault-export-template.py"
    )
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise ImportError("cannot load vault-export-template.py")
    spec.loader.exec_module(module)
    return module


def self_check_commands() -> List[List[str]]:
    """包内必须全绿的四条自检命令（顺序即执行顺序）。

    3️⃣ 模板 lint：裸文本引用体检（healthcheck 只查 wikilink/反引号，
    导出模板的断引用多为裸文本 → 仅靠 healthcheck 会"假绿"）。
    4️⃣ healthcheck：结构契约（入口副本一致性 Check 5 曾因 CRLF 物化
    全线 content-mismatch，只有把 healthcheck 纳入发布自检才能拦住）。
    """
    return [
        [sys.executable, "-m", "pytest", "scripts/tests/", "-q"],
        [sys.executable, "scripts/vault-quality-check.py", "--strict"],
        [sys.executable, "scripts/vault-template-lint.py", "--package-dir", "."],
        [sys.executable, "scripts/vault-healthcheck.py"],
    ]


def run_self_checks(package_dir: pathlib.Path) -> Tuple[bool, List[str]]:
    """在包内跑自检；返回 (是否全绿, 失败命令摘要)。"""
    failures: List[str] = []
    for cmd in self_check_commands():
        res = subprocess.run(
            cmd, cwd=str(package_dir), capture_output=True,
            encoding="utf-8", errors="replace",
        )
        if res.returncode != 0:
            tail = (res.stdout or res.stderr or "").strip().splitlines()[-3:]
            failures.append(f"{' '.join(cmd)} -> rc={res.returncode}\n  " + "\n  ".join(tail))
    return (not failures), failures


def _git(package_dir: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(package_dir), capture_output=True,
        encoding="utf-8", errors="replace",
    )


def publish(
    vault_root: pathlib.Path,
    package_dir: pathlib.Path,
    message: str,
    apply: bool = False,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
    export_fn: Optional[Callable[[], Dict]] = None,
    self_check_fn: Optional[Callable[[pathlib.Path], Tuple[bool, List[str]]]] = None,
) -> Dict:
    """执行发布流水线；apply=False 时只报告计划。"""
    report: Dict = {"applied": apply, "exported": None, "checks_passed": None,
                    "committed": False, "pushed": False, "detail": []}

    if not apply:
        report["detail"].append("dry-run：加 --apply 才会导出/提交/推送")
        return report

    if not (package_dir / ".git").exists():
        raise RuntimeError(f"{package_dir} 不是 git 仓库（先 git init 并配置 remote）")

    # 1) 导出刷新
    if export_fn is None:
        exporter = _load_exporter(vault_root)
        doc = exporter.load_manifest(vault_root / exporter.MANIFEST_REL)
        export_fn = lambda: exporter.export_template(vault_root, package_dir, doc, apply=True)  # noqa: E731
    report["exported"] = export_fn()

    # 2) 自检 fail-closed
    check = self_check_fn or run_self_checks
    ok, failures = check(package_dir)
    report["checks_passed"] = ok
    if not ok:
        report["detail"].extend(failures)
        raise RuntimeError("包内自检未通过，已中止（未提交、未推送）")

    # 3) 提交（无变更则跳过）
    _git(package_dir, "add", "-A")
    status = _git(package_dir, "status", "--porcelain").stdout.strip()
    if not status:
        report["detail"].append("无变更，跳过提交")
    else:
        res = _git(package_dir, "commit", "-m", message)
        if res.returncode != 0:
            report["detail"].append(f"提交失败：{res.stdout.strip()} {res.stderr.strip()}")
            raise RuntimeError("git commit 失败")
        report["committed"] = True

    # 4) 推送
    res = _git(package_dir, "push", remote, branch)
    if res.returncode != 0:
        report["detail"].append(f"推送失败：{res.stderr.strip()}")
        raise RuntimeError("git push 失败")
    report["pushed"] = True
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="重发布知识库模板（导出 → 自检 → 提交 → 推送；默认 dry-run）"
    )
    parser.add_argument("--package-dir", default=None,
                        help="模板包目录（须为 git 仓库；MUST 显式指定，不设默认值）")
    parser.add_argument("--message", default="chore: refresh template from source vault",
                        help="提交信息")
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run）")
    parser.add_argument("--vault-root", default=None, help="源库根（默认 scripts/ 父目录）")
    args = parser.parse_args(argv)

    if not args.package_dir:
        print("❌ 必须指定 --package-dir（模板包目录，须为 git 仓库）", file=sys.stderr)
        return 2
    vault_root = (
        pathlib.Path(args.vault_root).resolve() if args.vault_root
        else pathlib.Path(__file__).resolve().parent.parent
    )
    package_dir = pathlib.Path(args.package_dir).resolve()

    if vault_root == package_dir or vault_root in package_dir.parents:
        print("❌ 包目录不得位于源库内（会污染质量门与测试）。", file=sys.stderr)
        return 2

    try:
        report = publish(vault_root, package_dir, args.message, apply=args.apply,
                         remote=args.remote, branch=args.branch)
    except RuntimeError as exc:
        print(f"❌ 发布中止：{exc}", file=sys.stderr)
        return 1

    if not args.apply:
        print("=" * 60)
        print(" 🚀 TEMPLATE PUBLISH PLAN (dry-run)")
        print("=" * 60)
        print(f" 源库    : {vault_root}")
        print(f" 包目录  : {package_dir}")
        print(f" 远程    : {args.remote}/{args.branch}")
        print(" 自检    : pytest scripts/tests/ ; vault-quality-check --strict")
        print(" 加 --apply 执行导出 → 自检 → 提交 → 推送")
        return 0

    print(f"✅ 发布完成 → {package_dir}")
    print(f"  exported: {report['exported']}")
    print(f"  checks_passed: {report['checks_passed']}")
    print(f"  committed: {report['committed']} | pushed: {report['pushed']}")
    for line in report["detail"]:
        print(f"  · {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
