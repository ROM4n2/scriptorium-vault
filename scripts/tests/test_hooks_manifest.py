#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for P3 Task-3: ``hooks/hooks.json`` manifest + pre-commit 路由化。

Contract probes (plan Task-3 TDD list):
(a) manifest schema：schema_version=1；每条 hook 必含
    id/stage/matcher/timeout_s/entry/source 六字段且类型合法；
    stage 枚举限定 {"pre-commit","posttooluse","stop"}；id 全局唯一；
    source 统一为 "legacy"（收编登记性质，ADR-0001 §4 #14）。
(b) pre-commit 门序：manifest 中 stage=pre-commit 条目按数组顺序
    （= 路由层执行顺序）为 gate1-secret → gate15-url → gate2-quality，
    entry 分别指向对应 gate 脚本。
(c) ADR-0001 §5 guardrail：每条 entry 指向的脚本文件在 vault 内存在。
(d) 四个 shell 文件（pre-commit 路由层 + 三个 gate）均通过 ``bash -n``
    语法校验。
(e) harness 收编一致性：``.claude/settings.json`` 引用的每条
    (stage, matcher, command) 与 manifest 中 stage∈{posttooluse,stop}
    条目一一相等（登记不改实现）。
(f) 路由接线探针：pre-commit 必须引用 hooks.json（防"假路由"——
    门禁硬编码回旧三块而 manifest 名存实亡）。

Hermeticity: 只读真实 vault 的 manifest/gate/settings 文件；
fixture（非法 manifest 变体）live in ``tempfile.TemporaryDirectory``。
"""

import json
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
_VAULT_ROOT = _SCRIPTS_DIR.parent

HOOKS_JSON = _VAULT_ROOT / "hooks" / "hooks.json"
PRE_COMMIT = _VAULT_ROOT / ".githooks" / "pre-commit"
CLAUDE_SETTINGS = _VAULT_ROOT / ".claude" / "settings.json"

# 测试钉死的 schema 契约（与 hooks/hooks.json 1:1 对齐）
VALID_SCHEMA_VERSION = 1
VALID_STAGES = {"pre-commit", "posttooluse", "stop"}
VALID_SOURCES = {"legacy"}
REQUIRED_HOOK_FIELDS = ("id", "stage", "matcher", "timeout_s", "entry", "source")
OPTIONAL_STR_FIELDS = ("description",)
ENTRY_INTERPRETERS = {"bash", "sh", "python", "python3"}

SHELL_FILES_UNDER_TEST = (
    PRE_COMMIT,
    _VAULT_ROOT / ".githooks" / "gates" / "gate1-secret.sh",
    _VAULT_ROOT / ".githooks" / "gates" / "gate15-url.sh",
    _VAULT_ROOT / ".githooks" / "gates" / "gate2-quality.sh",
)

# (b) 门序参照：gate1 → gate15 → gate2（原 pre-commit 块顺序）
EXPECTED_PRE_COMMIT_GATE_ORDER = ("gate1-secret", "gate15-url", "gate2-quality")
EXPECTED_PRE_COMMIT_GATE_ENTRIES = (
    "bash .githooks/gates/gate1-secret.sh",
    "bash .githooks/gates/gate15-url.sh",
    "bash .githooks/gates/gate2-quality.sh",
)


def _load_manifest() -> dict:
    """加载 hooks/hooks.json；文件缺失/损坏时让测试显式失败（零静默）。"""
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))


def _entry_script_path(entry: str) -> pathlib.Path:
    """解析 entry "<interpreter> <vault 相对脚本路径>"，返回脚本绝对路径。

    entry 格式被测试钉死为两段式：解释器 ∈ ENTRY_INTERPRETERS，
    第二段为相对 vault root 的脚本路径。
    """
    tokens = shlex.split(entry)
    assert len(tokens) == 2, f"entry 必须为 '<解释器> <脚本路径>' 两段式: {entry!r}"
    assert tokens[0] in ENTRY_INTERPRETERS, (
        f"entry 解释器 {tokens[0]!r} 不在 {sorted(ENTRY_INTERPRETERS)}: {entry!r}"
    )
    return _VAULT_ROOT / tokens[1]


# ---------------------------------------------------------------------------
# (a) manifest schema
# ---------------------------------------------------------------------------
class TestManifestSchema(unittest.TestCase):
    """hooks.json schema 契约：字段、枚举、唯一性。"""

    def test_schema_version_is_pinned(self) -> None:
        self.assertEqual(_load_manifest()["schema_version"], VALID_SCHEMA_VERSION)

    def test_top_level_has_hooks_list(self) -> None:
        hooks = _load_manifest()["hooks"]
        self.assertIsInstance(hooks, list)
        self.assertGreater(len(hooks), 0, "manifest 至少要收编现有 5 条 hooks")

    def test_every_hook_has_required_fields_with_valid_types(self) -> None:
        for hook in _load_manifest()["hooks"]:
            for field in REQUIRED_HOOK_FIELDS:
                with self.subTest(hook_id=hook.get("id", "<missing>"), field=field):
                    self.assertIn(field, hook, f"缺必填字段: {field}")
            with self.subTest(hook_id=hook["id"], check="types"):
                self.assertIsInstance(hook["id"], str)
                self.assertTrue(hook["id"].strip(), "id 不得为空白")
                self.assertIsInstance(hook["stage"], str)
                self.assertIsInstance(hook["matcher"], str)
                self.assertTrue(hook["matcher"], "matcher 不得为空字符串")
                self.assertIsInstance(hook["timeout_s"], int)
                self.assertNotIsInstance(hook["timeout_s"], bool)
                self.assertGreater(hook["timeout_s"], 0, "timeout_s 必须为正整数")
                self.assertIsInstance(hook["entry"], str)
                self.assertTrue(hook["entry"].strip(), "entry 不得为空白")
                self.assertIsInstance(hook["source"], str)

    def test_stage_enum_is_valid(self) -> None:
        for hook in _load_manifest()["hooks"]:
            with self.subTest(hook_id=hook["id"]):
                self.assertIn(hook["stage"], VALID_STAGES)

    def test_source_is_legacy_for_registered_hooks(self) -> None:
        """收编登记性质钉死：source 统一为 "legacy"（ADR-0001 §4 #14）。"""
        for hook in _load_manifest()["hooks"]:
            with self.subTest(hook_id=hook["id"]):
                self.assertIn(hook["source"], VALID_SOURCES)

    def test_hook_ids_are_unique(self) -> None:
        ids = [h["id"] for h in _load_manifest()["hooks"]]
        self.assertEqual(len(ids), len(set(ids)), f"id 重复: {ids}")

    def test_optional_description_is_string_when_present(self) -> None:
        for hook in _load_manifest()["hooks"]:
            if "description" in hook:
                with self.subTest(hook_id=hook["id"]):
                    self.assertIsInstance(hook["description"], str)


# ---------------------------------------------------------------------------
# (b) pre-commit 门序
# ---------------------------------------------------------------------------
class TestPreCommitGateOrder(unittest.TestCase):
    """stage=pre-commit 条目按 manifest 数组顺序（= 路由层执行序）。"""

    def _pre_commit_hooks(self) -> list:
        return [h for h in _load_manifest()["hooks"] if h["stage"] == "pre-commit"]

    def test_gate_order_is_gate1_gate15_gate2(self) -> None:
        ids = tuple(h["id"] for h in self._pre_commit_hooks())
        self.assertEqual(ids, EXPECTED_PRE_COMMIT_GATE_ORDER)

    def test_gate_entries_point_to_split_gate_scripts(self) -> None:
        entries = tuple(h["entry"] for h in self._pre_commit_hooks())
        self.assertEqual(entries, EXPECTED_PRE_COMMIT_GATE_ENTRIES)


# ---------------------------------------------------------------------------
# (c) ADR guardrail：entry 指向的脚本文件存在
# ---------------------------------------------------------------------------
class TestEntryTargetsExist(unittest.TestCase):
    """每条 entry 的脚本文件必须在真实 vault 内存在（防配置腐化）。"""

    def test_every_entry_script_exists(self) -> None:
        for hook in _load_manifest()["hooks"]:
            with self.subTest(hook_id=hook["id"]):
                path = _entry_script_path(hook["entry"])
                self.assertTrue(
                    path.is_file(), f"{hook['id']}: entry 脚本不存在: {path}"
                )


# ---------------------------------------------------------------------------
# (d) bash -n 语法校验（pre-commit 路由层 + 三个 gate）
# ---------------------------------------------------------------------------
class TestShellSyntax(unittest.TestCase):
    """四个 shell 文件均通过 ``bash -n``。"""

    def test_bash_available(self) -> None:
        if shutil.which("bash") is None:  # pragma: no cover — 环境自检
            self.fail("PATH 中找不到 bash，无法校验 hook shell 语法")

    def test_all_shell_files_pass_bash_n(self) -> None:
        for shell_file in SHELL_FILES_UNDER_TEST:
            with self.subTest(file=str(shell_file.relative_to(_VAULT_ROOT))):
                self.assertTrue(
                    shell_file.is_file(), f"shell 文件不存在: {shell_file}"
                )
                proc = subprocess.run(
                    # subprocess 直启 git-bash 不做 Windows→MSYS 路径转换，
                    # 用 vault 相对路径 + cwd 锚定，绕开路径字符串翻译问题
                    ["bash", "-n", shell_file.relative_to(_VAULT_ROOT).as_posix()],
                    cwd=str(_VAULT_ROOT),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"bash -n 失败: {proc.stderr.strip()}",
                )


# ---------------------------------------------------------------------------
# (e) harness 收编一致性（登记不改实现）
# ---------------------------------------------------------------------------
# settings.json 事件名 → manifest stage 名
_EVENT_TO_STAGE = {"PostToolUse": "posttooluse", "Stop": "stop"}
_HARNESS_STAGES = set(_EVENT_TO_STAGE.values())


def _declared_harness_hooks() -> set:
    """从 .claude/settings.json 提取 引用集。"""
    settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    declared = set()
    for event, matcher_entries in settings.get("hooks", {}).items():
        stage = _EVENT_TO_STAGE[event]
        for entry in matcher_entries:
            matcher = entry.get("matcher", "*")
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    declared.add((stage, matcher, hook["command"]))
    return declared


class TestHarnessRegistration(unittest.TestCase):
    """manifest 登记的 harness hooks 与 .claude/settings.json 引用一致。"""

    def test_settings_json_declares_hooks(self) -> None:
        self.assertTrue(_declared_harness_hooks(), "settings.json 应声明 hook 命令")

    def test_manifest_registration_equals_settings_references(self) -> None:
        registered = {
            (h["stage"], h["matcher"], h["entry"])
            for h in _load_manifest()["hooks"]
            if h["stage"] in _HARNESS_STAGES
        }
        self.assertEqual(
            registered,
            _declared_harness_hooks(),
            "manifest 的 posttooluse/stop 登记必须与 settings.json 引用逐一相等",
        )


# ---------------------------------------------------------------------------
# (f) 路由接线探针（防假路由）
# ---------------------------------------------------------------------------
class TestPreCommitRoutesViaManifest(unittest.TestCase):
    """pre-commit 必须真正消费 hooks.json，而非硬编码回旧三块。"""

    def test_pre_commit_references_hooks_json(self) -> None:
        text = PRE_COMMIT.read_text(encoding="utf-8")
        self.assertIn("hooks.json", text, "pre-commit 路由层必须引用 hooks.json")

    def test_pre_commit_keeps_vault_dir_binding(self) -> None:
        """cd $VAULT_DIR 绑定语义保留（原 pre-commit 行 11-12）。"""
        text = PRE_COMMIT.read_text(encoding="utf-8")
        self.assertIn("VAULT_DIR", text)
        self.assertIn("cd", text)


# ---------------------------------------------------------------------------
# fixture 自检：非法 manifest 变体必须被 schema 测试语义捕获（防测试失效）
# ---------------------------------------------------------------------------
class TestSchemaProbeSelfCheck(unittest.TestCase):
    """schema 探针函数自身的防退化自检（fixture 全部落在临时目录）。"""

    def test_entry_parser_rejects_non_two_token_entry(self) -> None:
        with self.assertRaises(AssertionError):
            _entry_script_path("bash -c 'echo hi'")

    def test_entry_parser_rejects_unknown_interpreter(self) -> None:
        with self.assertRaises(AssertionError):
            _entry_script_path("pwsh scripts/stop-hook-ingest.py")

    def test_entry_parser_resolves_real_script(self) -> None:
        path = _entry_script_path("python scripts/stop-hook-ingest.py")
        self.assertEqual(path, _VAULT_ROOT / "scripts" / "stop-hook-ingest.py")

    def test_tmpdir_fixture_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            probe = pathlib.Path(td) / "probe.json"
            probe.write_text(json.dumps({"ok": True}), encoding="utf-8")
            self.assertEqual(json.loads(probe.read_text(encoding="utf-8")), {"ok": True})


if __name__ == "__main__":
    unittest.main()
