#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shell scripts MUST ship as LF — release-rehearsal blocker (2026-09-10).

Incident: with `* text=auto` plus `core.autocrlf=true` on Windows,
`git archive` rewrote `.githooks/pre-commit` and `.githooks/gates/*.sh` to
CRLF. Extracted copies then failed `bash -n` with `syntax error near
unexpected token 'done'` / `unexpected end of file` — i.e. the three commit
gates are dead on arrival for anyone who receives the template.

Contract pinned here:
1. `.gitattributes` MUST declare `eol=lf` for shell scripts and .githooks
   files, so checkout AND archive produce LF regardless of local autocrlf.
2. The repository index MUST already store those files without CR bytes.
"""

import pathlib
import subprocess
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _is_git_work_tree() -> bool:
    """True when ``_REPO_ROOT`` is a git work tree (has a resolvable git dir).

    ``git archive`` unpacked trees and green/receiver scenarios carry no
    ``.git``; the EOL contract below is only meaningful inside a real repo.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        # `git` binary itself missing — nothing here can hold.
        return False
    return res.returncode == 0


_IS_GIT_WORK_TREE = _is_git_work_tree()

SHELL_FILES = [
    ".githooks/pre-commit",
    ".githooks/gates/gate1-secret.sh",
    ".githooks/gates/gate15-url.sh",
    ".githooks/gates/gate2-quality.sh",
    "scripts/bootstrap.sh",
    "Templates/workmemory/precompact-session-save.sh",
    "Templates/workmemory/sessionstart-compact-restore.sh",
]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


class TestGitattributesForcesLf(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _IS_GIT_WORK_TREE:
            raise unittest.SkipTest("not a git work tree")

    def test_eol_attribute_is_lf_for_shell_files(self) -> None:
        for rel in SHELL_FILES:
            with self.subTest(path=rel):
                res = _git("check-attr", "eol", "--", rel)
                self.assertEqual(res.returncode, 0, res.stderr)
                # 形如 "path: eol: lf"
                self.assertTrue(
                    res.stdout.strip().endswith("eol: lf"),
                    f"{rel} MUST 声明 eol=lf（否则 Windows 出包变 CRLF，"
                    f"bash -n 直接语法错误，三道门报废）；实际: {res.stdout.strip()!r}",
                )


class TestIndexStoresLf(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _IS_GIT_WORK_TREE:
            raise unittest.SkipTest("not a git work tree")

    def test_index_blobs_have_no_cr(self) -> None:
        for rel in SHELL_FILES:
            with self.subTest(path=rel):
                res = _git("show", f":{rel}")
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertNotIn(
                    "\r\n", res.stdout,
                    f"{rel} 的索引 blob 含 CRLF——仓库存储必须为 LF",
                )


if __name__ == "__main__":
    unittest.main()
