r"""Tests for post-write-sync-agents.sh symlink self-heal (Release Plan Task 5).

Problem
-------
``.claude/hooks/post-write-sync-agents.sh`` requires the 5 multi-agent entry
files (``CLAUDE.md`` / ``GEMINI.md`` / ``.cursorrules`` / ``.windsurfrules`` /
``CONVENTIONS.md``) to be symlinks pointing at ``AGENTS.md``. On Windows the
default clone (``core.symlinks=false``) materializes those symlink blobs as
plain text files whose content is the literal target string ``AGENTS.md``.
The pre-task hook treated that shape as a hard error (exit 1) on every run
and never repaired it — evaluation red card #2: multi-agent mode broken out
of the box on the main platform.

Contract pinned here
--------------------
(a) Self-heal: a tmp git repo with a real ``AGENTS.md`` truth source and the
    5 entries materialized as regular text files (the symlinks=false checkout
    shape) — running the hook MUST exit 0 and leave every entry in a valid
    form: a symlink pointing at AGENTS.md (symlink-capable checkouts) or a
    regular file whose content is identical to AGENTS.md (downgraded
    content-copy form). The copy fallback MUST print the downgrade warning
    ("downgraded to content copy").
(b) Idempotency: a second run on the healed repo exits 0 without churning
    the healed entries (healed bytes stay identical).
(c) Fail-closed guard (red-line, unchanged): when ``AGENTS.md`` itself is
    missing, the hook still exits 1 — self-healing must not paper over a
    missing truth source.

Red-first evidence: against the pre-task hook the self-heal tests fail with
exit 1 ("exists but is a regular file, NOT a symlink!" x5) and the entries
keep the stale "AGENTS.md" text; the guard test passes both before and after
(fail-closed preserved).
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
_VAULT_ROOT = _SCRIPTS_DIR.parent
_HOOK_PATH = _VAULT_ROOT / ".claude" / "hooks" / "post-write-sync-agents.sh"

_ENTRIES = ("CLAUDE.md", "GEMINI.md", ".cursorrules", ".windsurfrules", "CONVENTIONS.md")

# What `git checkout` materializes a symlink blob into when core.symlinks=false:
# a plain text file whose entire content is the stored symlink target string.
_SYMLINK_BLOB_TEXT = "AGENTS.md"

# Small truth-source stub (stays far below the hook's 10KB size limit).
_AGENTS_STUB = (
    "# AGENTS.md - Single Source of Truth (test stub)\n"
    "\n"
    "All agent rules live in this file. Test stub only.\n"
)


def _find_bash():
    """Resolve a real bash executable; never the WSL stub.

    subprocess with the bare name "bash" binds to C:\\Windows\\System32\\bash.exe
    (WSL stub) because CreateProcess searches System32 ahead of PATH; the stub
    rejects C:/ style paths (exit 127). shutil.which() follows PATH only, but
    System32 may also precede the Git dirs in PATH — so the stub is filtered
    out and standard Git-for-Windows install locations are probed as fallback.
    """
    candidates = []
    exe = shutil.which("bash")
    if exe:
        candidates.append(pathlib.Path(exe))
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        if "git" in path_dir.lower():
            probe = pathlib.Path(path_dir) / "bash.exe"
            if probe.is_file():
                candidates.append(probe)
    for base in ("C:/Program Files/Git", "C:/Program Files (x86)/Git"):
        for sub in ("bin", "usr/bin"):
            probe = pathlib.Path(base) / sub / "bash.exe"
            if probe.is_file():
                candidates.append(probe)
    reals, stubs, seen = [], [], set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        (stubs if "system32" in key else reals).append(candidate)
    picks = reals or stubs
    return str(picks[0]) if picks else None


_BASH_EXE = _find_bash()


def _git(repo, *args):
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        timeout=60,
    )


def _make_windows_like_clone(tmp):
    """Simulate a Windows clone with core.symlinks=false.

    The hook is copied into the tmp repo (it derives its vault root from its
    own location), AGENTS.md is the real truth source, and the 5 entries are
    tracked plain text files containing the literal symlink target string.
    """
    repo = pathlib.Path(tmp) / "vault-clone"
    (repo / ".claude" / "hooks").mkdir(parents=True)
    shutil.copy2(_HOOK_PATH, repo / ".claude" / "hooks" / "post-write-sync-agents.sh")
    (repo / "AGENTS.md").write_text(_AGENTS_STUB, encoding="utf-8")
    for name in _ENTRIES:
        (repo / name).write_text(_SYMLINK_BLOB_TEXT, encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", "AGENTS.md", *_ENTRIES)
    return repo


def _run_hook(repo, bash_exe):
    return subprocess.run(
        [bash_exe, (repo / ".claude" / "hooks" / "post-write-sync-agents.sh").as_posix()],
        cwd=str(repo),
        capture_output=True,
        timeout=120,
    )


def _decoded(proc):
    return proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode(
        "utf-8", errors="replace"
    )


def _entry_is_valid(entry, agents_text):
    """Healed-form contract: symlink -> AGENTS.md, or content == AGENTS.md."""
    if entry.is_symlink():
        try:
            target = os.readlink(entry)
        except OSError:
            return False
        return "AGENTS.md" in target
    if entry.is_file():
        return entry.read_text(encoding="utf-8") == agents_text
    return False


class TestHookSelfHealsRegularFileEntries(unittest.TestCase):
    """(a) regular-file entries are repaired, hook exits 0."""

    @classmethod
    def setUpClass(cls):
        if _BASH_EXE is None:
            raise unittest.SkipTest("bash not available")
        if shutil.which("git") is None:
            raise unittest.SkipTest("git not available")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = _make_windows_like_clone(cls._tmp.name)
        cls.agents_text = (cls.repo / "AGENTS.md").read_text(encoding="utf-8")
        # fixture sanity: entries really start as stale text files
        for name in _ENTRIES:
            entry = cls.repo / name
            assert not entry.is_symlink(), f"fixture bug: {name} is a symlink"
            assert entry.read_text(encoding="utf-8") == _SYMLINK_BLOB_TEXT
        cls.proc = _run_hook(cls.repo, _BASH_EXE)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_hook_exits_zero(self):
        self.assertEqual(self.proc.returncode, 0, _decoded(self.proc))

    def test_every_entry_is_symlink_or_content_copy(self):
        for name in _ENTRIES:
            entry = self.repo / name
            self.assertTrue(
                _entry_is_valid(entry, self.agents_text),
                f"{name} not healed: neither symlink->AGENTS.md nor content copy",
            )

    def test_copy_fallback_prints_downgrade_warning(self):
        self.assertIn(
            "downgraded to content copy",
            _decoded(self.proc),
            "copy fallback must print the downgrade warning",
        )


class TestHookHealIsIdempotent(unittest.TestCase):
    """(b) a second run exits 0 and does not churn the healed entries."""

    @classmethod
    def setUpClass(cls):
        if _BASH_EXE is None:
            raise unittest.SkipTest("bash not available")
        if shutil.which("git") is None:
            raise unittest.SkipTest("git not available")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = _make_windows_like_clone(cls._tmp.name)
        first = _run_hook(cls.repo, _BASH_EXE)
        cls.first_rc = first.returncode
        cls.first_log = _decoded(first)
        cls.snapshot = {name: (cls.repo / name).read_bytes() for name in _ENTRIES}
        second = _run_hook(cls.repo, _BASH_EXE)
        cls.second_rc = second.returncode
        cls.second_log = _decoded(second)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_first_run_heals_with_exit_zero(self):
        self.assertEqual(self.first_rc, 0, self.first_log)

    def test_second_run_exits_zero_without_churn(self):
        self.assertEqual(self.second_rc, 0, self.second_log)
        for name, before in self.snapshot.items():
            after = (self.repo / name).read_bytes()
            self.assertEqual(before, after, f"{name} was churned by the second hook run")


class TestHookFailsClosedWithoutAgentsMd(unittest.TestCase):
    """(c) red-line: missing AGENTS.md still exits 1 (no self-heal escape)."""

    @classmethod
    def setUpClass(cls):
        if _BASH_EXE is None:
            raise unittest.SkipTest("bash not available")
        cls._tmp = tempfile.TemporaryDirectory()
        repo = pathlib.Path(cls._tmp.name) / "vault-no-agents"
        (repo / ".claude" / "hooks").mkdir(parents=True)
        shutil.copy2(_HOOK_PATH, repo / ".claude" / "hooks" / "post-write-sync-agents.sh")
        for name in _ENTRIES:
            (repo / name).write_text(_SYMLINK_BLOB_TEXT, encoding="utf-8")
        cls.repo = repo
        cls.proc = _run_hook(repo, _BASH_EXE)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_missing_agents_md_still_exit_1(self):
        self.assertEqual(self.proc.returncode, 1, _decoded(self.proc))


if __name__ == "__main__":
    unittest.main()
