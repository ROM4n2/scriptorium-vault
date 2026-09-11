#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for P1 Task-4: ``vault-auto-linker.py --write/--apply`` 单事务化。

Contract probes (plan Task-4 TDD list):
(a) 正常 apply：3 个互链文件各 +2 链接（共 6），改写后文本与改造前行为基线
    逐字一致；全部改写包在单个事务里——恰好一个 journal、status=committed、
    3 条 write 登记、无 .tmp 残留。
(a2) CLI 级 --write：rc=0，成功文案与改造前逐字一致（"Applied 6 new
    Wikilink(s) across 3 note(s) successfully"）。
(b) 注入失败（commit 阶段第 2 次 ``os.replace`` 抛 TransactionError）→
    所有文件字节与 apply 前一致、无 .tmp 残留、TransactionError 传播、
    journal status=rolled_back。
(b2) CLI 级失败：``main()`` 转 rc=1 + stderr 说明 + 无成功文案。
(c) SHA-256 前置：登记后、提交前外部篡改目标文件 → ``_commit_plan`` 抛
    TransactionError 且零写入（篡改文本保持原样、其余文件不受影响、
    被篡改文件不得登记进 journal）。
(d) 无候选可加时：apply 不产生新 journal / 无写盘（空计划早退，行为钉住）；
    dry-run 与无 flag CLI 均为纯只读（零写盘、零事务）。

Hermeticity: every fixture lives in ``tempfile.TemporaryDirectory``; the real
Coding Vault is never touched. Direct internal calls only — no subprocess.
"""

import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import vault_transaction  # noqa: E402
from vault_transaction import TransactionError  # noqa: E402

# vault-auto-linker.py 是连字符文件名，须按路径加载
_spec = importlib.util.spec_from_file_location(
    "vault_auto_linker", _SCRIPTS_DIR / "vault-auto-linker.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _journals(vault: pathlib.Path) -> list:
    """本脚本提交的事务 journal 列表（tx_id 前缀 auto-linker-）。"""
    return sorted((vault / ".vault-tx").glob("auto-linker-*.json"))


def _load_journal(vault: pathlib.Path, tx_id: str) -> dict:
    """按 tx_id 读取并解析持久化 journal（UTF-8 / ensure_ascii=False）。"""
    return json.loads(
        (vault / ".vault-tx" / f"{tx_id}.json").read_text(encoding="utf-8")
    )


class TestAutoLinkerApplyTransactional(unittest.TestCase):
    """--write/--apply 全链路：多文件改写包进单个 VaultTransaction。"""

    def setUp(self) -> None:
        # 脚本与测试共享同一事务实现——patch vault_transaction.os.replace 才能命中提交路径
        self.assertIs(mod.VaultTransaction, vault_transaction.VaultTransaction)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        vault = self.vault = pathlib.Path(self._tmp.name)
        (vault / "01-Rules").mkdir()
        (vault / "02-Fundamentals").mkdir()

        # 3 个互链文件：stem 注册为概念 term，正文裸写对方 stem → 每文件 2 候选
        self.original_texts = {
            "01-Rules/GUARD-PATTERNS.md":
                "# GUARD PATTERNS\n\n参考 ERROR-GROUP 与 TX-JOURNAL 章节的注意事项。\n",
            "02-Fundamentals/ERROR-GROUP.md":
                "# ERROR GROUP\n\n结合 GUARD-PATTERNS 食用更佳；另见 TX-JOURNAL。\n",
            "02-Fundamentals/TX-JOURNAL.md":
                "# TX JOURNAL\n\n与 GUARD-PATTERNS、ERROR-GROUP 联动。\n",
        }
        # 行为基线（与改造前逐文件直接写盘的逻辑文本逐字一致）
        self.expected_texts = {
            "01-Rules/GUARD-PATTERNS.md":
                "# GUARD PATTERNS\n\n参考 [[02-Fundamentals/ERROR-GROUP]] "
                "与 [[02-Fundamentals/TX-JOURNAL]] 章节的注意事项。\n",
            "02-Fundamentals/ERROR-GROUP.md":
                "# ERROR GROUP\n\n结合 [[01-Rules/GUARD-PATTERNS]] "
                "食用更佳；另见 [[02-Fundamentals/TX-JOURNAL]]。\n",
            "02-Fundamentals/TX-JOURNAL.md":
                "# TX JOURNAL\n\n与 [[01-Rules/GUARD-PATTERNS]]、"
                "[[02-Fundamentals/ERROR-GROUP]] 联动。\n",
        }
        self.paths: dict = {}
        self.original_bytes: dict = {}
        for rel, text in self.original_texts.items():
            p = vault / rel
            p.write_text(text, encoding="utf-8")
            self.paths[rel] = p
            self.original_bytes[rel] = p.read_bytes()

        self.linker = mod.VaultAutoLinker(vault_root=vault)

    def _make_flaky_replace(self, fail_on_call: int):
        # real_replace 取自事务模块实际引用的 os.replace，与 patch 目标同源
        real_replace = vault_transaction.os.replace
        seen: list = []

        def flaky_replace(src, dst) -> None:
            seen.append(dst)
            if len(seen) == fail_on_call:
                raise TransactionError(f"injected: replace #{fail_on_call} failed")
            real_replace(src, dst)

        return flaky_replace

    def _collect_plan(self) -> "mod._LinkPlan":
        """手动走 run_all 的收集阶段（只登记、零写盘），登记顺序固定。"""
        plan = mod._LinkPlan(self.vault)
        self.linker.prepare()
        for rel in (
            "01-Rules/GUARD-PATTERNS.md",
            "02-Fundamentals/ERROR-GROUP.md",
            "02-Fundamentals/TX-JOURNAL.md",
        ):
            res = self.linker.process_file(self.paths[rel], dry_run=False, plan=plan)
            self.assertEqual(res["candidate_count"], 2, rel)
        self.assertEqual(len(plan.writes), 3)
        return plan

    # -- (a) 正常 apply：行为基线一致 + 单事务证据 ---------------------------

    def test_a_apply_matches_pre_refactor_baseline_in_single_tx(self) -> None:
        report = self.linker.run_all(dry_run=False)

        self.assertFalse(report["dry_run"])
        self.assertEqual(report["total_candidate_links"], 6)
        self.assertEqual(report["files_with_candidates_count"], 3)
        for rel, p in self.paths.items():
            self.assertEqual(
                p.read_text(encoding="utf-8"), self.expected_texts[rel], rel
            )
            self.assertEqual(
                p.read_bytes(),
                self.expected_texts[rel].encode("utf-8"),
                rel,
            )

        # 单事务证据：恰好一个 journal；3 条 write 登记
        journals = _journals(self.vault)
        self.assertEqual(len(journals), 1, "apply 的全部改写必须包在单个事务里")
        log = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "committed")
        self.assertEqual(len(log["entries"]), 3)
        self.assertEqual({e["action"] for e in log["entries"]}, {"write"})

        self.assertEqual(list(self.vault.rglob("*.tmp")), [], "不得残留 .tmp")

    def test_a2_main_write_keeps_success_output_compatible(self) -> None:
        with mock.patch.object(
            sys, "argv",
            ["vault-auto-linker.py", "--write", "--vault-path", str(self.vault)],
        ):
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), \
                    contextlib.redirect_stderr(buf_err):
                rc = mod.main()

        self.assertEqual(rc, 0)
        self.assertIn(
            "Applied 6 new Wikilink(s) across 3 note(s) successfully",
            buf_out.getvalue(),
            "成功文案必须与改造前逐字一致",
        )
        for rel, p in self.paths.items():
            self.assertEqual(p.read_text(encoding="utf-8"), self.expected_texts[rel], rel)

    # -- (b) 注入失败：整体回滚 + TransactionError 传播 ----------------------

    def test_b_injected_commit_failure_rolls_back_everything(self) -> None:
        plan = self._collect_plan()

        # 登记阶段必须零写盘（登记 ≠ 落盘）
        for rel, p in self.paths.items():
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)

        with mock.patch(
            "vault_transaction.os.replace",
            side_effect=self._make_flaky_replace(fail_on_call=2),
        ):
            with self.assertRaises(TransactionError):
                mod._commit_plan(self.vault, plan)

        # 所有文件字节与 apply 前一致
        for rel, p in self.paths.items():
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)
        self.assertEqual(list(self.vault.rglob("*.tmp")), [], "不得残留 .tmp")

        journals = _journals(self.vault)
        self.assertEqual(len(journals), 1)
        self.assertEqual(
            json.loads(journals[0].read_text(encoding="utf-8"))["status"],
            "rolled_back",
        )

    def test_b2_main_apply_fails_with_rc1_stderr_and_rollback(self) -> None:
        with mock.patch(
            "vault_transaction.os.replace",
            side_effect=self._make_flaky_replace(fail_on_call=1),
        ):
            with mock.patch.object(
                sys, "argv",
                ["vault-auto-linker.py", "--write", "--vault-path", str(self.vault)],
            ):
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(buf_out), \
                        contextlib.redirect_stderr(buf_err):
                    rc = mod.main()

        self.assertEqual(rc, 1, "事务失败必须以非 0 退出")
        self.assertIn("回滚", buf_err.getvalue(), "stderr 必须说明整体回滚")
        self.assertNotIn("🎉", buf_out.getvalue(), "失败时 stdout 不得输出成功文案")

        for rel, p in self.paths.items():
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)
        journals = _journals(self.vault)
        self.assertEqual(len(journals), 1)
        self.assertEqual(
            json.loads(journals[0].read_text(encoding="utf-8"))["status"],
            "rolled_back",
        )

    # -- (c) SHA-256 前置：外部篡改 → TransactionError 且零写入 --------------

    def test_c_sha256_mismatch_blocks_apply_with_zero_side_effects(self) -> None:
        plan = self._collect_plan()

        # 提交前外部进程篡改 ERROR-GROUP.md（登记时快照的哈希将不再匹配）
        tampered_rel = "02-Fundamentals/ERROR-GROUP.md"
        tampered_text = "被外部进程篡改的内容\n"
        self.paths[tampered_rel].write_text(tampered_text, encoding="utf-8")

        with self.assertRaises(TransactionError):
            mod._commit_plan(self.vault, plan)

        # 零写入：被篡改文件保持篡改后内容（脚本不得写它），其余文件不受影响
        self.assertEqual(
            self.paths[tampered_rel].read_text(encoding="utf-8"), tampered_text
        )
        for rel, p in self.paths.items():
            if rel == tampered_rel:
                continue
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)
        self.assertEqual(list(self.vault.rglob("*.tmp")), [])

        journals = _journals(self.vault)
        self.assertEqual(len(journals), 1)
        log = json.loads(journals[0].read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "rolled_back")
        self.assertEqual(
            len(log["entries"]), 1, "哈希不匹配的文件不得登记进 journal"
        )
        self.assertEqual(
            log["entries"][0]["path"], str(self.paths["01-Rules/GUARD-PATTERNS.md"])
        )

    # -- (d) 无候选 / dry-run / 无 flag：行为明确且零写盘 ---------------------

    def test_d_second_apply_with_no_candidates_creates_no_journal(self) -> None:
        self.linker.run_all(dry_run=False)
        for rel, p in self.paths.items():
            self.assertEqual(p.read_text(encoding="utf-8"), self.expected_texts[rel])

        # 第二轮 apply：全部已链接 → 零候选 → 不创建新事务/journal、无写盘
        report2 = self.linker.run_all(dry_run=False)
        self.assertFalse(report2["dry_run"])
        self.assertEqual(report2["total_candidate_links"], 0)
        self.assertEqual(report2["files_with_candidates_count"], 0)
        self.assertEqual(
            len(_journals(self.vault)), 1, "无候选 apply 不得创建新事务 journal"
        )
        for rel, p in self.paths.items():
            self.assertEqual(
                p.read_bytes(), self.expected_texts[rel].encode("utf-8"), rel
            )

    def test_d2_dry_run_is_pure_readonly(self) -> None:
        buf_out = io.StringIO()
        with contextlib.redirect_stdout(buf_out):
            report = self.linker.run_all(dry_run=True)

        self.assertTrue(report["dry_run"])
        self.assertEqual(report["total_candidate_links"], 6)
        for rel, p in self.paths.items():
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)
        self.assertFalse(
            (self.vault / ".vault-tx").exists(), "dry-run 不得创建事务目录"
        )

    def test_d3_default_main_without_flag_is_dry_run(self) -> None:
        with mock.patch.object(
            sys, "argv", ["vault-auto-linker.py", "--vault-path", str(self.vault)]
        ):
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf_out), \
                    contextlib.redirect_stderr(buf_err):
                rc = mod.main()

        self.assertEqual(rc, 0)
        for rel, p in self.paths.items():
            self.assertEqual(p.read_bytes(), self.original_bytes[rel], rel)
        self.assertFalse(
            (self.vault / ".vault-tx").exists(), "无 flag 不得创建事务目录"
        )
        self.assertIn("DRY-RUN", buf_out.getvalue())


if __name__ == "__main__":
    unittest.main()
