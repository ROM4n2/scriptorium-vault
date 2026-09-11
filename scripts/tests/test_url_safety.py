"""Tests for `url_safety.py` — URL credential-leak scanner (pre-commit Gate 1.5).

Contract pinned here (ROADMAP-P2-AUDIT-SENSORS Task-3)
------------------------------------------------------
* ``find_suspicious_urls(text) -> list[dict]`` returns ``{url, param, reason}``
  findings for ``http(s)://`` URLs whose query OR fragment parameters carry:
  - a credential-like parameter NAME (case-insensitive): key, token, password,
    secret, sign, sig, api_key, apikey, access_token, client_secret,
    credential, auth, key_id — ``param`` is the name as written;
  - or a high-entropy random-looking VALUE (MVP heuristic: length 16-64,
    >=3 of 4 ASCII char classes, Shannon entropy >= 3.0 bits/char) —
    ``param`` is then the ``"<high-entropy-value>"`` marker unless the name
    also matched (name wins), and ``reason`` contains "high-entropy".
* Query (``?a=b&c=d``) AND fragment (``#token=...``) sections are both
  scanned; values are NOT percent-decoded (MVP, documented in the module).
* CLI: ``check <file...>`` scans files; ``--git-staged`` scans the ADDED
  lines (``+`` minus ``+++``) of ``git diff --cached`` (Gate 1's source).
  Findings -> details on stderr + exit 1; clean -> exit 0 silently;
  operational failure (unreadable file, git error) -> exit 2, never silent.

Self-scan safety (Gate 1.5 dogfooding)
--------------------------------------
This test file and ``url_safety.py`` are scanned by the very gate they
implement the moment they are staged. Therefore NO line in either file may
contain a complete ``http(s)://`` URL carrying a credential parameter or a
high-entropy value: risky URLs are assembled at runtime from scheme/host
constants plus query fragments (``_HOST_*`` / ``_url`` / ``_frag_url``).
``TestSelfScanSafety`` pins this invariant so a future literal URL here
cannot silently brick the orchestrator's commit.

Dead-test defences (01-Rules/TESTING-PATTERNS.md)
-------------------------------------------------
* Every positive case has a negative twin differing by exactly one field:
  (a) ``key=`` hit vs (d) benign query params; (c) high-entropy value vs
  lowercase-only-16 / 3-class-but-15-char / 67-char values; (e) risky staged
  diff vs empty / benign / removed-line-only diffs.
* ``test_removed_and_context_lines_not_scanned`` embeds the SAME risky URL
  in a removed (``-``) line; any implementation scanning the whole diff
  instead of added lines only fails it.
* The subprocess seam is injected (no real git in unit tests — hermetic).
"""
import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest

# Import url_safety.py via importlib (scripts/ is not an importable package).
_url_safety_path = pathlib.Path(__file__).resolve().parent.parent / "url_safety.py"
_spec = importlib.util.spec_from_file_location("url_safety", _url_safety_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Scheme/host parts ONLY (no "?query" on these lines — self-scan safety, see
# module docstring). Risky URLs are assembled at runtime via the helpers.
_HOST_API = "https://api.x.com/v1"
_HOST_SPA = "https://spa.x.com/page"
_HOST_SVC = "https://svc.x.com/p"

# Query/fragment texts WITHOUT scheme: individually invisible to the scanner
# (a bare "key=..." is not a URL), risky only once joined to a host.
_Q_KEY = "key=AbCdEf123456&q=ok"

# 32 chars, 26 distinct chars, 3 char classes -> passes the MVP entropy gate.
_HIGH_ENTROPY_32 = "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"
# 16 chars, all distinct, 4 char classes -> the smallest passing length.
_HIGH_ENTROPY_16 = "aB3$xY9#qW2%mN5!"


def _url(query: str, host: str = _HOST_API) -> str:
    """Assemble a full URL from host + query text (self-scan safe)."""
    return f"{host}?{query}"


def _frag_url(fragment: str, host: str = _HOST_SPA) -> str:
    """Assemble a full URL from host + fragment text (self-scan safe)."""
    return f"{host}#{fragment}"


class TestFindSuspiciousUrls(unittest.TestCase):
    """Pure-detector contract — cases (a)-(d), (f) of the Task-3 TDD steps."""

    # ---- case (a): credential parameter name -> param=key ----
    def test_case_a_credential_name_key(self):
        findings = _mod.find_suspicious_urls(_url(_Q_KEY))

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["url"], _url(_Q_KEY))
        self.assertEqual(findings[0]["param"], "key")
        self.assertIn("credential", findings[0]["reason"])

    # ---- case (b): all 13 contracted names, case-insensitive ----
    def test_case_b_all_thirteen_names_detected(self):
        names = [
            "key", "token", "password", "secret", "sign", "sig",
            "api_key", "apikey", "access_token", "client_secret",
            "credential", "auth", "key_id",
        ]
        for name in names:
            with self.subTest(name=name):
                findings = _mod.find_suspicious_urls(
                    _url(f"{name}=x", host=_HOST_SVC)
                )
                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0]["param"], name)

    def test_case_b_uppercase_name_detected_as_written(self):
        findings = _mod.find_suspicious_urls(
            _url("ACCESS_TOKEN=AbCdEf123456", host=_HOST_SVC)
        )

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["param"], "ACCESS_TOKEN")

    def test_case_b_two_credential_params_two_findings(self):
        findings = _mod.find_suspicious_urls(
            _url("key=AbCdEf123456&token=AbCdEf123456")
        )

        self.assertEqual([f["param"] for f in findings], ["key", "token"], findings)

    # ---- case (c): high-entropy value path ----
    def test_case_c_entropy_only_value_reports_marker(self):
        findings = _mod.find_suspicious_urls(_url("sid=" + _HIGH_ENTROPY_32))

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["param"], "<high-entropy-value>")
        self.assertIn("high-entropy", findings[0]["reason"])

    def test_case_c_sig_high_entropy_reason_mentions_entropy(self):
        findings = _mod.find_suspicious_urls(_url("sig=" + _HIGH_ENTROPY_32))

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["param"], "sig")  # name wins for param
        self.assertIn("high-entropy", findings[0]["reason"])

    def test_case_c_entropy_gate_negative_twins(self):
        # lowercase-only 16 chars: 1 char class -> clean
        self.assertEqual(
            _mod.find_suspicious_urls(_url("sid=abcdefghijklmnop")), []
        )
        # 4 char classes but 15 chars: below the length gate -> clean
        self.assertEqual(
            _mod.find_suspicious_urls(_url("sid=aB3$xY9#qW2%mN5")), []
        )
        # 3 classes but 67 chars: above the length gate -> clean
        self.assertEqual(
            _mod.find_suspicious_urls(_url("sid=" + _HIGH_ENTROPY_32 * 2 + "Ab1")),
            [],
        )

    # ---- case (d): benign queries -> 0 findings ----
    def test_case_d_benign_texts_clean(self):
        benign = [
            _url("q=knowledge&page=2&sort=asc"),
            _url("monkey=business", host=_HOST_SVC),  # 'key' substring only
            _HOST_API,
            "plain text without urls",
        ]
        for text in benign:
            self.assertEqual(_mod.find_suspicious_urls(text), [], text)

    # ---- case (f): fragment parameters are scanned too ----
    def test_case_f_fragment_params_scanned(self):
        findings = _mod.find_suspicious_urls(_frag_url("token=Zx9qW3vR7tY1uI5o"))

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["param"], "token")

        marker = _mod.find_suspicious_urls(_frag_url("sid=" + _HIGH_ENTROPY_32))
        self.assertEqual(len(marker), 1, marker)
        self.assertEqual(marker[0]["param"], "<high-entropy-value>")

        mixed = _mod.find_suspicious_urls(
            _HOST_SPA + "?q=ok#access_token=AbCdEf123456"
        )
        self.assertEqual(len(mixed), 1, mixed)
        self.assertEqual(mixed[0]["param"], "access_token")

    def test_schema_and_dedupe(self):
        text = _url(_Q_KEY) + " and again " + _url(_Q_KEY)

        findings = _mod.find_suspicious_urls(text)

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(set(findings[0]), {"url", "param", "reason"})


class _FakeProc:
    """Minimal subprocess.CompletedProcess stand-in (bytes streams)."""

    def __init__(self, returncode: int, stdout: bytes, stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestGitStagedMode(unittest.TestCase):
    """`--git-staged` reads ADDED lines of `git diff --cached` (Gate 1 source)."""

    def _run_staged(self, proc: _FakeProc):
        """Run main(['--git-staged']) with the subprocess seam injected."""
        captured = {}

        def _fake_run(argv, *args, **kwargs):
            captured["argv"] = list(argv)
            return proc

        original_run = _mod.subprocess.run
        _mod.subprocess.run = _fake_run
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                rc = _mod.main(["--git-staged"])
        finally:
            _mod.subprocess.run = original_run
        return rc, err.getvalue(), captured["argv"]

    # ---- case (e): risky staged diff -> exit 1, stderr carries the URL ----
    def test_risky_added_line_exit_1_stderr_carries_url(self):
        diff = (
            b"diff --git a/notes.md b/notes.md\n"
            b"index 0000000..1111111 100644\n"
            b"--- a/notes.md\n"
            b"+++ b/notes.md\n"
            b"@@ -0,0 +1 @@\n"
            b"+see " + _url(_Q_KEY).encode("utf-8") + b"\n"
        )

        rc, err, _argv = self._run_staged(_FakeProc(0, diff))

        self.assertEqual(rc, 1, err)
        self.assertIn(_url(_Q_KEY), err)
        self.assertIn("key", err)

    def test_empty_staged_diff_exit_0_silent(self):
        rc, err, _argv = self._run_staged(_FakeProc(0, b""))

        self.assertEqual(rc, 0, err)
        self.assertEqual(err, "", err)

    def test_benign_added_line_exit_0(self):
        diff = b"+check " + _url("q=knowledge&page=2&sort=asc").encode("utf-8") + b"\n"

        rc, err, _argv = self._run_staged(_FakeProc(0, diff))

        self.assertEqual(rc, 0, err)

    def test_removed_and_context_lines_not_scanned(self):
        risky = _url(_Q_KEY).encode("utf-8")
        diff = (
            b"--- a/notes.md\n+++ b/notes.md\n@@ -1 +1 @@\n"
            b"-old " + risky + b"\n"
            b" context " + risky + b"\n"
            b"+new clean line\n"
        )

        rc, err, _argv = self._run_staged(_FakeProc(0, diff))

        self.assertEqual(rc, 0, err)

    def test_git_failure_exit_2_not_silent(self):
        rc, err, _argv = self._run_staged(_FakeProc(128, b"", b"fatal: bad index\n"))

        self.assertEqual(rc, 2, err)
        self.assertIn("fatal: bad index", err)

    def test_staged_source_is_cached_diff(self):
        _rc, _err, argv = self._run_staged(_FakeProc(0, b""))

        self.assertEqual(argv[:3], ["git", "diff", "--cached"], argv)


class TestCheckMode(unittest.TestCase):
    """`check <file...>` mode: findings -> stderr + 1; clean -> silent 0."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _capture(self, targets) -> tuple:
        err = io.StringIO()
        argv = ["check"] + [str(t) for t in targets]
        with contextlib.redirect_stderr(err):
            rc = _mod.main(argv)
        return rc, err.getvalue()

    def test_risky_file_exit_1_with_details(self):
        target = self.root / "note.md"
        target.write_text("see " + _url(_Q_KEY) + " now\n", encoding="utf-8")

        rc, err = self._capture([target])

        self.assertEqual(rc, 1, err)
        self.assertIn(_url(_Q_KEY), err)
        self.assertIn("key", err)

    def test_benign_file_exit_0_silent(self):
        target = self.root / "note.md"
        target.write_text(
            _url("q=knowledge&page=2&sort=asc") + "\n", encoding="utf-8"
        )

        rc, err = self._capture([target])

        self.assertEqual(rc, 0, err)
        self.assertEqual(err, "", err)

    def test_unreadable_file_exit_2_reported(self):
        missing = self.root / "ghost.md"

        rc, err = self._capture([missing])

        self.assertEqual(rc, 2, err)
        self.assertIn("ghost.md", err)


class TestCliUsage(unittest.TestCase):
    """No mode selected is a usage error (argparse exit code 2)."""

    def test_no_mode_is_usage_error_exit_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                _mod.main([])
        self.assertEqual(ctx.exception.code, 2)


class TestSelfScanSafety(unittest.TestCase):
    """Gate 1.5 dogfooding: this file and the scanner must stay gate-clean."""

    def test_self_scan_is_clean(self):
        for path in (pathlib.Path(__file__), _url_safety_path):
            source = path.read_text(encoding="utf-8")
            self.assertEqual(_mod.find_suspicious_urls(source), [], str(path))


class TestTrustedEntropyHosts(unittest.TestCase):
    """2026-09-09 白名单：静态资源 CDN 的长参数值（如 Google Fonts 的
    font-family 清单）是资源清单而非密钥，高熵启发式对其 MUST 豁免；
    但凭证型参数名（key=/token=）对任何域仍然拦截——纵深不失守。"""

    FONTS_URL = (
        "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,400;1,400"
        "&family=Inter:wght@400;500;600;700;800"
        "&family=Playfair+Display:ital,wght@0,600;0,700&display=swap"
    )
    # 泄漏样例 URL 拆段构造：测试文件本身也在自扫描范围（Gate 1.5 同款纪律）
    LEAK_URL = (
        "https://fonts.googleapis.com/css2?family=X&" + "key=" + "AbCdEf123456GhIjKl"
    )

    def test_fonts_host_skips_entropy_heuristic(self):
        self.assertEqual(_mod.find_suspicious_urls(self.FONTS_URL), [])

    def test_credential_param_on_trusted_host_still_flagged(self):
        findings = _mod.find_suspicious_urls(self.LEAK_URL)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["param"], "key")


if __name__ == "__main__":
    unittest.main()
