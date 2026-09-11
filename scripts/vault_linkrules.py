#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared wikilink placeholder rule for the vault checkers.

Single source of truth for the question *"is this wikilink target a template
placeholder rather than a path that ought to exist?"*, imported by both
``vault-quality-check.py`` (``_check_wikilinks``) and ``vault-healthcheck.py``
(``check_wikilinks``).

Why a module and not two inline conditions
------------------------------------------
The two checkers previously each carried their own copy of this rule and drifted:

* quality-check dropped *every* unresolvable link under ``Templates/``
  (``if is_template: continue``) — a blanket amnesty that hid genuinely dangling
  links in files whose whole purpose is to be copied into new notes;
* healthcheck recognised only ``{{...}}`` and four literals, so the vault's
  date-shaped placeholder idiom (``RAW-YYYY-MM-DD``, mirroring the
  ``YYYY-MM-DD-`` naming rules) was reported as a hard failure.

``EXCLUDED_DIRS`` diverged between the same two scripts the same way, so the rule
lives here exactly once.

Scope: the predicate is **lexical and location-independent**. It answers a question
about the target string alone, never about the containing directory. Placeholder
syntax is not exclusive to ``Templates/`` — the ``目录/文件名`` literal below comes
from the wikilink-syntax documentation in ``01-Rules/AGENT-CONDUCT.md`` §2, not from
a template — and location-scoping it in one caller would immediately re-create the
divergence it removes, since ``check_wikilinks`` has no notion of templates at all.
"""

import sys

# Prevent Windows GBK stdout/stderr trap (RFC / Vault Standard MUST). This module
# is imported by CLI checkers (vault-quality-check.py, vault-healthcheck.py);
# reconfigure at import time so both streams are protected before any output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import re
from typing import FrozenSet

# `{{date}}`, `{{LANG}}` — Obsidian Templates / Templater mustache syntax.
_MUSTACHE_OPEN: str = "{{"

# `<placeholder>`, `<% tp.file.title %>` — angle-bracket placeholders. `<` and `>`
# are illegal in Windows filenames, so this can never shadow a real path.
_ANGLE_RE: re.Pattern = re.compile(r"<[^<>]*>")

# `RAW-YYYY-MM-DD`, `logs/YYYY-MM` — the vault's date-shaped placeholder idiom, the
# same literal spelling the naming rules use for the `YYYY-MM-DD-` prefix contract.
# Uppercase only and word-bounded on purpose: a lowercase or unbounded match would be
# a guess with no occurrence in the tree, and `2026-09-08-draft` (a *real* date) MUST
# stay checkable.
_DATE_SHAPED_RE: re.Pattern = re.compile(r"\bYYYY-MM(?:-DD)?\b")

# Docs-syntax examples that are targets in form only.
_LITERAL_PLACEHOLDERS: FrozenSet[str] = frozenset({"...", "..", "目录/文件名", ""})


def normalize_link_target(raw: str) -> str:
    """Strip alias/anchor/trailing-separator decoration off a raw wikilink body.

    The two call sites hand in differently-shaped strings: quality-check passes the
    raw body (``path#anchor|alias``), healthcheck passes an already-cleaned target.
    Normalising here makes the predicate total over both shapes, and is idempotent so
    the pre-cleaned caller is unaffected.
    """
    target = raw.strip()
    if "\\|" in target:
        target = target.split("\\|", 1)[0]
    elif "|" in target:
        target = target.split("|", 1)[0]
    if "#" in target:
        target = target.split("#", 1)[0]
    return target.strip().rstrip("\\").rstrip("/")


def is_placeholder_link(target: str) -> bool:
    """True when a wikilink target is a template placeholder, not a real path.

    Accepts either a raw wikilink body or an already-cleaned target; see
    ``normalize_link_target``. Placeholder targets are unresolvable *by design*, so
    callers skip them instead of reporting a broken link.

    ``〔…〕``（全角括号）是导出模板的**自建占位**记号：content_rewrites 把指向
    被剔规范的引用改写成该形态（如 ``05-Tools/Subagents/〔子代理派发指南〕``），
    与 `<…>`/``{{…}}`` 同属"接收者需自行创建"的占位语义（2026-09-11）。
    """
    normalized = normalize_link_target(target)
    if normalized in _LITERAL_PLACEHOLDERS:
        return True
    if _MUSTACHE_OPEN in normalized:
        return True
    if _ANGLE_RE.search(normalized):
        return True
    if "〔" in normalized and "〕" in normalized:
        return True
    return bool(_DATE_SHAPED_RE.search(normalized))
