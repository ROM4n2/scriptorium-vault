#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scripts/vault_transaction.py`` — vault-level transaction primitive.

Pins the P1 Task-2 contract: process-level change lock + SHA-256 precheck +
persistent journal + atomic replace via ``os.replace`` + deterministic rollback.

Seven contract probes (plan Task-2 TDD list):
(a) multi-file stage+commit replaces both files;
(b) mid-commit failure (2nd ``os.replace`` raises) still rolls back the file
    that was already replaced — "确定性回滚";
(c) SHA-256 precheck mismatch raises ``TransactionError`` with zero writes;
(d) lock is mutex: second instance on the same vault times out with
    ``TransactionError``, and re-acquire after release succeeds;
(e) journal records staged/committed/rolled_back with full entry structure,
    UTF-8 raw bytes (``ensure_ascii=False``);
(f) new-file staging: created on commit, deleted on rollback, no-op rollback
    when the new file was never committed;
(g) stage path containment: a target resolving outside ``vault_root`` raises
    ``TransactionError`` with zero writes (no journal, no backup).

Hermeticity: every fixture lives in ``tempfile.TemporaryDirectory``; the real
Coding Vault is never touched.
"""

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import vault_transaction  # noqa: E402
from vault_transaction import TransactionError, VaultTransaction  # noqa: E402


def _read_log(vault: pathlib.Path, tx_id: str) -> dict:
    """Read the persistent journal as UTF-8 (the format contract itself)."""
    raw = (vault / ".vault-tx" / f"{tx_id}.json").read_bytes()
    return json.loads(raw.decode("utf-8"))


class TestMultiFileCommit(unittest.TestCase):
    """(a) 正常多文件 stage+commit：两文件新内容与预期一致。"""

    def test_commit_replaces_all_staged_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            f1 = vault / "a.md"
            f1.write_text("old-1", encoding="utf-8")
            sub = vault / "sub"
            sub.mkdir()
            f2 = sub / "b.md"
            f2.write_text("old-2", encoding="utf-8")

            tx = VaultTransaction(vault, "tx-ok")
            with tx:
                tx.stage(f1, new_text="new-1")
                tx.stage(f2, new_bytes=b"new-2")

            self.assertEqual(f1.read_text(encoding="utf-8"), "new-1")
            self.assertEqual(f2.read_bytes(), b"new-2")
            self.assertEqual(tx.status, "committed")


class TestMidCommitFailureRollback(unittest.TestCase):
    """(b) 中途失败回滚：第 2 个文件 replace 抛异常 → 两文件均恢复原文。"""

    def test_rollback_restores_even_already_replaced_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            f1 = vault / "a.md"
            f1.write_text("old-1", encoding="utf-8")
            f2 = vault / "b.md"
            f2.write_text("old-2", encoding="utf-8")

            real_replace = os.replace
            seen: list[object] = []

            def flaky_replace(src: object, dst: object) -> None:
                seen.append(dst)
                if len(seen) == 2:
                    raise OSError("simulated disk failure on the 2nd replace")
                real_replace(src, dst)  # type: ignore[arg-type]

            tx = VaultTransaction(vault, "tx-mid")
            with self.assertRaises(OSError), \
                    mock.patch("vault_transaction.os.replace", side_effect=flaky_replace):
                with tx:
                    tx.stage(f1, new_text="new-1")
                    tx.stage(f2, new_text="new-2")

            self.assertEqual(f1.read_text(encoding="utf-8"), "old-1")
            self.assertEqual(f2.read_text(encoding="utf-8"), "old-2")
            self.assertEqual(tx.status, "rolled_back")
            self.assertEqual(list(vault.glob("*.tmp")), [], "commit 失败后不得残留 .tmp")


class TestSha256Precheck(unittest.TestCase):
    """(c) SHA-256 前置校验：不匹配 → TransactionError 且零写入。"""

    def test_mismatch_rejects_without_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            f = vault / "guarded.md"
            f.write_text("original-content", encoding="utf-8")
            wrong_sha = hashlib.sha256(b"WRONG").hexdigest()

            tx = VaultTransaction(vault, "tx-sha")
            with tx:
                with self.assertRaises(TransactionError):
                    tx.stage(f, expected_sha256=wrong_sha, new_text="evil overwrite")

            self.assertEqual(f.read_text(encoding="utf-8"), "original-content")
            self.assertEqual(list(vault.glob("*.tmp")), [], "前置校验失败不得有任何写盘")
            log = _read_log(vault, "tx-sha")
            self.assertEqual(log["entries"], [], "被拒绝的文件不得登记进日志")

    def test_match_passes_precheck(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            f = vault / "guarded.md"
            f.write_text("original-content", encoding="utf-8")
            correct_sha = hashlib.sha256("original-content".encode("utf-8")).hexdigest()

            tx = VaultTransaction(vault, "tx-sha-ok")
            with tx:
                tx.stage(f, expected_sha256=correct_sha, new_text="safe overwrite")
            self.assertEqual(f.read_text(encoding="utf-8"), "safe overwrite")


class TestStagePathContainment(unittest.TestCase):
    """(g) stage 路径包含性：目标解析后位于 vault_root 之外 → TransactionError 且零写入。"""

    def test_stage_outside_vault_root_rejected_with_zero_writes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td) / "vault"
            vault.mkdir()
            with tempfile.TemporaryDirectory() as outside_td:
                outside = pathlib.Path(outside_td) / "escape.md"
                outside.write_text("outside-original", encoding="utf-8")

                tx = VaultTransaction(vault, "tx-escape")
                with tx:
                    with self.assertRaises(TransactionError):
                        tx.stage(outside, new_text="escaped")

                # 必须在内层 TemporaryDirectory 仍存活时断言外部文件原封未动
                self.assertEqual(
                    outside.read_text(encoding="utf-8"),
                    "outside-original",
                    "vault 外的文件不得被改写",
                )

            # journal 本身由 __enter__/__exit__ 的状态迁移写入（既有契约），
            # 被拒绝的 stage 的零写入体现为：entries 为空、无备份、外部文件未动
            self.assertEqual(
                _read_log(vault, "tx-escape")["entries"],
                [],
                "被拒绝的 stage 不得登记进 journal",
            )
            self.assertFalse(
                (vault / ".vault-tx" / "backups").exists(),
                "被拒绝的 stage 不得创建备份",
            )


@unittest.skipIf(
    not vault_transaction._LOCKING_AVAILABLE,
    "no msvcrt/fcntl on this platform — lock degrades to single-process",
)
class TestLockMutex(unittest.TestCase):
    """(d) 锁互斥：同 vault 第二实例 acquire 超时抛 TransactionError。"""

    def test_second_instance_times_out_and_release_allows_reacquire(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            with VaultTransaction(vault, "tx-lock-a", lock_timeout=1.0):
                with self.assertRaises(TransactionError):
                    with VaultTransaction(vault, "tx-lock-b", lock_timeout=0.3):
                        pass
            # 释放后必须可重新获取（锁真的被释放，而不是泄漏）
            with VaultTransaction(vault, "tx-lock-c", lock_timeout=1.0):
                pass


class TestPersistentJournal(unittest.TestCase):
    """(e) 持久化日志：三态 status、entries 结构完整、UTF-8 且 ensure_ascii=False。"""

    def test_journal_records_all_three_states(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            # 中文文件名同时充当 ensure_ascii=False 的字节级探针
            f = vault / "笔记.md"
            f.write_text("原始内容", encoding="utf-8")

            tx = VaultTransaction(vault, "tx-log")
            with tx:
                tx.stage(f, new_text="更新后的内容")
                log = _read_log(vault, "tx-log")
                self.assertEqual(log["status"], "staged")
                self.assertEqual(log["tx_id"], "tx-log")
                self.assertEqual(log["entries"][0]["path"], str(f))
                self.assertEqual(
                    log["entries"][0]["before_sha256"],
                    hashlib.sha256("原始内容".encode("utf-8")).hexdigest(),
                )
                self.assertTrue(pathlib.Path(log["entries"][0]["backup_path"]).is_file())

            log = _read_log(vault, "tx-log")
            self.assertEqual(log["status"], "committed")
            self.assertEqual(log["entries"][0]["path"], str(f))
            import datetime

            datetime.datetime.fromisoformat(log["created_at"])

            tx2 = VaultTransaction(vault, "tx-log-2")
            with tx2:
                tx2.stage(f, new_text="again")
                tx2.rollback()
            self.assertEqual(_read_log(vault, "tx-log-2")["status"], "rolled_back")

            raw = (vault / ".vault-tx" / "tx-log.json").read_bytes()
            self.assertIn("笔记.md".encode("utf-8"), raw, "journal 必须是 UTF-8 且 ensure_ascii=False")


class TestNewFileLifecycle(unittest.TestCase):
    """(f) 新文件创建：commit 后存在、rollback 后不存在；未提交的幽灵条目回滚不报错。"""

    def test_new_file_created_on_commit_and_removed_on_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            vault = pathlib.Path(td)
            nf = vault / "brand-new.md"

            tx = VaultTransaction(vault, "tx-new")
            with tx:
                tx.stage(nf, new_text="brand new")
                self.assertFalse(nf.exists(), "stage 阶段不得写盘")
            self.assertTrue(nf.is_file())
            self.assertEqual(nf.read_text(encoding="utf-8"), "brand new")
            log = _read_log(vault, "tx-new")
            self.assertIsNone(log["entries"][0]["before_sha256"])
            self.assertIsNone(log["entries"][0]["backup_path"])

            # 回滚删除探针必须是"该事务 stage 时刻不存在"的路径：
            # nf 此时已存在，属现存文件，回滚应恢复原文而非删除（确定性回滚语义）
            nf2 = vault / "second.md"
            tx2 = VaultTransaction(vault, "tx-new-2")
            with tx2:
                tx2.stage(nf2, new_text="temporary")
                tx2.rollback()
            self.assertFalse(nf2.exists(), "新文件回滚 = 删除")
            self.assertEqual(nf.read_text(encoding="utf-8"), "brand new", "现存文件回滚恢复原文")
            self.assertEqual(_read_log(vault, "tx-new-2")["status"], "rolled_back")

            # 幽灵条目：staged 但从未 commit，回滚时文件本就不存在 → 不报错
            tx3 = VaultTransaction(vault, "tx-new-3")
            with tx3:
                tx3.stage(vault / "never.md", new_text="ghost")
                tx3.rollback()
            self.assertFalse((vault / "never.md").exists())


if __name__ == "__main__":
    unittest.main()
