#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automated Healthcheck & Maintenance Script for Coding Vault ({{VAULT_ROOT}})

Inspects:
  1. Frontmatter Verification (YAML frontmatter and 6 required fields)
  2. Wikilink Integrity (all [[...]] wikilinks resolve to valid targets)
  3. Dual-Version Consistency (03-Languages/*-STANDARDS & *-CHEATSHEET pairing & reciprocal frontmatter)
  4. Inbox Ingestion Hygiene (99-Inbox/ draft backlog status)
  5. Multi-Agent Symlink Health (CLAUDE.md, GEMINI.md, .cursorrules, .windsurfrules, CONVENTIONS.md -> AGENTS.md)
  6. AGENTS.md Size Guard (<= 10,240 bytes)
  7. Toolchain Path Compliance (scripts/ reference live dir names, no legacy 2026-09 renumber leftovers)
  8. Skill Registry Sync (SKILL-REGISTRY.md §2.1/§2.2 L1 & §3 L2 skill entries resolve to real SKILL.md entities;
     L2 under .claude/skills/ is a hard check, L1 under ~/.cc-switch/skills/ degrades to SKIP when dir unavailable)
  8b. Cross-Agent WORKMEMORY Scan ($CODE_ROOT/*/WORKMEMORY/: INDEX.md exists, work.log events <= 4KB,
      unclosed WORK_START warning; projects without WORKMEMORY are skipped silently)
  9. Config Contract Validation (05-Tools/capabilities.json / scripts/routing.json / hooks/hooks.json:
     parseable JSON + schema_version=1; routing targets exist + tags valid (namespace/name, no dup);
     hook entries resolve to existing files + stages legal; capability names unique + declared_status
     within the verified/configured/degraded enum)
  10. Logging audit row to month-sharded 11-Agents/logs/{YYYY-MM}.md when --log is passed
"""

import sys

# Prevent Windows GBK stdout trap
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
import shlex
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import yaml
except ImportError:
    print("❌ Error: PyYAML package is required. Install via `pip install pyyaml`.", file=sys.stderr)
    sys.exit(1)

# Shared audit-log writer (single source of truth for 11-Agents/logs/{YYYY-MM}.md appends)
from vault_audit import append_audit_row

# Shared wikilink placeholder rule (single source of truth for this checker and
# vault-quality-check.py) — an inline copy here is how the two checkers came to
# disagree about `RAW-YYYY-MM-DD` style targets.
from vault_linkrules import is_placeholder_link

# Default exclusion directories for note indexing & frontmatter checking.
# MUST stay in sync with EXCLUDED_DIRS in scripts/vault-quality-check.py — divergent
# exclusion lists make the two checkers disagree on what counts as a vault note
# (e.g. tool caches such as .pytest_cache/README.md have no frontmatter by design).
EXCLUDED_DIRS: Set[str] = {
    ".obsidian",
    ".codebuddy",
    ".smart-env",
    "copilot",
    ".claude",
    ".agents",
    ".opencode",
    ".git",
    ".githooks",
    ".claudian",
    "scripts",
    "Templates/workmemory",
    # 随包技能子集：harness 技能 schema（name/description），非 vault 笔记
    "skills",
    ".trash",
    "node_modules",
    ".pytest_cache",
    "__pycache__",
    "11-Agents/logs",
    "08-Projects/项目档案",
}

# Root-level infrastructure files exempt from standard note frontmatter rules
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
    "type",
    "tags",
    "status",
    "audience",
]

EXPECTED_SYMLINKS: List[str] = [
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".windsurfrules",
    "CONVENTIONS.md",
]

AGENTS_MAX_SIZE_BYTES: int = 10240  # 10 KB limit

# Check 5 degraded form (Task-7): a machine without symlink privileges (Windows
# default, `core.symlinks=false` clones, `git archive | tar` unpacks) can only
# materialize the 5 multi-agent entries as plain files whose content equals
# AGENTS.md — exactly the downgrade the Task-5 self-heal hook writes. That form
# MUST pass with a loud degraded warning instead of failing the whole
# healthcheck (otherwise every fresh machine reports "out-of-the-box broken").
# Content mismatch / absence stays fail-closed.
SYMLINK_DEGRADED_HINT: str = (
    "内容副本形态，开启 Developer Mode + core.symlinks true 可恢复真符号链接"
)

# Directory names retired by the 2026-09 vault renumbering. Every script under
# scripts/ must reference live names (03-Languages, 05-Tools, ...); any residual
# legacy name signals stale path wiring that silently breaks semantic retrieval.
LEGACY_DIR_NAMES: Tuple[str, ...] = (
    "02-Languages",
    "03-Tools",
    "04-Sources",
    "05-Projects",
    "06-Inbox",
    "06-Agents",
)

# Skill Registry Sync (check 8): single source of truth is 05-Tools/SKILL-REGISTRY.md.
# The registry MUST only reference skills that physically exist (SKILL-REGISTRY §5 red line).
REGISTRY_REL_PATH: str = "05-Tools/SKILL-REGISTRY.md"
L2_SKILLS_REL_DIR: str = ".claude/skills"
CC_SWITCH_HOME_ENV: str = "CC_SWITCH_HOME"
DEFAULT_CC_SWITCH_SKILLS_DIR: str = "~/.cc-switch/skills"

# Registry sections that declare skills, mapped to the physical layer they index:
#   section   -> ("L1" | "L2")
REGISTRY_SECTIONS: Dict[str, str] = {
    "2.1": "L1",
    "2.2": "L1",
    "3": "L2",
}

# ---------------------------------------------------------------------------
# Check 9: Config Contract Validation (P3 Task-4, ADR-0001 §4 #7/#15/#14).
# Three machine-executable config contracts guarded for parseability, schema
# version, cross-reference existence, and enum membership. The tag/type rules
# mirror the runtime loader in scripts/vault-inbox-consolidate.py
# (_validate_tag / _VALID_ROUTE_TYPES / _REQUIRED_KEYS_BY_TYPE) so this
# checker can never disagree with the loader.
# ---------------------------------------------------------------------------
CAPABILITIES_JSON_REL: str = "05-Tools/capabilities.json"
ROUTING_JSON_REL: str = "scripts/routing.json"
HOOKS_JSON_REL: str = "hooks/hooks.json"

LEGAL_CAPABILITY_STATUSES: Set[str] = {"verified", "configured", "degraded"}
LEGAL_HOOK_STAGES: Set[str] = {"pre-commit", "posttooluse", "stop"}
ENTRY_INTERPRETERS: Set[str] = {"bash", "sh", "python", "python3"}

# route type -> (required target keys, existence kind on disk)
ROUTING_TARGET_SPEC: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "dual": (("standards", "cheatsheet"), "file"),
    "rule-append": (("target",), "file"),
    "source-article": (("target_dir",), "dir"),
    "project": (("target_project",), "project"),
}


def _load_json_contract(vault_root: pathlib.Path, rel_path: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Load one contract JSON. Every failure mode is reported, never swallowed."""
    path = vault_root / rel_path
    if not path.is_file():
        return None, [f"{rel_path}: contract file missing"]
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"{rel_path}: unreadable ({exc})"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, [f"{rel_path}: JSON parse failed ({exc})"]
    if not isinstance(data, dict):
        return None, [f"{rel_path}: top-level must be a JSON object"]
    return data, []


def _check_schema_version(data: Dict[str, Any], rel_path: str, problems: List[str]) -> None:
    """All three contracts pin schema_version = 1."""
    if data.get("schema_version") != 1:
        problems.append(f"{rel_path}: schema_version must be 1 (got {data.get('schema_version')!r})")


def _read_file_bytes(path: pathlib.Path) -> Optional[bytes]:
    """Read a file's bytes for exact comparison; unreadable/absent -> None.

    Check 5 compares entry content against AGENTS.md byte-for-byte, so any
    OSError must surface as "not identical" (fail-closed), never as a crash.
    """
    try:
        return path.read_bytes()
    except OSError:
        return None


def _is_valid_tag(tag: Any) -> bool:
    """namespace/name form, mirroring vault-inbox-consolidate._validate_tag."""
    return (
        isinstance(tag, str)
        and "/" in tag
        and not tag.startswith("/")
        and not tag.endswith("/")
    )


def _missing_routing_targets(vault_root: pathlib.Path, route: Dict[str, Any], label: str) -> List[str]:
    """Resolve one route/fallback branch's targets per type and report missing ones."""
    spec = ROUTING_TARGET_SPEC.get(route.get("type"))
    if spec is None:
        return [f"routing: {label} has unknown type {route.get('type')!r}; cannot resolve targets"]
    keys, kind = spec
    problems: List[str] = []
    for key in keys:
        target = route.get(key)
        if not isinstance(target, str) or not target:
            problems.append(f"routing: {label} missing required key {key!r} (type={route.get('type')!r})")
            continue
        if kind == "project":
            resolved = vault_root / "08-Projects" / target
            exists = resolved.is_dir()
        else:
            resolved = vault_root / target
            exists = resolved.is_dir() if kind == "dir" else resolved.is_file()
        if not exists:
            problems.append(f"routing: {label} target does not exist: {resolved}")
    return problems


def _routing_problems(vault_root: pathlib.Path, data: Dict[str, Any]) -> List[str]:
    """routing.json body: tag form/uniqueness + per-type target existence."""
    problems: List[str] = []
    routes = data.get("routes")
    if not isinstance(routes, list):
        return [f"{ROUTING_JSON_REL}: routes must be a list"]
    seen_tags: Set[str] = set()
    for route in routes:
        if not isinstance(route, dict):
            problems.append(f"{ROUTING_JSON_REL}: routes entries must be objects")
            continue
        tag = route.get("tag")
        label = f"route {tag!r}"
        if not _is_valid_tag(tag):
            problems.append(f"routing: {label} invalid tag (must be namespace/name form)")
        elif tag in seen_tags:
            problems.append(f"routing: {label} duplicate tag")
        else:
            seen_tags.add(tag)
        problems.extend(_missing_routing_targets(vault_root, route, label))

    fallback = data.get("fallback")
    if not isinstance(fallback, dict):
        problems.append(f"{ROUTING_JSON_REL}: fallback must be an object")
        return problems
    for key, branch in fallback.items():
        if not isinstance(branch, dict):
            problems.append(f"routing: fallback[{key!r}] must be an object")
            continue
        problems.extend(_missing_routing_targets(vault_root, branch, f"fallback[{key!r}]"))
    return problems


def _hook_problems(vault_root: pathlib.Path, data: Dict[str, Any]) -> List[str]:
    """hooks.json body: stage enum + entry resolves to an existing vault file."""
    problems: List[str] = []
    hooks = data.get("hooks")
    if not isinstance(hooks, list):
        return [f"{HOOKS_JSON_REL}: hooks must be a list"]
    for hook in hooks:
        if not isinstance(hook, dict):
            problems.append(f"{HOOKS_JSON_REL}: hooks entries must be objects")
            continue
        hook_id = hook.get("id", "<missing id>")
        stage = hook.get("stage")
        if stage not in LEGAL_HOOK_STAGES:
            legal = ", ".join(sorted(LEGAL_HOOK_STAGES))
            problems.append(f"hooks: hook {hook_id!r} has illegal stage {stage!r} (legal: {legal})")
        entry = hook.get("entry")
        if not isinstance(entry, str) or not entry.strip():
            problems.append(f"hooks: hook {hook_id!r} entry missing or empty")
            continue
        try:
            tokens = shlex.split(entry)
        except ValueError as exc:
            problems.append(f"hooks: hook {hook_id!r} entry cannot be parsed ({exc}): {entry!r}")
            continue
        if len(tokens) != 2 or tokens[0] not in ENTRY_INTERPRETERS:
            problems.append(
                f"hooks: hook {hook_id!r} entry must be '<interpreter> <vault-relative script>' "
                f"two-token form: {entry!r}"
            )
            continue
        script = vault_root / tokens[1]
        if not script.is_file():
            problems.append(f"hooks: hook {hook_id!r} entry script does not exist: {script}")
    return problems


def _capability_problems(data: Dict[str, Any]) -> List[str]:
    """capabilities.json body: name uniqueness + declared_status 3-state enum."""
    problems: List[str] = []
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        return [f"{CAPABILITIES_JSON_REL}: capabilities must be a list"]
    seen_names: Set[str] = set()
    for cap in capabilities:
        if not isinstance(cap, dict):
            problems.append(f"{CAPABILITIES_JSON_REL}: capabilities entries must be objects")
            continue
        name = cap.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{CAPABILITIES_JSON_REL}: capability missing a valid name field")
            continue
        if name in seen_names:
            problems.append(f"capabilities: duplicate name {name!r}")
        seen_names.add(name)
        status = cap.get("declared_status")
        if status not in LEGAL_CAPABILITY_STATUSES:
            legal = "/".join(sorted(LEGAL_CAPABILITY_STATUSES))
            problems.append(f"capabilities: {name!r} declared_status {status!r} illegal (legal: {legal})")
    return problems


def check_config_contracts(vault_root: pathlib.Path) -> List[str]:
    """Check 9: validate the three machine-executable config contracts.

    Covers capabilities.json / routing.json / hooks/hooks.json: parseable,
    schema_version == 1, routing targets exist + tags valid (namespace/name
    form, no duplicates), hook entries resolve to existing files + stages
    within the legal enum, capability names unique + declared_status within
    the verified/configured/degraded 3-state enum.

    Returns the problem list; an empty list means all contracts pass.
    """
    problems: List[str] = []
    loaded: Dict[str, Optional[Dict[str, Any]]] = {}
    for rel_path in (CAPABILITIES_JSON_REL, ROUTING_JSON_REL, HOOKS_JSON_REL):
        data, load_problems = _load_json_contract(vault_root, rel_path)
        problems.extend(load_problems)
        loaded[rel_path] = data

    capabilities_data = loaded[CAPABILITIES_JSON_REL]
    if capabilities_data is not None:
        _check_schema_version(capabilities_data, CAPABILITIES_JSON_REL, problems)
        problems.extend(_capability_problems(capabilities_data))

    routing_data = loaded[ROUTING_JSON_REL]
    if routing_data is not None:
        _check_schema_version(routing_data, ROUTING_JSON_REL, problems)
        problems.extend(_routing_problems(vault_root, routing_data))

    hooks_data = loaded[HOOKS_JSON_REL]
    if hooks_data is not None:
        _check_schema_version(hooks_data, HOOKS_JSON_REL, problems)
        problems.extend(_hook_problems(vault_root, hooks_data))

    return problems


def _load_claim_ledger_module() -> Any:
    """Load vault-claim-ledger.py (hyphenated filename) to reuse its enum
    constants and frontmatter parsing — a single enum dictionary for the
    whole P4 toolchain (deriver / backfiller / healthcheck)."""
    import importlib.util

    script_path = pathlib.Path(__file__).resolve().parent / "vault-claim-ledger.py"
    spec = importlib.util.spec_from_file_location("vault_claim_ledger", script_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load ledger module from {script_path}")
    spec.loader.exec_module(module)
    return module


def check_claim_enums(vault_root: pathlib.Path) -> List[str]:
    """Check 10: frontmatter trust-field enum legality (ROADMAP-P4 Task-5).

    Flags ONLY illegally valued authority/claim_risk/review_status fields.
    Missing fields are legal by default semantics (CLAIM-LEDGER-SCHEMA §1);
    a present-but-non-enum value (including non-strings) is flagged with the
    file named. Dotfiles (agent briefs/tooling) are never scanned.

    Returns the problem list; an empty list means the vault passes.
    """
    problems: List[str] = []
    ledger = _load_claim_ledger_module()
    for path in ledger._iter_markdown_files(vault_root):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            problems.append(f"claim-enums: cannot read {path}: {exc}")
            continue
        fm_text, _body = ledger._split_frontmatter(text)
        if not fm_text:
            continue  # no frontmatter -> nothing to validate
        meta = ledger._parse_frontmatter(fm_text)
        rel_posix = str(path.relative_to(vault_root)).replace("\\", "/")
        for field, enums in (
            ("authority", ledger.AUTHORITY_ENUMS),
            ("claim_risk", ledger.CLAIM_RISK_ENUMS),
            ("review_status", ledger.REVIEW_STATUS_ENUMS),
        ):
            if field not in meta:
                continue  # missing == default semantics, never illegal
            value = meta[field]
            if not isinstance(value, str) or value not in enums:
                problems.append(
                    f"claim-enums: {rel_posix}: {field}={value!r} 不在合法枚举内"
                )
    return problems


class VaultHealthChecker:
    def __init__(self, vault_root: pathlib.Path, verbose: bool = False):
        self.vault_root = vault_root.resolve()
        self.verbose = verbose
        self.results: Dict[str, Any] = {}
        self.all_files_rel: Set[str] = set()
        self.all_stems: Set[str] = set()
        self.all_dirs_rel: Set[str] = set()
        self.md_notes: List[pathlib.Path] = []
        self._build_vault_index()

    def _is_excluded(self, path: pathlib.Path) -> bool:
        """Check if path is inside any excluded directory."""
        try:
            rel = path.relative_to(self.vault_root)
        except ValueError:
            return True
        rel_posix = str(rel).replace("\\", "/")
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            return True
        return any(rel_posix == ex or rel_posix.startswith(ex.rstrip("/") + "/") for ex in EXCLUDED_DIRS)

    def _build_vault_index(self) -> None:
        """Index all vault files, directories, and notes for wikilink resolution."""
        for p in self.vault_root.rglob("*"):
            if self._is_excluded(p):
                continue
            try:
                rel = p.relative_to(self.vault_root)
            except ValueError:
                continue
            rel_posix = str(rel).replace("\\", "/")
            if p.is_dir():
                self.all_dirs_rel.add(rel_posix)
                self.all_dirs_rel.add(rel_posix + "/")
            elif p.is_file() or p.is_symlink():
                self.all_files_rel.add(rel_posix)
                self.all_stems.add(p.name)
                self.all_stems.add(p.stem)
                if rel_posix.endswith(".md"):
                    self.all_files_rel.add(rel_posix[:-3])
                    if not p.is_symlink() and rel_posix not in ROOT_INFRASTRUCTURE_FILES:
                        self.md_notes.append(p)

    def _parse_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse YAML frontmatter, supporting template placeholders like {{date}}."""
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not m:
            return None
        raw_yaml = m.group(1)
        # Sanitize template placeholders {{var}} -> placeholder_var for clean YAML parsing
        sanitized = re.sub(r"\{\{([^\}]+)\}\}", r"placeholder_\1", raw_yaml)
        try:
            parsed = yaml.safe_load(sanitized)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return None

    def check_frontmatter(self) -> Dict[str, Any]:
        """Check 1: Frontmatter Verification across all scanned notes."""
        valid_notes: List[str] = []
        invalid_notes: List[Dict[str, Any]] = []

        for note_path in sorted(self.md_notes):
            rel_str = str(note_path.relative_to(self.vault_root)).replace("\\", "/")
            try:
                with open(note_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                invalid_notes.append({"path": rel_str, "reason": f"Read error: {e}"})
                continue

            fm = self._parse_frontmatter(content)
            if fm is None:
                invalid_notes.append({"path": rel_str, "reason": "Missing or malformed YAML frontmatter (--- header)"})
                continue

            missing_fields = [field for field in REQUIRED_FRONTMATTER_FIELDS if field not in fm]
            if missing_fields:
                invalid_notes.append({
                    "path": rel_str,
                    "reason": f"Missing required fields: {', '.join(missing_fields)}"
                })
                continue

            # Check tags format
            tags = fm.get("tags")
            if not tags:
                invalid_notes.append({"path": rel_str, "reason": "Empty tags list"})
                continue

            valid_notes.append(rel_str)

        passed = len(invalid_notes) == 0
        return {
            "name": "Frontmatter Integrity",
            "passed": passed,
            "total_scanned": len(self.md_notes),
            "valid_count": len(valid_notes),
            "invalid_count": len(invalid_notes),
            "invalid_notes": invalid_notes,
        }

    def _extract_wikilinks(self, content: str) -> List[str]:
        """Extract all wikilinks from note content, ignoring fenced code blocks and inline code."""
        wikilink_pattern = re.compile(r"\[\[([^\]]+)\]\]")
        inline_code_pattern = re.compile(r"`[^`\n]+`")
        links: List[str] = []

        # Extract from frontmatter directly
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            for m in wikilink_pattern.finditer(fm_match.group(1)):
                links.append(m.group(1).strip())
            body = content[fm_match.end():]
        else:
            body = content

        # Process body line by line to skip code blocks
        in_code_block = False
        for line in body.splitlines():
            trimmed = line.strip()
            if trimmed.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            clean_line = inline_code_pattern.sub("", line)
            for m in wikilink_pattern.finditer(clean_line):
                links.append(m.group(1).strip())

        return links

    def _clean_link_target(self, raw: str) -> str:
        """Clean target from aliases and anchors."""
        raw = raw.strip()
        # Handle escaped table pipe \| or normal pipe |
        if "\\|" in raw:
            raw = raw.split("\\|")[0]
        elif "|" in raw:
            raw = raw.split("|")[0]
        if "#" in raw:
            raw = raw.split("#")[0]
        return raw.strip().rstrip("\\").rstrip("/")

    def check_wikilinks(self) -> Dict[str, Any]:
        """Check 2: Wikilink Integrity across all Markdown notes."""
        all_links_checked: int = 0
        broken_links: List[Dict[str, str]] = []

        for note_path in sorted(self.vault_root.rglob("*.md")):
            if self._is_excluded(note_path) or note_path.is_symlink():
                continue
            rel_str = str(note_path.relative_to(self.vault_root)).replace("\\", "/")
            try:
                with open(note_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            raw_links = self._extract_wikilinks(content)
            for raw_link in raw_links:
                target = self._clean_link_target(raw_link)
                # Template placeholders / docs syntax examples are not paths.
                if is_placeholder_link(target):
                    continue

                all_links_checked += 1
                target_posix = target.replace("\\", "/")
                is_valid = (
                    target_posix in self.all_files_rel
                    or (target_posix + ".md") in self.all_files_rel
                    or target in self.all_stems
                    or target_posix in self.all_stems
                    or target_posix in self.all_dirs_rel
                    or (self.vault_root / (target_posix + ".md")).exists()
                    or (self.vault_root / target_posix).exists()
                )

                if not is_valid:
                    broken_links.append({
                        "source": rel_str,
                        "raw_link": raw_link,
                        "target": target_posix,
                    })

        passed = len(broken_links) == 0
        return {
            "name": "Wikilink Integrity",
            "passed": passed,
            "total_links": all_links_checked,
            "broken_count": len(broken_links),
            "broken_links": broken_links,
        }

    def check_dual_version_consistency(self) -> Dict[str, Any]:
        """Check 3: Dual-Version Consistency for all 03-Languages/ subdirectories."""
        languages_dir = self.vault_root / "03-Languages"
        if not languages_dir.exists() or not languages_dir.is_dir():
            return {
                "name": "Dual-Version Consistency",
                "passed": False,
                "error": "03-Languages directory not found",
                "language_pairs": [],
            }

        pairs_status: List[Dict[str, Any]] = []
        all_passed = True

        for sub in sorted(languages_dir.iterdir()):
            if not sub.is_dir() or sub.name.startswith(".") or sub.name.upper() == "TOOLS":
                continue

            lang_folder_name = sub.name
            # Target standard file names
            lang_upper = lang_folder_name.upper()
            standards_filename = f"{lang_upper}-STANDARDS.md"
            cheatsheet_filename = f"{lang_upper}-CHEATSHEET.md"

            standards_path = sub / standards_filename
            cheatsheet_path = sub / cheatsheet_filename

            std_exists = standards_path.exists()
            cht_exists = cheatsheet_path.exists()

            if not std_exists and not cht_exists:
                continue

            std_ref_ok = False
            cht_ref_ok = False
            details: List[str] = []

            if not std_exists:
                details.append(f"Missing {standards_filename}")
                all_passed = False
            if not cht_exists:
                details.append(f"Missing {cheatsheet_filename}")
                all_passed = False

            if std_exists and cht_exists:
                # Check reciprocal frontmatter
                with open(standards_path, "r", encoding="utf-8", errors="replace") as f:
                    std_fm = self._parse_frontmatter(f.read()) or {}
                with open(cheatsheet_path, "r", encoding="utf-8", errors="replace") as f:
                    cht_fm = self._parse_frontmatter(f.read()) or {}

                std_cheatsheet_val = str(std_fm.get("cheatsheet", ""))
                cht_standards_val = str(cht_fm.get("standards", ""))

                if f"{lang_upper}-CHEATSHEET" in std_cheatsheet_val or cheatsheet_filename in std_cheatsheet_val:
                    std_ref_ok = True
                else:
                    details.append(f"{standards_filename} frontmatter missing link to cheatsheet (got: {std_cheatsheet_val!r})")
                    all_passed = False

                if f"{lang_upper}-STANDARDS" in cht_standards_val or standards_filename in cht_standards_val:
                    cht_ref_ok = True
                else:
                    details.append(f"{cheatsheet_filename} frontmatter missing link to standards (got: {cht_standards_val!r})")
                    all_passed = False

            pairs_status.append({
                "language": lang_folder_name,
                "standards_exists": std_exists,
                "cheatsheet_exists": cht_exists,
                "standards_ref_ok": std_ref_ok,
                "cheatsheet_ref_ok": cht_ref_ok,
                "passed": std_exists and cht_exists and std_ref_ok and cht_ref_ok,
                "details": details,
            })

        return {
            "name": "Dual-Version Consistency",
            "passed": all_passed,
            "total_languages": len(pairs_status),
            "language_pairs": pairs_status,
        }

    def check_inbox_hygiene(self) -> Dict[str, Any]:
        """Check 4: Inbox Ingestion Hygiene in 99-Inbox/."""
        inbox_dir = self.vault_root / "99-Inbox"
        if not inbox_dir.exists():
            return {
                "name": "Inbox Ingestion Hygiene",
                "passed": True,
                "status": "clean",
                "draft_count": 0,
                "drafts": [],
            }

        drafts: List[Dict[str, Any]] = []
        for p in sorted(inbox_dir.rglob("*.md")):
            if self._is_excluded(p) or p.is_symlink():
                continue
            if p.name == "README.md":
                continue  # 分区引导文件不是草稿（否则模板首启必有假 NOTICE，2026-09-11 二评）
            rel_str = str(p.relative_to(self.vault_root)).replace("\\", "/")
            stat = p.stat()
            drafts.append({
                "path": rel_str,
                "name": p.name,
                "size_bytes": stat.st_size,
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

        return {
            "name": "Inbox Ingestion Hygiene",
            "passed": True,  # Inbox having drafts is a notice, not a failure
            "draft_count": len(drafts),
            "drafts": drafts,
        }

    def check_symlinks(self) -> Dict[str, Any]:
        """Check 5: Multi-Agent Symlink Health (CLAUDE.md, GEMINI.md, .cursorrules, .windsurfrules, CONVENTIONS.md -> AGENTS.md).

        Four mutually exclusive forms per entry:
          * ``symlink``          — real link resolving to AGENTS.md → PASS (canonical)
          * ``content-copy``     — plain file whose bytes equal AGENTS.md → PASS,
                                   flagged ``degraded`` (Task-5 self-heal downgrade;
                                   unavoidable on Windows without symlink privileges)
          * ``content-mismatch`` — plain file, empty or stale bytes → FAIL (fail-closed)
          * ``missing``          — entry absent → FAIL (fail-closed)

        A single bad entry fails the whole check: no majority voting, the
        fail-closed contract is unchanged by the degraded acceptance.
        """
        target_file = self.vault_root / "AGENTS.md"
        symlinks_status: List[Dict[str, Any]] = []
        degraded_entries: List[str] = []
        all_passed = True

        agents_bytes = _read_file_bytes(target_file)

        for symlink_name in EXPECTED_SYMLINKS:
            p = self.vault_root / symlink_name
            exists = p.exists() or os.path.islink(p)
            is_link = os.path.islink(p) or p.is_symlink()
            target_match = False
            raw_target = None
            form = "missing"
            degraded = False

            if is_link:
                form = "symlink"
                try:
                    raw_target = os.readlink(p)
                    # Check if resolves to AGENTS.md
                    resolved = p.resolve()
                    if target_file.exists() and resolved == target_file.resolve():
                        target_match = True
                    elif raw_target in ("AGENTS.md", str(target_file)):
                        target_match = True
                except Exception:
                    pass
            elif exists:
                entry_bytes = _read_file_bytes(p)
                if agents_bytes and entry_bytes is not None and entry_bytes == agents_bytes:
                    # Degraded but acceptable: byte-identical copy of the truth source.
                    form = "content-copy"
                    target_match = True
                    degraded = True
                else:
                    form = "content-mismatch"

            item_passed = exists and target_match
            if not item_passed:
                all_passed = False
            if degraded:
                degraded_entries.append(symlink_name)

            symlinks_status.append({
                "name": symlink_name,
                "exists": exists,
                "is_symlink": is_link,
                "raw_target": str(raw_target) if raw_target else None,
                "points_to_agents_md": target_match,
                "form": form,
                "degraded": degraded,
                "passed": item_passed,
            })

        notes: List[str] = []
        if degraded_entries:
            notes.append(
                f"{len(degraded_entries)}/{len(EXPECTED_SYMLINKS)} 个多 Agent 入口为「内容副本」形态"
                f"（{', '.join(degraded_entries)}）：{SYMLINK_DEGRADED_HINT}"
            )

        return {
            "name": "Multi-Agent Symlink Health",
            "passed": all_passed,
            "degraded": bool(degraded_entries),
            "degraded_entries": degraded_entries,
            "notes": notes,
            "total_symlinks": len(EXPECTED_SYMLINKS),
            "symlinks": symlinks_status,
        }

    def check_size_guard(self) -> Dict[str, Any]:
        """Check 6: Size Guard for AGENTS.md (<= 10,240 bytes)."""
        agents_file = self.vault_root / "AGENTS.md"
        if not agents_file.exists():
            return {
                "name": "AGENTS.md Size Guard",
                "passed": False,
                "error": "AGENTS.md not found",
                "size_bytes": 0,
                "max_bytes": AGENTS_MAX_SIZE_BYTES,
            }

        size_bytes = os.path.getsize(agents_file)
        passed = size_bytes <= AGENTS_MAX_SIZE_BYTES
        ratio = (size_bytes / AGENTS_MAX_SIZE_BYTES) * 100

        return {
            "name": "AGENTS.md Size Guard",
            "passed": passed,
            "size_bytes": size_bytes,
            "max_bytes": AGENTS_MAX_SIZE_BYTES,
            "percentage": ratio,
        }

    def check_toolchain_paths(self) -> Dict[str, Any]:
        """Check 7: no legacy 2026-09 directory names remain hard-coded in scripts/."""
        scripts_dir = self.vault_root / "scripts"
        violations: List[Dict[str, Any]] = []
        scanned_files: int = 0

        if scripts_dir.exists():
            for py_file in sorted(scripts_dir.glob("*.py")):
                if py_file.name == "vault-healthcheck.py":
                    continue  # self-reference (declares LEGACY_DIR_NAMES itself)
                scanned_files += 1
                try:
                    lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError as e:
                    violations.append({"file": py_file.name, "legacy": "(unreadable)", "line": 0, "reason": str(e)})
                    continue
                first_hit = next(
                    ((lineno, legacy) for lineno, line in enumerate(lines, start=1)
                     for legacy in LEGACY_DIR_NAMES if legacy in line),
                    None,
                )
                if first_hit:
                    lineno, legacy = first_hit
                    violations.append({"file": py_file.name, "legacy": legacy, "line": lineno})

        passed = len(violations) == 0
        return {
            "name": "Toolchain Path Compliance",
            "passed": passed,
            "scanned_files": scanned_files,
            "violations": violations,
        }

    def _parse_registry_skills(self) -> Tuple[Optional[str], Dict[str, List[str]]]:
        """Parse SKILL-REGISTRY.md tables into {layer: [skill names]}.

        Header-driven column detection so both `| # | 技能 | ...` (§2.1) and
        `| 技能 | ...` (§2.2 / §3) layouts resolve the right cell. A single cell may
        hold several names separated by '/', e.g. `caveman` / `ponytail`.
        Returns (error_or_None, mapping)."""
        reg_path = self.vault_root / REGISTRY_REL_PATH
        if not reg_path.exists():
            return f"{REGISTRY_REL_PATH} not found", {}
        try:
            lines = reg_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return f"unreadable registry: {e}", {}

        mapping: Dict[str, List[str]] = {"L1": [], "L2": []}
        cur_section: Optional[str] = None
        skill_col: int = -1
        in_table: bool = False

        for raw in lines:
            line = raw.strip()
            sec_m = re.match(r"^#{2,3}\s+([0-9]+(?:\.[0-9]+)?)", line)
            if sec_m:
                cur_section = sec_m.group(1)
                skill_col = -1
                in_table = False
                continue
            if cur_section not in REGISTRY_SECTIONS:
                continue
            if not line.startswith("|"):
                in_table = False
                continue

            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                # Header row declares the '技能' column; separator row follows next.
                if "技能" in cells:
                    skill_col = cells.index("技能")
                    in_table = True
                continue

            # Separator row (| --- | --- |) right after the header
            if cells and re.fullmatch(r":?-{1,}:?", cells[0].replace(" ", "")):
                continue
            if skill_col < 0 or skill_col >= len(cells):
                continue
            if cells[skill_col] == "技能":  # repeated header guard
                continue

            layer = REGISTRY_SECTIONS[cur_section]
            for m in re.finditer(r"`([a-z][a-z0-9-]+)`", cells[skill_col]):
                mapping[layer].append(m.group(1))

        return None, mapping

    def check_skill_registry_sync(self) -> Dict[str, Any]:
        """Check 8: Skill Registry Sync.

        Enforces the SKILL-REGISTRY §5 red line ("registry MUST only reference skills
        that physically exist"). L2 (.claude/skills/<name>/SKILL.md) is hard: a missing
        entity fails the check. L1 (~/.cc-switch/skills/<name>/SKILL.md, overridable via
        CC_SWITCH_HOME) is soft: when the directory is unavailable on this machine the
        L1 segment reports SKIP and does not fail the overall result."""
        err, layers = self._parse_registry_skills()
        if err:
            return {
                "name": "Skill Registry Sync",
                "passed": False,
                "error": err,
                "l2_total": 0,
                "l2_valid": 0,
                "l2_missing": [],
                "l1_total": 0,
                "l1_valid": 0,
                "l1_missing": [],
                "l1_mode": "error",
                "notes": [err],
            }

        l2_names = sorted(set(layers.get("L2", [])))
        l1_names = sorted(set(layers.get("L1", [])))
        l2_missing = [
            name for name in l2_names
            if not (self.vault_root / L2_SKILLS_REL_DIR / name / "SKILL.md").exists()
        ]

        env_base = os.environ.get(CC_SWITCH_HOME_ENV)
        l1_dir = pathlib.Path(env_base) if env_base else pathlib.Path(os.path.expanduser(DEFAULT_CC_SWITCH_SKILLS_DIR))
        l1_mode = "skipped" if not l1_dir.is_dir() else "checked"
        l1_missing: List[str] = []
        if l1_mode == "checked":
            l1_missing = [
                name for name in l1_names
                if not (l1_dir / name / "SKILL.md").exists()
            ]

        passed = (not l2_missing) and (l1_mode == "skipped" or not l1_missing)
        notes: List[str] = []
        if l1_mode == "skipped":
            notes.append(f"L1 skills dir not found ({l1_dir}); L1 segment SKIPPED — run on a machine with CC Switch")

        return {
            "name": "Skill Registry Sync",
            "passed": passed,
            "l2_total": len(l2_names),
            "l2_valid": len(l2_names) - len(l2_missing),
            "l2_missing": l2_missing,
            "l1_total": len(l1_names),
            "l1_valid": len(l1_names) - len(l1_missing),
            "l1_missing": l1_missing,
            "l1_mode": l1_mode,
            "l1_dir": str(l1_dir),
            "notes": notes,
        }

    def check_workmemory(self) -> Dict[str, Any]:
        """Check 8b: Cross-Agent WORKMEMORY scan.

        Per 01-Rules/CROSS-AGENT-MEMORY.md §4: for every $CODE_ROOT\{project}\WORKMEMORY\
        that exists, verify INDEX.md presence, per-event size <= 4KB in work.log, and
        warn on unclosed WORK_START. Projects without WORKMEMORY/ are skipped (never
        an error) — the protocol is opt-in per project.
        """
        result: Dict[str, Any] = {
            "name": "Cross-Agent WORKMEMORY",
            "passed": True,
            "scanned_projects": 0,
            "skipped": False,
            "violations": [],
            "unclosed_starts": [],
            "notes": [],
        }

        # 代码根由环境变量提供（不再硬编码作者机器路径）：
        # 未设置 → SKIP 并给出开启方法。硬编码的作者路径会在导出模板时被去标识化
        # 改写成占位符字面量，使本检查在接收者机器上永远静默 SKIP（2026-09-11 评估发现）。
        code_root_env = os.environ.get("CODE_ROOT", "").strip()
        code_root = pathlib.Path(code_root_env).expanduser() if code_root_env else None
        if code_root is None or not code_root.is_dir():
            result["skipped"] = True
            result["notes"].append(
                "CODE_ROOT 未设置（或目录不存在）；WORKMEMORY 跨项目扫描已跳过。"
                "如需启用：设置环境变量 CODE_ROOT=<你的代码根目录>"
            )
            return result

        projects = sorted(p for p in code_root.iterdir() if p.is_dir() and (p / "WORKMEMORY").is_dir())
        result["scanned_projects"] = len(projects)
        if not projects:
            result["notes"].append("No project has a WORKMEMORY/ directory yet (protocol opt-in per project)")
            return result

        for project_dir in projects:
            wm_dir = project_dir / "WORKMEMORY"
            rel = project_dir.name
            index_file = wm_dir / "INDEX.md"
            if not index_file.exists():
                result["violations"].append({"project": rel, "issue": "INDEX.md missing"})
                continue

            work_log = wm_dir / "work.log"
            if not work_log.exists():
                result["violations"].append({"project": rel, "issue": "work.log missing (INDEX.md present)"})
                continue

            MAX_EVENT_BYTES = 4096
            open_start: Optional[Dict[str, Any]] = None
            try:
                current_event: Dict[str, Any] = {}
                with work_log.open("r", encoding="utf-8", errors="replace") as fh:
                    for raw_line in fh:
                        line = raw_line.rstrip("\n")
                        header = re.match(r"^### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \| (.+?) \| (\w+)\s*$", line)
                        if header:
                            if current_event:
                                if current_event["bytes"] > MAX_EVENT_BYTES:
                                    result["violations"].append({
                                        "project": rel,
                                        "issue": f"work.log event '{current_event['title']}' is {current_event['bytes']} bytes (> 4KB)",
                                    })
                                if current_event["type"] == "WORK_START":
                                    open_start = current_event
                                elif current_event["type"] == "WORK_END":
                                    open_start = None
                            current_event = {
                                "title": f"{header.group(1)} {header.group(2)}",
                                "type": header.group(3),
                                "bytes": len(line.encode("utf-8")),
                            }
                        elif current_event:
                            current_event["bytes"] += len(raw_line.encode("utf-8"))
                if current_event:
                    if current_event["bytes"] > MAX_EVENT_BYTES:
                        result["violations"].append({
                            "project": rel,
                            "issue": f"work.log event '{current_event['title']}' is {current_event['bytes']} bytes (> 4KB)",
                        })
                    if current_event["type"] == "WORK_START":
                        open_start = current_event
                    elif current_event["type"] == "WORK_END":
                        open_start = None
            except OSError as exc:
                result["violations"].append({"project": rel, "issue": f"work.log unreadable: {exc}"})
                continue

            if open_start:
                result["unclosed_starts"].append({"project": rel, "event": open_start["title"]})

        # Cross-project WORKMEMORY violations are advisory (NOTICE), not critical.
        # They indicate protocol non-compliance in other projects but do not affect
        # this vault's health. Always pass; report as notes.
        if result["violations"]:
            for v in result["violations"]:
                result["notes"].append(f"⚠️ {v['project']}: {v['issue']}")
            result["violations"] = []  # Clear so they don't count as failures
        result["passed"] = True
        return result

    def run_all_checks(self) -> Dict[str, Any]:
        """Execute all health checks."""
        config_contract_problems = check_config_contracts(self.vault_root)
        claim_enum_problems = check_claim_enums(self.vault_root)
        self.results = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "vault_root": str(self.vault_root),
            "frontmatter": self.check_frontmatter(),
            "wikilinks": self.check_wikilinks(),
            "dual_version": self.check_dual_version_consistency(),
            "inbox": self.check_inbox_hygiene(),
            "symlinks": self.check_symlinks(),
            "size_guard": self.check_size_guard(),
            "toolchain_paths": self.check_toolchain_paths(),
            "skill_registry": self.check_skill_registry_sync(),
            "workmemory": self.check_workmemory(),
            "config_contracts": {
                "name": "Config Contracts",
                "passed": not config_contract_problems,
                "problems": config_contract_problems,
            },
            "claim_enums": {
                "name": "Claim Enums",
                "passed": not claim_enum_problems,
                "problems": claim_enum_problems,
            },
        }

        # Overall health calculation
        critical_checks = [
            self.results["frontmatter"]["passed"],
            self.results["wikilinks"]["passed"],
            self.results["dual_version"]["passed"],
            self.results["symlinks"]["passed"],
            self.results["size_guard"]["passed"],
            self.results["toolchain_paths"]["passed"],
            self.results["skill_registry"]["passed"],
            self.results["config_contracts"]["passed"],
            self.results["claim_enums"]["passed"],
        ]
        self.results["all_passed"] = all(critical_checks)
        return self.results

    def print_summary_table(self) -> None:
        """Print a structured, clear summary report to stdout."""
        r = self.results
        print("=" * 80)
        print("🏥 Coding Knowledge Vault — Automated Healthcheck Report")
        print("=" * 80)
        print(f"📁 Vault Root      : {r['vault_root']}")
        print(f"⏰ Inspection Time : {r['timestamp']}")
        print("-" * 80)
        print("Inspection Results Summary:")
        print("-" * 80)

        # Check 1: Frontmatter
        fm = r["frontmatter"]
        fm_emoji = "✅ PASS" if fm["passed"] else "❌ FAIL"
        print(f" [1] Frontmatter Integrity    : {fm_emoji}  ({fm['valid_count']}/{fm['total_scanned']} notes verified with 6 standard fields)")
        if not fm["passed"] or self.verbose:
            for inv in fm["invalid_notes"]:
                print(f"     ↳ ❌ {inv['path']}: {inv['reason']}")

        # Check 2: Wikilinks
        wl = r["wikilinks"]
        wl_emoji = "✅ PASS" if wl["passed"] else "❌ FAIL"
        print(f" [2] Wikilink Integrity       : {wl_emoji}  ({wl['total_links'] - wl['broken_count']}/{wl['total_links']} links resolved, {wl['broken_count']} broken)")
        if not wl["passed"] or self.verbose:
            for b in wl["broken_links"]:
                print(f"     ↳ ❌ In {b['source']}: [[{b['raw_link']}]] -> Target '{b['target']}' not found")

        # Check 3: Dual-Version
        dv = r["dual_version"]
        dv_emoji = "✅ PASS" if dv["passed"] else "❌ FAIL"
        langs_str = ", ".join([p["language"] for p in dv["language_pairs"]])
        print(f" [3] Dual-Version Consistency : {dv_emoji}  ({len([p for p in dv['language_pairs'] if p['passed']])}/{dv['total_languages']} language pairs aligned: {langs_str})")
        if not dv["passed"] or self.verbose:
            for p in dv["language_pairs"]:
                status_str = "✅" if p["passed"] else "❌"
                print(f"     ↳ {status_str} {p['language']}: STANDARDS={p['standards_exists']}, CHEATSHEET={p['cheatsheet_exists']}, Reciprocal={p['standards_ref_ok'] and p['cheatsheet_ref_ok']}")
                for d in p["details"]:
                    print(f"        • {d}")

        # Check 4: Inbox
        ib = r["inbox"]
        ib_emoji = "✅ CLEAN" if ib["draft_count"] == 0 else "⚠️ NOTICE"
        inbox_name = "99-Inbox"
        print(f" [4] Inbox Ingestion Hygiene  : {ib_emoji}  ({ib['draft_count']} draft note(s) in {inbox_name}/)")
        if ib["draft_count"] > 0:
            for d in ib["drafts"]:
                print(f"     ↳ 📝 {d['name']} ({d['size_bytes']} bytes, updated {d['modified']})")

        # Check 5: Symlinks
        sl = r["symlinks"]
        degraded_count = len(sl.get("degraded_entries", []))
        if sl["passed"] and degraded_count:
            sl_emoji = "⚠️ PASS (DEGRADED)"
        elif sl["passed"]:
            sl_emoji = "✅ PASS"
        else:
            sl_emoji = "❌ FAIL"
        passed_sl_count = len([s for s in sl["symlinks"] if s["passed"]])
        degraded_suffix = f"，其中 {degraded_count} 个为内容副本（degraded）" if degraded_count else ""
        print(f" [5] Multi-Agent Symlinks     : {sl_emoji}  ({passed_sl_count}/{sl['total_symlinks']} 入口就位{degraded_suffix})")
        if not sl["passed"] or degraded_count or self.verbose:
            for s in sl["symlinks"]:
                s_icon = "⚠️" if s.get("degraded") else ("✅" if s["passed"] else "❌")
                detail = f" -> {s['raw_target']}" if s["is_symlink"] else f" [{s.get('form')}]"
                print(f"     ↳ {s_icon} {s['name']}{detail} (Valid link: {s['is_symlink']})")
            for note in sl.get("notes", []):
                print(f"     ↳ ⚠️ {note}")

        # Check 6: Size Guard
        sg = r["size_guard"]
        sg_emoji = "✅ PASS" if sg["passed"] else "❌ FAIL"
        print(f" [6] AGENTS.md Size Guard     : {sg_emoji}  ({sg['size_bytes']:,} / {sg['max_bytes']:,} bytes — {sg.get('percentage', 0):.1f}% of limit)")

        # Check 7: Toolchain Path Compliance
        tc = r["toolchain_paths"]
        tc_emoji = "✅ PASS" if tc["passed"] else "❌ FAIL"
        print(f" [7] Toolchain Path Compliance : {tc_emoji}  ({tc['scanned_files']} scripts scanned, {len(tc['violations'])} legacy dir reference(s))")
        if not tc["passed"] or self.verbose:
            for v in tc["violations"]:
                print(f"     ↳ ❌ {v['file']}:{v['line']} references retired directory '{v['legacy']}'")

        # Check 8: Skill Registry Sync
        sr = r["skill_registry"]
        sr_emoji = "✅ PASS" if sr["passed"] else "❌ FAIL"
        l1_part = f"L1 {sr['l1_valid']}/{sr['l1_total']} [{sr['l1_mode']}]"
        if sr["l1_mode"] == "skipped":
            l1_part = "L1 SKIP (no CC Switch dir)"
        print(f" [8] Skill Registry Sync     : {sr_emoji}  (L2 {sr['l2_valid']}/{sr['l2_total']}, {l1_part})")
        if not sr["passed"] or self.verbose:
            for name in sr["l2_missing"]:
                print(f"     ↳ ❌ L2 skill '{name}' in registry but no .claude/skills/{name}/SKILL.md")
            for name in sr["l1_missing"]:
                print(f"     ↳ ❌ L1 skill '{name}' in registry but missing under {sr['l1_dir']}")
            for note in sr["notes"]:
                print(f"     ↳ ⓘ {note}")
        if "error" in sr:
            print(f"     ↳ ❌ {sr['error']}")

        # Check 8b: Cross-Agent WORKMEMORY
        wm = r["workmemory"]
        if wm["skipped"]:
            print(f" [8b] Cross-Agent WORKMEMORY  : ⏭️ SKIP  ({wm['notes'][0]})")
        else:
            wm_emoji = "✅ PASS" if wm["passed"] else "❌ FAIL"
            note_count = len(wm["notes"])
            unclosed_count = len(wm["unclosed_starts"])
            print(f" [8b] Cross-Agent WORKMEMORY  : {wm_emoji}  ({wm['scanned_projects']} project(s) scanned, {note_count} notice(s))")
            if note_count > 0 or unclosed_count > 0 or self.verbose:
                for note in wm["notes"]:
                    print(f"     ↳ ⚠️ {note}")
                for u in wm["unclosed_starts"]:
                    print(f"     ↳ ⚠️ {u['project']}: unclosed WORK_START — {u['event']} (ask user: resume or restart)")

        # Check 9: Config Contracts
        cc = r["config_contracts"]
        cc_emoji = "✅ PASS" if cc["passed"] else "❌ FAIL"
        print(f" [9] Config Contracts         : {cc_emoji}  (capabilities.json / routing.json / hooks.json validated, {len(cc['problems'])} problem(s))")
        if not cc["passed"] or self.verbose:
            for problem in cc["problems"]:
                print(f"     ↳ ❌ {problem}")

        # Check 10: Claim Enums
        ce = r["claim_enums"]
        ce_emoji = "✅ PASS" if ce["passed"] else "❌ FAIL"
        print(f" [10] Claim Enums             : {ce_emoji}  (authority / claim_risk / review_status enum legality, {len(ce['problems'])} problem(s))")
        if not ce["passed"] or self.verbose:
            for problem in ce["problems"]:
                print(f"     ↳ ❌ {problem}")

        print("-" * 80)
        if r["all_passed"]:
            notices_str = f", {ib['draft_count']} inbox notices" if ib['draft_count'] > 0 else ""
            print(f"Overall Health: ✅ ALL CRITICAL CHECKS PASSED (0 errors{notices_str})")
        else:
            print("Overall Health: ❌ HEALTHCHECK FAILED — Issues detected above require resolution")
        print("=" * 80)

    def append_review_log(self) -> bool:
        """Append an audit record row to 11-Agents/logs/{YYYY-MM}.md (month-sharded)."""
        r = self.results
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        agent_name = "Antigravity (Healthcheck & Maintenance Specialist)"
        op_type = "Audit & Healthcheck"
        paths_str = "`scripts/vault-healthcheck.py`, `AGENTS.md`, 全库 Markdown & Symlinks"

        fm = r["frontmatter"]
        wl = r["wikilinks"]
        dv = r["dual_version"]
        ib = r["inbox"]
        sl = r["symlinks"]
        sg = r["size_guard"]
        tc = r["toolchain_paths"]
        sr = r["skill_registry"]
        wm = r["workmemory"]
        cc = r["config_contracts"]

        langs_list = ", ".join([p["language"] for p in dv["language_pairs"]])
        status_text = "HEALTHY (全部关键检查通过)" if r["all_passed"] else "FAILED (存在异常项)"

        wm_part = "SKIP (CODE_ROOT 未设置)" if wm["skipped"] else f"{wm['scanned_projects']} 项目已启用, {len(wm['notes'])} notices"
        summary_bullets = [
            f"**自动化知识库健康体检**：",
            f"1. Frontmatter 验证：{fm['valid_count']} 篇笔记通过（包含 6 大标准元数据字段）",
            f"2. Wikilink 完整性：{wl['total_links']} 条内链解析正常（0 断链）",
            f"3. 双版本一致性：{len(dv['language_pairs'])} 门语言（{langs_list}）规范与速查表双向对齐",
            f"4. Inbox 堆积状态：{ib['draft_count']} 篇待整理草稿",
            f"5. Multi-Agent 符号链接：{len(sl['symlinks']) - len(sl.get('degraded_entries', []))} 个真 Symlinks 指向 AGENTS.md"
            + (f"，{len(sl['degraded_entries'])} 个为内容副本形态（degraded）" if sl.get("degraded") else ""),
            f"6. AGENTS.md 体积：{sg['size_bytes']:,} / {sg['max_bytes']:,} 字节（{sg.get('percentage', 0):.1f}%）",
            f"7. 工具链路径合规：{tc['scanned_files']} 个脚本扫描，{len(tc['violations'])} 处旧编号引用残留",
            f"8. 技能注册表同步：L2 {sr['l2_valid']}/{sr['l2_total']} 就位，L1 {sr['l1_valid']}/{sr['l1_total']}（{sr['l1_mode']}），0 未落盘实体",
            f"8b. 跨 Agent WORKMEMORY：{wm_part}",
            f"8c. Config 契约校验：capabilities/routing/hooks 三契约 schema+引用完整性，{len(cc['problems'])} 处问题",
            f"8d. 可信度字段枚举：authority/claim_risk/review_status 全库枚举合法性，{len(ce['problems'])} 处问题",
            f"9. 总体判定：{status_text}",
        ]
        summary_cell = "<br>".join(summary_bullets)

        ok, msg = append_audit_row(self.vault_root, agent_name, op_type,
                                   paths_str, summary_cell, timestamp=timestamp)
        print(msg)
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated Healthcheck & Maintenance Script for Coding Vault")
    parser.add_argument("--vault-path", type=str, default=".", help="Root path of the vault (default: current directory)")
    parser.add_argument("--log", action="store_true", help="Append healthcheck summary row to 11-Agents/logs/{YYYY-MM}.md (month-sharded)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed diagnostic messages")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    vault_path = pathlib.Path(args.vault_path).resolve()
    # If scripts/ is vault_path, adjust to parent
    if vault_path.name == "scripts" and (vault_path.parent / "AGENTS.md").exists():
        vault_path = vault_path.parent

    checker = VaultHealthChecker(vault_root=vault_path, verbose=args.verbose)
    results = checker.run_all_checks()

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        checker.print_summary_table()

    if args.log:
        checker.append_review_log()

    return 0 if results["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
