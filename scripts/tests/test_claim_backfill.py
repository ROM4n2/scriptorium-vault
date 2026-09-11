#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for vault-claim-backfill.py (ROADMAP-P4 Task-4).

Covers the plan's four contract clauses:
(a) plan_backfill lists exactly the missing fields per file;
(b) apply adds ONLY the three-field lines, every other byte round-trips;
(c) no-frontmatter files are skipped without producing empty `---` heads;
(d) a mid-apply failure rolls the whole transaction back byte-for-byte.
"""

import importlib.util
import hashlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "vault-claim-backfill.py"
spec = importlib.util.spec_from_file_location("vault_claim_backfill", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _read(path: pathlib.Path) -> str:
    """Raw text with original line endings preserved (no universal newline)."""
    return path.read_bytes().decode("utf-8")


def _make_vault(root: pathlib.Path) -> dict[str, str]:
    """Five-shape fixture: returns {rel: original_text}."""
    files = {
        # plain frontmatter, fully missing three fields
        "01-Rules/EXAMPLE-RULES.md": (
            "---\ntitle: Example Rules\ncreated: 2026-09-09\n"
            "updated: 2026-09-09\ntype: rules\nstatus: stable\n"
            "audience: both\n---\n\n# Example\n\n错误 MUST 只处理一次。\n"
        ),
        # no frontmatter at all -> must be skipped
        "00-MOC/NoFrontmatter.md": "# Just a heading\n\nbody\n",
        # authority already present -> must be kept verbatim, others added
        "06-Sources/Books/Some-Book.md": (
            "---\ntitle: Some Book\nauthority: primary\nstatus: stable\n"
            "---\n\nbody\n"
        ),
        # YAML-special title with quotes -> text-level insert must not
        # re-serialize the frontmatter
        "09-Career/Exam-Prep/Special.md": (
            "---\ntitle: \"Go: 并发 '高频考点' 手册\"\nsource: \"{{CODE_ROOT}}/x.md\"\n"
            "type: notes\nstatus: stable\n---\n\n- SHOULD 保持背诵\n"
        ),
        # daily log shape -> unknown/none mapping
        "10-Daily/2026-09-09.md": (
            "---\ntitle: Daily\nstatus: draft\n---\n\n叙事行，无断言。\n"
        ),
    }
    for rel, text in files.items():
        _write(root / rel, text)
    return files


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPlanBackfill(unittest.TestCase):
    """(a) plan lists exactly the missing fields, never existing ones."""

    def test_plan_lists_missing_fields_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = _make_vault(root)
            plan = mod.plan_backfill(root)
            by_rel = {entry["rel"]: entry for entry in plan}
            # plain file: all three fields planned
            self.assertEqual(
                by_rel["01-Rules/EXAMPLE-RULES.md"]["adds"],
                {"authority": "synthetic", "claim_risk": "high",
                 "review_status": "unreviewed"},
            )
            # partial file: authority kept -> only two adds
            self.assertEqual(
                by_rel["06-Sources/Books/Some-Book.md"]["adds"],
                {"claim_risk": "medium", "review_status": "unreviewed"},
            )
            # daily log maps to unknown/none
            self.assertEqual(
                by_rel["10-Daily/2026-09-09.md"]["adds"],
                {"authority": "unknown", "claim_risk": "none",
                 "review_status": "unreviewed"},
            )
            # no-frontmatter file never planned
            self.assertNotIn("00-MOC/NoFrontmatter.md", by_rel)
            del original

    def test_plan_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = _make_vault(root)
            before = {rel: _sha(root / rel) for rel in original}
            mod.plan_backfill(root)
            after = {rel: _sha(root / rel) for rel in original}
            self.assertEqual(before, after, "plan_backfill MUST be read-only")


def _expected_after_insert(text: str, adds: dict[str, str]) -> str:
    """Build the exact expected post-insert text for a fixture file.

    Mirrors the ADD-ONLY contract: the missing-field lines are inserted
    immediately before the closing `---`, everything else byte-identical.
    """
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(eol)
    closing = next(
        i for i in range(1, len(lines)) if lines[i].strip() == "---"
    )
    insert = [
        f"{key}: {adds[key]}"
        for key in ("authority", "claim_risk", "review_status")
        if key in adds
    ]
    return eol.join(lines[:closing] + insert + lines[closing:])


class TestApplyBackfill(unittest.TestCase):
    """(b) byte-level round-trip: only the added lines differ."""

    def test_apply_adds_only_three_lines(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = _make_vault(root)
            plan = mod.plan_backfill(root)
            adds_by_rel = {entry["rel"]: entry["adds"] for entry in plan}
            with mod.VaultTransaction(root, tx_id="tx-test-apply") as tx:
                stats = mod.apply_backfill(plan, tx)
            self.assertEqual(stats["files_updated"], 4)
            for rel, text in original.items():
                new_raw = _read(root / rel)
                if rel == "00-MOC/NoFrontmatter.md":
                    self.assertEqual(
                        new_raw, text, "no-frontmatter file untouched"
                    )
                    continue
                expected = _expected_after_insert(text, adds_by_rel[rel])
                self.assertEqual(
                    new_raw, expected,
                    f"{rel}: file must equal original + inserted field lines",
                )
            # spot-check the partial file keeps its original authority value
            book = _read(root / "06-Sources/Books/Some-Book.md")
            self.assertIn("authority: primary", book)
            self.assertEqual(book.count("authority:"), 1)

    def test_apply_with_crlf_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            text = (
                "---\r\ntitle: CRLF Note\r\nstatus: stable\r\n---\r\n\r\nbody\r\n"
            )
            path = root / "01-Rules/CRLF-Note.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            plan = mod.plan_backfill(root)
            self.assertEqual(len(plan), 1)
            with mod.VaultTransaction(root, tx_id="tx-crlf") as tx:
                mod.apply_backfill(plan, tx)
            new_bytes = path.read_bytes()
            self.assertTrue(new_bytes.replace(b"\r\n", b"\n").decode("utf-8")
                            .startswith("---\ntitle: CRLF Note"))
            self.assertIn(b"authority: synthetic", new_bytes)
            # no stray mixed endings introduced: count of \r\n unchanged + 3
            self.assertEqual(
                new_bytes.count(b"\r\n"), text.count("\r\n") + 3
            )


class TestNoFrontmatterSkip(unittest.TestCase):
    """(c) skipped files must not gain an empty `---` head."""

    def test_no_frontmatter_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = _make_vault(root)
            plan = mod.plan_backfill(root)
            with mod.VaultTransaction(root, tx_id="tx-nofm") as tx:
                mod.apply_backfill(plan, tx)
            self.assertEqual(
                _read(root / "00-MOC/NoFrontmatter.md"),
                original["00-MOC/NoFrontmatter.md"],
            )


class TestRollbackOnFailure(unittest.TestCase):
    """(d) mid-apply failure -> full rollback, byte-identical restore."""

    def test_failure_rolls_back_everything(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            original = _make_vault(root)
            before = {rel: (root / rel).read_bytes() for rel in original}
            plan = mod.plan_backfill(root)
            real_stage = mod.VaultTransaction.stage
            calls = {"n": 0}

            def failing_stage(self, path, **kwargs):
                calls["n"] += 1
                if calls["n"] >= 2:
                    raise mod.TransactionError("injected mid-apply failure")
                return real_stage(self, path, **kwargs)

            with self.assertRaises(mod.TransactionError):
                with mod.VaultTransaction(root, tx_id="tx-fail") as tx:
                    with mock.patch.object(
                        mod.VaultTransaction, "stage", failing_stage
                    ):
                        mod.apply_backfill(plan, tx)
            after = {rel: (root / rel).read_bytes() for rel in original}
            self.assertEqual(
                before, after, "rollback MUST restore every file byte-for-byte"
            )


class TestMappingPriority(unittest.TestCase):
    """S1-S15/F1 priority semantics from CLAIM-LEDGER-CALIBRATION §2."""

    def test_s5_community_by_frontmatter_fields(self) -> None:
        auth, risk = mod.classify(
            "05-Tools/Guide.md",
            {"source-type": "article", "source-author": "Someone"},
        )
        self.assertEqual((auth, risk), ("community", "low"))

    def test_s6_cheatsheet_before_generic_language(self) -> None:
        self.assertEqual(
            mod.classify("03-Languages/GO/GO-CHEATSHEET.md", {}),
            ("synthetic", "low"),
        )

    def test_s9_moc_and_readme_low_risk(self) -> None:
        self.assertEqual(mod.classify("00-MOC/Home.md", {}), ("synthetic", "none"))
        self.assertEqual(
            mod.classify("04-Systems/README.md", {"type": "moc"}),
            ("synthetic", "none"),
        )

    def test_fallback_f1_unknown_none(self) -> None:
        self.assertEqual(
            mod.classify("42-Universe/Answer.md", {}), ("unknown", "none")
        )


if __name__ == "__main__":
    unittest.main()
