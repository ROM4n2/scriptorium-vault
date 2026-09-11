#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural-file exemptions in the quality gate (2026-09-10).

Two false-positive classes surfaced when the exported template was pushed:

1. `10-Daily/README.md` and `99-Inbox/README.md` — directory-level guidance
   READMEs are **structural files**, not a daily note / inbox draft; the naming
   rules must not flag them (template recipients would otherwise open their
   copy with warnings on day one).
2. `Templates/workmemory/*.md` — the WORKMEMORY kit is copied into *projects*
   as project-level memory files where vault frontmatter does not apply; the
   frontmatter checker must stay silent for that subtree instead of emitting
   "Template frontmatter note" warnings.

Both are pinned here against the real checker.
"""

import importlib.util
import pathlib
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "vault_quality_check", _SCRIPTS_DIR / "vault-quality-check.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _make_vault(root: pathlib.Path) -> None:
    (root / "10-Daily").mkdir(parents=True, exist_ok=True)
    (root / "99-Inbox").mkdir(parents=True, exist_ok=True)
    (root / "Templates" / "workmemory").mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "10-Daily" / "README.md").write_text(
        "---\ntitle: Daily\ntype: notes\nstatus: stable\naudience: both\n"
        "tags:\n  - category/notes\n---\n\n本区承载每日流水。\n", encoding="utf-8"
    )
    (root / "99-Inbox" / "README.md").write_text(
        "---\ntitle: Inbox\ntype: notes\nstatus: stable\naudience: both\n"
        "tags:\n  - category/notes\n---\n\n本区是 Landing Zone。\n", encoding="utf-8"
    )
    for name in ("PROTOCOL", "INDEX", "PROJECT_OVERVIEW", "corrections"):
        (root / "Templates" / "workmemory" / f"{name}.md").write_text(
            f"# {name}（项目级模板，无 vault frontmatter）\n", encoding="utf-8"
        )
    # 随包技能子集：使用 harness 技能 schema（name/description），非 vault 笔记 schema
    (root / "skills" / "vault-save").mkdir(parents=True, exist_ok=True)
    (root / "skills" / "vault-save" / "SKILL.md").write_text(
        "---\nname: vault-save\ndescription: harvest session knowledge\n---\n\n# vault-save\n",
        encoding="utf-8",
    )


def _issue_messages(root: pathlib.Path) -> list:
    """展平 run_check() 的 issues_by_file → 消息列表。

    issues_by_file 的值可能是 Issue 对象或（序列化后的）dict，两者都要兼容。
    """
    checker = mod.VaultQualityChecker(root)
    result = checker.run_check()
    messages = []
    for _rel, issues in (result.get("issues_by_file") or {}).items():
        for item in issues or []:
            if isinstance(item, dict):
                messages.append(str(item.get("message", "")))
            else:
                messages.append(str(getattr(item, "message", "")))
    return messages


class TestStructuralExemptions(unittest.TestCase):
    def test_zone_readmes_produce_no_naming_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _make_vault(root)
            msgs = _issue_messages(root)
            offenders = [
                m for m in msgs
                if ("Inbox draft should start" in m or "Daily note should match" in m)
            ]
            self.assertEqual(offenders, [], f"结构性 README 不应触发命名告警: {offenders}")

    def test_shipped_skills_produce_no_frontmatter_errors(self) -> None:
        """skills/** 使用 harness 技能 schema（name/description），MUST NOT 被 vault 字段校验。"""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _make_vault(root)
            checker = mod.VaultQualityChecker(root)
            result = checker.run_check()
            offenders = []
            for rel, issues in (result.get("issues_by_file") or {}).items():
                if not rel.startswith("skills/"):
                    continue
                for item in issues or []:
                    msg = item.get("message", "") if isinstance(item, dict) else getattr(item, "message", "")
                    offenders.append(f"{rel}: {msg}")
            self.assertEqual(offenders, [], f"skills/ 不应触发 vault 字段校验: {offenders}")

    def test_workmemory_kit_produces_no_frontmatter_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _make_vault(root)
            msgs = _issue_messages(root)
            offenders = [m for m in msgs if "Template frontmatter note" in m]
            self.assertEqual(
                offenders, [], f"WORKMEMORY 件套不应触发 frontmatter 告警: {offenders}"
            )


if __name__ == "__main__":
    unittest.main()
