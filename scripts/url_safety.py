#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
URL Credential-Leak Scanner for Coding Vault ({{VAULT_ROOT}})

ROADMAP-P2 Task-3 (#8 url-safety) — pre-commit Gate 1.5 audit sensor. Scans
text for ``http(s)://`` URLs whose query or fragment parameters carry
credentials. Two detection paths, both reported as ``{url, param, reason}``:

1. Credential-like parameter NAME (case-insensitive exact membership):
   {key, token, password, secret, sign, sig, api_key, apikey, access_token,
    client_secret, credential, auth, key_id}
   -> flagged with ``param`` = the name as written (e.g. the query text
   ``key=...`` of a URL). A bare name without ``=`` (``...?token``) is
   flagged the same way — leaking intent counts even with an empty value.
2. High-entropy random-looking VALUE (name-independent backstop, catching
   renamed/opaque parameters). MVP heuristic, deliberately simple:
   - length 16..64 chars inclusive (long enough to be a token, short enough
     to stay out of prose-hash territory beyond it);
   - characters from >=3 of the 4 ASCII classes {a-z, A-Z, 0-9, symbol};
   - Shannon entropy of the char distribution >= 3.0 bits/char, which
     rejects low-diversity repeats (``UserUser...1234``) and padding.
   No dictionary list is shipped: pure-word values are single-class by
   construction and already rejected by the class gate. A hit reports
   ``param`` = the ``"<high-entropy-value>"`` marker unless the NAME also
   matched — the name then wins and ``reason`` carries both parts, with
   "high-entropy" always present on the entropy path.

Known MVP limitations (documented, accepted): percent-encoding is NOT
decoded (``k%65y=`` slips through); URLs are matched per line, so a URL
hard-wrapped across two lines is not detected; ``;``-separated params are
not parsed (only ``&``).

CLI (consumed by ``.githooks/pre-commit`` Gate 1.5):
    url_safety.py check <file...>   scan the given files
    url_safety.py --git-staged      scan the ADDED lines (``+`` minus
                                    ``+++``) of ``git diff --cached`` —
                                    the same staged source Gate 1 scans

Exit codes: 0 = clean (silent), 1 = findings (details on stderr),
2 = operational failure (unreadable file, git error — zero silent swallow).

Hermeticity: strictly read-only (no FS writes; git is invoked only for
``git diff --cached``). Docstrings deliberately avoid complete ``http(s)``
URLs carrying credential params so this file stays clean under its own gate
when staged (pinned by ``scripts/tests/test_url_safety.py`` self-scan).
"""

import sys

# Prevent Windows GBK stdout trap (vault-wide convention)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from urllib.parse import urlparse
import math
import pathlib
import re
import subprocess
from collections import Counter
from typing import Iterator, Optional

# Credential-ish parameter names (case-insensitive exact membership).
CREDENTIAL_PARAM_NAMES: frozenset = frozenset({
    "key", "token", "password", "secret", "sign", "sig", "api_key",
    "apikey", "access_token", "client_secret", "credential", "auth",
    "key_id",
})

# `param` marker when the hit comes from the value-entropy path and the
# parameter name itself is not credential-like.
HIGH_ENTROPY_PARAM: str = "<high-entropy-value>"

# MVP entropy gate (see module docstring path 2 for the spec).
_MIN_VALUE_LEN: int = 16
_MAX_VALUE_LEN: int = 64
_MIN_CHAR_CLASSES: int = 3
_MIN_ENTROPY_BITS: float = 3.0

# URL extraction: stop at whitespace, quotes, markdown/code delimiters and
# brackets so ``[text](url)`` and backtick spans terminate cleanly. URLs are
# matched per line (no cross-newline match — MVP limitation, documented).
_URL_RE: re.Pattern = re.compile(
    r"""https?://[^\s"'`<>{}\\^|()\[\]]+""", re.IGNORECASE
)
_TRAILING_PUNCT: str = ".,;:!?"

# 可信静态资源域：参数值是资源清单（字体族、资源哈希等）而非密钥，
# 高熵启发式对这些域豁免（2026-09-09：vault-workbench.css 的 Google Fonts
# @import 被 >=3bits/char 熵判定误报）。凭证型参数名检查不受影响。
TRUSTED_ENTROPY_HOSTS: frozenset = frozenset(
    {"fonts.googleapis.com", "fonts.gstatic.com"}
)


def _is_high_entropy_value(value: str) -> bool:
    """MVP short-random-token gate — see module docstring path 2."""
    if not (_MIN_VALUE_LEN <= len(value) <= _MAX_VALUE_LEN):
        return False
    has_lower = re.search(r"[a-z]", value) is not None
    has_upper = re.search(r"[A-Z]", value) is not None
    has_digit = re.search(r"[0-9]", value) is not None
    has_symbol = re.search(r"[^A-Za-z0-9]", value) is not None
    if sum([has_lower, has_upper, has_digit, has_symbol]) < _MIN_CHAR_CLASSES:
        return False
    total = float(len(value))
    bits = -sum(
        (count / total) * math.log2(count / total)
        for count in Counter(value).values()
    )
    return bits >= _MIN_ENTROPY_BITS


def _iter_param_sections(url: str) -> Iterator[str]:
    """Yield the query text and the fragment text (either may be absent)."""
    query_start = url.find("?")
    if query_start != -1:
        fragment_start = url.find("#", query_start + 1)
        end = fragment_start if fragment_start != -1 else len(url)
        yield url[query_start + 1:end]
    fragment_start = url.find("#")
    if fragment_start != -1:
        yield url[fragment_start + 1:]


def _inspect_url(url: str) -> Iterator[tuple]:
    """Yield (param, reason) for every suspicious parameter of the URL."""
    # 静态资源 CDN 白名单：其参数值是资源清单（如 font-family 列表）而非密钥，
    # 高熵启发式对其误报。凭证型参数名检查不受白名单影响——纵深不失守。
    host = (urlparse(url).hostname or "").lower()
    trusted = host in TRUSTED_ENTROPY_HOSTS
    for section in _iter_param_sections(url):
        for pair in section.split("&"):
            if not pair:
                continue
            name, _, value = pair.partition("=")
            reasons: list = []
            name_hit = name.lower() in CREDENTIAL_PARAM_NAMES
            if name_hit:
                reasons.append(f"credential-like parameter name '{name}'")
            if not trusted and _is_high_entropy_value(value):
                reasons.append(
                    f"high-entropy random-looking value (len {len(value)}, "
                    f">={_MIN_CHAR_CLASSES} char classes, "
                    f"Shannon >= {_MIN_ENTROPY_BITS:g} bits/char)"
                )
            if not reasons:
                continue
            yield (name if name_hit else HIGH_ENTROPY_PARAM), "; ".join(reasons)


def find_suspicious_urls(text: str) -> list:
    """Scan text for URLs with credential-bearing query/fragment params.

    Returns ``{url, param, reason}`` dicts in textual order, deduplicated on
    the (url, param, reason) triple. See the module docstring for both
    detection paths (credential NAME / high-entropy VALUE).
    """
    findings: list = []
    seen: set = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
        for param, reason in _inspect_url(url):
            key = (url, param, reason)
            if key in seen:
                continue
            seen.add(key)
            findings.append({"url": url, "param": param, "reason": reason})
    return findings


def _staged_added_text() -> Optional[str]:
    """ADDED lines of ``git diff --cached`` — Gate 1's staged-diff source.

    Lines starting with ``+`` (except the ``+++`` file header) are kept;
    context and removed lines are ignored (only what the commit INTRODUCES
    is scanned). Returns None on operational failure AFTER reporting it on
    stderr (zero silent swallow — main() then exits 2, never a clean scan).
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--no-color", "-U0"],
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        print(f"url_safety: git invocation failed: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        print(
            f"url_safety: git diff --cached failed "
            f"(rc={proc.returncode}): {detail}",
            file=sys.stderr,
        )
        return None
    added: list = []
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added.append(line[1:])
    return "\n".join(added)


def _print_findings(findings: list, source: str) -> None:
    """Render finding details to stderr (the hook aborts on any finding)."""
    print(
        f"❌ url_safety: {len(findings)} suspicious URL parameter(s) "
        f"in {source}:",
        file=sys.stderr,
    )
    for idx, finding in enumerate(findings, 1):
        print(f"  [{idx}] url   : {finding['url']}", file=sys.stderr)
        print(f"      param : {finding['param']}", file=sys.stderr)
        print(f"      reason: {finding['reason']}", file=sys.stderr)


def _check_files(paths: list) -> int:
    """`check <file...>` mode: scan files; 1 on findings, 2 on read errors."""
    findings: list = []
    for raw_path in paths:
        try:
            text = pathlib.Path(raw_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError as exc:
            print(f"url_safety: cannot read {raw_path}: {exc}", file=sys.stderr)
            return 2
        findings.extend(find_suspicious_urls(text))
    if findings:
        _print_findings(findings, "the given file(s)")
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="url_safety.py",
        description="URL credential-leak scanner (pre-commit Gate 1.5 sensor)",
    )
    parser.add_argument(
        "--git-staged",
        action="store_true",
        help="scan the ADDED lines of `git diff --cached` (Gate 1's source)",
    )
    subparsers = parser.add_subparsers(dest="mode")
    check_parser = subparsers.add_parser(
        "check", help="scan the given files for credential-bearing URLs"
    )
    check_parser.add_argument("files", nargs="+", help="files to scan")
    return parser


def main(argv: Optional[list] = None) -> int:
    """CLI entry: returns the exit code (0 clean / 1 findings / 2 error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.git_staged:
        staged_text = _staged_added_text()
        if staged_text is None:
            return 2
        findings = find_suspicious_urls(staged_text)
        if findings:
            _print_findings(findings, "staged diff (added lines)")
            return 1
        return 0
    if args.mode == "check":
        return _check_files(list(args.files))
    parser.error("choose one mode: 'check <file...>' or '--git-staged'")


if __name__ == "__main__":
    sys.exit(main())
