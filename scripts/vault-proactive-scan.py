#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Proactive Knowledge Discovery Scanner ({{VAULT_ROOT}})

Features:
  1. Target Scan Paths:
     - Scans {{CODE_ROOT}} engineering projects for source code & design notes.
     - Supported file extensions: .go, .py, .ts, .tsx, .js, .jsx, .rs, .md.
     - Strictly ignores dependencies, minified bundles, and build directories:
       .venv, venv, node_modules, vendor, target, dist, build, out, .next,
       _next, coverage, .git, .codegraph, etc.
  2. Pattern Recognition:
     - Annotations: TODO:, FIXME:, HACK:, BUG:, NOTE:, XXX:, OPTIMIZE:, WARN:
     - Architecture / Conventions: files or headers containing convention, architecture, design, rule, pattern.
     - Workarounds & Traps: comments mentioning workaround, trap, override, compatibility, bypass, gotcha, deadlock, race condition.
  3. Knowledge Value Scoring Algorithm (0.0 to 1.0):
     - Computes value score based on pattern weight, comment length, contextual detail, and complexity indicators.
  4. Suggested Inbox Draft Generator:
     - Suggests canonical YYYY-MM-DD-{project}-{slug}.md filename and target vault destination (99-Inbox/ -> 01-Rules/, 03-Languages/, 08-Projects/).
  5. CLI Options:
     - --limit N (default: 20): maximum number of top candidates to output.
     - --json: outputs structured JSON list.
     - --code-dir P: root path to search for projects (default: {{CODE_ROOT}}).
     - --min-score S: minimum value score filter (default: 0.50).
     - --verbose, -v: verbose scanning diagnostics.
  6. UTF-8 stdout protection and exit code 0.
"""

import sys

# Prevent Windows GBK stdout trap (RFC / Vault Standard MUST)
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
from typing import Any, Dict, List, Optional, Set, Tuple

SKIP_DIRS = {
    ".git",
    ".github",
    ".vscode",
    ".idea",
    ".venv",
    "venv",
    "env",
    "site-packages",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "out",
    ".next",
    "_next",
    "coverage",
    ".turbo",
    ".parcel-cache",
    "target",
    "bin",
    "obj",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".codegraph",
    ".understand-anything",
    "_artifacts",
    "data",
    ".obsidian",
}

VALID_EXTENSIONS = {".go", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".md"}

# High-value complexity indicator keywords
HIGH_VALUE_KEYWORDS = [
    "because",
    "reason",
    "windows",
    "crash",
    "leak",
    "deadlock",
    "race",
    "thread",
    "goroutine",
    "performance",
    "silent",
    "buffer",
    "encoding",
    "timeout",
    "mutex",
    "unsafe",
    "workaround",
    "trap",
    "override",
    "compat",
    "fallback",
    "patch",
    "drift",
    "symlink",
]

# Architecture doc keywords
ARCH_KEYWORDS = ["convention", "architecture", "design", "rule", "pattern", "guideline", "standard"]


class CandidateItem:
    def __init__(
        self,
        category: str,
        pattern_matched: str,
        file_path: pathlib.Path,
        code_root: pathlib.Path,
        line_num: int,
        excerpt: str,
        full_text: str,
        value_score: float,
    ):
        self.category = category
        self.pattern_matched = pattern_matched
        self.file_path = file_path.resolve()
        self.code_root = code_root.resolve()
        self.line_num = line_num
        self.excerpt = excerpt.strip()
        self.full_text = full_text.strip()
        self.value_score = round(min(max(value_score, 0.0), 1.0), 2)

        self.project_name = self._extract_project_name()
        self.suggested_inbox_filename = self._generate_inbox_filename()
        self.recommended_destination = self._determine_destination()

    def _extract_project_name(self) -> str:
        """Extract top-level project directory name under code root."""
        try:
            rel = self.file_path.relative_to(self.code_root)
            parts = rel.parts
            if len(parts) > 1:
                return parts[0]
            return self.file_path.stem
        except Exception:
            return "general"

    def _generate_inbox_filename(self) -> str:
        """Generate standardized YYYY-MM-DD-{project}-{slug}.md filename."""
        today_str = datetime.date.today().isoformat()
        proj_slug = re.sub(r"[^a-zA-Z0-9]+", "-", self.project_name).strip("-").lower()

        # Create meaningful slug from excerpt
        clean_text = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5\s]+", " ", self.excerpt)
        words = [w for w in clean_text.split() if len(w) > 2 and w.lower() not in ["the", "and", "for", "with", "this", "that"]]
        slug_part = "-".join(words[:4]).lower() if words else self.pattern_matched.lower()
        slug_part = re.sub(r"[^a-zA-Z0-9\-]+", "", slug_part).strip("-")
        if not slug_part:
            slug_part = f"{self.category.lower()}-note"

        return f"{today_str}-{proj_slug}-{slug_part}.md"

    def _determine_destination(self) -> str:
        """Determine target vault promotion destination."""
        ext = self.file_path.suffix.lower()
        if ext == ".go":
            return "03-Languages/GO/GO-STANDARDS.md"
        elif ext == ".py":
            return "03-Languages/Python/PYTHON-STANDARDS.md"
        elif ext in [".ts", ".tsx", ".js", ".jsx"]:
            return "03-Languages/TypeScript/TYPESCRIPT-STANDARDS.md"
        elif ext == ".rs":
            return "03-Languages/Rust/RUST-STANDARDS.md"

        lower_text = (self.excerpt + " " + self.file_path.name).lower()
        if any(k in lower_text for k in ["concurrency", "channel", "mutex", "goroutine", "async"]):
            return "01-Rules/〔领域专题规范〕.md"
        if any(k in lower_text for k in ["error", "panic", "exception", "fault"]):
            return "01-Rules/〔领域专题规范〕.md"
        if any(k in lower_text for k in ["git", "commit", "branch", "symlink"]):
            return "01-Rules/GIT-CONVENTIONS.md"

        if self.project_name and self.project_name != "general":
            return f"08-Projects/{self.project_name}/{self.project_name.upper()}-RULES.md"

        return "01-Rules/〔你的领域通用规范〕.md"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize candidate item to dictionary."""
        try:
            rel_file = str(self.file_path.relative_to(self.code_root)).replace("\\", "/")
        except Exception:
            rel_file = str(self.file_path).replace("\\", "/")

        return {
            "category": self.category,
            "pattern": self.pattern_matched,
            "value_score": self.value_score,
            "project": self.project_name,
            "file": rel_file,
            "line": self.line_num,
            "excerpt": self.excerpt,
            "suggested_inbox_file": self.suggested_inbox_filename,
            "recommended_destination": self.recommended_destination,
        }


class ProactiveCodeScanner:
    def __init__(
        self,
        code_root: pathlib.Path,
        min_score: float = 0.50,
        limit: int = 20,
        verbose: bool = False,
    ):
        self.code_root = code_root.resolve()
        self.min_score = min_score
        self.limit = limit
        self.verbose = verbose
        self.candidates: List[CandidateItem] = []

    def scan(self) -> List[CandidateItem]:
        """Perform proactive scan across source repositories."""
        self.candidates = []
        if not self.code_root.exists() or not self.code_root.is_dir():
            return self.candidates

        for root, dirs, files in os.walk(self.code_root):
            # Prune noisy directories
            dirs[:] = [
                d for d in dirs
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for file in files:
                file_path = pathlib.Path(root) / file
                ext = file_path.suffix.lower()
                if ext not in VALID_EXTENSIONS:
                    continue

                # Skip minified or bundle files
                if file.endswith(".min.js") or file.endswith(".bundle.js") or file.endswith(".chunk.js"):
                    continue

                try:
                    if file_path.stat().st_size > 1024 * 1024:
                        continue
                except Exception:
                    continue

                self._scan_file(file_path)

        # Sort candidates by value score descending, then by line count
        self.candidates.sort(key=lambda c: c.value_score, reverse=True)
        return self.candidates

    def _scan_file(self, file_path: pathlib.Path) -> None:
        """Scan a single file for candidate knowledge patterns."""
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        lines = content.splitlines()

        # Check for minified content (lines > 1000 characters)
        if any(len(l) > 1000 for l in lines[:5]):
            return

        # 1. Architecture / Convention Docs check (.md files or filenames)
        filename_lower = file_path.name.lower()
        if file_path.suffix == ".md" and any(k in filename_lower for k in ARCH_KEYWORDS):
            score = 0.75
            excerpt = f"Architecture / Design document: {file_path.stem}"
            if len(lines) > 20:
                score += 0.10
            self.candidates.append(
                CandidateItem(
                    category="ARCHITECTURE_DOC",
                    pattern_matched="architecture-filename",
                    file_path=file_path,
                    code_root=self.code_root,
                    line_num=1,
                    excerpt=excerpt,
                    full_text=content[:300],
                    value_score=score,
                )
            )

        # 2. Line by line pattern scanning
        for line_idx, line in enumerate(lines, start=1):
            line_str = line.strip()
            if not line_str or len(line_str) > 1000:
                continue

            # Skip common generated file markings
            if any(g in line_str for g in ["Code generated by", "DO NOT EDIT", "Autogenerated by"]):
                continue

            # (A) Workarounds & Traps
            workaround_regex = re.compile(
                r"(?i)(?:^|[\s/#*;-]+)\b(workaround|work-around|trap|override|gotcha|bypass|edge[- ]case|monkey[- ]patch|deadlock|race condition|silent drift)\b[:：\s]*(.+)?",
            )
            w_match = workaround_regex.search(line_str)
            if w_match:
                tag = w_match.group(1).upper()
                detail = (w_match.group(2) or "").strip()
                full_excerpt = f"{tag}: {detail}" if detail else line_str
                score = self._compute_score(
                    base_weight=0.78,
                    text=full_excerpt,
                    is_annotation=False,
                )
                if score >= self.min_score:
                    self.candidates.append(
                        CandidateItem(
                            category="WORKAROUND_TRAP",
                            pattern_matched=tag,
                            file_path=file_path,
                            code_root=self.code_root,
                            line_num=line_idx,
                            excerpt=full_excerpt[:140],
                            full_text=line_str,
                            value_score=score,
                        )
                    )
                continue

            # (B) Critical Annotations (HACK, BUG, FIXME)
            crit_regex = re.compile(
                r"(?i)(?:^|[\s/#*;-]+)\b(HACK|BUG|FIXME|COMPATIBILITY)\b[:：\s]+(.+)",
            )
            c_match = crit_regex.search(line_str)
            if c_match:
                tag = c_match.group(1).upper()
                detail = c_match.group(2).strip()
                full_excerpt = f"{tag}: {detail}"
                base = 0.72 if tag in ["HACK", "BUG"] else 0.65
                score = self._compute_score(
                    base_weight=base,
                    text=detail,
                    is_annotation=True,
                )
                if score >= self.min_score:
                    self.candidates.append(
                        CandidateItem(
                            category=f"ANNOTATION_{tag}",
                            pattern_matched=tag,
                            file_path=file_path,
                            code_root=self.code_root,
                            line_num=line_idx,
                            excerpt=full_excerpt[:140],
                            full_text=line_str,
                            value_score=score,
                        )
                    )
                continue

            # (C) Informational Annotations (TODO, NOTE, XXX, OPTIMIZE)
            info_regex = re.compile(
                r"(?i)(?:^|[\s/#*;-]+)\b(TODO|NOTE|XXX|OPTIMIZE|WARN)\b[:：\s]+(.+)",
            )
            i_match = info_regex.search(line_str)
            if i_match:
                tag = i_match.group(1).upper()
                detail = i_match.group(2).strip()
                # Skip trivial todos (e.g. "TODO: test", "TODO: cleanup")
                if len(detail) < 15 and not any(k in detail.lower() for k in HIGH_VALUE_KEYWORDS):
                    continue
                full_excerpt = f"{tag}: {detail}"
                score = self._compute_score(
                    base_weight=0.52,
                    text=detail,
                    is_annotation=True,
                )
                if score >= self.min_score:
                    self.candidates.append(
                        CandidateItem(
                            category=f"ANNOTATION_{tag}",
                            pattern_matched=tag,
                            file_path=file_path,
                            code_root=self.code_root,
                            line_num=line_idx,
                            excerpt=full_excerpt[:140],
                            full_text=line_str,
                            value_score=score,
                        )
                    )
                continue

            # (D) Architecture & Design Comments in Code Header
            if line_idx <= 25 and any(h in line_str.lower() for h in ["architecture:", "design decision:", "pattern:", "convention:"]):
                score = self._compute_score(
                    base_weight=0.70,
                    text=line_str,
                    is_annotation=False,
                )
                if score >= self.min_score:
                    self.candidates.append(
                        CandidateItem(
                            category="ARCHITECTURE_COMMENT",
                            pattern_matched="architecture-header",
                            file_path=file_path,
                            code_root=self.code_root,
                            line_num=line_idx,
                            excerpt=line_str[:140],
                            full_text=line_str,
                            value_score=score,
                        )
                    )

    def _compute_score(self, base_weight: float, text: str, is_annotation: bool) -> float:
        """Compute candidate knowledge value score (0.0 to 1.0)."""
        score = base_weight
        text_lower = text.lower()

        # 1. Length Factor
        length = len(text)
        if length >= 80:
            score += 0.12
        elif length >= 40:
            score += 0.06
        elif length < 15:
            score -= 0.10

        # 2. High-value keyword indicators
        matched_indicators = sum(1 for kw in HIGH_VALUE_KEYWORDS if kw in text_lower)
        score += min(matched_indicators * 0.04, 0.15)

        # 3. Chinese explanatory content bonus
        if re.search(r"[\u4e00-\u9fa5]", text):
            score += 0.05

        return round(min(max(score, 0.0), 1.0), 2)


    def check_project_freshness(self) -> List[Dict[str, Any]]:
        """Audit freshness and detect temporal drift between project rules and real codebases."""
        vault_projects_dir = pathlib.Path(__file__).parent.parent / "08-Projects"
        if not vault_projects_dir.is_dir():
            return []

        results = []
        for p_dir in sorted(vault_projects_dir.iterdir()):
            if not p_dir.is_dir() or p_dir.name.startswith("."):
                continue

            proj_name = p_dir.name
            rule_files = list(p_dir.glob("*.md"))
            if not rule_files:
                continue

            # Read newest updated date from rule files
            rule_latest_date = None
            for rf in rule_files:
                try:
                    txt = rf.read_text(encoding="utf-8", errors="replace")
                    m = re.search(r'updated:\s*(\d{4}-\d{2}-\d{2})', txt)
                    if m:
                        d_val = datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
                        if rule_latest_date is None or d_val > rule_latest_date:
                            rule_latest_date = d_val
                except Exception:
                    pass

            if rule_latest_date is None:
                rule_latest_date = datetime.date.fromtimestamp(rule_files[0].stat().st_mtime)

            # Check target repo in {{CODE_ROOT}}
            target_repo = self.code_root / proj_name
            if not target_repo.is_dir():
                target_repo = pathlib.Path("{{CODE_ROOT}}") / proj_name

            repo_exists = target_repo.is_dir()
            repo_latest_date = None
            recent_commits_count = 0

            if repo_exists:
                # Try git log
                try:
                    r = subprocess.run(
                        ["git", "log", "-1", "--format=%cs"],
                        cwd=str(target_repo),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=5
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        repo_latest_date = datetime.datetime.strptime(r.stdout.strip(), "%Y-%m-%d").date()
                except Exception:
                    pass

                if repo_latest_date is None:
                    # Fallback to mtime of files
                    mtimes = [f.stat().st_mtime for f in target_repo.glob("*") if f.is_file()]
                    if mtimes:
                        repo_latest_date = datetime.date.fromtimestamp(max(mtimes))
                    else:
                        repo_latest_date = rule_latest_date

            # Calculate drift
            is_drift = False
            drift_days = 0
            if repo_latest_date and rule_latest_date:
                drift_days = (repo_latest_date - rule_latest_date).days
                if drift_days > 7:
                    is_drift = True

            results.append({
                "project_name": proj_name,
                "repo_path": str(target_repo) if repo_exists else "Not Found",
                "rule_updated": str(rule_latest_date),
                "code_latest": str(repo_latest_date or "Unknown"),
                "drift_days": drift_days,
                "status": "DRIFT_RISK (⚠️ 规则待同步)" if is_drift else "SYNCED (🟢 时效新鲜)"
            })

        return results

    def get_summary(self) -> Dict[str, Any]:
        """Produce structured scan report."""
        top_candidates = self.candidates[: self.limit]
        return {
            "code_root": str(self.code_root),
            "total_candidates_found": len(self.candidates),
            "limit": self.limit,
            "min_score": self.min_score,
            "top_candidates_count": len(top_candidates),
            "candidates": [c.to_dict() for c in top_candidates],
        }

    def print_terminal_report(self) -> None:
        """Render beautiful CLI discovery report."""
        summary = self.get_summary()
        total = summary["total_candidates_found"]
        top_items = self.candidates[: self.limit]

        print("=" * 86)
        print("  🔭 CODING VAULT — PROACTIVE KNOWLEDGE DISCOVERY SCANNER")
        print("=" * 86)
        print(f" Source Repository Root : {self.code_root}")
        print(f" Value Score Threshold  : >= {self.min_score:.2f}")
        print(f" Total Candidates Found : {total} potential knowledge items")
        print(f" Output Ranking Limit   : Top {self.limit} items")
        print(f" Report Generated       : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 86)

        if not top_items:
            print("\n  🔍 No knowledge patterns matching criteria found.\n")
            print("=" * 86)
            return

        print("\n [1] Top Ranked Knowledge Candidates for Ingestion:")
        print(" " + "-" * 84)
        for idx, c in enumerate(top_items, 1):
            try:
                rel_file = str(c.file_path.relative_to(self.code_root)).replace("\\", "/")
            except Exception:
                rel_file = str(c.file_path).replace("\\", "/")

            badge = f"[{c.value_score:.2f}]"
            print(f" {idx:2d}. {badge} {c.category} | 📁 Project: {c.project_name}")
            print(f"     • Source Location : {rel_file}:{c.line_num}")
            print(f"     • Excerpt Snippet : {c.excerpt}")
            print(f"     • Suggested Inbox : 📥 99-Inbox/{c.suggested_inbox_filename}")
            print(f"     • Suggested Target: 🎯 {c.recommended_destination}")
            print(" " + "-" * 84)


        freshness_list = self.check_project_freshness()
        if freshness_list:
            print("\n [3] Project Rules Freshness & Drift Guard (08-Projects/):")
            print(" " + "-" * 84)
            for f in freshness_list:
                status_icon = "🟢" if "SYNCED" in f["status"] else "⚠️"
                print(f"  {status_icon} Project: {f['project_name']:15} | Rule: {f['rule_updated']} | Code: {f['code_latest']} | {f['status']}")
            print(" " + "-" * 84)

        print("\n [2] Actionable Workflow Recommendation (AGENTS.md §9):")
        print("   To promote any candidate into the knowledge base:")
        print("   1. Create `99-Inbox/<suggested_inbox_filename>` with full root cause & reproduction.")
        print("   2. Run `python scripts/vault-inbox-triage.py` to audit and triage.")
        print("   3. Integrate into target standards / rules via Karpathy ingestion flow.")
        print("=" * 86)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vault Proactive Knowledge Discovery Scanner for {{CODE_ROOT}}"
    )
    parser.add_argument(
        "--code-dir",
        type=str,
        default="{{CODE_ROOT}}",
        help="Root path to source code repositories (default: {{CODE_ROOT}})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum candidate items to display (default: 20)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.50,
        help="Minimum knowledge value score filter (default: 0.50)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    parser.add_argument(
        "--freshness",
        action="store_true",
        help="Audit project rules freshness and temporal drift against codebases",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )

    args = parser.parse_args()

    code_path = pathlib.Path(args.code_dir).resolve()
    if not code_path.exists():
        code_path = pathlib.Path("{{CODE_ROOT}}")

    scanner = ProactiveCodeScanner(
        code_root=code_path,
        min_score=args.min_score,
        limit=args.limit,
        verbose=args.verbose,
    )
    scanner.scan()

    if args.json:
        summary = scanner.get_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        scanner.print_terminal_report()

    return 0


if __name__ == "__main__":
    sys.exit(main())
