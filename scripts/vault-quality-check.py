#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Quality Checker & Linter for Coding Vault ({{VAULT_ROOT}})

Tasks performed:
  1. Parse YAML Frontmatter & validate required fields:
     - title, created, updated, type, tags, status, audience
  2. Validate allowed enum values:
     - status: draft | stable | archived | active | completed
     - type: standards | cheatsheet | rules | source-notes | daily | project | moc | notes | inbox
     - audience: agent | human | both
     - tags: two-level namespaces (lang/*, category/*, topic/*, source/*, status/*, project/*)
  3. Scan all Wikilinks [[...]] (excluding code fences and inline code) and verify targets exist.
  4. Detect file naming convention anomalies (standards uppercase, inbox/daily date prefixes,
     spaces/special chars, and draft-style dated/full-width-paren filenames leaking into formal dirs).
  5. Detect `updated:` staleness on files the git working tree currently reports as
     dirty (modified/staged): content moved, metadata did not. Deliberately scoped to
     dirty files only — see _get_dirty_files() for why mtime and `git log` are both
     unusable as the authority.
  6. AST Dual-Version Section Alignment (03-Languages/{LANG}/):
     - Extract AST headings (H2 ## and H3 ###).
     - Validate 1:1 section count and numbering alignment between STANDARDS.md and CHEATSHEET.md.
     - Detect modification time drift & unsynchronized updates between STANDARDS and CHEATSHEET.
     - Validate bidirectional references between standards and cheatsheets.
  7. Support CLI options:
     - --strict    : Exit with code 1 if any ERRORs or broken wikilinks are found (Git pre-commit barrier).
     - --json      : Output machine-readable JSON structure.
     - --verbose   : Print itemized and detailed diagnostic output.
     - --vault-path: Specify custom vault root directory.
  8. Windows UTF-8 stdout protection and clean terminal report with ANSI formatting.
"""

import sys

# Prevent Windows GBK stdout/stderr trap (RFC / Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import json
import os
import pathlib
import re
import subprocess
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import yaml
except ImportError:
    yaml = None

# Shared wikilink placeholder rule — single source of truth, also imported by
# vault-healthcheck.py. The explicit sys.path entry is required because this
# hyphenated file is itself loaded by path (importlib) from scripts/tests/, where
# scripts/ is not guaranteed to be on sys.path.
_SCRIPT_DIR: str = str(pathlib.Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from vault_linkrules import is_placeholder_link

# Excluded directories from linting
EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".obsidian",
    ".claudian",
    ".smart-env",
    ".agents",
    ".opencode",
    ".claude",
    ".githooks",
    ".codebuddy",
    "node_modules",
    "scripts",
    "copilot",
    # 随包技能子集：harness 技能 schema（name/description），非 vault 笔记
    # （MUST 与 vault-healthcheck.py 的 EXCLUDED_DIRS 同步）
    "skills",
    ".trash",
    ".pytest_cache",
    "__pycache__",
    "11-Agents/logs",
    "08-Projects/项目档案",
}

# Root-level infrastructure files exempt from strict note frontmatter rules
ROOT_INFRASTRUCTURE_FILES: Set[str] = {
    "AGENTS.md",
    "README.md",
    "项目档案.md",
    "项目档案-V2.md",
    "MULTI-AGENT-LIMITATIONS-AND-RISKS.md",
    "PHASE4-IMPLEMENTATION-PLAN.md",
    "PHASE5-VALIDATION-PLAN.md",
    "PHASE6-AUTOMATION-PLAN.md",
    "PHASE6-FIX-PLAN.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".windsurfrules",
}

REQUIRED_FRONTMATTER_FIELDS: List[str] = [
    "title",
    "created",
    "updated",
    "type",
    "tags",
    "status",
    "audience",
]

VALID_STATUSES: Set[str] = {"draft", "stable", "archived", "active", "completed"}
VALID_TYPES: Set[str] = {
    "standards",
    "cheatsheet",
    "rules",
    "source-notes",
    "daily",
    "project",
    "moc",
    "notes",
    "inbox",
    "draft",
}
VALID_AUDIENCES: Set[str] = {"agent", "human", "both", "architect", "developer"}
VALID_TAG_NAMESPACES: Set[str] = {"lang", "category", "topic", "source", "status", "project"}

# `updated:` may lag the file's own mtime by this many days before it is called a lie.
# 2 days absorbs the ordinary "edited late on the 8th, committed on the 9th" case and
# any timezone skew between the frontmatter date and the filesystem clock.
STALENESS_GRACE_DAYS = 2


def _coerce_frontmatter_date(value: Any) -> Optional[datetime.date]:
    """Frontmatter date value -> date, or None when absent / not a YYYY-MM-DD date.

    None deliberately means "not this check's business": a missing `updated` is the
    required-field check's defect and a malformed one is the date-format check's
    defect (both in _check_frontmatter). Re-reporting either here would double-report
    a single defect on a single line.
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


# ANSI Color codes for clean terminal output
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_RED = "\033[91m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_BLUE = "\033[94m"
ANSI_MAGENTA = "\033[95m"
ANSI_CYAN = "\033[96m"
ANSI_WHITE = "\033[97m"


def supports_color() -> bool:
    """Check if color is supported in stdout."""
    return sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"


def colorize(text: str, color_code: str) -> str:
    """Wrap text in ANSI escape sequence if supported."""
    return f"{color_code}{text}{ANSI_RESET}" if supports_color() else text


class Issue:
    def __init__(self, level: str, category: str, message: str, line: Optional[int] = None):
        self.level = level.upper()  # ERROR, WARN, INFO
        self.category = category    # FRONTMATTER, WIKILINK, NAMING, ALIGNMENT, CONVENTION, FILE
        self.message = message
        self.line = line

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "level": self.level,
            "category": self.category,
            "message": self.message,
        }
        if self.line is not None:
            d["line"] = self.line
        return d


class HeadingInfo:
    def __init__(self, level: int, raw_text: str, line: int):
        self.level = level  # 1, 2, 3...
        self.raw_text = raw_text.strip()
        self.line = line
        self.section_num, self.title = self._parse_number_and_title(self.raw_text)
        self.normalized_title = self._normalize_title(self.title)

    @staticmethod
    def _parse_number_and_title(raw: str) -> Tuple[Optional[str], str]:
        """
        Extract section number and clean title from heading line.
        e.g. '## 1. 适用范围...' -> ('1', '适用范围...')
             '### 1.1 适用范围（MUST）' -> ('1.1', '适用范围（MUST）')
             '## 3. Windows / MSYS2 / Git Bash 跨平台防御' -> ('3', 'Windows / MSYS2 / Git Bash 跨平台防御')
        """
        cleaned = re.sub(r"^#+\s*", "", raw).strip()
        pattern = r"^(?:(?:§|第)?\s*(\d+(?:\.\d+)*|[一二三四五六七八九十]+)(?:章|节)?[\.、\s\-\:]+)?(.*)$"
        m = re.match(pattern, cleaned)
        if m:
            num = m.group(1)
            title = m.group(2).strip()
            return num, title
        return None, cleaned

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for fuzzy topic alignment."""
        t = re.sub(r"[\(（].*?[\)）]", "", title)  # remove (MUST), （Agent 约束版）, etc.
        t = re.sub(r"[`*_\[\]]", "", t)
        t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)  # keep alphanumeric and CJK
        return t.lower()


class DualVersionReport:
    def __init__(self, lang: str, standards_path: pathlib.Path, cheatsheet_path: pathlib.Path):
        self.lang = lang
        self.standards_path = standards_path
        self.cheatsheet_path = cheatsheet_path
        self.standards_h2: List[HeadingInfo] = []
        self.cheatsheet_h2: List[HeadingInfo] = []
        self.standards_h3: List[HeadingInfo] = []
        self.cheatsheet_h3: List[HeadingInfo] = []
        self.section_count_st: int = 0
        self.section_count_cs: int = 0
        self.aligned: bool = False
        self.drift_detected: bool = False
        self.drift_reason: Optional[str] = None
        self.issues: List[Issue] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lang": self.lang,
            "standards_file": self.standards_path.name,
            "cheatsheet_file": self.cheatsheet_path.name,
            "standards_h2_count": self.section_count_st,
            "cheatsheet_h2_count": self.section_count_cs,
            "standards_h3_count": len(self.standards_h3),
            "cheatsheet_h3_count": len(self.cheatsheet_h3),
            "aligned": self.aligned,
            "drift_detected": self.drift_detected,
            "drift_reason": self.drift_reason,
            "issues": [i.to_dict() for i in self.issues],
        }


class VaultQualityChecker:
    def __init__(self, vault_root: pathlib.Path, verbose: bool = False):
        self.vault_root = vault_root.resolve()
        self.verbose = verbose

        self.all_files: Set[pathlib.Path] = set()
        self.all_files_rel: Set[str] = set()
        self.all_stems: Dict[str, List[pathlib.Path]] = {}
        self.all_dirs_rel: Set[str] = set()
        self.md_notes: List[pathlib.Path] = []
        self.file_headings: Dict[str, Set[str]] = {}

        self.results: Dict[str, List[Issue]] = {}
        self.dual_version_reports: List[DualVersionReport] = []
        self.stats: Dict[str, Any] = {
            "total_files_scanned": 0,
            "exempt_files": 0,
            "template_files": 0,
            "files_with_errors": 0,
            "files_with_warnings": 0,
            "total_errors": 0,
            "total_warnings": 0,
            "total_wikilinks_checked": 0,
            "broken_wikilinks": 0,
            "frontmatter_valid": 0,
            "frontmatter_invalid": 0,
            "naming_issues": 0,
            "stale_updated_warnings": 0,
            "dual_version_pairs_checked": 0,
            "alignment_errors": 0,
            "alignment_warnings": 0,
            "drift_warnings": 0,
        }

        self._index_vault()

    def _is_excluded(self, path: pathlib.Path) -> bool:
        try:
            rel = path.relative_to(self.vault_root)
        except ValueError:
            return False
        parts = rel.parts
        for excluded in EXCLUDED_DIRS:
            if excluded in parts:
                return True
            if "/" in excluded:
                norm_rel = str(rel).replace("\\", "/")
                if norm_rel.startswith(excluded):
                    return True
        return False

    def _index_vault(self) -> None:
        """Indexes all files, stems, directories, and headings for link resolution."""
        for root, dirs, files in os.walk(self.vault_root):
            root_path = pathlib.Path(root)
            if self._is_excluded(root_path):
                dirs.clear()
                continue

            try:
                rel_dir = str(root_path.relative_to(self.vault_root)).replace("\\", "/")
                if rel_dir != ".":
                    self.all_dirs_rel.add(rel_dir)
                    self.all_dirs_rel.add(f"{rel_dir}/")
            except ValueError:
                pass

            for f in files:
                file_path = root_path / f
                if self._is_excluded(file_path):
                    continue

                self.all_files.add(file_path)
                try:
                    rel_p = str(file_path.relative_to(self.vault_root)).replace("\\", "/")
                    self.all_files_rel.add(rel_p)
                except ValueError:
                    rel_p = f

                stem = file_path.stem
                if stem not in self.all_stems:
                    self.all_stems[stem] = []
                self.all_stems[stem].append(file_path)

                if file_path.suffix.lower() == ".md":
                    self.md_notes.append(file_path)
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        headings = set()
                        for h_match in re.finditer(r"^#{1,6}\s+(.+)$", content, re.MULTILINE):
                            h_text = h_match.group(1).strip()
                            h_clean = re.sub(r"[#*`_\[\]]", "", h_text).strip()
                            headings.add(h_clean.lower())
                            headings.add(h_text.lower())
                        self.file_headings[rel_p] = headings
                    except Exception:
                        pass

    def _extract_headings(self, content: str) -> List[HeadingInfo]:
        """Parses Markdown AST headings, excluding content inside code fences."""
        headings: List[HeadingInfo] = []
        in_code_block = False
        fence_pattern = re.compile(r"^```|^~~~")
        heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

        for line_num, line in enumerate(content.splitlines(), start=1):
            line_str = line.strip()
            if fence_pattern.match(line_str):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue

            m = heading_pattern.match(line_str)
            if m:
                level = len(m.group(1))
                headings.append(HeadingInfo(level, line_str, line_num))

        return headings

    def _parse_frontmatter(self, content: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Parses YAML frontmatter block."""
        if not content.startswith("---"):
            return None, "File does not start with YAML frontmatter delimiter (---)"

        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            return None, "Unterminated YAML frontmatter delimiter"

        fm_text = content[3:end_idx].strip()
        if not fm_text:
            return {}, None

        # Try PyYAML safe_load first
        if yaml is not None:
            try:
                data = yaml.safe_load(fm_text)
                if isinstance(data, dict):
                    return data, None
                elif data is None:
                    return {}, None
            except Exception:
                pass

        # Regex fallback parser
        data: Dict[str, Any] = {}
        current_key: Optional[str] = None
        for line in fm_text.split("\n"):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if line.startswith("  - ") or line.startswith("- "):
                val = line.split("-", 1)[1].strip().strip("\"'")
                if current_key:
                    if not isinstance(data.get(current_key), list):
                        data[current_key] = []
                    data[current_key].append(val)
            elif ":" in line:
                key, _, val = line.partition(":")
                current_key = key.strip()
                val = val.strip()
                if val.startswith("[") and val.endswith("]"):
                    items = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
                    data[current_key] = items
                elif val:
                    val_clean = val.strip("\"'")
                    data[current_key] = val_clean
                else:
                    data[current_key] = None
        return data, None

    def _check_frontmatter(self, file_path: pathlib.Path, content: str, rel_path: str) -> List[Issue]:
        issues: List[Issue] = []
        # WORKMEMORY 件套是**项目级**记忆文件（会被复制进 {{CODE_ROOT}}\* 的 WORKMEMORY/），
        # vault frontmatter 对其不适用 —— 直接静默，不产生任何告警（2026-09-10：
        # 模板包首推时这 4 个文件产生 4 条 "Template frontmatter note" 噪声）。
        if rel_path.startswith("Templates/workmemory/"):
            return issues  # skills/ 同理由 EXCLUDED_DIRS 覆盖
        is_template = rel_path.startswith("Templates/") or "tpl-" in rel_path

        fm, err = self._parse_frontmatter(content)
        if err or fm is None:
            if is_template:
                issues.append(Issue("WARN", "FRONTMATTER", f"Template frontmatter note: {err}"))
            else:
                issues.append(Issue("ERROR", "FRONTMATTER", f"Missing or malformed frontmatter: {err}"))
            self.stats["frontmatter_invalid"] += 1
            return issues

        # Check required fields
        for req in REQUIRED_FRONTMATTER_FIELDS:
            val = fm.get(req)
            if val is None or (isinstance(val, str) and not val.strip()):
                if is_template and f"{{{{{req}}}}}" in content:
                    continue
                issues.append(Issue("ERROR", "FRONTMATTER", f"Missing required field: '{req}'"))

        # Validate status enum
        status_val = fm.get("status")
        if status_val is not None:
            status_str = str(status_val).lower().strip()
            if status_str not in VALID_STATUSES and not (is_template and "{{" in str(status_val)):
                issues.append(Issue("ERROR", "FRONTMATTER", f"Invalid status '{status_val}'. Allowed: {sorted(VALID_STATUSES)}"))

        # Validate type enum
        type_val = fm.get("type")
        if type_val is not None:
            type_str = str(type_val).lower().strip()
            if type_str not in VALID_TYPES and not (is_template and "{{" in str(type_val)):
                issues.append(Issue("WARN", "FRONTMATTER", f"Unknown type '{type_val}'. Recommended: {sorted(VALID_TYPES)}"))

        # Validate audience enum
        audience_val = fm.get("audience")
        if audience_val is not None:
            # Handle YAML list format (e.g., ['architect', 'agent'])
            if isinstance(audience_val, list):
                audience_values = [str(v).lower().strip() for v in audience_val]
            else:
                audience_values = [str(audience_val).lower().strip()]
            for av in audience_values:
                if av not in VALID_AUDIENCES and not (is_template and "{{" in str(audience_val)):
                    issues.append(Issue("WARN", "FRONTMATTER", f"Unknown audience '{audience_val}'. Allowed: {sorted(VALID_AUDIENCES)}"))

        # Validate tags structure & namespace
        tags = fm.get("tags")
        if tags is not None:
            tag_list: List[str] = []
            if isinstance(tags, list):
                tag_list = [str(t).strip() for t in tags if t]
            elif isinstance(tags, str):
                tag_list = [t.strip() for t in tags.split(",") if t.strip()]

            for t in tag_list:
                if is_template and "{{" in t:
                    continue
                if "/" not in t:
                    issues.append(Issue("WARN", "FRONTMATTER", f"Tag '{t}' does not use 2-level namespace (e.g. lang/{t}, category/{t})"))
                else:
                    ns = t.split("/", 1)[0].lower()
                    if ns not in VALID_TAG_NAMESPACES:
                        issues.append(Issue("WARN", "FRONTMATTER", f"Tag namespace '{ns}' in '{t}' not recognized. Recommended: {sorted(VALID_TAG_NAMESPACES)}"))

        # Validate created / updated date format
        for date_field in ["created", "updated"]:
            val = fm.get(date_field)
            if val is not None:
                if is_template:
                    continue
                if isinstance(val, (datetime.date, datetime.datetime)):
                    pass
                elif isinstance(val, str):
                    val_clean = val.strip()
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val_clean):
                        issues.append(Issue("WARN", "FRONTMATTER", f"Field '{date_field}' value '{val_clean}' does not match YYYY-MM-DD format"))

        if not any(i.level == "ERROR" for i in issues):
            self.stats["frontmatter_valid"] += 1
        else:
            self.stats["frontmatter_invalid"] += 1

        return issues

    def _resolve_wikilink(self, source_path: pathlib.Path, raw_link: str) -> Tuple[bool, str]:
        """Resolves a wikilink target against vault files, directories, canvas, assets, or anchors."""
        link = raw_link.strip()
        # Handle escaped table pipe \| first, then normal pipe |
        if "\\|" in link:
            link = link.split("\\|", 1)[0].strip()
        elif "|" in link:
            link = link.split("|", 1)[0].strip()

        heading_anchor: Optional[str] = None
        if "#" in link:
            link_part, heading_anchor = link.split("#", 1)
            link = link_part.strip()
            heading_anchor = heading_anchor.strip()
            if heading_anchor.startswith("^"):
                heading_anchor = None

        # Pure local anchor [[#heading]]
        if not link and heading_anchor:
            try:
                rel_src = str(source_path.relative_to(self.vault_root)).replace("\\", "/")
                headings = self.file_headings.get(rel_src, set())
                if heading_anchor.lower() in headings or not headings:
                    return True, f"Local anchor #{heading_anchor}"
                else:
                    return True, f"Anchor #{heading_anchor}"
            except ValueError:
                return True, f"Anchor #{heading_anchor}"

        link = link.replace("\\", "/")

        # Directory link [[08-Projects/]] or [[99-Inbox]]
        link_dir = link if link.endswith("/") else f"{link}/"
        if link in self.all_dirs_rel or link_dir in self.all_dirs_rel:
            return True, f"Directory {link}"

        # Try exact relative path from vault root
        candidates_rel = [
            link,
            f"{link}.md",
            f"{link}.canvas",
            f"{link}.png",
            f"{link}.jpg",
            f"{link}.pdf",
            f"{link}.svg",
        ]
        for c in candidates_rel:
            if c in self.all_files_rel:
                return True, c

        # Try relative to current source file directory
        source_dir = source_path.parent
        for c in candidates_rel:
            resolved_c = (source_dir / c).resolve()
            try:
                rel_cand = str(resolved_c.relative_to(self.vault_root)).replace("\\", "/")
                if rel_cand in self.all_files_rel:
                    return True, rel_cand
            except ValueError:
                pass

        # Try stem match across entire vault
        target_stem = pathlib.Path(link).stem
        if target_stem in self.all_stems and self.all_stems[target_stem]:
            match_file = self.all_stems[target_stem][0]
            try:
                return True, str(match_file.relative_to(self.vault_root)).replace("\\", "/")
            except ValueError:
                return True, match_file.name

        # Template placeholders
        if "{{" in raw_link or "<%" in raw_link or "..." in raw_link or "目录/文件名" in raw_link:
            return True, f"Template link {raw_link}"

        # Fallback direct physical filesystem existence check
        for c in candidates_rel:
            if (self.vault_root / c).exists():
                return True, c

        return False, f"Target '{raw_link}' not found in vault"

    def _check_wikilinks(self, file_path: pathlib.Path, content: str) -> List[Issue]:
        """Scans and validates wikilinks outside of code blocks and inline code.

        `Templates/` gets **no** blanket amnesty: a template is copied into every note
        made from it, so a dangling link there propagates instead of staying local.
        Only placeholder-shaped targets are skipped, via the shared
        `vault_linkrules.is_placeholder_link` that vault-healthcheck.py also uses —
        the two checkers previously carried divergent copies of this rule.
        """
        issues: List[Issue] = []

        lines = content.split("\n")
        in_code_block = False
        wikilink_pattern = re.compile(r"\[\[([^\]]+)\]\]")

        for line_num, line in enumerate(lines, start=1):
            line_str = line.strip()
            if line_str.startswith("```") or line_str.startswith("~~~"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                continue

            # Strip inline code (`...`) to prevent bash test syntax [[ -f ... ]] matching
            line_no_inline = re.sub(r"`[^`]*`", "", line)

            for match in wikilink_pattern.finditer(line_no_inline):
                raw_link = match.group(1).strip()
                if not raw_link:
                    continue

                if raw_link.startswith("-f ") or raw_link.startswith("-d ") or raw_link.startswith("$"):
                    continue

                # Placeholders ({{var}}, <var>, RAW-YYYY-MM-DD, "...") are unresolvable
                # by design; skipping them before the counter keeps
                # `total_wikilinks_checked` meaning "links actually resolved".
                if is_placeholder_link(raw_link):
                    continue

                self.stats["total_wikilinks_checked"] += 1
                exists, desc = self._resolve_wikilink(file_path, raw_link)
                if not exists:
                    self.stats["broken_wikilinks"] += 1
                    issues.append(Issue("WARN", "WIKILINK", f"Broken wikilink [[{raw_link}]]: {desc}", line=line_num))

        return issues

    def _check_binary_bytes(self, raw: bytes) -> List[Issue]:
        """
        Guards against literal NUL (0x00) bytes inside a Markdown note.

        A single 0x00 makes `file` classify the note as `data` and makes grep/ripgrep
        skip it as binary, so search-vault.py (BM25 index), vault-dedup.py and
        vault-auto-linker.py all silently drop the note: the gate stays green while
        the knowledge asset becomes unreachable.

        MUST be applied to the raw bytes *before* any decode. `bytes.decode(...,
        errors='ignore'/'replace')` — or a future codec swap — can drop or transform
        0x00, so a post-decode check would silently never fire (dead check).
        """
        nul_count = raw.count(b"\x00")
        if nul_count == 0:
            return []

        first_line = raw[: raw.index(b"\x00")].count(b"\n") + 1
        return [
            Issue(
                "ERROR",
                "ENCODING",
                f"Contains {nul_count} literal NUL (0x00) byte(s): grep/ripgrep treat the note "
                f"as binary, so the BM25 index, dedup and auto-linker silently skip it. "
                f"Replace each with the two-character escape \\0.",
                line=first_line,
            )
        ]

    @staticmethod
    def _parse_porcelain_z(raw: str) -> Set[str]:
        """Parse `git status --porcelain=v1 -z` output into vault-relative POSIX paths.

        `-z` (not plain `--porcelain=v1`) is mandatory here: without it git applies
        core.quotePath C-style escaping to any non-ASCII path, so every CJK-named note
        would arrive as `"\\345\\244\\207..."` and never match a scanned rel_path — a
        check that silently never fires on part of the vault.

        Untracked (`??`) and ignored (`!!`) entries are dropped: a note that was never
        committed has no `updated:` history to be stale against. Rename/copy records
        carry a second NUL-terminated path field; both fields are emitted, because
        every path named by an `R`/`C` record is genuinely part of that change.
        """
        dirty: Set[str] = set()
        fields = [f for f in raw.split("\0") if f]
        idx = 0
        while idx < len(fields):
            entry = fields[idx]
            idx += 1
            if len(entry) < 4 or entry[2] != " ":
                continue
            xy, path = entry[:2], entry[3:]
            if xy[0] in ("R", "C") and idx < len(fields):
                dirty.add(fields[idx].replace("\\", "/"))
                idx += 1
            if xy in ("??", "!!"):
                continue
            dirty.add(path.replace("\\", "/"))
        return dirty

    def _get_dirty_files(self) -> Set[str]:
        """Vault-relative paths of the files the git working tree reports as dirty.

        This is the *seam* of the `updated:` staleness check, and the reason it is the
        working tree rather than the two obvious alternatives:

        * **Filesystem mtime as the authority**: a fresh `git clone` stamps every file
          with the clone time, so an mtime-vs-`updated` rule fires on all ~171 notes at
          once. Mass false positives destroy the signal.
        * **`git log -1 -- <file>` as the authority**: CI checks out with
          `actions/checkout` at the default `fetch-depth: 1`, so the single fetched
          commit is reported as the last commit touching *every* file — same mass
          false positive, only in CI where nobody can see it coming.

        The dirty set is empty on any clean checkout, so a fresh clone and a shallow CI
        checkout are silent *by construction*. The set is non-empty exactly when the
        author has edited notes and not committed them yet, which is precisely the
        pre-commit case worth catching.

        Returns an empty set when the vault root is not itself a git repository root
        (unit-test vaults, exported copies, zip downloads). Any other git failure is
        raised: "clean tree" and "git is broken" MUST NOT be indistinguishable to the
        caller, because the second one silently disables the check.
        """
        if not (self.vault_root / ".git").exists():
            return set()

        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain=v1", "-z"],
                cwd=str(self.vault_root),
                capture_output=True,
                timeout=60,
            )
        except OSError as e:
            raise RuntimeError(f"Cannot run `git status` in {self.vault_root}: {e}") from e

        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"`git status` exited {proc.returncode} in {self.vault_root}: {stderr}"
            )

        return self._parse_porcelain_z(proc.stdout.decode("utf-8", errors="replace"))

    def _check_updated_staleness(
        self,
        file_path: pathlib.Path,
        content: str,
        rel_path: str,
        dirty_files: Set[str],
    ) -> List[Issue]:
        """WARN when a note git reports as dirty carries an `updated:` older than itself.

        The existing frontmatter checks only prove `updated` is a well-formed date, not
        that it is true. A note can be rewritten while `updated:` still claims a date
        from months ago, and every consumer that ranks or triages by recency then works
        off a lie. Scope is the dirty set only (see _get_dirty_files).
        """
        if rel_path not in dirty_files:
            return []

        fm, err = self._parse_frontmatter(content)
        if err or not fm:
            return []

        updated = _coerce_frontmatter_date(fm.get("updated"))
        if updated is None:
            return []

        try:
            mtime_date = datetime.date.fromtimestamp(file_path.stat().st_mtime)
        except OSError as e:
            return [Issue("ERROR", "FILE", f"Cannot stat file for freshness check: {e}")]

        lag_days = (mtime_date - updated).days
        if lag_days <= STALENESS_GRACE_DAYS:
            return []

        self.stats["stale_updated_warnings"] += 1
        return [
            Issue(
                "WARN",
                "FRESHNESS",
                f"'updated' is {lag_days} days behind this note's own content: the working "
                f"tree has uncommitted changes to it and it was last modified "
                f"{mtime_date.isoformat()}, but frontmatter still says "
                f"updated: {updated.isoformat()}. Bump it before committing.",
            )
        ]

    def _check_naming_conventions(self, file_path: pathlib.Path, rel_path: str) -> List[Issue]:
        issues: List[Issue] = []
        filename = file_path.name
        stem = file_path.stem

        illegal_chars = set('<>:"|?*')
        for ch in filename:
            if ch in illegal_chars:
                issues.append(Issue("ERROR", "NAMING", f"Filename contains illegal Windows character '{ch}': {filename}"))
                self.stats["naming_issues"] += 1

        if " " in filename and not rel_path.startswith("10-Daily/") and not rel_path.startswith("Templates/"):
            issues.append(Issue("WARN", "NAMING", f"Filename contains spaces (prefer kebab-case or uppercase): '{filename}'"))
            self.stats["naming_issues"] += 1

        if rel_path.startswith("03-Languages/"):
            parts = rel_path.split("/")
            if len(parts) >= 3:
                lang = parts[1]
                if "-standards" in stem.lower():
                    expected = f"{lang.upper()}-STANDARDS.md"
                    if filename != expected and filename != f"{lang}-STANDARDS.md":
                        issues.append(Issue("WARN", "NAMING", f"Language standards note should follow naming '{expected}', got '{filename}'"))
                        self.stats["naming_issues"] += 1
                elif "-cheatsheet" in stem.lower():
                    expected = f"{lang.upper()}-CHEATSHEET.md"
                    if filename != expected and filename != f"{lang}-CHEATSHEET.md":
                        issues.append(Issue("WARN", "NAMING", f"Language cheatsheet note should follow naming '{expected}', got '{filename}'"))
                        self.stats["naming_issues"] += 1

        # 目录级 README.md 是**结构性说明文件**，不是 Inbox 草稿/每日日志
        # （2026-09-10：模板包引导 README 曾被判命名违规）。
        if rel_path.startswith("99-Inbox/"):
            if filename != "README.md" and not re.match(r"^\d{4}-\d{2}-\d{2}-", filename):
                issues.append(Issue("WARN", "NAMING", f"Inbox draft should start with date prefix 'YYYY-MM-DD-': '{filename}'"))
                self.stats["naming_issues"] += 1

        if rel_path.startswith("10-Daily/"):
            if filename != "README.md" and not re.match(r"^\d{4}-\d{2}-\d{2}", filename):
                issues.append(Issue("WARN", "NAMING", f"Daily note should match 'YYYY-MM-DD*.md': '{filename}'"))
                self.stats["naming_issues"] += 1

        # Draft-state filename leak into formal directories (INGESTION-WORKFLOW §2.2).
        # Dated / Chinese-parenthesized names are legal only under 99-Inbox/ (YYYY-MM-DD- prefix),
        # 10-Daily/, Templates/, and 11-Agents/; promotion MUST rename to kebab/uppercase KEBAB
        # ({RULE}.md) via git mv. Raised as ERROR so the pre-commit --strict barrier blocks a
        # promote-by-move that leaves the inbox-style filename in a formal directory.
        if not (
            rel_path.startswith("99-Inbox/")
            or rel_path.startswith("10-Daily/")
            or rel_path.startswith("Templates/")
            or rel_path.startswith("11-Agents/")
        ):
            if re.match(r"^\d{4}-\d{2}-\d{2}", filename):
                issues.append(Issue(
                    "ERROR", "NAMING",
                    f"Draft-style dated filename is only legal in 99-Inbox//10-Daily/; formal note "
                    f"MUST be renamed to kebab/uppercase KEBAB (INGESTION-WORKFLOW §2.2): '{filename}'"
                ))
                self.stats["naming_issues"] += 1
            if "（" in filename or "）" in filename:
                issues.append(Issue(
                    "ERROR", "NAMING",
                    f"Full-width parentheses are an inbox-draft filename artifact; formal note MUST be "
                    f"renamed to kebab/uppercase KEBAB (INGESTION-WORKFLOW §2.2): '{filename}'"
                ))
                self.stats["naming_issues"] += 1

        return issues

    def _check_dual_version_alignment(self) -> None:
        """
        Validates 1:1 section alignment and drift detection for dual-version language notes in 03-Languages/.
        Per AGENTS.md §5:
          - Standards: Source of Truth (RFC 2119).
          - Cheatsheet: Single-direction derivation from Standards.
          - Section numbering and count MUST be strictly 1:1 aligned.
          - Check modification time drift between STANDARDS and CHEATSHEET.
        """
        lang_root = self.vault_root / "03-Languages"
        if not lang_root.exists() or not lang_root.is_dir():
            return

        for lang_dir in sorted(lang_root.iterdir()):
            if not lang_dir.is_dir() or lang_dir.name.startswith("."):
                continue

            lang_name = lang_dir.name
            st_files = [f for f in lang_dir.glob("*.md") if "-standards" in f.name.lower()]
            cs_files = [f for f in lang_dir.glob("*.md") if "-cheatsheet" in f.name.lower()]

            if not st_files and not cs_files:
                continue

            if st_files and not cs_files:
                rel_st = str(st_files[0].relative_to(self.vault_root)).replace("\\", "/")
                iss = Issue("WARN", "ALIGNMENT", f"Language standards '{st_files[0].name}' exists without paired CHEATSHEET.md in {lang_name}")
                self.results.setdefault(rel_st, []).append(iss)
                self.stats["total_warnings"] += 1
                self.stats["alignment_warnings"] += 1
                continue

            if cs_files and not st_files:
                rel_cs = str(cs_files[0].relative_to(self.vault_root)).replace("\\", "/")
                iss = Issue("WARN", "ALIGNMENT", f"Language cheatsheet '{cs_files[0].name}' exists without paired STANDARDS.md in {lang_name}")
                self.results.setdefault(rel_cs, []).append(iss)
                self.stats["total_warnings"] += 1
                self.stats["alignment_warnings"] += 1
                continue

            st_path = st_files[0]
            cs_path = cs_files[0]
            rel_st = str(st_path.relative_to(self.vault_root)).replace("\\", "/")
            rel_cs = str(cs_path.relative_to(self.vault_root)).replace("\\", "/")

            report = DualVersionReport(lang_name, st_path, cs_path)
            self.stats["dual_version_pairs_checked"] += 1

            try:
                st_content = st_path.read_text(encoding="utf-8", errors="ignore")
                cs_content = cs_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                iss = Issue("ERROR", "FILE", f"Cannot read dual-version note files in {lang_name}: {e}")
                self.results.setdefault(rel_st, []).append(iss)
                self.stats["total_errors"] += 1
                self.stats["alignment_errors"] += 1
                continue

            st_headings = self._extract_headings(st_content)
            cs_headings = self._extract_headings(cs_content)

            st_h2 = [h for h in st_headings if h.level == 2]
            cs_h2 = [h for h in cs_headings if h.level == 2]
            st_h3 = [h for h in st_headings if h.level == 3]
            cs_h3 = [h for h in cs_headings if h.level == 3]

            report.standards_h2 = st_h2
            report.cheatsheet_h2 = cs_h2
            report.standards_h3 = st_h3
            report.cheatsheet_h3 = cs_h3
            report.section_count_st = len(st_h2)
            report.section_count_cs = len(cs_h2)

            # 1. Validate Section Count (H2)
            alignment_errors_count = 0
            if len(st_h2) != len(cs_h2):
                msg = (
                    f"Dual-version section count mismatch in {lang_name}: "
                    f"STANDARDS has {len(st_h2)} H2 sections, but CHEATSHEET has {len(cs_h2)} H2 sections"
                )
                iss = Issue("ERROR", "ALIGNMENT", msg)
                report.issues.append(iss)
                self.results.setdefault(rel_cs, []).append(iss)
                alignment_errors_count += 1

            # 2. Validate Section Numbering Alignment
            max_len = max(len(st_h2), len(cs_h2))
            for idx in range(max_len):
                s_item = st_h2[idx] if idx < len(st_h2) else None
                c_item = cs_h2[idx] if idx < len(cs_h2) else None

                if s_item and c_item:
                    if s_item.section_num != c_item.section_num:
                        msg = (
                            f"Section number mismatch in {lang_name} at index {idx+1}: "
                            f"STANDARDS has section '{s_item.section_num}' ('{s_item.title}'), "
                            f"but CHEATSHEET has section '{c_item.section_num}' ('{c_item.title}')"
                        )
                        iss = Issue("ERROR", "ALIGNMENT", msg, line=c_item.line)
                        report.issues.append(iss)
                        self.results.setdefault(rel_cs, []).append(iss)
                        alignment_errors_count += 1

            # 3. Check Modification Time Drift
            # If STANDARDS st_mtime is significantly newer than CHEATSHEET (e.g. > 300s) and contains newer sections/updates
            st_stat = st_path.stat()
            cs_stat = cs_path.stat()
            st_mtime = st_stat.st_mtime
            cs_mtime = cs_stat.st_mtime
            time_diff = st_mtime - cs_mtime

            # Parse updated frontmatter dates if available
            st_fm, _ = self._parse_frontmatter(st_content)
            cs_fm, _ = self._parse_frontmatter(cs_content)
            st_updated = str((st_fm or {}).get("updated", ""))
            cs_updated = str((cs_fm or {}).get("updated", ""))

            # Drift triggers if STANDARDS is modified > 5 mins after CHEATSHEET or frontmatter date is newer, with unaligned/diverged content
            if (time_diff > 300 or (st_updated and cs_updated and st_updated > cs_updated)) and (len(st_h2) != len(cs_h2) or alignment_errors_count > 0):
                report.drift_detected = True
                report.drift_reason = f"Standards updated without synchronized Cheatsheet (STANDARDS: {datetime.datetime.fromtimestamp(st_mtime).strftime('%Y-%m-%d %H:%M')}, CHEATSHEET: {datetime.datetime.fromtimestamp(cs_mtime).strftime('%Y-%m-%d %H:%M')})"
                iss = Issue("WARN", "ALIGNMENT", f"[DRIFT] {report.drift_reason}")
                report.issues.append(iss)
                self.results.setdefault(rel_cs, []).append(iss)
                self.stats["total_warnings"] += 1
                self.stats["drift_warnings"] += 1

            # 4. Check Bidirectional References
            st_refs_cs = cs_path.stem in st_content or cs_path.name in st_content
            cs_refs_st = st_path.stem in cs_content or st_path.name in cs_content

            if not cs_refs_st:
                iss = Issue("WARN", "ALIGNMENT", f"Cheatsheet '{cs_path.name}' does not reference source standards note '{st_path.stem}'")
                report.issues.append(iss)
                self.results.setdefault(rel_cs, []).append(iss)
                self.stats["total_warnings"] += 1
                self.stats["alignment_warnings"] += 1

            if not st_refs_cs:
                iss = Issue("WARN", "ALIGNMENT", f"Standards note '{st_path.name}' does not link to paired cheatsheet '{cs_path.stem}'")
                report.issues.append(iss)
                self.results.setdefault(rel_st, []).append(iss)
                self.stats["total_warnings"] += 1
                self.stats["alignment_warnings"] += 1

            report.aligned = (alignment_errors_count == 0)
            if alignment_errors_count > 0:
                self.stats["alignment_errors"] += alignment_errors_count
                self.stats["total_errors"] += alignment_errors_count

            self.dual_version_reports.append(report)

    def run_check(self) -> Dict[str, Any]:
        """Runs quality checks across all notes in vault."""
        dirty_files = self._get_dirty_files()

        for file_path in self.md_notes:
            try:
                rel_path = str(file_path.relative_to(self.vault_root)).replace("\\", "/")
            except ValueError:
                rel_path = file_path.name

            if rel_path in ROOT_INFRASTRUCTURE_FILES or ("/" not in rel_path and ("PLAN" in rel_path.upper() or rel_path.startswith("PHASE"))):
                self.stats["exempt_files"] += 1
                continue

            if rel_path.startswith("Templates/"):
                self.stats["template_files"] += 1

            self.stats["total_files_scanned"] += 1

            try:
                raw_bytes = file_path.read_bytes()
            except OSError as e:
                self.results[rel_path] = [Issue("ERROR", "FILE", f"Cannot read file: {e}")]
                self.stats["total_errors"] += 1
                self.stats["files_with_errors"] += 1
                continue

            # Decode manually (not read_text) so the raw bytes stay available for the
            # binary-byte guard below; .replace() reproduces read_text()'s universal
            # newline translation so downstream line-based checks are unchanged.
            content = raw_bytes.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")

            file_issues: List[Issue] = []

            # 0. Binary/NUL byte guard (raw bytes, pre-decode)
            file_issues.extend(self._check_binary_bytes(raw_bytes))

            # 1. Frontmatter check
            file_issues.extend(self._check_frontmatter(file_path, content, rel_path))

            # 2. Wikilink check
            file_issues.extend(self._check_wikilinks(file_path, content))

            # 3. Naming convention check
            file_issues.extend(self._check_naming_conventions(file_path, rel_path))

            # 4. `updated:` staleness (only for files dirty in the git working tree)
            file_issues.extend(
                self._check_updated_staleness(file_path, content, rel_path, dirty_files)
            )

            if file_issues:
                self.results.setdefault(rel_path, []).extend(file_issues)
                err_cnt = sum(1 for i in file_issues if i.level == "ERROR")
                warn_cnt = sum(1 for i in file_issues if i.level == "WARN")
                if err_cnt > 0:
                    self.stats["files_with_errors"] += 1
                    self.stats["total_errors"] += err_cnt
                if warn_cnt > 0:
                    self.stats["files_with_warnings"] += 1
                    self.stats["total_warnings"] += warn_cnt

        # 5. AST Dual-Version Section Alignment & Drift Check (03-Languages/)
        self._check_dual_version_alignment()

        return self.get_summary()

    def get_summary(self) -> Dict[str, Any]:
        scanned = self.stats["total_files_scanned"]
        errs = self.stats["total_errors"]
        warns = self.stats["total_warnings"]

        if scanned > 0:
            score = max(0.0, 100.0 - (errs * 5.0 + warns * 1.0) / max(1, scanned) * 10.0)
        else:
            score = 100.0

        return {
            "vault_root": str(self.vault_root).replace("\\", "/"),
            "timestamp": datetime.datetime.now().isoformat(),
            "quality_score": round(score, 1),
            "stats": self.stats,
            "dual_version_reports": [r.to_dict() for r in self.dual_version_reports],
            "issues_by_file": {
                f: [iss.to_dict() for iss in iss_list]
                for f, iss_list in self.results.items()
            },
        }

    def print_terminal_report(self) -> None:
        """Prints a clean, formatted terminal summary report."""
        summary = self.get_summary()
        stats = summary["stats"]
        score = summary["quality_score"]

        print(colorize("\n" + "=" * 76, ANSI_CYAN))
        print(colorize(" 🔍 VAULT QUALITY CHECK & AST ALIGNMENT GATEKEEPER REPORT", ANSI_BOLD + ANSI_CYAN))
        print(colorize("=" * 76, ANSI_CYAN))
        print(f" 📂 Vault Root: {colorize(summary['vault_root'], ANSI_WHITE)}")
        print(f" ⏰ Timestamp : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f" 📊 Score     : {colorize(f'{score}/100', ANSI_GREEN if score >= 90 else (ANSI_YELLOW if score >= 75 else ANSI_RED))}")
        print("-" * 76)

        print(colorize(" [1] 扫描概览 (Scan Overview)", ANSI_BOLD))
        print(f"   • 扫描笔记总数   : {stats['total_files_scanned']} 篇 ({stats['exempt_files']} 篇根规范豁免, {stats['template_files']} 篇模板)")
        print(f"   • 存在错误文件数 : {colorize(str(stats['files_with_errors']), ANSI_RED if stats['files_with_errors'] > 0 else ANSI_GREEN)}")
        print(f"   • 存在警告文件数 : {colorize(str(stats['files_with_warnings']), ANSI_YELLOW if stats['files_with_warnings'] > 0 else ANSI_GREEN)}")
        print(f"   • 总错误数 (ERR) : {colorize(str(stats['total_errors']), ANSI_RED if stats['total_errors'] > 0 else ANSI_GREEN)}")
        print(f"   • 总警告数 (WARN): {colorize(str(stats['total_warnings']), ANSI_YELLOW if stats['total_warnings'] > 0 else ANSI_GREEN)}")

        print(colorize("\n [2] 元数据与链接检查 (Metadata & Links)", ANSI_BOLD))
        print(f"   • Frontmatter 合格: {colorize(str(stats['frontmatter_valid']), ANSI_GREEN)} 篇")
        print(f"   • Frontmatter 异常: {colorize(str(stats['frontmatter_invalid']), ANSI_RED if stats['frontmatter_invalid'] > 0 else ANSI_GREEN)} 篇")
        print(f"   • Wikilinks 总检查: {stats['total_wikilinks_checked']} 条")
        print(f"   • 断链/失效 Wikilink: {colorize(str(stats['broken_wikilinks']), ANSI_YELLOW if stats['broken_wikilinks'] > 0 else ANSI_GREEN)} 条")
        print(f"   • 命名规范告警    : {colorize(str(stats['naming_issues']), ANSI_YELLOW if stats['naming_issues'] > 0 else ANSI_GREEN)} 项")
        print(f"   • updated 未同步告警: {colorize(str(stats['stale_updated_warnings']), ANSI_YELLOW if stats['stale_updated_warnings'] > 0 else ANSI_GREEN)} 项 (仅检查 git 工作区脏文件)")

        print(colorize("\n [3] 语言双版本规范 AST 对齐与漂移守卫 (Dual-Version Alignment)", ANSI_BOLD))
        print(f"   • 校验语言双版本对: {stats['dual_version_pairs_checked']} 对")
        print(f"   • 章节对齐异常    : {colorize(str(stats['alignment_errors']), ANSI_RED if stats['alignment_errors'] > 0 else ANSI_GREEN)} 项")
        print(f"   • 规范/速查漂移告警: {colorize(str(stats['drift_warnings']), ANSI_YELLOW if stats['drift_warnings'] > 0 else ANSI_GREEN)} 项")

        if self.dual_version_reports:
            for rep in self.dual_version_reports:
                align_badge = colorize("✅ 1:1 对齐", ANSI_GREEN) if rep.aligned else colorize("❌ 对齐异常", ANSI_RED)
                drift_badge = colorize("🟢 无漂移", ANSI_GREEN) if not rep.drift_detected else colorize("⚠️ 检测到漂移", ANSI_YELLOW)
                print(f"   • [{rep.lang:^10}] H2章节: {rep.section_count_st} vs {rep.section_count_cs} | {align_badge} | {drift_badge} (ST: {rep.standards_path.name} ⟷ CS: {rep.cheatsheet_path.name})")

        if self.results:
            print(colorize("\n [4] 详细问题清单 (Itemized Issues)", ANSI_BOLD))
            for f_rel, issues in sorted(self.results.items()):
                err_in_f = any(i.level == "ERROR" for i in issues)
                f_color = ANSI_RED if err_in_f else ANSI_YELLOW
                print(f"\n  📄 {colorize(f_rel, ANSI_BOLD + f_color)}")
                for iss in issues:
                    badge = f"[{iss.level}]"
                    badge_color = ANSI_RED if iss.level == "ERROR" else ANSI_YELLOW
                    line_info = f" (line {iss.line})" if iss.line else ""
                    print(f"     {colorize(badge, badge_color)} [{iss.category}]{line_info} {iss.message}")
        else:
            print(colorize("\n ✨ 知识库完美无瑕！未发现任何 Frontmatter、Wikilink、命名或双版本对齐问题。", ANSI_GREEN + ANSI_BOLD))

        print(colorize("\n" + "=" * 76, ANSI_CYAN))
        if stats["total_errors"] == 0 and stats["total_warnings"] == 0:
            print(colorize(" 🎉 质量检查结论: PASS (全部合规)", ANSI_GREEN + ANSI_BOLD))
        elif stats["total_errors"] == 0:
            print(colorize(f" ⚠️  质量检查结论: WARN (存在 {stats['total_warnings']} 个警告，建议优化)", ANSI_YELLOW + ANSI_BOLD))
        else:
            print(colorize(f" ❌ 质量检查结论: FAILED (存在 {stats['total_errors']} 个错误，需修正)", ANSI_RED + ANSI_BOLD))
        print(colorize("=" * 76 + "\n", ANSI_CYAN))


def main() -> int:
    parser = argparse.ArgumentParser(description="Vault Quality Checker & Linter for Coding Knowledge Base")
    parser.add_argument("--vault-path", type=str, default=None, help="Root path of the Obsidian vault")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if errors or broken wikilinks are found (Git hook barrier)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose details")
    args = parser.parse_args()

    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        script_dir = pathlib.Path(__file__).resolve().parent
        if (script_dir.parent / "AGENTS.md").exists():
            vault_root = script_dir.parent
        else:
            vault_root = pathlib.Path("{{VAULT_ROOT}}").resolve()

    checker = VaultQualityChecker(vault_root, verbose=args.verbose)
    summary = checker.run_check()

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        checker.print_terminal_report()

    stats = summary["stats"]
    total_errors = stats.get("total_errors", 0)
    broken_wikilinks = stats.get("broken_wikilinks", 0)

    if args.strict:
        if total_errors > 0 or broken_wikilinks > 0:
            return 1
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
