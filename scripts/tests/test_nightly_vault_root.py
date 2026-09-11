"""Tests for nightly vault-root parameterization (Release Plan Task 3).

Problem
-------
``nightly-maintenance.py`` hardcoded a machine-bound vault absolute path
(a ``d:``-drive ``Path`` constant), binding the nightly pipeline to one
machine (evaluation red card #3). The portability contract
``vault_paths.resolve_vault_root()`` (CLI > $VAULT_ROOT > scripts/ parent)
already existed but had zero adopters; this task wires it in.

NOTE: this file deliberately contains **no literal copy** of the forbidden
machine path — the forbidden literal is assembled dynamically in
``_FORBIDDEN_LITERAL`` below. A verbatim literal here would (1) leak through
the template export pipeline and (2) get rewritten by the deidentifier,
breaking the assertion (the "token-fixture self-reference" trap).

Contract pinned here
--------------------
(a) Static scan: the module source MUST NOT contain the machine-bound literal
    (case-insensitive, so ``D:\\...`` drive variants fail too).
(b) ``VAULT`` == ``resolve_vault_root()`` under default resolution (no env
    interference), i.e. the module consumes the shared contract instead of
    its own constant. Red-line: the default derivation MUST equal the old
    hardcoded path on the original machine, so this assertion doubles as the
    zero-behavior-change guard.
(c) With ``VAULT_ROOT`` pointing at a tmp directory, reloading the module
    makes ``VAULT`` follow the env (env precedence actually takes effect).

Import safety: loading the module via importlib (hyphenated filename — same
technique as ``test_nightly_steps.py``) must stay side-effect-free apart from
stream reconfiguration and the root resolution itself.

Red-first evidence: against the pre-task module, the static scan fails on the
L46 literal, and the env-override test fails because the hardcoded constant
ignores ``VAULT_ROOT`` entirely.
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import sys
import tempfile
import unittest

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent

# nightly-maintenance.py imports from scripts/ (vault_audit, vault_paths);
# make scripts/ importable regardless of how pytest assembled sys.path.
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import vault_paths  # noqa: E402  (needs the sys.path insert above)

_SOURCE_PATH = _SCRIPTS_DIR / "nightly-maintenance.py"
_SOURCE_TEXT = _SOURCE_PATH.read_text(encoding="utf-8")

# 动态拼装禁用字面量（不得在文件里出现 verbatim 私有路径——防导出泄漏与自指改写）。
_BS = chr(92)  # backslash
_FORBIDDEN_LITERAL = (
    "d:" + _BS + "Obsidian" + _BS + "Coding"
).lower()


def _load_module():
    """Load nightly-maintenance.py via importlib (hyphenated filename)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        spec = importlib.util.spec_from_file_location(
            "nightly_maintenance_vault_root", _SOURCE_PATH
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class TestNightlySourceHasNoHardcodedPath(unittest.TestCase):
    """(a) Static scan: the machine-bound literal is gone from the source."""

    def test_source_has_no_hardcoded_vault_path(self):
        self.assertNotIn(
            _FORBIDDEN_LITERAL,
            _SOURCE_TEXT.lower(),
            "nightly-maintenance.py still hardcodes a machine-bound vault path",
        )


class TestVaultEqualsResolveVaultRoot(unittest.TestCase):
    """(b) VAULT is resolved through the shared portability contract."""

    def setUp(self):
        # Default resolution means NO ambient VAULT_ROOT interference.
        self._saved_env = os.environ.pop("VAULT_ROOT", None)

    def tearDown(self):
        if self._saved_env is not None:
            os.environ["VAULT_ROOT"] = self._saved_env

    def test_vault_equals_resolved_default(self):
        mod = _load_module()
        self.assertEqual(mod.VAULT, vault_paths.resolve_vault_root())


class TestVaultFollowsEnvOverride(unittest.TestCase):
    """(c) VAULT_ROOT env points at a tmp dir -> reloaded VAULT follows it."""

    def test_vault_follows_vault_root_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved_env = os.environ.get("VAULT_ROOT")
            try:
                os.environ["VAULT_ROOT"] = str(pathlib.Path(tmp).resolve())
                mod = _load_module()
                self.assertEqual(mod.VAULT, pathlib.Path(tmp).resolve())
            finally:
                if saved_env is None:
                    os.environ.pop("VAULT_ROOT", None)
                else:
                    os.environ["VAULT_ROOT"] = saved_env


if __name__ == "__main__":
    unittest.main()
