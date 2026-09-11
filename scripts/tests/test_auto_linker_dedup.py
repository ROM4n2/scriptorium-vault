#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the auto-linker duplicate-link guard (2026-09-09 incident).

Real-world failure: ``vault-auto-linker.py --apply`` inserted a *second*
``[[01-Rules/〔你的领域通用规范〕]]`` on lines that already linked the same
target (e.g. ``- 跨语言通用编码规范…：[[01-Rules/〔你的领域通用规范〕]]`` became
``- [[01-Rules/〔你的领域通用规范〕|跨语言通用编码规范]]…：[[01-Rules/〔你的领域通用规范〕]]``).

Root cause: ``file_linked_concepts`` was never seeded with the file's
pre-existing wikilinks, so the "already linked in this file" guard only saw
links the linker itself had just created.

Contract pinned here: a plain-text mention of a concept MUST NOT be linked
when the file already contains a link to the same target — in full-path,
filename-only, or alias form.
"""

import importlib.util
import pathlib
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "vault_auto_linker", _SCRIPTS_DIR / "vault-auto-linker.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

TERM = "跨语言通用编码规范"
TARGET = "01-Rules/〔你的领域通用规范〕"


def make_linker(vault_root: pathlib.Path) -> mod.VaultAutoLinker:
    linker = mod.VaultAutoLinker(vault_root)
    linker.concepts = {
        TERM: mod.ConceptEntry(TERM, TARGET, vault_root / (TARGET + ".md"))
    }
    linker.sorted_terms = [TERM]
    return linker


class TestExtractExistingLinkTargets(unittest.TestCase):
    def test_full_path_link_detected(self) -> None:
        targets = mod.extract_existing_link_targets("见 [[01-Rules/〔你的领域通用规范〕]]")
        self.assertIn("01-Rules/〔你的领域通用规范〕", targets)
        self.assertIn("〔你的领域通用规范〕", targets)  # 文件名形式同源

    def test_alias_and_embed_detected(self) -> None:
        targets = mod.extract_existing_link_targets(
            "[[01-Rules/〔你的领域通用规范〕|通用]] 与 ![[img.png]]"
        )
        self.assertIn("01-Rules/〔你的领域通用规范〕", targets)

    def test_plain_text_not_detected(self) -> None:
        targets = mod.extract_existing_link_targets("跨语言通用编码规范：〔你的领域通用规范〕")
        self.assertEqual(targets, set())


class TestLineDedup(unittest.TestCase):
    def _process(self, line: str):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            linker = make_linker(root)
            existing = mod.extract_existing_link_targets(line)
            # current_file 必须不同于目标文件，否则会命中"自我链接规避"而非被测逻辑
            other = root / "01-Rules" / "OTHER-NOTE.md"
            return linker._process_line(line, other, set(), existing, 1)

    def test_line_with_full_path_link_not_relinked(self) -> None:
        """事故原样复现：该行已有 [[01-Rules/〔你的领域通用规范〕]]，纯文本提及不得再链。"""
        line = "- 跨语言通用编码规范（反转自问检验 / 死测成因 #1 #2）：[[01-Rules/〔你的领域通用规范〕]]\n"
        new_line, cands = self._process(line)
        self.assertEqual(new_line, line, "已有链接的行 MUST NOT 被重复插入")
        self.assertEqual(cands, [])

    def test_line_with_alias_link_not_relinked(self) -> None:
        line = "- [[01-Rules/〔你的领域通用规范〕|通用规范]]：跨语言通用编码规范\n"
        new_line, cands = self._process(line)
        self.assertEqual(new_line.count("[[01-Rules/〔你的领域通用规范〕"), 1)

    def test_filename_only_link_blocks_too(self) -> None:
        line = "- 见 [[〔你的领域通用规范〕]]；跨语言通用编码规范是上位规则\n"
        new_line, cands = self._process(line)
        self.assertEqual(new_line, line, "文件名形式的既有链接同样应视为已链接")
        self.assertEqual(cands, [])

    def test_unlinked_mention_still_linked(self) -> None:
        """防过度拦截：真正未链接的提及仍应被链接（既有行为不回退）。"""
        line = "- 跨语言通用编码规范是上位规则\n"
        new_line, cands = self._process(line)
        self.assertIn("[[01-Rules/〔你的领域通用规范〕]]", new_line)
        self.assertEqual(len(cands), 1)


class TestProcessFileEndToEnd(unittest.TestCase):
    """整文件级回归：已含目标链接的文件，--apply 后 MUST 零改动。"""

    def test_apply_is_noop_when_target_already_linked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            note = root / "01-Rules" / "TESTING-PATTERNS.md"
            note.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "---\ntitle: T\ncreated: 2026-09-09\nupdated: 2026-09-09\n"
                "type: rules\nstatus: stable\naudience: both\n---\n\n"
                "- 跨语言通用编码规范（反转自问检验）：[[01-Rules/〔你的领域通用规范〕]]\n"
            )
            note.write_text(content, encoding="utf-8")
            target = root / (TARGET + ".md")
            target.write_text("# target\n", encoding="utf-8")

            linker = make_linker(root)
            report = linker.process_file(note, dry_run=False)
            self.assertEqual(report["candidate_count"], 0, report["candidates"])
            self.assertEqual(note.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
