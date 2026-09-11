#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the one-command template publisher (export → self-check → commit → push).

Hermetic: a local bare repo stands in for the GitHub remote, and the export /
self-check steps are injected so no real vault export runs here.
"""

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "vault_publish_template", _SCRIPTS_DIR / "vault-publish-template.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, encoding="utf-8",
        errors="replace",
    )


def _make_repo(root: pathlib.Path, name: str) -> pathlib.Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "tester")
    (path / "README.md").write_text("# pkg\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


class TestSelfCheckCommands(unittest.TestCase):
    def test_covers_pytest_and_quality(self) -> None:
        joined = [" ".join(c) for c in mod.self_check_commands()]
        self.assertTrue(any("pytest" in c for c in joined))
        self.assertTrue(any("vault-quality-check.py" in c and "--strict" in c for c in joined))


class TestPublishPipeline(unittest.TestCase):
    def _env(self, root: pathlib.Path):
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        pkg = _make_repo(root, "pkg")
        _git(pkg, "remote", "add", "origin", str(remote))
        _git(pkg, "push", "-q", "-u", "origin", "master")
        return remote, pkg

    def test_dry_run_does_not_export_or_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _remote, pkg = self._env(root)
            called = []
            report = mod.publish(
                root, pkg, "msg", apply=False,
                export_fn=lambda: called.append("export") or {},
                self_check_fn=lambda _d: (True, []),
            )
            self.assertFalse(report["applied"])
            self.assertEqual(called, [])
            self.assertFalse(report["committed"])

    def test_self_check_failure_aborts_before_commit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            remote, pkg = self._env(root)
            before = _git(pkg, "rev-parse", "HEAD").stdout.strip()
            with self.assertRaises(RuntimeError):
                mod.publish(
                    root, pkg, "msg", apply=True,
                    export_fn=lambda: (pkg / "new.md").write_text("x") or {},
                    self_check_fn=lambda _d: (False, ["pytest failed"]),
                )
            after = _git(pkg, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(before, after, "自检失败 MUST NOT 提交")
            # 远程也未被推进
            remote_head = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", "master"],
                capture_output=True, encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(remote_head, before)

    def test_happy_path_commits_and_pushes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            remote, pkg = self._env(root)
            report = mod.publish(
                root, pkg, "chore: refresh", apply=True,
                export_fn=lambda: (pkg / "new.md").write_text("x") or {"keep": 1},
                self_check_fn=lambda _d: (True, []),
            )
            self.assertTrue(report["committed"])
            self.assertTrue(report["pushed"])
            local_head = _git(pkg, "rev-parse", "HEAD").stdout.strip()
            remote_head = subprocess.run(
                ["git", "--git-dir", str(remote), "rev-parse", "master"],
                capture_output=True, encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(local_head, remote_head, "远程应收到新提交")

    def test_no_changes_skips_commit_but_still_ok(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _remote, pkg = self._env(root)
            report = mod.publish(
                root, pkg, "msg", apply=True,
                export_fn=lambda: {},  # 不产生任何变更
                self_check_fn=lambda _d: (True, []),
            )
            self.assertFalse(report["committed"])
            self.assertTrue(report["pushed"], "无变更也应视为发布成功（推送为 no-op）")

    def test_non_git_package_dir_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            plain = root / "plain"
            plain.mkdir()
            with self.assertRaises(RuntimeError):
                mod.publish(root, plain, "msg", apply=True,
                            export_fn=lambda: {}, self_check_fn=lambda _d: (True, []))


if __name__ == "__main__":
    unittest.main()
