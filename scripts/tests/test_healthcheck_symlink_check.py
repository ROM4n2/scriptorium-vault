#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for Release Plan Task-7: healthcheck Check 5 接受「降级内容副本」形态。

发布彩排实证：Windows 默认无符号链接权限时，`git archive | tar` 解压或 clone
后，5 个多 Agent 入口（CLAUDE.md / GEMINI.md / .cursorrules / .windsurfrules /
CONVENTIONS.md）只能成为**内容与 AGENTS.md 完全一致的普通文件副本**（正是
Task-5 自愈 hook 的降级形态）。旧 Check 5 对普通文件一律判 FAIL → 新机器
`Overall: HEALTHCHECK FAILED` → 连带
`test_capability_commands.py::test_every_verification_command_exits_zero`
失败，等于「开箱即坏」。

本文件钉死新的四态契约（fail-closed 语义不变）：
(a) 5 入口均为「内容与 AGENTS.md 完全一致的普通文件」→ Check 5 **降级通过**
    且 `run_all_checks()["all_passed"]` 为 True（整体 PASSED），但报告输出中
    必须带明确降级告警（含恢复指引文案）；
(b) 入口内容为空 / 与 AGENTS.md 不一致 → 仍 FAIL（fail-closed 不变；
    4 好 1 坏也必须整体 FAIL，不做多数派投票）；
(c) 入口缺失 → 仍 FAIL（既有 fail-closed 语义）；
(d) 真符号链接形态 → 仍 PASSED，且不带降级告警。

Hermeticity: 全部 fixture 落在 ``tempfile.TemporaryDirectory``；真实 Coding
Vault 只读不写（真库冒烟由 ``python scripts/vault-healthcheck.py`` 承担）。
(d) 真符号链接用例在无权创建 symlink 的机器上自动 skip（Windows 常态）。
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

# Prevent Windows GBK stdout/stderr trap (Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# vault-healthcheck.py 是连字符文件名，须按路径加载
_spec = importlib.util.spec_from_file_location(
    "vault_healthcheck", _SCRIPTS_DIR / "vault-healthcheck.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

# 与 healthcheck 中 EXPECTED_SYMLINKS 逐个对齐（防清单漂移）
ENTRIES = ["CLAUDE.md", "GEMINI.md", ".cursorrules", ".windsurfrules", "CONVENTIONS.md"]

# AGENTS.md 真相源；降级副本必须与它逐字节一致
AGENTS_TEXT = "# AGENTS\n\nfixture truth source for Task-7 checks\n"


# ---------------------------------------------------------------------------
# Fixture：迷你 vault（除 Check 5 外，其余 critical check 天然全部通过，
# 因此 run_all_checks()["all_passed"] 可以真实反映 Check 5 的判定）
# ---------------------------------------------------------------------------
def _write_note(path: pathlib.Path, title: str, extra: dict = None) -> None:
    """写一个带 6 大标准 frontmatter 字段的笔记（Check 1 全通过的前提）。"""
    lines = [
        "---",
        f"title: {title}",
        "created: 2026-01-01",
        "type: rule",
        "tags:",
        f"  - {title.lower().replace(' ', '-')}",
        "status: active",
        "audience: agent",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"{key}: {value}")
    lines += ["---", "", f"# {title}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_json(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _scaffold_other_checks(root: pathlib.Path) -> None:
    """铺好 Check 1/2/3/6/7/8/9/10 的通过条件，隔离出 Check 5 的判定。"""
    # Check 3：一对双版本（含互引 frontmatter）
    _write_note(root / "03-Languages/Python/PYTHON-STANDARDS.md", "Python Standards",
                {"cheatsheet": "PYTHON-CHEATSHEET.md"})
    _write_note(root / "03-Languages/Python/PYTHON-CHEATSHEET.md", "Python Cheatsheet",
                {"standards": "PYTHON-STANDARDS.md"})
    # Check 9：三份契约 + 其引用目标
    _write_note(root / "01-Rules/GIT-CONVENTIONS.md", "Git Conventions")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts/noop.py").write_text("# fixture\n", encoding="utf-8")
    _write_json(root / "05-Tools/capabilities.json", {
        "schema_version": 1,
        "capabilities": [{"name": "symlink-selfheal", "declared_status": "verified"}],
    })
    _write_json(root / "scripts/routing.json", {
        "schema_version": 1,
        "routes": [{
            "tag": "lang/python", "type": "dual", "name": "Py 双版本",
            "standards": "03-Languages/Python/PYTHON-STANDARDS.md",
            "cheatsheet": "03-Languages/Python/PYTHON-CHEATSHEET.md",
        }],
        "fallback": {
            "default": {"type": "rule-append", "target": "01-Rules/GIT-CONVENTIONS.md",
                        "name": "通用规则 (fallback)"},
        },
    })
    _write_json(root / "hooks/hooks.json", {
        "schema_version": 1,
        "hooks": [{"id": "noop", "stage": "stop", "matcher": "*", "timeout_s": 30,
                   "entry": "python scripts/noop.py"}],
    })
    # Check 8：注册表存在但为空表 → 0 缺失实体
    _write_note(root / "05-Tools/SKILL-REGISTRY.md", "Skill Registry")


def _make_vault(root: pathlib.Path, form: str = "copy", skip=(), overrides: dict = None) -> pathlib.Path:
    """构造迷你 vault；5 个入口按 ``form`` 落地。

    form:
      "copy"    —— 普通文件，内容 == AGENTS.md（Task-5 降级形态）
      "symlink" —— 真符号链接 -> AGENTS.md
      "missing" —— 不创建
    ``overrides``: {entry_name: text} 覆盖该入口内容（构造空/不一致坏例）。
    """
    (root / "AGENTS.md").write_text(AGENTS_TEXT, encoding="utf-8")
    _scaffold_other_checks(root)
    for name in ENTRIES:
        if name in skip or form == "missing":
            continue
        entry = root / name
        if form == "symlink":
            os.symlink("AGENTS.md", entry)
            continue
        text = (overrides or {}).get(name, AGENTS_TEXT)
        entry.write_text(text, encoding="utf-8")
    return root


def _can_symlink() -> bool:
    """本机是否具备创建符号链接的权限（Windows 需 Developer Mode / 管理员）。"""
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "src.txt"
        src.write_text("x", encoding="utf-8")
        try:
            os.symlink(src.name, pathlib.Path(td) / "link.txt")
        except (OSError, NotImplementedError, ValueError):
            return False
        return True


_CAN_SYMLINK = _can_symlink()


def _run(vault: pathlib.Path):
    checker = mod.VaultHealthChecker(vault_root=vault)
    return checker, checker.run_all_checks()


def _render(checker) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        checker.print_summary_table()
    return buf.getvalue()


def _hint() -> str:
    """降级告警的恢复指引文案（实现侧常量，测试侧不硬编码字面量）。"""
    return getattr(mod, "SYMLINK_DEGRADED_HINT")


# ---------------------------------------------------------------------------
# (a) 5 个入口为内容一致的普通文件副本 → 降级通过 + 整体 PASSED + 明确告警
# ---------------------------------------------------------------------------
class TestContentCopyDegradesToPass(unittest.TestCase):
    """降级形态必须「通过但告警」，不再把新机器判成开箱即坏。"""

    def test_check5_passes_on_content_identical_copies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            self.assertTrue(results["symlinks"]["passed"],
                            "内容一致的普通文件副本必须判 Check 5 通过")

    def test_check5_is_flagged_degraded_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            sl = results["symlinks"]
            self.assertTrue(sl.get("degraded"), "降级形态必须被显式标记 degraded")
            self.assertEqual(sorted(sl.get("degraded_entries", [])), sorted(ENTRIES))
            self.assertTrue(all(s.get("degraded") for s in sl["symlinks"]))

    def test_overall_healthcheck_passes_on_copy_form(self) -> None:
        """整体 PASSED —— 这是「开箱即坏」回归的正面断言。"""
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            self.assertTrue(results["all_passed"],
                            "降级副本形态下 healthcheck 整体必须 PASSED")

    def test_report_prints_degraded_warning_with_recovery_hint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            checker, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            out = _render(checker)
            self.assertIn("内容副本", out, "报告必须写明当前是内容副本形态")
            self.assertIn(_hint(), out, "报告必须给出恢复真符号链接的指引")
            self.assertIn("ALL CRITICAL CHECKS PASSED", out)

    def test_degraded_note_carried_in_result_notes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            notes = "\n".join(results["symlinks"].get("notes", []))
            self.assertIn(_hint(), notes)

    def test_copy_entry_records_content_copy_form(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="copy"))
            for item in results["symlinks"]["symlinks"]:
                self.assertFalse(item["is_symlink"])
                self.assertEqual(item.get("form"), "content-copy")

    def test_fixture_entries_really_are_regular_files(self) -> None:
        """防假绿：确认 fixture 确实是普通文件（而不是本机悄悄建成了 symlink）。"""
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(pathlib.Path(td), form="copy")
            for name in ENTRIES:
                self.assertFalse(os.path.islink(vault / name), f"{name} 不应是 symlink")
                self.assertEqual((vault / name).read_text(encoding="utf-8"), AGENTS_TEXT)


# ---------------------------------------------------------------------------
# (b)(c) fail-closed 语义不变：内容不一致 / 空 / 缺失 → 仍 FAIL
# ---------------------------------------------------------------------------
class TestFailClosedSemanticsUnchanged(unittest.TestCase):
    """降级口子只放行「内容一致」；任何不一致/缺失仍是一票否决。"""

    def test_empty_content_fails(self) -> None:
        for name in ENTRIES:
            with self.subTest(entry=name):
                with tempfile.TemporaryDirectory() as td:
                    _, results = _run(_make_vault(pathlib.Path(td), form="copy",
                                                  overrides={name: ""}))
                    self.assertFalse(results["symlinks"]["passed"],
                                     f"{name} 内容为空必须 FAIL")
                    self.assertFalse(results["all_passed"])

    def test_mismatched_content_fails(self) -> None:
        for name in ENTRIES:
            with self.subTest(entry=name):
                with tempfile.TemporaryDirectory() as td:
                    _, results = _run(_make_vault(pathlib.Path(td), form="copy",
                                                  overrides={name: "AGENTS.md"}))
                    self.assertFalse(results["symlinks"]["passed"],
                                     f"{name} 内容为 symlink blob 文本而非副本必须 FAIL")

    def test_single_bad_entry_fails_whole_check(self) -> None:
        """4 好 1 坏 → 整体 FAIL（不做多数派投票）。"""
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(pathlib.Path(td), form="copy")
            (vault / "GEMINI.md").write_text("stale copy\n", encoding="utf-8")
            _, results = _run(vault)
            sl = results["symlinks"]
            self.assertFalse(sl["passed"])
            failed = [s["name"] for s in sl["symlinks"] if not s["passed"]]
            self.assertEqual(failed, ["GEMINI.md"])

    def test_missing_entry_fails(self) -> None:
        for name in ENTRIES:
            with self.subTest(entry=name):
                with tempfile.TemporaryDirectory() as td:
                    _, results = _run(_make_vault(pathlib.Path(td), form="copy",
                                                  skip=(name,)))
                    self.assertFalse(results["symlinks"]["passed"],
                                     f"{name} 缺失必须 FAIL")

    def test_all_entries_missing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="missing"))
            self.assertFalse(results["symlinks"]["passed"])
            self.assertEqual(len([s for s in results["symlinks"]["symlinks"]
                                  if not s["passed"]]), len(ENTRIES))

    def test_failure_report_does_not_claim_overall_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            checker, results = _run(_make_vault(pathlib.Path(td), form="missing"))
            out = _render(checker)
            self.assertFalse(results["all_passed"])
            self.assertIn("HEALTHCHECK FAILED", out)

    def test_symlink_pointing_elsewhere_still_fails(self) -> None:
        """真 symlink 但指向非 AGENTS.md → 仍 FAIL（既有语义不回退）。"""
        if not _CAN_SYMLINK:
            self.skipTest("symlink not permitted on this machine")
        with tempfile.TemporaryDirectory() as td:
            vault = _make_vault(pathlib.Path(td), form="copy")
            (vault / "CLAUDE.md").unlink()
            (vault / "OTHER.md").write_text("other\n", encoding="utf-8")
            os.symlink("OTHER.md", vault / "CLAUDE.md")
            _, results = _run(vault)
            self.assertFalse(results["symlinks"]["passed"])


# ---------------------------------------------------------------------------
# (d) 真符号链接形态 → 仍 PASSED 且无告警
# ---------------------------------------------------------------------------
@unittest.skipUnless(_CAN_SYMLINK, "symlink not permitted on this machine")
class TestRealSymlinkFormUnchanged(unittest.TestCase):
    """symlink 形态的判定与输出不得因本次改动回退。"""

    def test_symlinks_pass_without_degraded_flag(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="symlink"))
            sl = results["symlinks"]
            self.assertTrue(sl["passed"])
            self.assertFalse(sl.get("degraded"), "真 symlink 形态不得标记为 degraded")
            self.assertEqual(sl.get("degraded_entries", []), [])

    def test_symlinks_pass_overall(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="symlink"))
            self.assertTrue(results["all_passed"])

    def test_symlink_report_has_no_degraded_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            checker, _ = _run(_make_vault(pathlib.Path(td), form="symlink"))
            out = _render(checker)
            self.assertNotIn(_hint(), out)
            self.assertNotIn("内容副本", out)

    def test_symlink_entry_records_symlink_form(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, results = _run(_make_vault(pathlib.Path(td), form="symlink"))
            for item in results["symlinks"]["symlinks"]:
                self.assertTrue(item["is_symlink"])
                self.assertEqual(item.get("form"), "symlink")


# ---------------------------------------------------------------------------
# 注入探针（防假注入：检查名存实亡 / 降级判定被写死）
# ---------------------------------------------------------------------------
class TestHealthcheckWiring(unittest.TestCase):
    """Check 5 的新判定必须真正并入执行链与输出链。"""

    def test_run_all_checks_consumes_check_symlinks(self) -> None:
        src = __import__("inspect").getsource(mod.VaultHealthChecker.run_all_checks)
        self.assertIn("check_symlinks(", src)

    def test_degraded_hint_constant_exists(self) -> None:
        hint = getattr(mod, "SYMLINK_DEGRADED_HINT", None)
        self.assertIsInstance(hint, str)
        self.assertTrue(hint, "降级告警文案不得为空")
        self.assertIn("core.symlinks", hint)

    def test_summary_table_renders_symlinks_section(self) -> None:
        src = __import__("inspect").getsource(mod.VaultHealthChecker.print_summary_table)
        self.assertIn("Multi-Agent Symlinks", src)


if __name__ == "__main__":
    unittest.main()
