#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inbox Triage & Backlog Analysis Script for Coding Vault ({{VAULT_ROOT}})

Features:
  1. Scan 99-Inbox/ for all markdown draft notes.
  2. Parse YAML Frontmatter (title, created, updated, type, tags, status, audience, source).
  3. Calculate draft age in days (from created date in frontmatter, falling back to file mtime).
  4. Categorize age into four standard tiers:
       - >=30d : 建议删除或强制归档 (Critical Stale)
       - >=14d : 建议尽快处理 (High Urgency)
       - >=7d  : 超龄待办 (Medium Urgency / Stale SLA)
       - <7d   : 正常新鲜 (Fresh SLA)
  5. Category triage breakdown: group drafts by lang/, topic/, category/, and source/ tags
     and recommend promotion destinations (03-Languages/, 01-Rules/, 06-Sources/, etc.).
  6. Support CLI flags:
       --days N       : Custom age threshold in days (default: 7).
       --json         : Output structured JSON results.
       --log          : Append audit summary to 11-Agents/logs/{YYYY-MM}.md (month-sharded).
       --vault-path P : Root directory of the vault (default: auto-detected).
       --verbose, -v  : Print detailed triage diagnostic information.
  7. UTF-8 stdout protection for Windows environments and exit code 0.
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

try:
    import yaml
except ImportError:
    yaml = None

# Shared audit-log writer (single source of truth for 11-Agents/logs/{YYYY-MM}.md appends)
from vault_audit import append_audit_row


# Language folder name mapping dictionary (casing alignment with vault conventions)
LANG_DIR_MAP: Dict[str, str] = {
    "go": "GO",
    "golang": "GO",
    "python": "Python",
    "py": "Python",
    "rust": "Rust",
    "rs": "Rust",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "bash": "Bash",
    "sh": "Bash",
    "shell": "Bash",
    "c": "C",
    "cpp": "CPP",
    "c++": "CPP",
    "java": "Java",
    "dart": "Dart",
    "flutter": "Flutter",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "lua": "Lua",
}

# Known Sources directories
SOURCE_TYPE_MAP: Dict[str, str] = {
    "book": "Books",
    "books": "Books",
    "video": "Videos",
    "videos": "Videos",
    "article": "Articles",
    "articles": "Articles",
    "paper": "Papers",
    "papers": "Papers",
}


class DraftItem:
    def __init__(self, file_path: pathlib.Path, vault_root: pathlib.Path):
        self.file_path = file_path.resolve()
        self.vault_root = vault_root.resolve()
        self.rel_path = str(self.file_path.relative_to(self.vault_root)).replace("\\", "/")
        self.filename = self.file_path.name

        self.raw_content: str = ""
        self.frontmatter: Dict[str, Any] = {}
        self.parse_error: Optional[str] = None

        self.title: str = self.file_path.stem
        self.created_date: Optional[datetime.date] = None
        self.updated_date: Optional[datetime.date] = None
        self.note_type: str = "draft"
        self.status: str = "draft"
        self.tags: List[str] = []
        self.audience: str = "both"
        self.source: str = ""
        self.promoted_to: str = ""
        self.size_bytes: int = 0
        self.mtime: datetime.datetime = datetime.datetime.now()

        self.age_days: int = 0
        self.age_source: str = "created"  # "created" or "mtime"
        self.is_overdue: bool = False
        self.age_tier: str = "<7d"
        self.age_action_advice: str = "正常新鲜"

        self.lang_tags: List[str] = []
        self.topic_tags: List[str] = []
        self.category_tags: List[str] = []
        self.source_tags: List[str] = []

        self.recommended_destination: str = "01-Rules/"
        self.recommended_action: str = "按规范评估转入正式目录"
        self.target_files: List[str] = []

        self._load_and_parse()

    def _load_and_parse(self) -> None:
        """Read file and parse frontmatter metadata."""
        try:
            stat = self.file_path.stat()
            self.size_bytes = stat.st_size
            self.mtime = datetime.datetime.fromtimestamp(stat.st_mtime)

            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                self.raw_content = f.read()

            fm_text = self._extract_frontmatter_text(self.raw_content)
            if fm_text:
                if yaml is not None:
                    try:
                        parsed = yaml.safe_load(fm_text)
                        if isinstance(parsed, dict):
                            self.frontmatter = parsed
                    except Exception as ye:
                        self.frontmatter = self._fallback_yaml_parse(fm_text)
                        self.parse_error = f"PyYAML warning: {ye}"
                else:
                    self.frontmatter = self._fallback_yaml_parse(fm_text)
            else:
                self.frontmatter = {}

            # Extract fields
            self.title = str(self.frontmatter.get("title") or self.file_path.stem)
            self.note_type = str(self.frontmatter.get("type") or "draft")
            self.status = str(self.frontmatter.get("status") or "draft")
            self.audience = str(self.frontmatter.get("audience") or "both")
            self.source = str(self.frontmatter.get("source") or "")
            self.promoted_to = str(self.frontmatter.get("promoted_to") or "")

            # Tags normalization
            raw_tags = self.frontmatter.get("tags")
            if isinstance(raw_tags, list):
                self.tags = [str(t).strip() for t in raw_tags if t]
            elif isinstance(raw_tags, str):
                self.tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            else:
                self.tags = []

            # Parse created date
            self.created_date = self._parse_date(self.frontmatter.get("created"))
            self.updated_date = self._parse_date(self.frontmatter.get("updated"))

            # Calculate Age
            today = datetime.date.today()
            if self.created_date:
                self.age_days = (today - self.created_date).days
                self.age_source = "created"
            else:
                # Fallback to file mtime
                self.age_days = (datetime.datetime.now() - self.mtime).days
                self.age_source = "mtime"

            if self.age_days < 0:
                self.age_days = 0

            # Determine age tier & advice
            if self.age_days >= 30:
                self.age_tier = ">=30d"
                self.age_action_advice = "建议删除或强制归档"
            elif self.age_days >= 14:
                self.age_tier = ">=14d"
                self.age_action_advice = "建议尽快处理"
            elif self.age_days >= 7:
                self.age_tier = ">=7d"
                self.age_action_advice = "超龄待办"
            else:
                self.age_tier = "<7d"
                self.age_action_advice = "正常新鲜"

            self._categorize_tags()
            self._determine_recommendations()

        except Exception as e:
            self.parse_error = str(e)

    def _extract_frontmatter_text(self, content: str) -> Optional[str]:
        """Extract YAML block between leading --- delimiters."""
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[1]
        return None

    def _fallback_yaml_parse(self, fm_text: str) -> Dict[str, Any]:
        """Minimal fallback YAML parser when PyYAML is unavailable."""
        result: Dict[str, Any] = {}
        current_key = None
        for line in fm_text.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if line_str.startswith("- ") and current_key:
                val = line_str[2:].strip().strip('"').strip("'")
                if not isinstance(result.get(current_key), list):
                    result[current_key] = []
                result[current_key].append(val)
                continue
            if ":" in line_str:
                k, v = line_str.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                current_key = k
                if v:
                    result[k] = v
                else:
                    result[k] = []
        return result

    def _parse_date(self, val: Any) -> Optional[datetime.date]:
        """Parse various date formats into datetime.date."""
        if not val:
            return None
        if isinstance(val, datetime.date):
            return val
        if isinstance(val, datetime.datetime):
            return val.date()
        val_str = str(val).strip()
        # Match YYYY-MM-DD
        m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", val_str)
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        return None

    def _categorize_tags(self) -> None:
        """Deconstruct tags into namespaces."""
        for t in self.tags:
            tag_lower = t.lower()
            if tag_lower.startswith("lang/"):
                self.lang_tags.append(t[5:])
            elif tag_lower.startswith("topic/"):
                self.topic_tags.append(t[6:])
            elif tag_lower.startswith("category/"):
                self.category_tags.append(t[9:])
            elif tag_lower.startswith("source/"):
                self.source_tags.append(t[7:])
            elif tag_lower.startswith("project/"):
                self.category_tags.append(f"project:{t[8:]}")

    def _determine_recommendations(self) -> None:
        """Determine promotion destination and action based on AGENTS.md §9.5."""
        # Check explicit promoted_to in frontmatter
        if self.promoted_to:
            clean_target = self.promoted_to.strip("[]").replace("\\", "/")
            if clean_target.startswith("01-Rules/"):
                self.recommended_destination = "01-Rules/"
                self.target_files = [clean_target if clean_target.endswith(".md") else f"{clean_target}.md"]
                self.recommended_action = f"已流转至跨语言规则 (`{self.target_files[0]}`)"
                return
            elif clean_target.startswith("03-Languages/"):
                self.recommended_destination = "03-Languages/"
                self.target_files = [clean_target if clean_target.endswith(".md") else f"{clean_target}.md"]
                self.recommended_action = f"已流转至语言双版本规范 (`{self.target_files[0]}`)"
                return

        # 1. Check Language tag
        if self.lang_tags:
            raw_lang = self.lang_tags[0].lower()
            lang_dir = LANG_DIR_MAP.get(raw_lang, raw_lang.capitalize())
            lang_upper = raw_lang.upper()
            self.recommended_destination = f"03-Languages/{lang_dir}/"
            self.target_files = [
                f"03-Languages/{lang_dir}/{lang_upper}-STANDARDS.md",
                f"03-Languages/{lang_dir}/{lang_upper}-CHEATSHEET.md",
            ]
            self.recommended_action = (
                f"提炼整合至 {lang_dir} 语言双版本规范 "
                f"(`{lang_upper}-STANDARDS.md` / `{lang_upper}-CHEATSHEET.md`)"
            )
            return

        # 2. Check Specific Topics -> 01-Rules/ or 03-Languages/
        if any(t in ["git", "symlink", "windows"] for t in self.topic_tags):
            self.recommended_destination = "01-Rules/"
            self.target_files = ["01-Rules/GIT-CONVENTIONS.md"]
            self.recommended_action = "提炼为 Git / 跨平台环境通用规范 (`01-Rules/GIT-CONVENTIONS.md`)"
            return
        if any(t in ["concurrency", "channel", "mutex", "errgroup"] for t in self.topic_tags):
            self.recommended_destination = "01-Rules/"
            self.target_files = ["01-Rules/〔领域专题规范〕.md"]
            self.recommended_action = "提炼为并发工程设计规范 (`01-Rules/〔领域专题规范〕.md`)"
            return
        if any(t in ["error", "error-handling", "panic"] for t in self.topic_tags):
            self.recommended_destination = "01-Rules/"
            self.target_files = ["01-Rules/〔领域专题规范〕.md"]
            self.recommended_action = "提炼为错误处理工程规范 (`01-Rules/〔领域专题规范〕.md`)"
            return

        # 3. Check Tools
        if any("tool" in c.lower() for c in self.category_tags) or any("tool" in t.lower() for t in self.topic_tags):
            tool_name = self.file_path.stem.replace("guide", "").strip("-_").upper()
            self.recommended_destination = "05-Tools/"
            self.target_files = [f"05-Tools/{tool_name}-GUIDE.md"]
            self.recommended_action = f"提炼为专项工具使用指南 (`05-Tools/{tool_name}-GUIDE.md`)"
            return

        # 4. Check Source notes
        sources_root = "06-Sources" if (self.vault_root / "06-Sources").exists() else "03-Sources"
        if self.note_type == "source-notes" or self.source_tags or self.source:
            src_type_raw = self.source_tags[0].lower() if self.source_tags else "articles"
            src_folder = SOURCE_TYPE_MAP.get(src_type_raw, "Articles")
            clean_stem = re.sub(r"^\d{4}-\d{2}-\d{2}-?", "", self.file_path.stem)
            self.recommended_destination = f"{sources_root}/{src_folder}/"
            self.target_files = [f"{sources_root}/{src_folder}/{clean_stem}-notes.md"]
            self.recommended_action = f"归档至外部知识源沉淀目录 (`{sources_root}/{src_folder}/`)"
            return

        # 5. Check Project
        project_tag = next((c.split(":", 1)[1] for c in self.category_tags if c.startswith("project:")), None)
        if project_tag or "project" in self.category_tags:
            p_name = project_tag.capitalize() if project_tag else "Project"
            self.recommended_destination = f"08-Projects/{p_name}/"
            self.target_files = [f"08-Projects/{p_name}/{p_name.upper()}-RULES.md"]
            self.recommended_action = f"沉淀为项目专属工程约束笔记 (`08-Projects/{p_name}/`)"
            return

        # 6. Check Universal Rules / Topics
        if self.topic_tags or "rules" in self.category_tags or self.note_type == "rules":
            topic_str = (self.topic_tags[0] if self.topic_tags else self.file_path.stem).upper().replace("-", "_")
            self.recommended_destination = "01-Rules/"
            self.target_files = [f"01-Rules/{topic_str}.md"]
            self.recommended_action = f"提炼为跨语言通用工程规则 (`01-Rules/{topic_str}.md`)"
            return

        # Default Fallback
        self.recommended_destination = "01-Rules/"
        self.target_files = ["01-Rules/"]
        self.recommended_action = "根据草稿内容价值评估，流转至 01-Rules 或 03-Languages"

    def evaluate_age_threshold(self, threshold_days: int) -> None:
        """Mark overdue status based on given threshold."""
        self.is_overdue = self.age_days >= threshold_days

    def to_dict(self) -> Dict[str, Any]:
        """Convert draft item to dictionary for JSON output."""
        return {
            "filename": self.filename,
            "relative_path": self.rel_path,
            "title": self.title,
            "created": self.created_date.isoformat() if self.created_date else None,
            "updated": self.updated_date.isoformat() if self.updated_date else None,
            "type": self.note_type,
            "status": self.status,
            "tags": self.tags,
            "audience": self.audience,
            "source": self.source,
            "promoted_to": self.promoted_to,
            "size_bytes": self.size_bytes,
            "age_days": self.age_days,
            "age_source": self.age_source,
            "age_tier": self.age_tier,
            "age_action_advice": self.age_action_advice,
            "is_overdue": self.is_overdue,
            "recommended_destination": self.recommended_destination,
            "recommended_action": self.recommended_action,
            "target_files": self.target_files,
            "parse_error": self.parse_error,
        }


class InboxTriageScanner:
    def __init__(self, vault_root: pathlib.Path, threshold_days: int = 7, verbose: bool = False):
        self.vault_root = vault_root.resolve()
        self.threshold_days = threshold_days
        self.verbose = verbose
        self.drafts: List[DraftItem] = []
        self.scan_performed: bool = False

        # Locate inbox directory (single source: 99-Inbox)
        self.inbox_dirs: List[pathlib.Path] = []
        p = self.vault_root / "99-Inbox"
        if p.exists() and p.is_dir():
            self.inbox_dirs.append(p)

    def scan(self) -> List[DraftItem]:
        """Scan Inbox directories for all markdown files."""
        self.drafts = []
        if not self.inbox_dirs:
            self.scan_performed = True
            return self.drafts

        seen_paths: Set[pathlib.Path] = set()
        for inbox_dir in self.inbox_dirs:
            for root, _, files in os.walk(inbox_dir):
                for file in files:
                    if file.endswith(".md"):
                        full_path = (pathlib.Path(root) / file).resolve()
                        if full_path in seen_paths:
                            continue
                        seen_paths.add(full_path)
                        item = DraftItem(full_path, self.vault_root)
                        item.evaluate_age_threshold(self.threshold_days)
                        self.drafts.append(item)

        # Sort by age descending (oldest first)
        self.drafts.sort(key=lambda x: x.age_days, reverse=True)
        self.scan_performed = True
        return self.drafts

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Compute aggregate statistics of inbox drafts."""
        if not self.scan_performed:
            self.scan()

        total = len(self.drafts)
        overdue = [d for d in self.drafts if d.is_overdue]
        fresh = [d for d in self.drafts if not d.is_overdue]

        # Age tier counts
        tier_counts = {
            ">=30d": len([d for d in self.drafts if d.age_days >= 30]),
            ">=14d": len([d for d in self.drafts if 14 <= d.age_days < 30]),
            ">=7d": len([d for d in self.drafts if 7 <= d.age_days < 14]),
            "<7d": len([d for d in self.drafts if d.age_days < 7]),
        }

        # Group by language tags
        lang_groups: Dict[str, List[DraftItem]] = {}
        # Group by topic tags
        topic_groups: Dict[str, List[DraftItem]] = {}
        # Group by destination
        destination_groups: Dict[str, List[DraftItem]] = {}

        for d in self.drafts:
            # Lang groups
            if d.lang_tags:
                for l in d.lang_tags:
                    lang_groups.setdefault(l, []).append(d)
            else:
                lang_groups.setdefault("generic / unassigned", []).append(d)

            # Topic groups
            if d.topic_tags:
                for t in d.topic_tags:
                    topic_groups.setdefault(t, []).append(d)
            else:
                topic_groups.setdefault("general", []).append(d)

            # Destination groups
            destination_groups.setdefault(d.recommended_destination, []).append(d)

        inbox_names = [d.name for d in self.inbox_dirs]
        return {
            "vault_root": str(self.vault_root),
            "inbox_dirs": [str(d) for d in self.inbox_dirs],
            "inbox_names": inbox_names,
            "threshold_days": self.threshold_days,
            "total_drafts": total,
            "overdue_count": len(overdue),
            "fresh_count": len(fresh),
            "tier_breakdown": tier_counts,
            "is_clean": total == 0,
            "has_overdue": len(overdue) > 0,
            "drafts": [d.to_dict() for d in self.drafts],
            "lang_breakdown": {k: len(v) for k, v in lang_groups.items()},
            "topic_breakdown": {k: len(v) for k, v in topic_groups.items()},
            "destination_breakdown": {k: len(v) for k, v in destination_groups.items()},
        }

    def print_terminal_report(self) -> None:
        """Render a clean, formatted terminal summary table with emojis."""
        stats = self.get_summary_statistics()
        total = stats["total_drafts"]
        overdue_cnt = stats["overdue_count"]
        fresh_cnt = stats["fresh_count"]
        threshold = stats["threshold_days"]
        tiers = stats["tier_breakdown"]
        inbox_str = ", ".join(stats["inbox_names"]) if stats["inbox_names"] else "None found"

        print("=" * 86)
        print("  📥 CODING VAULT — INBOX TRIAGE & BACKLOG AUDIT REPORT")
        print("=" * 86)
        print(f" Vault Location      : {self.vault_root}")
        print(f" Target Directory    : {inbox_str}")
        print(f" Age Threshold       : {threshold} Days")
        print(f" Report Generated    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 86)

        # Overview status
        if total == 0:
            status_banner = "✅ INBOX CLEAN — No pending drafts in landing zone"
        elif overdue_cnt == 0:
            status_banner = f"🟢 HEALTHY — {total} active draft(s) within SLA (< {threshold} days)"
        else:
            status_banner = f"⚠️ ACTION REQUIRED — {overdue_cnt} draft(s) exceeding {threshold}-day threshold"

        print(f" Ingestion Health    : {status_banner}")
        print(f" Inventory Metrics   : Total = {total} | Fresh (<{threshold}d) = {fresh_cnt} | Overdue (>={threshold}d) = {overdue_cnt}")
        print(f" Age Tier Breakdown  : >=30d (删除/归档): {tiers['>=30d']} | >=14d (尽快处理): {tiers['>=14d']} | >=7d (超龄待办): {tiers['>=7d']} | <7d (正常新鲜): {tiers['<7d']}")
        print("-" * 86)

        if total == 0:
            print(f"\n  🎉 {inbox_str} landing zone is completely empty! All notes are promoted to stable.\n")
            print("=" * 86)
            return

        # Draft Items Table
        print("\n [1] Inbox Inventory & Age Analysis:")
        print(" " + "-" * 84)
        for idx, d in enumerate(self.drafts, 1):
            if d.age_days >= 30:
                badge = "🔴 >=30d (建议删除或强制归档)"
            elif d.age_days >= 14:
                badge = "🟠 >=14d (建议尽快处理)"
            elif d.age_days >= 7:
                badge = "🟡 >=7d  (超龄待办)"
            else:
                badge = "🟢 <7d   (正常新鲜)"

            age_info = f"{d.age_days:2d}d old (by {d.age_source})"
            created_str = d.created_date.strftime("%Y-%m-%d") if d.created_date else "Unknown"

            print(f" {idx:2d}. [{badge}] {d.filename}")
            print(f"     • Title       : {d.title}")
            print(f"     • Created     : {created_str} ({age_info}) | Size: {d.size_bytes:,} bytes")
            print(f"     • Tags        : {', '.join(d.tags) if d.tags else '(none)'}")
            print(f"     • Status      : {d.status} | Type: {d.note_type} | Audience: {d.audience}")
            if d.promoted_to:
                print(f"     • Promoted To : {d.promoted_to}")
            print(f"     • Destination : 🎯 {d.recommended_destination}")
            print(f"     • Action Plan : 📋 {d.recommended_action}")
            if d.parse_error:
                print(f"     • ⚠️ Notice   : {d.parse_error}")
            print(" " + "-" * 84)

        # Category & Tag Triage Breakdown
        print("\n [2] Category Triage & Promotion Destination Breakdown:")
        dest_map = stats["destination_breakdown"]
        for dest, count in dest_map.items():
            matching = [d for d in self.drafts if d.recommended_destination == dest]
            print(f"   📁 Destination Target: {dest} ({count} draft(s))")
            for m in matching:
                tier_flag = f" [{m.age_tier} - {m.age_action_advice}]"
                print(f"      ↳ 📄 {m.filename} ({m.age_days}d){tier_flag} ➜ {m.recommended_action}")

        # Action advice breakdown
        overdue_drafts = [d for d in self.drafts if d.age_days >= 7]
        if overdue_drafts:
            print("\n [3] ⚠️ Action Required for Stale Drafts (>= 7 Days):")
            print("   According to AGENTS.md §9.5, execute promotion / archival workflow:")
            for od in overdue_drafts:
                print(f"   • Draft: {od.filename} ({od.age_days}d / {od.age_action_advice})")
                print(f"     Target: {od.recommended_destination} | Action: {od.recommended_action}")
        else:
            print("\n [3] ✅ All drafts are within the 7-day SLA (<7d 正常新鲜). Ingestion pipeline is healthy.")

        print("=" * 86)

    def append_review_log(self) -> bool:
        """Append an audit record row to 11-Agents/logs/{YYYY-MM}.md (month-sharded)."""
        stats = self.get_summary_statistics()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        agent_name = "Antigravity (Inbox Triage Specialist)"
        op_type = "Triage & Audit"
        inbox_label = ", ".join(stats["inbox_names"]) if stats["inbox_names"] else "99-Inbox"
        paths_str = f"`{inbox_label}/`, `11-Agents/logs/`（当月分片）"

        total = stats["total_drafts"]
        fresh = stats["fresh_count"]
        overdue = stats["overdue_count"]
        threshold = stats["threshold_days"]
        tiers = stats["tier_breakdown"]

        # Build recommendations bullet
        recs = []
        for dest, cnt in stats["destination_breakdown"].items():
            recs.append(f"{dest} ({cnt} 篇)")
        recs_str = ", ".join(recs) if recs else "无待分流项"

        status_text = "CLEAN (无需干预)" if total == 0 else ("HEALTHY (无超龄草稿)" if overdue == 0 else f"ACTION REQUIRED ({overdue} 篇超龄)")

        draft_list_items = []
        for d in self.drafts:
            draft_list_items.append(f"{d.filename} ({d.age_days}天/{d.age_action_advice} ➜ {d.recommended_destination})")
        draft_str = "; ".join(draft_list_items) if draft_list_items else "无草稿"

        summary_bullets = [
            f"**Inbox 草稿分流与超龄巡检 (Phase 6 Task 1)**：",
            f"1. 草稿总数：{total} 篇（>=30d: {tiers['>=30d']} 篇, >=14d: {tiers['>=14d']} 篇, >=7d: {tiers['>=7d']} 篇, <7d: {tiers['<7d']} 篇）",
            f"2. 分流目标推荐：{recs_str}",
            f"3. 待处理明细：{draft_str}",
            f"4. 巡检状态：{status_text}",
        ]
        summary_cell = "<br>".join(summary_bullets)

        ok, msg = append_audit_row(self.vault_root, agent_name, op_type,
                                   paths_str, summary_cell, timestamp=timestamp)
        print(msg)
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inbox Triage & Backlog Analysis CLI Tool for Coding Vault"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Age threshold in days to flag stale drafts (default: 7)",
    )
    parser.add_argument(
        "--vault-path",
        type=str,
        default=".",
        help="Root path of the Obsidian vault (default: current directory)",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Append triage summary row to 11-Agents/logs/{YYYY-MM}.md (month-sharded)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output triage results in JSON format",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )

    args = parser.parse_args()

    vault_path = pathlib.Path(args.vault_path).resolve()
    if vault_path.name == "scripts" and (vault_path.parent / "AGENTS.md").exists():
        vault_path = vault_path.parent

    scanner = InboxTriageScanner(
        vault_root=vault_path,
        threshold_days=args.days,
        verbose=args.verbose,
    )
    scanner.scan()

    if args.json:
        stats = scanner.get_summary_statistics()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
    else:
        scanner.print_terminal_report()

    if args.log:
        scanner.append_review_log()

    return 0


if __name__ == "__main__":
    sys.exit(main())
