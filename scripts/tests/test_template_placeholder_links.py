"""Tests for the shared wikilink placeholder rule (scripts/vault_linkrules.py).

Problem
-------
Two checkers disagreed about what counts as a broken wikilink inside ``Templates/``
and **both were wrong**:

* ``vault-quality-check.py`` ``_check_wikilinks`` granted a blanket amnesty
  (``if is_template: continue``): *any* unresolvable link under ``Templates/`` was
  dropped. Templates are instantiated, so a genuinely broken link there propagates
  into every note produced from the template — the amnesty hid exactly the class of
  defect that costs the most.
* ``vault-healthcheck.py`` ``check_wikilinks`` skipped only ``{{...}}`` plus four
  literals, so the date-shaped placeholder idiom (``RAW-YYYY-MM-DD``) was reported as
  a hard failure — the sole reason the healthcheck gate exited 1.

The rule now lives once, in ``vault_linkrules.is_placeholder_link``, and both call
sites delegate to it. The two call sites pass differently-shaped strings
(quality-check passes the raw link body including ``#anchor``/``|alias``, healthcheck
passes an already-``_clean_link_target``-ed target), which is why the predicate
normalises internally and why ``test_raw_and_cleaned_forms_agree`` pins that both
shapes get the same verdict — that asymmetry is how the two copies drifted apart in
the first place.

Scope decision: is the predicate location-scoped to ``Templates/``?
------------------------------------------------------------------
**No — it is purely lexical and applies vault-wide.** Reasons:

1. ``vault-healthcheck.py`` ``check_wikilinks`` has no notion of templates at all;
   its placeholder skip is already vault-wide. Scoping the shared predicate to
   ``Templates/`` on the quality-check side would guarantee a fresh disagreement
   between the two checkers about the same target — the exact defect being removed.
2. The signature is ``is_placeholder_link(target)``: a question about the string.
   Feeding it the containing directory would push policy back into the call sites,
   which is where the two copies drifted.
3. The rule's own literals come from documentation, not from templates:
   ``目录/文件名`` is the wikilink-syntax example in ``01-Rules/AGENT-CONDUCT.md`` §2.
   (Measured: those occurrences are inside inline code today, so they are stripped
   before either checker sees them — the literal is evidence of intent, not a live
   skip. Prose that quotes link syntax outside backticks is one edit away.)
4. Measured blast radius on the real tree: every link the predicate currently skips
   vault-wide is under ``Templates/`` (7 of them — six ``{{LANG}}``/``{{stack}}``
   links plus ``（已移除的考试模板）.md:24``), so the vault-wide choice is behaviour-
   neutral today and only differs on links that do not yet exist.

The residual false-negative risk is a real note literally named ``RAW-YYYY-MM-DD.md``.
Such a file is itself a naming violation (a literal ``YYYY`` is not a date) and is
caught by ``_check_naming_conventions``; ``test_date_shaped_placeholder_outside_
templates_is_also_skipped`` documents the accepted trade, and its sibling
``test_ordinary_broken_link_outside_templates_still_reported`` keeps the exemption
from widening into "non-template notes are unchecked".

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* §2 Occurrence Precheck: every message/source assertion below was measured with
  ``len(re.findall(pattern, slice))`` and pins **exactly one** match (or exactly zero
  for the deletions), asserted mechanically rather than via ``assertIn``. The
  narrowing is load-bearing, not decorative: ``if is_template`` still occurs **4**
  times file-wide in ``vault-quality-check.py`` (legitimately, in
  ``_check_frontmatter``), so the "amnesty is gone" assertion is only discriminating
  because it is measured against the ``_check_wikilinks`` slice.
* §1 Inversion / mutation — executed against a ``cp`` backup of the implementation
  (never ``git checkout --``); these are the observed results, not predictions:
  - M1 restore the blanket amnesty (``is_template = "Templates/" in ...`` plus
    ``if is_template: continue``) -> **3 failed**:
    ``test_genuinely_broken_link_inside_a_template_is_reported``,
    ``test_placeholder_and_broken_link_in_one_template_report_only_the_broken_one``,
    ``test_quality_check_no_longer_grants_templates_a_blanket_amnesty``.
  - M2 drop the date-shaped branch from ``is_placeholder_link`` -> **5 failed**
    across all three layers (predicate unit, quality-check integration, healthcheck
    integration), and ``python scripts/vault-healthcheck.py`` returns to ``EXIT=1``.
  - M3 make the predicate skip ``normalize_link_target`` and test the raw string ->
    **2 failed**: ``test_raw_and_cleaned_forms_agree`` (subtest ``目录/文件名|别名``)
    and ``test_aliased_literal_placeholder_is_skipped_before_resolution``. The first
    version of this file had only the former; the behavioural sibling was added
    because a single predicate-level guard for the call-site asymmetry is thin
    cover for the failure mode that produced this task.
  - M4 revert ``vault-healthcheck.py`` to its inline literal condition -> **2
    failed** (``test_date_shaped_placeholder_no_longer_fails_the_gate``,
    ``test_healthcheck_delegates_to_the_shared_predicate``) and ``EXIT=1`` again.
"""
import importlib.util
import pathlib
import re
import sys
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from vault_linkrules import is_placeholder_link  # noqa: E402


def _load(filename: str, module_name: str):
    """Import a hyphenated script by path (house style, cf. test_updated_staleness)."""
    spec = importlib.util.spec_from_file_location(module_name, _SCRIPTS_DIR / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_vqc = _load("vault-quality-check.py", "vault_quality_check")
_vhc = _load("vault-healthcheck.py", "vault_healthcheck")
QualityChecker = _vqc.VaultQualityChecker
HealthChecker = _vhc.VaultHealthChecker

# A path that cannot resolve by any route _resolve_wikilink tries (exact path, path
# relative to the source, stem match, physical existence). `2026-01-01` is a *real*
# date, not the `YYYY-MM-DD` placeholder token, so this fixture also proves the
# predicate does not swallow date-prefixed paths wholesale.
_BROKEN = "09-Career/Certifications/考试备考/02-Wrongbook/2026-01-01-nonexistent-entry"
# The production idiom that the healthcheck used to fail on
# (Templates/（已移除的考试模板）.md:24).
_DATE_PLACEHOLDER = "09-Career/Certifications/考试备考/02-Wrongbook/RAW-YYYY-MM-DD#E-001|E-001"


def _note(title: str, body: str) -> str:
    """A note whose only possible defect is the wikilink under test."""
    return (
        "---\n"
        f'title: "{title}"\n'
        "created: 2026-09-01\n"
        "updated: 2026-09-08\n"
        "type: rules\n"
        "tags:\n"
        "  - category/rules\n"
        "status: stable\n"
        "audience: both\n"
        "---\n"
        "\n"
        f"# {title}\n"
        "\n"
        f"{body}\n"
    )


class TestPlaceholderPredicate(unittest.TestCase):
    """Unit contract of the single source of truth."""

    def test_fullwidth_bracket_placeholders_are_placeholders(self):
        """〔…〕（全角括号）是导出模板的自建占位记号，须被两 checker 一致豁免。"""
        self.assertTrue(is_placeholder_link("05-Tools/Subagents/〔子代理派发指南〕"))
        self.assertTrue(is_placeholder_link("01-Rules/〔你的领域通用规范〕"))
        self.assertTrue(is_placeholder_link("01-Rules/〔你的领域通用规范〕.md|别名"))
        self.assertFalse(is_placeholder_link("01-Rules/GIT-CONVENTIONS.md"))

    def test_mustache_placeholders_are_placeholders(self):
        self.assertTrue(is_placeholder_link("{{LANG}}"))
        self.assertTrue(is_placeholder_link("03-Languages/{{LANG}}/{{LANG}}-STANDARDS"))
        self.assertTrue(is_placeholder_link("99-Inbox/{{draft_title}}"))

    def test_angle_bracket_placeholders_are_placeholders(self):
        self.assertTrue(is_placeholder_link("<placeholder>"))
        self.assertTrue(is_placeholder_link("08-Projects/<project>/README"))
        self.assertTrue(is_placeholder_link("<% tp.file.title %>"))

    def test_date_shaped_tokens_are_placeholders(self):
        self.assertTrue(is_placeholder_link("09-Career/02-Wrongbook/RAW-YYYY-MM-DD"))
        self.assertTrue(is_placeholder_link("11-Agents/logs/YYYY-MM"))
        self.assertTrue(is_placeholder_link("99-Inbox/YYYY-MM-DD-topic"))

    def test_literal_placeholders_are_placeholders(self):
        self.assertTrue(is_placeholder_link("..."))
        self.assertTrue(is_placeholder_link(".."))
        self.assertTrue(is_placeholder_link("目录/文件名"))
        self.assertTrue(is_placeholder_link(""))

    def test_real_paths_are_not_placeholders(self):
        """The predicate must stay narrow: concrete dates and normal paths resolve.

        fixture 选用**源库与导出模板都真实存在**的路径（勿用被剔文件名——
        导出改写会把它们变成〔占位符〕，断言随即自相矛盾，2026-09-11 实测）。
        """
        self.assertFalse(is_placeholder_link("01-Rules/GIT-CONVENTIONS"))
        self.assertFalse(is_placeholder_link("01-Rules/DOC-GOVERNANCE"))
        self.assertFalse(is_placeholder_link("99-Inbox/2026-09-08-draft"))
        self.assertFalse(is_placeholder_link(_BROKEN))
        self.assertFalse(is_placeholder_link("03-Languages/Go/GO-STANDARDS#3-并发"))
        self.assertFalse(is_placeholder_link("YYYYMMDD-not-the-idiom"))

    def test_raw_and_cleaned_forms_agree(self):
        """Both call sites must get the same verdict for the same link.

        quality-check passes the raw body (``target#anchor|alias``); healthcheck passes
        ``_clean_link_target(raw)``. The cleaner used here is the *real* one imported
        from vault-healthcheck.py — re-implementing it in the test would be dead-test
        cause #5 (a probe carrying its own copy of the implementation).
        """
        with tempfile.TemporaryDirectory() as tmp:
            clean = HealthChecker(pathlib.Path(tmp))._clean_link_target
            raws = [
                _DATE_PLACEHOLDER,
                "03-Languages/{{LANG}}/{{LANG}}-STANDARDS|规范",
                "08-Projects/<project>/README#Setup",
                "目录/文件名|别名",
                "01-Rules/〔你的领域通用规范〕#2-命名|命名",
                _BROKEN + "#E-001|E-001",
            ]
            for raw in raws:
                with self.subTest(raw=raw):
                    self.assertEqual(
                        is_placeholder_link(raw),
                        is_placeholder_link(clean(raw)),
                        f"raw vs cleaned verdict diverged for {raw!r}",
                    )
            # Not vacuous: the sample really does contain both verdicts.
            verdicts = {is_placeholder_link(clean(r)) for r in raws}
            self.assertEqual(verdicts, {True, False})


class TestQualityCheckTemplateGate(unittest.TestCase):
    """`Templates/` loses its amnesty but keeps its placeholders."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "Templates").mkdir()
        (self.vault / "01-Rules").mkdir()
        (self.vault / "01-Rules" / "REAL-TARGET.md").write_text(
            _note("Real Target", "Body prose with no wikilinks."), encoding="utf-8"
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write(self, rel: str, body: str) -> str:
        path = self.vault / rel
        path.write_text(_note(pathlib.Path(rel).stem, body), encoding="utf-8")
        return rel

    def _run(self):
        checker = QualityChecker(self.vault)
        summary = checker.run_check()
        return checker, summary

    def _wikilink_issues(self, checker, rel):
        return [i for i in checker.results.get(rel, []) if i.category == "WIKILINK"]

    def _all_issues(self, checker, rel):
        return [(i.level, i.category, i.message) for i in checker.results.get(rel, [])]

    # ------------------------------------------------------- placeholders: skipped

    def test_date_shaped_placeholder_in_template_is_skipped(self):
        """Case 1: the production idiom `RAW-YYYY-MM-DD` raises nothing."""
        rel = self._write("Templates/tpl-fixture.md", f"参见 [[{_DATE_PLACEHOLDER}]]。")
        checker, summary = self._run()

        self.assertEqual(
            len(self._wikilink_issues(checker, rel)), 0, self._all_issues(checker, rel)
        )
        self.assertEqual(summary["stats"]["broken_wikilinks"], 0)
        # Mechanism, not luck: it was skipped as a placeholder, never resolved.
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 0)

    def test_mustache_and_angle_placeholders_in_template_are_skipped(self):
        """Case 3: `{{var}}` and `<placeholder>` raise nothing and are not resolved."""
        rel = self._write(
            "Templates/tpl-fixture.md",
            "See [[03-Languages/{{LANG}}/{{LANG}}-STANDARDS]] and [[08-Projects/<project>/README]].",
        )
        checker, summary = self._run()

        self.assertEqual(
            len(self._wikilink_issues(checker, rel)), 0, self._all_issues(checker, rel)
        )
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 0)

    # -------------------------------------------------- anti-regression: no amnesty

    def test_genuinely_broken_link_inside_a_template_is_reported(self):
        """Case 2 — the anti-regression test for the deleted blanket amnesty.

        A template link to a real-shaped path that does not exist MUST be reported:
        the template gets instantiated, so the dangling link is copied into every note
        made from it. Under the old ``if is_template: continue`` this test is red.
        """
        rel = self._write("Templates/tpl-fixture.md", f"参见 [[{_BROKEN}]]。")
        checker, summary = self._run()

        found = self._wikilink_issues(checker, rel)
        # Occurrence precheck (§2): exactly one issue pins this defect.
        self.assertEqual(len(found), 1, self._all_issues(checker, rel))
        self.assertEqual(found[0].level, "WARN")
        self.assertEqual(summary["stats"]["broken_wikilinks"], 1)
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 1)
        # Occurrence precheck (§2): the pattern matches exactly once in the message.
        self.assertEqual(
            len(re.findall(r"Broken wikilink \[\[" + re.escape(_BROKEN) + r"\]\]", found[0].message)),
            1,
            found[0].message,
        )

    def test_placeholder_and_broken_link_in_one_template_report_only_the_broken_one(self):
        """The two rules must not cross-contaminate inside a single file."""
        rel = self._write(
            "Templates/tpl-fixture.md",
            f"占位 [[{_DATE_PLACEHOLDER}]]\n\n真断链 [[{_BROKEN}]]\n",
        )
        checker, summary = self._run()

        found = self._wikilink_issues(checker, rel)
        self.assertEqual(len(found), 1, self._all_issues(checker, rel))
        self.assertEqual(
            len(re.findall(r"RAW-YYYY-MM-DD", found[0].message)), 0, found[0].message
        )
        self.assertEqual(summary["stats"]["broken_wikilinks"], 1)
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 1)

    # ---------------------------------------------------------- valid link: checked

    def test_valid_link_in_template_resolves_and_is_not_skipped(self):
        """Case 4: a real target raises nothing *and* actually went through resolution."""
        rel = self._write("Templates/tpl-fixture.md", "See [[01-Rules/REAL-TARGET]].")
        checker, summary = self._run()

        self.assertEqual(
            len(self._wikilink_issues(checker, rel)), 0, self._all_issues(checker, rel)
        )
        # Non-vacuous: the link was counted as checked, i.e. resolved rather than skipped.
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 1)
        self.assertEqual(summary["stats"]["broken_wikilinks"], 0)

    def test_aliased_literal_placeholder_is_skipped_before_resolution(self):
        """The raw-vs-cleaned boundary, behaviourally.

        quality-check hands the predicate the *raw* link body, so `目录/文件名|别名`
        only matches the literal after normalisation. Without normalisation the link
        falls through to `_resolve_wikilink`, which pardons it via a *third*,
        substring-based copy of the placeholder rule — no issue is raised either way,
        so only the "was it actually resolved" counter can tell the two apart. Added
        after mutation M3 showed the predicate-level test was the sole guard.
        """
        rel = self._write("Templates/tpl-fixture.md", "格式 [[目录/文件名|别名]]。")
        checker, summary = self._run()

        self.assertEqual(
            len(self._wikilink_issues(checker, rel)), 0, self._all_issues(checker, rel)
        )
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 0)

    # ------------------------------------------------- case 5: outside Templates/

    def test_date_shaped_placeholder_outside_templates_is_also_skipped(self):
        """Case 5, chosen behaviour: the predicate is lexical, not location-scoped.

        Full rationale in the module docstring. Short form: healthcheck's placeholder
        rule is already vault-wide, so a ``Templates/``-only rule on this side would
        re-create the divergence; and on the current tree the choice is behaviour-
        neutral (every link the predicate skips vault-wide is under ``Templates/``).
        """
        rel = self._write("01-Rules/RULES-FIXTURE.md", f"命名示例 [[{_DATE_PLACEHOLDER}]]。")
        checker, summary = self._run()

        self.assertEqual(
            len(self._wikilink_issues(checker, rel)), 0, self._all_issues(checker, rel)
        )
        self.assertEqual(summary["stats"]["total_wikilinks_checked"], 0)

    def test_ordinary_broken_link_outside_templates_still_reported(self):
        """The lexical exemption must not widen into "non-template notes are unchecked"."""
        rel = self._write("01-Rules/RULES-FIXTURE.md", f"断链 [[{_BROKEN}]]。")
        checker, summary = self._run()

        self.assertEqual(len(self._wikilink_issues(checker, rel)), 1, self._all_issues(checker, rel))
        self.assertEqual(summary["stats"]["broken_wikilinks"], 1)


class TestHealthcheckWikilinkGate(unittest.TestCase):
    """The second call site: same rule, cleaned-target shape."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.vault = pathlib.Path(self.tmpdir.name)
        (self.vault / "Templates").mkdir()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _check(self, body: str):
        (self.vault / "Templates" / "tpl-fixture.md").write_text(
            _note("Tpl Fixture", body), encoding="utf-8"
        )
        return HealthChecker(self.vault).check_wikilinks()

    def test_date_shaped_placeholder_no_longer_fails_the_gate(self):
        """The headline defect: this link is why vault-healthcheck.py exited 1."""
        result = self._check(f"参见 [[{_DATE_PLACEHOLDER}]]。")

        self.assertEqual(result["broken_count"], 0, result["broken_links"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["total_links"], 0)

    def test_genuinely_broken_link_still_fails_the_gate(self):
        """Loosening the placeholder rule must not blind the healthcheck."""
        result = self._check(f"断链 [[{_BROKEN}]]。")

        self.assertEqual(result["broken_count"], 1, result["broken_links"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["broken_links"][0]["target"], _BROKEN)


class TestRuleIsNotDuplicated(unittest.TestCase):
    """Static contract: one rule, two delegating call sites, zero inline copies."""

    @staticmethod
    def _function_slice(filename: str, func_name: str) -> str:
        src = (_SCRIPTS_DIR / filename).read_text(encoding="utf-8")
        start = src.index(f"    def {func_name}(")
        rest = src[start + 1:]
        nxt = re.search(r"\n    (?:def |@)", rest)
        end = start + 1 + (nxt.start() if nxt else len(rest))
        return src[start:end]

    def test_quality_check_no_longer_grants_templates_a_blanket_amnesty(self):
        body = self._function_slice("vault-quality-check.py", "_check_wikilinks")
        # Slice guardrail (§3.2): a mis-sliced/empty body must fail loudly, not pass.
        self.assertEqual(len(re.findall(r'self\.stats\["broken_wikilinks"\] \+= 1', body)), 1, body)

        self.assertEqual(len(re.findall(r"if is_template", body)), 0, body)
        self.assertEqual(len(re.findall(r"is_placeholder_link\(raw_link\)", body)), 1, body)

    def test_healthcheck_delegates_to_the_shared_predicate(self):
        body = self._function_slice("vault-healthcheck.py", "check_wikilinks")
        # Slice guardrail (§3.2).
        self.assertEqual(len(re.findall(r"broken_links\.append\(", body)), 1, body)

        self.assertEqual(
            len(re.findall(r'target in \("\.\.\.", "\.\.", "目录/文件名", ""\)', body)), 0, body
        )
        self.assertEqual(len(re.findall(r"is_placeholder_link\(target\)", body)), 1, body)


if __name__ == "__main__":
    unittest.main()
