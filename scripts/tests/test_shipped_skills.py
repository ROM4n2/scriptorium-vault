#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tripwires for the shipped skill subset (skills/), 2026-09-10.

`skills/` is vendored into the public template. Two things must hold:

1. Every shipped skill is a real skill: `<dir>/SKILL.md` exists and its
   frontmatter carries the harness schema fields `name` + `description`.
2. The subset is exactly the declared allowlist — domain-neutral, vault-operation
   skills only. Accidentally copying a career/coding skill (e.g. vault-interview,
   vault-tdd) into this directory MUST fail this test.
"""

import pathlib
import re
import unittest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SKILLS_DIR = _REPO_ROOT / "skills"

# 随包白名单（领域无关的知识库运作技能）
EXPECTED = {
    "vault",
    "vault-save",
    "vault-inbox-consolidate",
    "vault-handoff",
    "vault-plan",
    "vault-exec",
    "vault-adr",
    "vault-grill",
    "vault-spark",
    "vault-debug",
    "vault-team",
}

# 明确排除（编程/求职类，与领域无关定位不符）
MUST_NOT_SHIP = {
    "vault-interview", "vault-tdd", "vault-refactor", "vault-perf",
    "vault-review", "vault-onboard", "vault-bootstrap", "vault-pipeline",
    "vault-agent-sdk",
}


def _skill_dirs() -> set:
    if not _SKILLS_DIR.is_dir():
        return set()
    return {
        p.name for p in _SKILLS_DIR.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    }


class TestShippedSkillAllowlist(unittest.TestCase):
    def test_subset_matches_allowlist(self) -> None:
        found = _skill_dirs()
        self.assertEqual(
            found, EXPECTED,
            f"随包技能子集与白名单不一致。多出: {sorted(found - EXPECTED)}；"
            f"缺失: {sorted(EXPECTED - found)}",
        )

    def test_coding_and_career_skills_are_not_shipped(self) -> None:
        found = _skill_dirs()
        offenders = sorted(found & MUST_NOT_SHIP)
        self.assertEqual(offenders, [], f"以下技能不应随包发布: {offenders}")


class TestSkillShape(unittest.TestCase):
    def test_every_skill_has_name_and_description(self) -> None:
        for name in sorted(_skill_dirs()):
            with self.subTest(skill=name):
                text = (_SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---"), f"{name}: 缺少 frontmatter")
                head = text.split("---", 2)[1]
                self.assertRegex(head, r"(?m)^name:\s*\S+", f"{name}: 缺少 name")
                self.assertRegex(head, r"(?m)^description:\s*\S+", f"{name}: 缺少 description")


if __name__ == "__main__":
    unittest.main()
