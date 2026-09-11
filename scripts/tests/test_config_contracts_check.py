#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for P3 Task-4: config 契约校验并入 vault-healthcheck。

Contract probes (plan Task-4 TDD list):
(a) 三份合法契约（临时目录迷你 vault fixture）→ ``check_config_contracts``
    返回空问题清单（空=通过）；
(b) 计划点名的四坏例各自检出对应问题条目：routing 目标缺失 /
    hook entry 不存在 / capability declared_status 非法 / JSON 损坏；
(c) spec 面补钉（ADR-0001 §4 #7/#15/#14 各字段）：schema_version≠1 /
    tag 非 namespace/name 形式 / tag 重复 / hook stage 非法枚举 /
    capability name 重复 / 契约文件缺失 —— 各自显式报问题（零静默吞异常）；
(d) 注入探针（防假注入）：``VaultHealthChecker.run_all_checks`` 真正消费
    ``check_config_contracts`` 且计入 critical、print_summary_table 渲染
    "Config Contracts" 段。

tag/type 权威口径镜像自运行时加载器 ``vault-inbox-consolidate.py``
（``_validate_tag`` / ``_VALID_ROUTE_TYPES`` / ``_REQUIRED_KEYS_BY_TYPE``），
避免 healthcheck 与加载器双标。

Hermeticity: fixtures live in ``tempfile.TemporaryDirectory``；真实 Coding
Vault 只读不写（真库冒烟由 ``python scripts/vault-healthcheck.py`` 承担）。
"""

import importlib.util
import inspect
import json
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

CAPABILITIES_REL = "05-Tools/capabilities.json"
ROUTING_REL = "scripts/routing.json"
HOOKS_REL = "hooks/hooks.json"

# 与 hooks manifest 契约（test_hooks_manifest.py）钉死的枚举基线保持一致
LEGAL_CAPABILITY_STATUSES = {"verified", "configured", "degraded"}
LEGAL_HOOK_STAGES = {"pre-commit", "posttooluse", "stop"}


# ---------------------------------------------------------------------------
# Fixture：迷你 vault（三契约合法且引用的目标文件/目录真实存在）
# ---------------------------------------------------------------------------
def _valid_capabilities() -> dict:
    return {
        "schema_version": 1,
        "generated_tooling": "capability-check.py",
        "capabilities": [
            {
                "name": "cap-a", "type": "script", "tier": "core",
                "verification_command": "python scripts/probe.py",
                "declared_status": "verified", "section": "scripts",
                "scope": "read-only", "confirmation_required": False,
            },
            {
                "name": "cap-b", "type": "skill", "tier": "core",
                "verification_command": None,
                "declared_status": "configured", "section": "skills",
                "scope": "read-only", "confirmation_required": True,
            },
        ],
    }


def _valid_routing() -> dict:
    return {
        "schema_version": 1,
        "routes": [
            {"tag": "lang/python", "type": "dual", "name": "Py 双版本",
             "standards": "03-Languages/Python/PYTHON-STANDARDS.md",
             "cheatsheet": "03-Languages/Python/PYTHON-CHEATSHEET.md"},
            {"tag": "topic/git", "type": "rule-append", "name": "Git 规范",
             "target": "01-Rules/GIT-CONVENTIONS.md"},
        ],
        "fallback": {
            "source-notes": {"type": "source-article",
                             "target_dir": "06-Sources/Articles",
                             "name": "source-notes (fallback)"},
            "default": {"type": "rule-append",
                        "target": "01-Rules/GIT-CONVENTIONS.md",
                        "name": "通用规则 (fallback)"},
        },
    }


def _valid_hooks() -> dict:
    return {
        "schema_version": 1,
        "hooks": [
            {"id": "gate1", "stage": "pre-commit", "matcher": "*", "timeout_s": 60,
             "entry": "bash .githooks/gates/gate1-secret.sh", "source": "legacy"},
            {"id": "stop-ingest", "stage": "stop", "matcher": "*", "timeout_s": 120,
             "entry": "python scripts/stop-hook-ingest.py", "source": "legacy"},
        ],
    }


def _touch(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fixture target\n", encoding="utf-8")


def _make_valid_vault(tmp: pathlib.Path) -> pathlib.Path:
    """迷你 vault：三契约全部合法，且路由/hook 引用的目标真实存在。"""
    _touch(tmp / "03-Languages/Python/PYTHON-STANDARDS.md")
    _touch(tmp / "03-Languages/Python/PYTHON-CHEATSHEET.md")
    _touch(tmp / "01-Rules/GIT-CONVENTIONS.md")
    _touch(tmp / "scripts/stop-hook-ingest.py")
    _touch(tmp / ".githooks/gates/gate1-secret.sh")
    (tmp / "06-Sources/Articles").mkdir(parents=True, exist_ok=True)
    for rel, data in (
        (CAPABILITIES_REL, _valid_capabilities()),
        (ROUTING_REL, _valid_routing()),
        (HOOKS_REL, _valid_hooks()),
    ):
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp


def _rewrite_json(tmp: pathlib.Path, rel: str, mutate) -> None:
    """加载 tmp 下某契约 JSON → mutate(dict) → 原位写回（构造坏例）。"""
    path = tmp / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _joined(problems: list) -> str:
    return "\n".join(problems)


# ---------------------------------------------------------------------------
# (a) 三份合法契约 → 0 问题
# ---------------------------------------------------------------------------
class TestValidContractsZeroProblems(unittest.TestCase):
    """合法 fixture 必须零问题（空列表 = 通过）。"""

    def test_valid_contracts_produce_zero_problems(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            self.assertEqual(mod.check_config_contracts(vault), [])

    def test_return_shape_is_list_of_str(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            problems = mod.check_config_contracts(vault)
            self.assertIsInstance(problems, list)
            self.assertTrue(all(isinstance(p, str) for p in problems))


# ---------------------------------------------------------------------------
# (b) 四坏例：各自检出对应问题
# ---------------------------------------------------------------------------
class TestFourBadCases(unittest.TestCase):
    """计划点名的四坏例，各坏例必须产出可定位的问题条目。"""

    def test_routing_missing_target_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, ROUTING_REL, lambda d: d["routes"][1].update(
                {"target": "01-Rules/NO-SUCH-RULE.md"}))
            problems = mod.check_config_contracts(vault)
            self.assertTrue(problems, "routing 目标缺失必须产生问题条目")
            joined = _joined(problems)
            self.assertIn("topic/git", joined, "问题条目须含命中路由的 tag")
            self.assertIn("NO-SUCH-RULE", joined, "问题条目须可定位缺失目标")

    def test_routing_dual_missing_cheatsheet_detected(self) -> None:
        """dual 路由的 standards/cheatsheet 双文件均受存在性校验。"""
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            (vault / "03-Languages/Python/PYTHON-CHEATSHEET.md").unlink()
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn("lang/python", joined)
            self.assertIn("PYTHON-CHEATSHEET", joined)

    def test_hook_entry_missing_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, HOOKS_REL, lambda d: d["hooks"][1].update(
                {"entry": "python scripts/no-such-ingest.py"}))
            problems = mod.check_config_contracts(vault)
            self.assertTrue(problems, "hook entry 指向文件缺失必须产生问题条目")
            joined = _joined(problems)
            self.assertIn("stop-ingest", joined, "问题条目须含 hook id")
            self.assertIn("no-such-ingest.py", joined, "问题条目须可定位缺失脚本")

    def test_hook_entry_unbalanced_quote_reported_not_crash(self) -> None:
        """entry 含不平衡引号时 shlex 抛 ValueError，必须转为问题条目而非击穿 healthcheck。"""
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, HOOKS_REL, lambda d: d["hooks"][1].update(
                {"entry": 'bash "scripts/unbalanced.sh'}))
            problems = mod.check_config_contracts(vault)
            self.assertTrue(problems, "entry 无法解析必须产生问题条目")
            joined = _joined(problems)
            self.assertIn("stop-ingest", joined, "问题条目须含 hook id")
            self.assertIn("cannot be parsed", joined, "问题条目须标注解析失败")

    def test_capability_status_illegal_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, CAPABILITIES_REL, lambda d: d["capabilities"][0].update(
                {"declared_status": "bogus-status"}))
            problems = mod.check_config_contracts(vault)
            self.assertTrue(problems, "declared_status 非法必须产生问题条目")
            joined = _joined(problems)
            self.assertIn("cap-a", joined, "问题条目须含 capability name")
            self.assertIn("bogus-status", joined, "问题条目须含非法状态值")

    def test_corrupt_json_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            (vault / ROUTING_REL).write_text("{ not json", encoding="utf-8")
            problems = mod.check_config_contracts(vault)
            self.assertTrue(problems, "JSON 损坏必须产生问题条目")
            self.assertIn(ROUTING_REL, _joined(problems))


# ---------------------------------------------------------------------------
# (c) spec 面补钉：schema_version / tag 形式与重复 / stage / name 重复 / 缺文件
# ---------------------------------------------------------------------------
class TestSpecSurfaceBadCases(unittest.TestCase):
    """目标 spec 各校验面逐一钉死（零静默吞异常）。"""

    def test_schema_version_must_be_one(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, ROUTING_REL, lambda d: d.update({"schema_version": 2}))
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn("schema_version", joined)

    def test_tag_must_be_namespace_slash_name(self) -> None:
        """口径镜像加载器 _validate_tag：含 "/" 且非首尾斜杠。"""
        for bad_tag in ("python", "/python", "lang/"):
            with self.subTest(tag=bad_tag):
                with tempfile.TemporaryDirectory() as td:
                    vault = _make_valid_vault(pathlib.Path(td))
                    _rewrite_json(
                        vault, ROUTING_REL,
                        lambda d, t=bad_tag: d["routes"][0].update({"tag": t}),
                    )
                    joined = _joined(mod.check_config_contracts(vault))
                    self.assertIn(bad_tag, joined, f"非法 tag {bad_tag!r} 必须被报出")

    def test_duplicate_tag_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, ROUTING_REL,
                          lambda d: d["routes"].append(dict(d["routes"][0])))
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn("lang/python", joined)
            self.assertIn("duplicate", joined)

    def test_hook_stage_illegal_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, HOOKS_REL,
                          lambda d: d["hooks"][0].update({"stage": "precommit"}))
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn("gate1", joined, "问题条目须含 hook id")
            self.assertIn("precommit", joined, "问题条目须含非法 stage 值")

    def test_capability_duplicate_name_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            _rewrite_json(vault, CAPABILITIES_REL,
                          lambda d: d["capabilities"].append(dict(d["capabilities"][0])))
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn("cap-a", joined)
            self.assertIn("duplicate", joined)

    def test_missing_contract_file_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = _make_valid_vault(pathlib.Path(td))
            (vault / HOOKS_REL).unlink()
            joined = _joined(mod.check_config_contracts(vault))
            self.assertIn(HOOKS_REL, joined)

    def test_all_three_contract_files_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            joined = _joined(mod.check_config_contracts(pathlib.Path(td)))
            for rel in (CAPABILITIES_REL, ROUTING_REL, HOOKS_REL):
                self.assertIn(rel, joined)


# ---------------------------------------------------------------------------
# (d) 注入探针（防假注入：门禁硬编码回旧逻辑而检查名存实亡）
# ---------------------------------------------------------------------------
class TestHealthcheckWiring(unittest.TestCase):
    """新检查必须真正并入 healthcheck 的执行链与输出链。"""

    def test_run_all_checks_consumes_check_config_contracts(self) -> None:
        source = inspect.getsource(mod.VaultHealthChecker.run_all_checks)
        self.assertIn("check_config_contracts(", source)

    def test_run_all_checks_counts_config_contracts_as_critical(self) -> None:
        source = inspect.getsource(mod.VaultHealthChecker.run_all_checks)
        self.assertIn('self.results["config_contracts"]', source)

    def test_summary_table_renders_config_contracts_section(self) -> None:
        source = inspect.getsource(mod.VaultHealthChecker.print_summary_table)
        self.assertIn("Config Contracts", source)


if __name__ == "__main__":
    unittest.main()
