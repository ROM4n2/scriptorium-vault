#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Auto-Linker Script for Coding Vault ({{VAULT_ROOT}})

Features:
  1. Concept Indexer:
     - Extracts concept definitions, titles, aliases, and filenames across all content directories.
     - Extracts concept terms from YAML frontmatter tags, note titles, and key engineering keywords.
     - Automatically ignores generic words, single common identifiers, and skill templates.
  2. Scanner & Linker:
     - Scans markdown notes line-by-line while strictly skipping:
       * Frontmatter blocks (--- ... ---)
       * Multiline code blocks (``` ... ```)
       * Markdown headers (# ...)
       * Inline code spans (`...`)
       * Existing Wikilinks ([[...]])
       * Markdown hyperlinks and images ([...](...))
       * URLs (http://, https://)
     - Safe matching with word boundary protections to prevent partial-word matching (e.g. matching 'go' in 'good' or 'algorithm').
     - Self-linking avoidance: ignores references pointing to the current file itself.
     - Per-file deduplication: links each concept at most once per note to avoid link spam.
  3. CLI Interface:
     - --dry-run (default): reports candidate links without modifying files.
     - --write / --apply: applies modifications to vault markdown files.
       All rewrites commit atomically via a single VaultTransaction (P1
       Task-4): any failure mid-way rolls back every touched file to its
       pre-apply state, prints the reason to stderr and exits non-zero.
     - --json: outputs structured candidate linking results in JSON format.
     - --vault-path P: path to vault root.
     - Exit code 0.
"""

import sys

# Prevent Windows GBK stdout trap (RFC / Vault Standard MUST)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# vault 级事务原语（P1 Task-4）。本文件是连字符文件名，常被 importlib 按路径
# 加载（scripts/ 不保证在 sys.path），显式插入脚本目录再导入
# （同 vault-quality-check.py 的做法）。
_SCRIPT_DIR: str = str(pathlib.Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from vault_transaction import TransactionError, VaultTransaction  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

SKIP_DIRS = {
    ".git",
    ".obsidian",
    ".claudian",
    ".smart-env",
    ".agents",
    ".opencode",
    ".claude",
    "copilot",
    "scripts",
    "Templates",
    ".vscode",
    "node_modules",
    ".venv",
}

# Stopwords / terms too short or ambiguous to auto-link
IGNORE_TERMS = {
    "the", "and", "for", "with", "from", "that", "this", "rule", "rules", "guide",
    "notes", "note", "code", "file", "path", "test", "tests", "tool", "tools",
    "lang", "topic", "category", "status", "draft", "stable", "archived", "audience",
    "both", "agent", "human", "true", "false", "null", "none", "date", "name",
    "go", "py", "rs", "ts", "js", "sh", "c", "cpp", "md", "src", "bin", "lib",
    "git", "bash", "rust", "python", "typescript", "golang", "skill", "home", "agents",
    "review-log", "log", "logs", "readme"
}


_WIKILINK_RE = re.compile(r"!?\[\[([^\]\|#]+)(?:#[^\]\|]*)?(?:\|[^\]]*)?\]\]")


def extract_existing_link_targets(content: str) -> Set[str]:
    """Collect every link target already present in a document.

    Returns both the full-path form (``01-Rules/〔你的领域通用规范〕``) and the
    filename-only form (``〔你的领域通用规范〕``) so a concept is considered
    "already linked" no matter how the author wrote the reference.
    """
    targets: Set[str] = set()
    for match in _WIKILINK_RE.finditer(content):
        target = match.group(1).strip()
        if target:
            targets.add(target)
            targets.add(target.split("/")[-1])
    return targets


class ConceptEntry:
    def __init__(self, term: str, target_link: str, source_file: pathlib.Path, is_exact: bool = True):
        self.term = term.strip()
        self.target_link = target_link.strip()
        self.source_file = source_file.resolve()
        self.is_exact = is_exact

    def __repr__(self):
        return f"<ConceptEntry '{self.term}' -> '[[{self.target_link}]]'>"


class VaultConceptIndexer:
    def __init__(self, vault_root: pathlib.Path, verbose: bool = False):
        self.vault_root = vault_root.resolve()
        self.verbose = verbose
        self.concepts: Dict[str, ConceptEntry] = {}

    def build_index(self) -> Dict[str, ConceptEntry]:
        """Scan vault for standard notes across all content directories."""
        self.concepts = {}

        # 1. Register canonical core rules & language standards
        canonical_map = {
            "〔你的领域通用规范〕": ("01-Rules/〔你的领域通用规范〕", "01-Rules/〔你的领域通用规范〕.md"),
            "领域专题规范": ("01-Rules/领域专题规范", "01-Rules/〔领域专题规范〕.md"),
            "领域专题规范": ("01-Rules/领域专题规范", "01-Rules/领域专题规范.md"),
            "领域专题规范": ("01-Rules/领域专题规范", "01-Rules/〔领域专题规范〕.md"),
            "GIT-CONVENTIONS": ("01-Rules/GIT-CONVENTIONS", "01-Rules/GIT-CONVENTIONS.md"),
            "INGESTION-WORKFLOW": ("01-Rules/INGESTION-WORKFLOW", "01-Rules/INGESTION-WORKFLOW.md"),
            "AGENT-CONDUCT": ("01-Rules/AGENT-CONDUCT", "01-Rules/AGENT-CONDUCT.md"),
            "GO-STANDARDS": ("03-Languages/GO/GO-STANDARDS", "03-Languages/GO/GO-STANDARDS.md"),
            "GO-CHEATSHEET": ("03-Languages/GO/GO-CHEATSHEET", "03-Languages/GO/GO-CHEATSHEET.md"),
            "GO-80-PERCENT-PHILOSOPHY": ("03-Languages/GO/GO-80-PERCENT-PHILOSOPHY", "03-Languages/GO/GO-80-PERCENT-PHILOSOPHY.md"),
            "GO-CONVENTIONS-FOR-AGENTS": ("03-Languages/GO/GO-CONVENTIONS-FOR-AGENTS", "03-Languages/GO/GO-CONVENTIONS-FOR-AGENTS.md"),
            "GO-CONVENTIONS-FOR-BEGINNERS": ("03-Languages/GO/GO-CONVENTIONS-FOR-BEGINNERS", "03-Languages/GO/GO-CONVENTIONS-FOR-BEGINNERS.md"),
            "PYTHON-STANDARDS": ("03-Languages/Python/PYTHON-STANDARDS", "03-Languages/Python/PYTHON-STANDARDS.md"),
            "PYTHON-CHEATSHEET": ("03-Languages/Python/PYTHON-CHEATSHEET", "03-Languages/Python/PYTHON-CHEATSHEET.md"),
            "RUST-STANDARDS": ("03-Languages/Rust/RUST-STANDARDS", "03-Languages/Rust/RUST-STANDARDS.md"),
            "RUST-CHEATSHEET": ("03-Languages/Rust/RUST-CHEATSHEET", "03-Languages/Rust/RUST-CHEATSHEET.md"),
            "TYPESCRIPT-STANDARDS": ("03-Languages/TypeScript/TYPESCRIPT-STANDARDS", "03-Languages/TypeScript/TYPESCRIPT-STANDARDS.md"),
            "TYPESCRIPT-CHEATSHEET": ("03-Languages/TypeScript/TYPESCRIPT-CHEATSHEET", "03-Languages/TypeScript/TYPESCRIPT-CHEATSHEET.md"),
            "BASH-STANDARDS": ("03-Languages/Bash/BASH-STANDARDS", "03-Languages/Bash/BASH-STANDARDS.md"),
            "BASH-CHEATSHEET": ("03-Languages/Bash/BASH-CHEATSHEET", "03-Languages/Bash/BASH-CHEATSHEET.md"),
        }

        for term, (link_target, rel_file) in canonical_map.items():
            target_path = self.vault_root / rel_file
            if target_path.exists():
                self._add_concept(term, link_target, target_path)

        # 2. Dynamic discovery from all content dirs (Templates/copilot/scripts skipped via SKIP_DIRS).
        target_dirs = ["00-MOC", "01-Rules", "02-Fundamentals", "03-Languages", "04-Systems", "05-Tools", "06-Sources", "07-Academics", "08-Projects", "09-Career"]
        for t_dir in target_dirs:
            p_dir = self.vault_root / t_dir
            if not p_dir.exists():
                continue
            for root, dirs, files in os.walk(p_dir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for file in files:
                    if not file.endswith(".md"):
                        continue
                    file_path = pathlib.Path(root) / file
                    rel_path = str(file_path.relative_to(self.vault_root)).replace("\\", "/")
                    target_link = rel_path[:-3] if rel_path.endswith(".md") else rel_path

                    stem = file_path.stem
                    if len(stem) >= 4 and stem.lower() not in IGNORE_TERMS:
                        self._add_concept(stem, target_link, file_path)

                    # Parse frontmatter tags & title
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                        fm = self._extract_frontmatter(content)
                        if fm:
                            title = fm.get("title")
                            if title and isinstance(title, str):
                                clean_title = title.strip().strip('"').strip("'")
                                if 4 <= len(clean_title) <= 40 and clean_title.lower() not in IGNORE_TERMS:
                                    self._add_concept(clean_title, f"{target_link}|{clean_title}", file_path)

                            tags = fm.get("tags")
                            if isinstance(tags, list):
                                for tag in tags:
                                    t_str = str(tag).strip()
                                    if "/" in t_str:
                                        concept_word = t_str.split("/")[-1]
                                        # Only index substantial multi-word / hyphenated concepts
                                        if len(concept_word) >= 5 and "-" in concept_word and concept_word.lower() not in IGNORE_TERMS:
                                            self._add_concept(concept_word, target_link, file_path)
                    except Exception as e:
                        if self.verbose:
                            print(f"Warning indexing {file_path}: {e}", file=sys.stderr)

        return self.concepts

    def _add_concept(self, term: str, target_link: str, source_file: pathlib.Path) -> None:
        """Register concept term, ignoring duplicates or shorter existing matches."""
        term_clean = term.strip()
        if not term_clean or len(term_clean) < 4:
            return
        if term_clean.lower() in IGNORE_TERMS:
            return
        if term_clean not in self.concepts:
            self.concepts[term_clean] = ConceptEntry(term_clean, target_link, source_file)

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract YAML frontmatter dictionary."""
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
        fm_text = parts[1]
        if yaml is not None:
            try:
                parsed = yaml.safe_load(fm_text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        # Fallback minimal parser
        res = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, v = line.split(":", 1)
                res[k.strip()] = v.strip().strip('"').strip("'")
        return res


# ---------------------------------------------------------------------------
# Transaction plan: collect apply rewrites, commit via single VaultTransaction
# ---------------------------------------------------------------------------
class _LinkPlan:
    """``--write/--apply`` 模式的改写收集器：只登记、不落盘（P1 Task-4）。

    所有候选改写先在内存累积（目标绝对路径 → 改写后全文），同时快照登记
    时刻的现盘 SHA-256；循环结束后由 :func:`_commit_plan` 包进单个
    ``VaultTransaction`` 一次性提交——任何一步失败（SHA-256 前置不符、
    commit 中途失败）由事务整体回滚，不会产生半成品。
    """

    def __init__(self, vault_root: pathlib.Path) -> None:
        self.vault_root = vault_root
        self.writes: Dict[pathlib.Path, str] = {}
        # 登记时刻的现盘内容哈希：提交前文件被外部篡改 → stage 前置校验拦截
        self.expected_sha256: Dict[pathlib.Path, str] = {}

    def stage_write(self, path: pathlib.Path, new_text: str) -> None:
        """登记一次改写；同一路径后写覆盖前写（auto-linker 每文件仅处理一次）。"""
        if path not in self.expected_sha256:
            self.expected_sha256[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.writes[path] = new_text


def _commit_plan(vault_root: pathlib.Path, plan: _LinkPlan) -> None:
    """把收集到的全部改写包进单个 VaultTransaction 提交（P1 Task-4）。

    任何一步失败（SHA-256 前置不符 / commit 中途）→ 事务整体回滚并抛出
    ``TransactionError``；调用方负责 stderr 说明与非 0 退出码。
    """
    tx_id = f"auto-linker-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    with VaultTransaction(vault_root, tx_id=tx_id) as tx:
        for path, text in plan.writes.items():
            tx.stage(
                path,
                expected_sha256=plan.expected_sha256.get(path),
                new_text=text,
            )


class VaultAutoLinker:
    def __init__(self, vault_root: pathlib.Path, verbose: bool = False):
        self.vault_root = vault_root.resolve()
        self.verbose = verbose
        self.indexer = VaultConceptIndexer(vault_root, verbose=verbose)
        self.concepts: Dict[str, ConceptEntry] = {}
        self.sorted_terms: List[str] = []

    def prepare(self) -> None:
        """Build concept index and sort terms by length descending (longest match first)."""
        self.concepts = self.indexer.build_index()
        # Sort terms: longest string first
        self.sorted_terms = sorted(self.concepts.keys(), key=lambda t: len(t), reverse=True)

    def process_file(
        self,
        file_path: pathlib.Path,
        dry_run: bool = True,
        plan: Optional[_LinkPlan] = None,
    ) -> Dict[str, Any]:
        """Scan a markdown file and find / apply candidate auto-links safely.

        ``plan`` 非空（--write/--apply 事务模式，P1 Task-4）时改写只登记进
        计划、不落盘；为 None 时保持旧行为（apply 直接写盘）。
        """
        file_path = file_path.resolve()
        rel_path = str(file_path.relative_to(self.vault_root)).replace("\\", "/")

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {
                "file": rel_path,
                "candidate_count": 0,
                "candidates": [],
                "error": str(e),
            }

        lines = content.splitlines(keepends=True)
        new_lines: List[str] = []

        in_frontmatter = False
        in_code_block = False

        candidate_records: List[Dict[str, Any]] = []
        file_linked_concepts: Set[str] = set()
        # 既有链接去重基线（2026-09-09 事故修复）：文件里已链接到某目标的，
        # 同目标的纯文本提及 MUST NOT 再插入链接。旧实现只防"本次运行内重复"，
        # 从不读取文件既有 wikilink，导致已链接行被二次插入。
        existing_targets = extract_existing_link_targets(content)

        for line_idx, line in enumerate(lines, start=1):
            line_stripped = line.strip()

            # 1. Track frontmatter (only at the top of file)
            if line_idx == 1 and line_stripped == "---":
                in_frontmatter = True
                new_lines.append(line)
                continue
            if in_frontmatter:
                if line_stripped == "---":
                    in_frontmatter = False
                new_lines.append(line)
                continue

            # 2. Track multiline code blocks (``` or ~~~)
            if line_stripped.startswith("```") or line_stripped.startswith("~~~"):
                in_code_block = not in_code_block
                new_lines.append(line)
                continue
            if in_code_block:
                new_lines.append(line)
                continue

            # 3. Skip Markdown Headers (#, ##, ###, etc.)
            if line_stripped.startswith("#"):
                new_lines.append(line)
                continue

            # 4. Skip HTML comments
            if line_stripped.startswith("<!--") and line_stripped.endswith("-->"):
                new_lines.append(line)
                continue

            # 5. Process candidate line for concept replacements
            processed_line, line_candidates = self._process_line(
                line, file_path, file_linked_concepts, existing_targets, line_idx
            )
            new_lines.append(processed_line)
            if line_candidates:
                candidate_records.extend(line_candidates)

        total_changes = len(candidate_records)
        if total_changes > 0 and not dry_run:
            new_text = "".join(new_lines)
            if plan is None:
                file_path.write_text(new_text, encoding="utf-8")
            else:
                plan.stage_write(file_path, new_text)

        return {
            "file": rel_path,
            "filename": file_path.name,
            "candidate_count": total_changes,
            "candidates": candidate_records,
            "applied": not dry_run if total_changes > 0 else False,
        }

    def _process_line(
        self,
        line: str,
        current_file: pathlib.Path,
        file_linked_concepts: Set[str],
        existing_targets: Set[str],
        line_num: int,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Safely find and replace concepts in unprotected segments of a single line."""
        token_regex = re.compile(
            r"(\[\[[^\]]+\]\]|!?\[[^\]]*\]\([^)]+\)|`[^`]+`|<[^>]+>|https?://[^\s)\]]+)"
        )

        segments = []
        last_end = 0
        for match in token_regex.finditer(line):
            start, end = match.span()
            if start > last_end:
                segments.append((line[last_end:start], False))  # Plain text
            segments.append((line[start:end], True))  # Protected token
            last_end = end
        if last_end < len(line):
            segments.append((line[last_end:], False))

        candidates_in_line = []
        new_segments = []

        for seg_text, is_protected in segments:
            if is_protected:
                new_segments.append(seg_text)
                continue

            # Process plain text segment against indexed terms
            seg_modified = seg_text
            for term in self.sorted_terms:
                concept_entry = self.concepts[term]

                # Self-link avoidance: do not link to the file itself
                if concept_entry.source_file == current_file:
                    continue

                # Don't link if already linked in this file
                if term in file_linked_concepts:
                    continue

                # Don't link if the file already links this target —
                # full-path 或文件名形式任一命中即视为已链接（2026-09-09 事故防线）
                if (
                    concept_entry.target_link in existing_targets
                    or concept_entry.target_link.split("/")[-1] in existing_targets
                ):
                    continue

                # Prepare matching pattern with boundary protections
                # For ASCII alphanumeric strings, use boundary assertion
                if re.match(r"^[A-Za-z0-9_\-]+$", term):
                    pattern = re.compile(rf"(?<![\[`\w\-\/]){re.escape(term)}(?![\]`\w\-\.])")
                else:
                    # For Chinese or mixed strings
                    pattern = re.compile(rf"(?<![\[`]){re.escape(term)}(?![\]`])")

                match = pattern.search(seg_modified)
                if match:
                    matched_text = match.group(0)
                    target_wikilink = f"[[{concept_entry.target_link}]]"
                    # Replace only first occurrence in this plain segment
                    prefix = seg_modified[: match.start()]
                    suffix = seg_modified[match.end() :]
                    seg_modified = prefix + target_wikilink + suffix

                    file_linked_concepts.add(term)
                    candidates_in_line.append({
                        "line": line_num,
                        "term": term,
                        "matched_text": matched_text,
                        "wikilink": target_wikilink,
                        "target_file": str(concept_entry.source_file.relative_to(self.vault_root)).replace("\\", "/"),
                    })

            new_segments.append(seg_modified)

        return "".join(new_segments), candidates_in_line

    def run_all(self, dry_run: bool = True) -> Dict[str, Any]:
        """Scan all markdown files in vault and generate comprehensive report.

        ``--write/--apply`` 路径（P1 Task-4）：全部改写先登记进单个
        :class:`_LinkPlan`，循环结束后由 :func:`_commit_plan` 包进单个
        ``VaultTransaction`` 一次性提交；任何一步失败（含 commit 中途）→
        事务整体回滚并抛出 ``TransactionError``，调用方负责 stderr 说明
        与非 0 退出码。无候选时不创建事务（零 journal、零写盘）。
        """
        self.prepare()

        # 事务模式（apply）：先收集后提交；dry-run 保持纯只读
        plan = _LinkPlan(self.vault_root) if not dry_run else None

        file_reports: List[Dict[str, Any]] = []
        total_candidates = 0

        for root, dirs, files in os.walk(self.vault_root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for file in files:
                if not file.endswith(".md"):
                    continue
                # Skip template files and root agent rules
                if file.startswith("tpl-") or file in ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "CONVENTIONS.md"]:
                    continue

                file_path = pathlib.Path(root) / file
                res = self.process_file(file_path, dry_run=dry_run, plan=plan)
                if res["candidate_count"] > 0:
                    file_reports.append(res)
                    total_candidates += res["candidate_count"]

        # Sort files by candidate count descending
        file_reports.sort(key=lambda x: x["candidate_count"], reverse=True)

        # P1 Task-4: 全部改写包进单个事务；无候选 → 不创建事务（无 journal）
        if plan is not None and plan.writes:
            _commit_plan(self.vault_root, plan)

        return {
            "vault_root": str(self.vault_root),
            "dry_run": dry_run,
            "indexed_concepts_count": len(self.concepts),
            "total_candidate_links": total_candidates,
            "files_with_candidates_count": len(file_reports),
            "files": file_reports,
        }

    def print_terminal_report(self, report: Dict[str, Any]) -> None:
        """Print clean, structured CLI summary report."""
        dry_run = report["dry_run"]
        mode_str = "[DRY-RUN - NO CHANGES WRITTEN]" if dry_run else "[WRITE MODE - CHANGES APPLIED]"
        total_links = report["total_candidate_links"]
        file_cnt = report["files_with_candidates_count"]
        indexed_cnt = report["indexed_concepts_count"]

        print("=" * 86)
        print("  🔗 CODING VAULT — AUTO-LINKER CONCEPT INJECTION REPORT")
        print("=" * 86)
        print(f" Vault Location      : {report['vault_root']}")
        print(f" Execution Mode      : {mode_str}")
        print(f" Indexed Concepts    : {indexed_cnt} distinct concepts indexed across 01-Rules/ & 03-Languages/")
        print(f" Candidate Links     : {total_links} links identified across {file_cnt} file(s)")
        print(f" Report Generated    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 86)

        if total_links == 0:
            print("\n  ✅ All concepts are already fully linked! No new candidate links discovered.\n")
            print("=" * 86)
            return

        print("\n [1] Candidate Links Per File Breakdown:")
        print(" " + "-" * 84)
        for idx, f_rep in enumerate(report["files"], 1):
            print(f" {idx:2d}. 📄 {f_rep['file']} (+{f_rep['candidate_count']} links):")
            for c in f_rep["candidates"]:
                print(f"     • Line {c['line']:3d}: '{c['matched_text']}' ➜ {c['wikilink']} (Target: {c['target_file']})")
            print(" " + "-" * 84)

        print(f"\n [2] Summary & Execution:")
        if dry_run:
            print(f"   ℹ️  Dry run completed. Found {total_links} candidate link(s).")
            print("   👉 Run with `--write` or `--apply` to commit these links to vault markdown files.")
        else:
            print(f"   🎉 Applied {total_links} new Wikilink(s) across {file_cnt} note(s) successfully.")
        print("=" * 86)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vault Auto-Linker CLI Tool for Coding Vault ({{VAULT_ROOT}})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode without modifying files (default: True)",
    )
    parser.add_argument(
        "--write",
        "--apply",
        dest="write",
        action="store_true",
        help="Apply and write link changes directly into markdown files",
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=".",
        help="Root path of the Obsidian vault (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in structured JSON format",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )

    args = parser.parse_args()

    is_dry_run = not args.write

    vault_path = pathlib.Path(args.vault_path).resolve()
    if vault_path.name == "scripts" and (vault_path.parent / "AGENTS.md").exists():
        vault_path = vault_path.parent

    linker = VaultAutoLinker(vault_root=vault_path, verbose=args.verbose)
    try:
        report = linker.run_all(dry_run=is_dry_run)
    except TransactionError as exc:
        # P1 Task-4: 事务失败 = 已整体回滚（vault 文件保持 apply 前状态）
        print(
            f"❌ 链接注入事务提交失败，已整体回滚（无半成品写入，vault 文件保持 apply 前状态）: {exc}",
            file=sys.stderr,
        )
        return 1

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        linker.print_terminal_report(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
