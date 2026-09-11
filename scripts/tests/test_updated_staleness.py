"""Tests for the dirty-working-tree `updated:` staleness WARN (Task 6).

Problem
-------
``vault-quality-check.py`` validated that ``created`` / ``updated`` are *well-formed*
dates but never that ``updated`` is *truthful*. A note can be rewritten while
``updated:`` still claims a date from months ago, and every consumer that ranks or
triages by recency then works off a lie.

Why the authority is `git status`, and not the two obvious alternatives
-----------------------------------------------------------------------
* **Filesystem mtime alone**: a fresh ``git clone`` stamps *every* file with the
  clone time, so an mtime-vs-``updated`` rule fires on all ~171 notes at once.
* **`git log -1 -- <file>`**: CI uses ``actions/checkout`` at the default
  ``fetch-depth: 1``, so the single fetched commit is reported as the last commit of
  *every* file — the same mass-false-positive failure mode.

The implemented rule evaluates **only files git currently reports as dirty**
(modified/staged). That set is empty on any clean checkout, so a fresh clone and a
shallow CI checkout are silent *by construction*, not by tuning — which is exactly
what ``test_clean_tree_is_silent_even_when_updated_is_a_year_stale`` pins.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §2 Occurrence Precheck: every message assertion below was first measured with
  ``len(re.findall(pattern, slice))`` and pins **exactly one** match; the counts are
  asserted mechanically rather than through ``assertTrue(... in ...)``.
* §4 Fixture coherence: the mtime the tests rely on is asserted back off ``stat()``
  after ``os.utime`` — a filesystem that ignored the timestamp would fail loudly
  instead of silently producing a lag of 0.
* §1 Inversion / mutation — every claim below was executed against a `cp` backup of
  the implementation (never `git checkout --`), and these are the observed results:
  - M1 delete the ``_check_updated_staleness`` call in ``run_check``
    -> 3 failed (the two positive tests + the message test).
  - M2 drop the ``rel_path not in dirty_files`` guard, i.e. degrade the rule to
    "mtime vs updated" -> 2 failed:
    ``test_clean_tree_is_silent_even_when_updated_is_a_year_stale`` and
    ``test_untracked_and_clean_neighbours_are_not_evaluated``. Those two are what
    hold the fresh-clone / shallow-CI property; nothing else notices.
  - M3 flip the threshold ``lag_days <= STALENESS_GRACE_DAYS`` -> ``<``
    -> **survived the first version of this file** (lag 1 and lag 3 agree under
    either operator). Fixed by adding
    ``test_two_day_lag_is_the_last_day_inside_the_grace_window``; M3 re-run after
    that addition -> 1 failed. Recorded rather than quietly patched, because the
    surviving mutant is the evidence that the boundary test earns its place.
  - M4 downgrade an unexpected git failure to ``return set()``
    -> ``test_unexpected_git_failure_raises_instead_of_looking_clean`` red.
  - M5 treat a missing/malformed ``updated`` as ``1970-01-01`` instead of skipping
    -> both no-double-report tests red.
  - M6 reverse the comparison to ``(updated - mtime_date).days`` -> 4 failed,
    including ``test_updated_newer_than_mtime_emits_no_warning``.
  - M7 stop filtering ``??``/``!!`` out of the porcelain parse -> 1 failed.
  - M8 stop consuming the rename origin field -> 1 failed.
"""
import datetime
import importlib.util
import os
import pathlib
import re
import tempfile
import unittest

# Import vault-quality-check.py (hyphenated name needs importlib)
_vqc_path = pathlib.Path(__file__).resolve().parent.parent / "vault-quality-check.py"
_spec = importlib.util.spec_from_file_location("vault_quality_check", _vqc_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
QualityChecker = _mod.VaultQualityChecker

_REL = "01-Rules/staleness-fixture.md"

# Fixed clock: the rule compares the file's mtime against frontmatter `updated`,
# so the fixtures are independent of the day the suite happens to run.
_MTIME = datetime.datetime(2026, 3, 11, 12, 0, 0)
_MTIME_DATE = "2026-03-11"


def _note(updated_line: str) -> str:
    """A note whose only possible defect is the one under test."""
    return (
        "---\n"
        'title: "Staleness fixture"\n'
        "created: 2026-03-01\n"
        f"{updated_line}"
        "type: rules\n"
        "tags:\n"
        "  - category/rules\n"
        "status: stable\n"
        "audience: both\n"
        "---\n"
        "\n"
        "# Staleness Fixture\n"
        "\n"
        "Body prose with no wikilinks.\n"
    )


class TestUpdatedStaleness(unittest.TestCase):
    """A dirty note whose `updated:` lags its own content MUST raise a WARN."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "01-Rules").mkdir()
        self.target = self.vault / "01-Rules" / "staleness-fixture.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, updated_line: str, mtime: datetime.datetime = _MTIME) -> None:
        self.target.write_text(_note(updated_line), encoding="utf-8")
        stamp = mtime.timestamp()
        os.utime(self.target, (stamp, stamp))
        # Fixture coherence (TESTING-PATTERNS §4): the mtime really is on disk, so a
        # lag of 0 can never be an artefact of a filesystem that dropped the utime.
        self.assertEqual(
            datetime.date.fromtimestamp(self.target.stat().st_mtime),
            mtime.date(),
        )

    def _run(self, dirty):
        checker = QualityChecker(self.vault)
        checker._get_dirty_files = lambda: set(dirty)
        summary = checker.run_check()
        return checker, summary

    def _freshness(self, checker):
        return [i for i in checker.results.get(_REL, []) if i.category == "FRESHNESS"]

    def _all_issues(self, checker):
        return [(i.level, i.category, i.message) for i in checker.results.get(_REL, [])]

    # ------------------------------------------------------------------ positive

    def test_dirty_note_with_stale_updated_warns(self):
        """Dirty file, `updated` 10 days behind mtime -> exactly one WARN/FRESHNESS."""
        self._write("updated: 2026-03-01\n")
        checker, summary = self._run({_REL})

        found = self._freshness(checker)
        # Occurrence precheck (§2): exactly one issue pins this defect.
        self.assertEqual(len(found), 1, f"issues on the note: {self._all_issues(checker)}")
        self.assertEqual(found[0].level, "WARN")
        self.assertEqual(summary["stats"]["stale_updated_warnings"], 1)
        self.assertEqual(summary["stats"]["total_warnings"], 1)
        self.assertEqual(summary["stats"]["total_errors"], 0)

    def test_warning_names_the_lag_and_both_dates(self):
        """The message must carry the lag and both sides of the comparison."""
        self._write("updated: 2026-03-01\n")
        checker, _ = self._run({_REL})
        msg = self._freshness(checker)[0].message

        # Occurrence precheck (§2): each pattern matches exactly once in the message,
        # so each assertion pins one phrase rather than a family of them.
        self.assertEqual(len(re.findall(r"'updated' is 10 days behind", msg)), 1, msg)
        self.assertEqual(len(re.findall(r"last modified 2026-03-11", msg)), 1, msg)
        self.assertEqual(len(re.findall(r"updated: 2026-03-01", msg)), 1, msg)

    # ------------------------------------------------------------------ negative

    def test_updated_equal_to_mtime_emits_no_warning(self):
        """Dirty file whose `updated` matches its mtime is honest -> no WARN."""
        self._write(f"updated: {_MTIME_DATE}\n")
        checker, summary = self._run({_REL})

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )
        self.assertEqual(summary["stats"]["stale_updated_warnings"], 0)
        # The negative case must not be green because the fixture was never scanned.
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)

    def test_updated_newer_than_mtime_emits_no_warning(self):
        """`updated` ahead of the mtime (post-dated bump) is not staleness."""
        self._write("updated: 2026-04-20\n")
        checker, summary = self._run({_REL})

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)

    def test_one_day_lag_is_below_the_threshold(self):
        """Boundary: 1 day of lag is inside the 2-day grace window -> no WARN."""
        self._write("updated: 2026-03-10\n")
        checker, summary = self._run({_REL})

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )
        self.assertEqual(summary["stats"]["stale_updated_warnings"], 0)
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)

    def test_two_day_lag_is_the_last_day_inside_the_grace_window(self):
        """Boundary, exact: a lag of exactly STALENESS_GRACE_DAYS still does not warn.

        Added after mutation M3 (`<=` -> `<`) survived the first version of this file:
        lag 1 and lag 3 both agree under either operator, so only the exact boundary
        discriminates. Without this test the grace window is off-by-one-able in silence.
        """
        self._write("updated: 2026-03-09\n")
        checker, summary = self._run({_REL})

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )
        self.assertEqual(summary["stats"]["stale_updated_warnings"], 0)
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)

    def test_three_day_lag_is_above_the_threshold(self):
        """Boundary, other side: 3 days of lag clears the 2-day grace window."""
        self._write("updated: 2026-03-08\n")
        checker, _ = self._run({_REL})

        self.assertEqual(len(self._freshness(checker)), 1)

    # ------------------------------------- anti-regression: clone / shallow CI

    def test_clean_tree_is_silent_even_when_updated_is_a_year_stale(self):
        """Empty dirty set -> no WARN, however far `updated` lags the mtime.

        This is the fresh-clone / ``fetch-depth: 1`` CI case: after a clone every
        file's mtime is the clone time while ``updated:`` keeps its authored date, so
        an mtime-only rule would flag the whole vault. Silence here must come from
        the dirty-set guard, not from the lag being small — hence a full year of lag.
        """
        self._write("updated: 2025-03-11\n")
        checker, summary = self._run(set())

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )
        self.assertEqual(summary["stats"]["stale_updated_warnings"], 0)
        self.assertEqual(summary["stats"]["total_warnings"], 0)
        # Not vacuous: the file was scanned and the lag really is ~1 year.
        self.assertEqual(summary["stats"]["total_files_scanned"], 1)
        self.assertGreater(
            (datetime.date.fromtimestamp(self.target.stat().st_mtime) - datetime.date(2025, 3, 11)).days,
            300,
        )

    def test_untracked_and_clean_neighbours_are_not_evaluated(self):
        """Only paths in the dirty set are judged, even inside the same vault."""
        self._write("updated: 2026-03-01\n")
        checker, _ = self._run({"01-Rules/some-other-note.md"})

        self.assertEqual(
            len(self._freshness(checker)), 0, f"issues on the note: {self._all_issues(checker)}"
        )

    # ----------------------------------------- malformed metadata: no double-report

    def test_missing_updated_does_not_crash_or_double_report(self):
        """A missing `updated` is the required-field check's defect, not this one."""
        self._write("")  # no `updated:` line at all
        checker, summary = self._run({_REL})

        self.assertEqual(len(self._freshness(checker)), 0, self._all_issues(checker))
        missing = [
            i
            for i in checker.results.get(_REL, [])
            if i.level == "ERROR" and len(re.findall(r"Missing required field: 'updated'", i.message)) == 1
        ]
        # Occurrence precheck (§2): the defect is reported exactly once, by one owner.
        self.assertEqual(len(missing), 1, self._all_issues(checker))
        self.assertEqual(summary["stats"]["total_errors"], 1)

    def test_malformed_updated_does_not_crash_or_double_report(self):
        """A non-date `updated` is the format check's defect, not this one."""
        self._write("updated: last tuesday\n")
        checker, summary = self._run({_REL})

        self.assertEqual(len(self._freshness(checker)), 0, self._all_issues(checker))
        fmt = [
            i
            for i in checker.results.get(_REL, [])
            if len(re.findall(r"does not match YYYY-MM-DD format", i.message)) == 1
        ]
        self.assertEqual(len(fmt), 1, self._all_issues(checker))
        self.assertEqual(summary["stats"]["total_warnings"], 1)


class TestDirtyFileSeam(unittest.TestCase):
    """`_get_dirty_files` is the injectable seam; its failure modes must be honest."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_non_git_vault_returns_empty_set_without_invoking_git(self):
        """Unit-test vaults and exported copies are silent, and cheaply so."""
        checker = QualityChecker(self.vault)
        original_run = _mod.subprocess.run

        def _explode(*args, **kwargs):
            raise AssertionError("git MUST NOT be invoked when the vault has no .git")

        _mod.subprocess.run = _explode
        try:
            self.assertEqual(checker._get_dirty_files(), set())
        finally:
            _mod.subprocess.run = original_run

    def test_unexpected_git_failure_raises_instead_of_looking_clean(self):
        """A broken repo MUST NOT be downgraded to an (indistinguishable) clean tree."""
        (self.vault / ".git").mkdir()
        checker = QualityChecker(self.vault)
        original_run = _mod.subprocess.run

        class _Failed:
            returncode = 128
            stdout = b""
            stderr = b"fatal: unable to read index file .git/index"

        _mod.subprocess.run = lambda *a, **k: _Failed()
        try:
            with self.assertRaises(RuntimeError) as ctx:
                checker._get_dirty_files()
        finally:
            _mod.subprocess.run = original_run

        # Occurrence precheck (§2): the underlying stderr is surfaced exactly once.
        self.assertEqual(
            len(re.findall(r"unable to read index file", str(ctx.exception))), 1, str(ctx.exception)
        )

    def test_porcelain_parse_keeps_tracked_changes_and_drops_untracked(self):
        """`--porcelain=v1 -z` -> vault-relative paths; `??`/`!!` are not staleness."""
        raw = (
            " M 01-Rules/〔你的领域通用规范〕.md\0"
            "M  03-Languages/Go/GO-STANDARDS.md\0"
            "?? 99-Inbox/2026-09-08-draft.md\0"
            "!! .obsidian/workspace.json\0"
            "D  02-Sources/gone.md\0"
        )
        self.assertEqual(
            QualityChecker._parse_porcelain_z(raw),
            {
                "01-Rules/〔你的领域通用规范〕.md",
                "03-Languages/Go/GO-STANDARDS.md",
                "02-Sources/gone.md",
            },
        )

    def test_porcelain_parse_consumes_the_rename_origin_field(self):
        """A rename's second NUL field MUST NOT be mis-read as the next status entry."""
        raw = (
            "R  01-Rules/NEW-NAME.md\0" "99-Inbox/2026-09-01-old.md\0" " M 01-Rules/AFTER.md\0"
        )
        self.assertEqual(
            QualityChecker._parse_porcelain_z(raw),
            {
                "01-Rules/NEW-NAME.md",
                "99-Inbox/2026-09-01-old.md",
                "01-Rules/AFTER.md",
            },
        )


if __name__ == "__main__":
    unittest.main()
