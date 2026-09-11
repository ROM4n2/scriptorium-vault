r"""Tests for bootstrap double-script portability (Release Plan Task 4).

Problem
-------
Both ``bootstrap.ps1`` and ``bootstrap.sh`` hardcode the author's machine
paths (a ``d:``-drive vault absolute path), binding the scaffolding scripts
to one machine (evaluation red card #5). ``bootstrap.sh`` additionally
writes the draft directory as ``08-Inbox`` — a typo; the real draft area is
``99-Inbox`` (the one ``vault-inbox-consolidate`` / ``save_inbox_draft``
consume). ``bootstrap.sh`` is also missing the WORKMEMORY 4-piece scaffold
that ``bootstrap.ps`` section 3.5/3.6 and ``01-Rules/CROSS-AGENT-MEMORY.md``
§4.3 mandate ("新项目 bootstrap MUST 下发 WORKMEMORY 4 件套与项目级 anchor").

NOTE: this file deliberately contains **no verbatim copy** of the forbidden
machine literals — they live only inside the compiled regexes below
(assembled from character classes), so the template export pipeline can never
leak or rewrite them (the "token-fixture self-reference" trap).

Contract pinned here
--------------------
(a) Static scan: NEITHER script source MAY contain the machine-bound
    ``d:``-drive vault/user literals (case-insensitive, any slash/escape
    variant) nor the ``08-Inbox`` typo.
(b) Path derivation: ``bootstrap.ps1`` derives everything from
    ``$PSScriptRoot`` (vault root = scripts/ parent, workmemory templates =
    ``<vault>/Templates/workmemory``); ``bootstrap.sh`` does the same via
    ``BASH_SOURCE``. No drive-letter literal survives in the assignment.
(c) Runtime contract (bash, exercised on a tmp "fresh clone" copy): running
    ``bash <vault-copy>/scripts/bootstrap.sh <new-project>`` scaffolds the
    WORKMEMORY 4-piece set into the new project, interpolates the anchor
    text at runtime so it points at the *user's own* vault copy (not the
    author's machine), creates the vault-side ``99-Inbox/`` draft directory
    (git archive drops empty dirs), and leaves zero residue of the author's
    machine in any generated file. A second run stays idempotent (no
    duplicated anchors). The PowerShell side is exercised the same way when
    a pwsh/powershell runtime is available.

Red-line: the secret-leak protection (.gitignore guards, pre-commit hook
content) and ``core.hooksPath`` configuration logic are NOT touched by this
task and are therefore not asserted here beyond the run succeeding.

Red-first evidence: against the pre-task scripts, the static scan fails on
the ``d:``-drive vault literal (ps1 L182-184/192/209, sh L136-138) and
``08-Inbox`` (sh L138); the derivation tests fail because neither script
carries ``$PSScriptRoot``/``BASH_SOURCE``-based ``WM_SOURCE`` assignments;
the bash runtime test fails because ``bootstrap.sh`` lacks the WORKMEMORY
scaffold and the 99-Inbox creation; the pwsh runtime test fails because the
injected anchor text points at the author's machine path instead of the
runtime-derived vault copy.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
_VAULT_ROOT = _SCRIPTS_DIR.parent

_PS1_PATH = _SCRIPTS_DIR / "bootstrap.ps1"
_SH_PATH = _SCRIPTS_DIR / "bootstrap.sh"

_PS1_TEXT = _PS1_PATH.read_text(encoding="utf-8")
_SH_TEXT = _SH_PATH.read_text(encoding="utf-8")

# Machine-bound / typo literals that MUST NOT appear in either script source
# (case-insensitive; the char class covers every slash/escape variant without
#  writing any verbatim machine path into THIS file).
_FORBIDDEN_PATTERNS = (
    re.compile(r"d:[/\\]+obsidian", re.IGNORECASE),
    re.compile(r"c:[/\\]+users", re.IGNORECASE),
    re.compile(r"08-inbox", re.IGNORECASE),
)

_RESIDUE_PATTERN = re.compile(r"d:[/\\]+obsidian", re.IGNORECASE)

_VM_FILES = ("PROTOCOL.md", "INDEX.md", "PROJECT_OVERVIEW.md", "work.log")


# --------------------------------------------------------------------------- #
# (a) Static scan: machine-bound literals and the 08-Inbox typo are gone.
# --------------------------------------------------------------------------- #
class TestStaticNoMachineBoundLiterals(unittest.TestCase):
    def test_ps1_source_has_no_forbidden_literals(self):
        for pattern in _FORBIDDEN_PATTERNS:
            self.assertIsNone(
                pattern.search(_PS1_TEXT),
                f"bootstrap.ps1 still contains machine-bound literal {pattern.pattern!r}",
            )

    def test_sh_source_has_no_forbidden_literals(self):
        for pattern in _FORBIDDEN_PATTERNS:
            self.assertIsNone(
                pattern.search(_SH_TEXT),
                f"bootstrap.sh still contains machine-bound literal {pattern.pattern!r}",
            )


# --------------------------------------------------------------------------- #
# (b) Script-location derivation: $PSScriptRoot / BASH_SOURCE, no drive letters.
# --------------------------------------------------------------------------- #
class TestScriptLocationDerivation(unittest.TestCase):
    def test_ps1_derives_paths_from_psscriptroot(self):
        self.assertIn("$PSScriptRoot", _PS1_TEXT, "ps1 must derive from $PSScriptRoot")
        self.assertIn("$vaultRoot", _PS1_TEXT, "ps1 must expose a vault-root variable")
        wm_assign = re.search(r"^\$wmSource\s*=.*$", _PS1_TEXT, re.MULTILINE)
        self.assertIsNotNone(wm_assign, "ps1 must keep the $wmSource assignment")
        self.assertIn("workmemory", wm_assign.group(0), "$wmSource must point at Templates/workmemory")
        self.assertIsNone(
            re.search(r"[A-Za-z]:[/\\]", wm_assign.group(0)),
            "$wmSource must be derived from script location, not a drive-letter literal",
        )

    def test_sh_derives_paths_from_bash_source(self):
        self.assertIn("BASH_SOURCE", _SH_TEXT, "sh must derive from BASH_SOURCE")
        self.assertIn("VAULT_ROOT", _SH_TEXT, "sh must expose a vault-root variable")
        wm_assign = re.search(r"^WM_SOURCE=.*$", _SH_TEXT, re.MULTILINE)
        self.assertIsNotNone(wm_assign, "sh must define WM_SOURCE (workmemory scaffold)")
        self.assertIn("workmemory", wm_assign.group(0), "WM_SOURCE must point at Templates/workmemory")
        self.assertIsNone(
            re.search(r"[A-Za-z]:[/\\]", wm_assign.group(0)),
            "WM_SOURCE must be derived from script location, not a drive-letter literal",
        )


# --------------------------------------------------------------------------- #
# Shared fixture: simulate `git archive` unpacked at an arbitrary new path.
# --------------------------------------------------------------------------- #
def _make_tmp_vault_and_project(tmp):
    """Copy scripts/ + Templates/ into a tmp vault clone (no 99-Inbox — empty
    dirs do not survive git archive), plus an empty target project dir."""
    vault_copy = pathlib.Path(tmp) / "vault-copy"
    newproj = pathlib.Path(tmp) / "new-project"
    vault_copy.mkdir(parents=True)
    shutil.copytree(
        _SCRIPTS_DIR,
        vault_copy / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    shutil.copytree(_VAULT_ROOT / "Templates", vault_copy / "Templates")
    newproj.mkdir()
    return vault_copy, newproj


def _bash_posix_path(path):
    """Convert a Windows path to its POSIX form as MSYS bash reports it."""
    cygpath = shutil.which("cygpath")
    if cygpath:
        proc = subprocess.run([cygpath, "-u", str(path)], capture_output=True)
        if proc.returncode == 0:
            return proc.stdout.decode("utf-8", errors="replace").strip()
    return path.as_posix()


# Real Git Bash executable resolved once via PATH. Windows CreateProcess would
# otherwise bind the bare name "bash" to the WSL stub in System32 (its search
# order puts System32 ahead of PATH), which rejects C:/ style paths (exit 127).
_BASH_EXE = shutil.which("bash")


# --------------------------------------------------------------------------- #
# (c) Runtime contract on the bash side (directly exercisable in Git Bash).
# --------------------------------------------------------------------------- #
class TestBashBootstrapRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Windows 坑：subprocess 传裸 "bash" 时 CreateProcess 的搜索顺序固定为
        # System32 先于 PATH，会命中 C:\Windows\System32\bash.exe（WSL stub），
        # 后者无法消费 C:/ 风格路径（报 "No such file or directory"，exit 127）。
        # 必须用 shutil.which 解析出真实 Git Bash 的绝对路径再调用。
        if _BASH_EXE is None:
            raise unittest.SkipTest("bash not available")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.vault_copy, cls.newproj = _make_tmp_vault_and_project(cls._tmp.name)
        proc = subprocess.run(
            [
                _BASH_EXE,
                (cls.vault_copy / "scripts" / "bootstrap.sh").as_posix(),
                cls.newproj.as_posix(),
            ],
            capture_output=True,
            timeout=120,
        )
        cls.returncode = proc.returncode
        cls.stdout = proc.stdout.decode("utf-8", errors="replace")
        cls.vault_posix = _bash_posix_path(cls.vault_copy)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_bootstrap_exits_zero(self):
        self.assertEqual(self.returncode, 0, self.stdout)

    def test_workmemory_four_piece_set_landed(self):
        for name in _VM_FILES:
            path = self.newproj / "WORKMEMORY" / name
            self.assertTrue(path.is_file(), f"missing scaffolded file: {path}")
        body = (self.newproj / "WORKMEMORY" / "work.log").read_text(encoding="utf-8")
        self.assertIn(self.newproj.name, body, "{{PROJECT_NAME}} must be interpolated")
        self.assertNotIn("{{PROJECT_NAME}}", body)
        self.assertNotIn("{{TIMESTAMP}}", body)

    def test_protocol_md_vault_root_interpolated(self):
        text = (self.newproj / "WORKMEMORY" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "{{VAULT_ROOT}}", text, "PROTOCOL.md {{VAULT_ROOT}} placeholder must be interpolated"
        )
        self.assertIn(
            self.vault_posix,
            text,
            "PROTOCOL.md must reference the runtime-interpolated user's own vault",
        )
        self.assertNotIn(
            "{{", text, "PROTOCOL.md template carries no other legal {{ placeholders"
        )

    def test_rule_anchor_points_at_users_own_vault(self):
        text = (self.newproj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("/AGENTS.md", text)
        self.assertIn("/scripts/search-vault.py", text)
        self.assertIn("/99-Inbox/", text, "draft anchor must target 99-Inbox (typo fixed)")
        self.assertIn(
            self.vault_posix, text, "anchor paths must be runtime-interpolated to the user's own vault"
        )
        self.assertNotIn("08-Inbox", text)

    def test_vault_side_99_inbox_created(self):
        self.assertTrue(
            (self.vault_copy / "99-Inbox").is_dir(),
            "bootstrap must create the vault-side 99-Inbox/ (git archive drops empty dirs)",
        )

    def test_no_residue_of_author_machine_in_generated_files(self):
        for path in self.newproj.rglob("*"):
            if path.is_file():
                text = path.read_bytes().decode("utf-8", errors="ignore")
                self.assertIsNone(_RESIDUE_PATTERN.search(text), f"author-machine residue in {path}")

    def test_second_run_is_idempotent_no_duplicate_anchor(self):
        proc = subprocess.run(
            [
                _BASH_EXE,
                (self.vault_copy / "scripts" / "bootstrap.sh").as_posix(),
                self.newproj.as_posix(),
            ],
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout.decode("utf-8", errors="replace"))
        claude_md = (self.newproj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(claude_md.count("工程规范与避坑检索"), 1, "rules anchor must not duplicate")
        self.assertEqual(claude_md.count("共享工作记忆"), 1, "WORKMEMORY anchor must not duplicate")


# --------------------------------------------------------------------------- #
# (c) Runtime contract on the PowerShell side (pwsh preferred; 5.1 fallback).
#     Assertions stick to ASCII because Windows PowerShell 5.1 may mis-decode
#     BOM-less UTF-8 sources (mojibake in Chinese anchor text, no syntax harm).
# --------------------------------------------------------------------------- #
class TestPwshBootstrapRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if exe is None:
            raise unittest.SkipTest("no PowerShell runtime available")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.vault_copy, cls.newproj = _make_tmp_vault_and_project(cls._tmp.name)
        proc = subprocess.run(
            [
                exe,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(cls.vault_copy / "scripts" / "bootstrap.ps1"),
                "-TargetPath",
                str(cls.newproj),
            ],
            capture_output=True,
            timeout=180,
        )
        cls.returncode = proc.returncode
        cls.stdout = proc.stdout.decode("utf-8", errors="replace")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_bootstrap_exits_zero(self):
        self.assertEqual(self.returncode, 0, self.stdout)

    def test_workmemory_four_piece_set_landed(self):
        for name in _VM_FILES:
            path = self.newproj / "WORKMEMORY" / name
            self.assertTrue(path.is_file(), f"missing scaffolded file: {path}")
        body = (self.newproj / "WORKMEMORY" / "work.log").read_text(encoding="utf-8")
        self.assertIn(self.newproj.name, body)
        self.assertNotIn("{{PROJECT_NAME}}", body)
        self.assertNotIn("{{TIMESTAMP}}", body)

    def test_protocol_md_vault_root_interpolated(self):
        text = (self.newproj / "WORKMEMORY" / "PROTOCOL.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "{{VAULT_ROOT}}", text, "PROTOCOL.md {{VAULT_ROOT}} placeholder must be interpolated"
        )
        self.assertIn(
            str(self.vault_copy),
            text,
            "PROTOCOL.md must reference the runtime-interpolated user's own vault",
        )
        self.assertNotIn(
            "{{", text, "PROTOCOL.md template carries no other legal {{ placeholders"
        )

    def test_anchor_paths_derived_not_hardcoded(self):
        text = (self.newproj / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("99-Inbox", text)
        self.assertNotIn("08-Inbox", text)
        self.assertIsNone(_RESIDUE_PATTERN.search(text), "anchor must not reference the author's vault")
        self.assertIn(
            str(self.vault_copy / "AGENTS.md"),
            text,
            "anchor must reference the runtime-derived (user's own) vault copy",
        )


if __name__ == "__main__":
    unittest.main()
