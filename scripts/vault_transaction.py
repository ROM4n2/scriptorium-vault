#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vault_transaction.py — vault 级事务原语（P1 Task-2）。

在 vault 任意子树内提供"多文件一致性替换"：

  * 进程级变更锁 ``{vault_root}/.vault-tx/.lock``
    （Windows 用 ``msvcrt.locking``，POSIX 用 ``fcntl.flock``；
    两者都不可用则降级为无互斥保护、仅向 stderr 告警一次）。
  * SHA-256 前置校验：``stage()`` 可要求现存内容哈希与 ``expected_sha256``
    一致，不匹配抛 ``TransactionError`` 且零写盘。
  * 持久化日志 ``{vault_root}/.vault-tx/{tx_id}.json``
    （UTF-8 / ``ensure_ascii=False``），记录
    ``{tx_id, created_at, status, entries}``，
    ``status ∈ staged | committed | rolled_back``。
  * 原子替换：commit 逐文件写同目录 ``.tmp`` 后 ``os.replace``。
  * 确定性回滚：按登记顺序用备份原文恢复（含已 commit 的文件）；
    新文件回滚 = 删除；被删除文件回滚 = 从备份逐字节恢复。

纯标准库，零第三方依赖。典型用法::

    with VaultTransaction(vault_root, tx_id="tx-20260215-01") as tx:
        tx.stage(path, expected_sha256=..., new_text=...)
        tx.stage_deletion(path)  # 登记待删文件：commit 删除，rollback 恢复

边界（P1 Task-3 起支持删除登记）：同一事务内不得重复登记同一路径
（写/删皆然）；``stage_deletion`` 要求目标在登记时刻存在。
"""

from __future__ import annotations

import sys

# Prevent Windows GBK stdout trap (RFC / Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import time
from types import TracebackType

try:
    import fcntl  # POSIX advisory lock
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    _HAVE_FCNTL = False

try:
    import msvcrt  # Windows mandatory region lock
    _HAVE_MSVCRT = True
except ImportError:  # pragma: no cover - POSIX
    _HAVE_MSVCRT = False

__all__ = ["TransactionError", "VaultTransaction"]

_LOCKING_AVAILABLE = _HAVE_FCNTL or _HAVE_MSVCRT
_LOCK_POLL_INTERVAL = 0.05
_TX_DIRNAME = ".vault-tx"
_TX_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class TransactionError(RuntimeError):
    """事务操作失败（锁超时、哈希不匹配、非法状态迁移、非法入参等）。"""


@dataclasses.dataclass
class _StagedFile:
    """单条待写/待删条目：登记信息（进日志）+ 待写内容（内存快照）。"""

    path: pathlib.Path
    before_sha256: str | None
    backup_path: pathlib.Path | None
    tmp_path: pathlib.Path
    payload: bytes
    is_deletion: bool = False


_degraded_warned = False


def _warn_lock_degraded() -> None:
    """平台无锁原语时警告一次（降级模式：无互斥保护，仅告警）。"""
    global _degraded_warned
    if _degraded_warned:
        return
    print(
        "[VaultTransaction] 警告: 平台缺少 msvcrt/fcntl，事务锁降级：无互斥保护，仅告警。",
        file=sys.stderr,
    )
    _degraded_warned = True


class VaultTransaction:
    """vault 级事务：锁 → stage / stage_deletion（快照+校验）
    → commit（原子替换/删除）/ rollback（确定性恢复）。"""

    def __init__(self, vault_root: pathlib.Path, tx_id: str, lock_timeout: float = 10.0) -> None:
        if not _TX_ID_PATTERN.match(tx_id):
            raise TransactionError(f"非法 tx_id（仅允许 [A-Za-z0-9._-]）: {tx_id!r}")
        self.vault_root = pathlib.Path(vault_root)
        self.tx_id = tx_id
        self.lock_timeout = lock_timeout
        self.tx_dir = self.vault_root / _TX_DIRNAME
        self.journal_path = self.tx_dir / f"{tx_id}.json"
        self.lock_path = self.tx_dir / ".lock"
        self.backup_dir = self.tx_dir / "backups" / tx_id
        self.created_at = datetime.datetime.now().isoformat()
        self.status: str = "initialized"
        self._entries: list[_StagedFile] = []
        self._lock_fd: int | None = None

    # ---------- 上下文管理 ----------

    def __enter__(self) -> "VaultTransaction":
        self.tx_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        self._set_status("staged")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """异常 → rollback 并重新抛出；正常 → commit；两者最终释放锁。"""
        try:
            self._finalize(exc_type)
            return False  # 永不吞异常
        finally:
            self._release_lock()

    def _finalize(self, exc_type: type[BaseException] | None) -> None:
        if exc_type is not None:
            self.rollback()
            return
        if self.status != "staged":  # 手动 commit/rollback 后正常退出：不重复迁移
            return
        try:
            self.commit()
        except Exception as commit_exc:
            self._rollback_after_failure(commit_exc)
            raise

    def _rollback_after_failure(self, primary: BaseException) -> None:
        """commit 失败后回滚；回滚自身失败必须连报（cause = commit 异常）。"""
        try:
            self.rollback()
        except Exception as rb_exc:
            raise TransactionError(f"commit 失败后回滚也失败: {rb_exc}") from primary

    # ---------- 核心操作 ----------

    def stage(
        self,
        path: pathlib.Path,
        expected_sha256: str | None = None,
        new_text: str | None = None,
        new_bytes: bytes | None = None,
    ) -> None:
        """登记一条待写文件：快照备份现存内容，可按 ``expected_sha256`` 前置校验。

        目标解析后必须位于 ``vault_root`` 内，越界抛 ``TransactionError``。
        新内容仅在内存随条目保存，commit 时才原子替换落盘。
        """
        if self.status != "staged":
            raise TransactionError(f"stage 仅允许在 staged 状态调用，当前 status={self.status}")
        if (new_text is None) == (new_bytes is None):
            raise TransactionError("new_text 与 new_bytes 必须二选一")
        p = path if path.is_absolute() else self.vault_root / path
        if not p.resolve().is_relative_to(self.vault_root.resolve()):
            raise TransactionError(
                f"stage 目标越界: {p} 解析后不在 vault_root 内 ({self.vault_root})"
            )
        if any(e.path == p for e in self._entries):
            raise TransactionError(f"同一事务内重复登记同一文件: {p}")
        payload = new_bytes if new_bytes is not None else new_text.encode("utf-8")
        backup_path: pathlib.Path | None = None
        before: str | None = None
        if p.is_file():
            current = p.read_bytes()
            before = hashlib.sha256(current).hexdigest()
            if expected_sha256 is not None and expected_sha256 != before:
                raise TransactionError(
                    f"SHA-256 前置校验失败: {p} 现存 {before} != 期望 {expected_sha256}"
                )
            backup_path = self.backup_dir / f"{len(self._entries):02d}_{p.name}.bak"
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(current)
        self._entries.append(
            _StagedFile(
                path=p,
                before_sha256=before,
                backup_path=backup_path,
                tmp_path=p.parent / (p.name + ".tmp"),
                payload=payload,
            )
        )
        self._write_journal()

    def stage_deletion(
        self,
        path: pathlib.Path,
        expected_sha256: str | None = None,
    ) -> None:
        """登记一条待删除文件（P1 Task-3）：快照备份原文，commit 时删除，
        rollback 时用备份逐字节恢复。

        约束与 ``stage`` 一致：目标解析后必须位于 ``vault_root`` 内（越界抛
        ``TransactionError``）；同一事务内不得重复登记同一路径（写/删皆然）；
        ``expected_sha256`` 可对现存内容前置校验。目标在登记时刻不存在 →
        ``TransactionError``——删除必须是已确认存在的事实，静默容忍缺失会
        掩盖登记侧的状态不一致。
        """
        if self.status != "staged":
            raise TransactionError(
                f"stage_deletion 仅允许在 staged 状态调用，当前 status={self.status}"
            )
        p = path if path.is_absolute() else self.vault_root / path
        if not p.resolve().is_relative_to(self.vault_root.resolve()):
            raise TransactionError(
                f"stage_deletion 目标越界: {p} 解析后不在 vault_root 内 ({self.vault_root})"
            )
        if any(e.path == p for e in self._entries):
            raise TransactionError(f"同一事务内重复登记同一文件: {p}")
        if not p.is_file():
            raise TransactionError(f"stage_deletion 目标不存在: {p}")
        current = p.read_bytes()
        before = hashlib.sha256(current).hexdigest()
        if expected_sha256 is not None and expected_sha256 != before:
            raise TransactionError(
                f"SHA-256 前置校验失败: {p} 现存 {before} != 期望 {expected_sha256}"
            )
        backup_path = self.backup_dir / f"{len(self._entries):02d}_{p.name}.bak"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(current)
        self._entries.append(
            _StagedFile(
                path=p,
                before_sha256=before,
                backup_path=backup_path,
                tmp_path=p.parent / (p.name + ".tmp"),
                payload=b"",
                is_deletion=True,
            )
        )
        self._write_journal()

    def commit(self) -> None:
        """逐文件：写同目录 ``.tmp`` → ``os.replace`` 原子替换；
        删除条目直接 ``unlink``（登记时已备份原文）；全部完成后 status=committed。"""
        if self.status != "staged":
            raise TransactionError(f"commit 仅允许在 staged 状态调用，当前 status={self.status}")
        for entry in self._entries:
            if entry.is_deletion:
                entry.path.unlink()
                continue
            entry.tmp_path.write_bytes(entry.payload)
            os.replace(entry.tmp_path, entry.path)
        self._set_status("committed")

    def rollback(self) -> None:
        """确定性恢复：按登记顺序用备份原文恢复（含已 commit 文件）；
        新文件回滚 = 删除；被删除文件回滚 = 从备份逐字节恢复。"""
        if self.status not in ("staged", "committed"):
            raise TransactionError(
                f"rollback 仅允许在 staged/committed 状态调用，当前 status={self.status}"
            )
        for entry in self._entries:
            if entry.backup_path is not None:
                entry.tmp_path.write_bytes(entry.backup_path.read_bytes())
                os.replace(entry.tmp_path, entry.path)
            elif entry.path.exists():
                entry.path.unlink()
            if entry.tmp_path.exists():
                entry.tmp_path.unlink()
        self._set_status("rolled_back")

    # ---------- 持久化日志 ----------

    def _set_status(self, status: str) -> None:
        self.status = status
        self._write_journal()

    def _write_journal(self) -> None:
        data = {
            "tx_id": self.tx_id,
            "created_at": self.created_at,
            "status": self.status,
            "entries": [
                {
                    "path": str(e.path),
                    "before_sha256": e.before_sha256,
                    "backup_path": str(e.backup_path) if e.backup_path else None,
                    "action": "delete" if e.is_deletion else "write",
                }
                for e in self._entries
            ],
        }
        self.tx_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- 进程级变更锁 ----------

    def _acquire_lock(self) -> None:
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT)
        self._lock_fd = fd
        if not _LOCKING_AVAILABLE:
            _warn_lock_degraded()
            return
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                self._lock_once(fd)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    self._lock_fd = None
                    raise TransactionError(
                        f"获取事务锁超时（{self.lock_timeout}s，他事务在写同一 vault？）: {self.lock_path}"
                    )
                time.sleep(_LOCK_POLL_INTERVAL)

    def _lock_once(self, fd: int) -> None:
        if _HAVE_MSVCRT:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        elif _HAVE_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        fd = self._lock_fd
        self._lock_fd = None
        if _LOCKING_AVAILABLE:
            if _HAVE_MSVCRT:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            elif _HAVE_FCNTL:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == "__main__":
    print("vault_transaction 是库模块，请从脚本/测试导入使用（无 CLI）。", file=sys.stderr)
    raise SystemExit(2)
