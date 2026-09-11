#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the claim-enum healthcheck (ROADMAP-P4 Task-5).

Contract: check_claim_enums(vault_root) -> list[str] flags ONLY illegally
valued authority/claim_risk/review_status fields. Missing fields are legal
(default semantics per CLAIM-LEDGER-SCHEMA §1) and must NOT be flagged;
non-enum values (including non-strings) must be flagged with the file named.
"""

import importlib.util
import pathlib
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "vault_healthcheck", _SCRIPTS_DIR / "vault-healthcheck.py"
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _write_note(root: pathlib.Path, rel: str, frontmatter: str, body: str = "\nbody\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")


_BASE_FM = (
    "title: T\ncreated: 2026-09-09\nupdated: 2026-09-09\n"
    "type: notes\nstatus: stable\naudience: both\n"
)


class TestCheckClaimEnums(unittest.TestCase):
    def test_legal_values_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, "01-Rules/Ok.md", _BASE_FM +
                        "authority: synthetic\nclaim_risk: high\n"
                        "review_status: unreviewed\n")
            self.assertEqual(mod.check_claim_enums(root), [])

    def test_missing_fields_are_legal(self) -> None:
        """Default semantics: absent fields are NOT illegal (SCHEMA §1)."""
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, "01-Rules/Bare.md", _BASE_FM)
            self.assertEqual(mod.check_claim_enums(root), [])

    def test_bogus_authority_detected_and_named(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, "01-Rules/Bad.md", _BASE_FM + "authority: bogus\n")
            problems = mod.check_claim_enums(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("01-Rules/Bad.md", problems[0])
            self.assertIn("authority", problems[0])
            self.assertIn("bogus", problems[0])

    def test_bogus_claim_risk_and_review_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, "03-Languages/GO/X.md",
                        _BASE_FM + "claim_risk: kind-of\nreview_status: maybe\n")
            problems = mod.check_claim_enums(root)
            self.assertEqual(len(problems), 2)
            joined = "\n".join(problems)
            self.assertIn("claim_risk", joined)
            self.assertIn("review_status", joined)

    def test_non_string_value_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, "09-Career/Y.md", _BASE_FM + "authority: [a, b]\n")
            problems = mod.check_claim_enums(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("authority", problems[0])

    def test_tmp_and_dotfiles_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            _write_note(root, ".tmp-x.md", _BASE_FM + "authority: bogus\n")
            self.assertEqual(mod.check_claim_enums(root), [])


if __name__ == "__main__":
    unittest.main()
