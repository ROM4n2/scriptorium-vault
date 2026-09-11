#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Search Engine & Knowledge Retriever for Coding Vault ({{VAULT_ROOT}})

Pure Python local search engine (zero external dependencies):
  - Index notes in all content dirs (00-MOC, 01-Rules, 02-Fundamentals, 03-Languages, 04-Systems, 05-Tools,
    06-Sources, 07-Academics, 08-Projects, 09-Career, 10-Daily, 99-Inbox, Templates) and root. See 01-Rules/VAULT-STRUCTURE.md §7.1.
  - Parses Markdown sections (H1, H2, H3) and YAML frontmatter tags.
  - Hybrid Search & Semantic Intent Mapping (Synonym Clusters & Bidirectional Expansions):
      * 死锁 / 阻塞 <-> deadlock, channel, mutex, lock, concurrency, context
      * 乱码 / 编码 <-> gbk, utf-8, encoding, stdout, cp936, unicode
      * 泄露 / 安全 <-> leak, memory, secret, key, gitleaks, pre-commit
      * 异常 / 崩溃 <-> panic, crash, exception, error, unwrap, recover
      * 并发 / 异步 <-> concurrency, async, await, goroutine, tokio, taskgroup
      * 测试 / 断言 <-> test, pytest, assert, testing, benchmark
      * 规范 / 速查 <-> standards, rules, cheatsheet, rfc 2119
  - Implements Okapi BM25 keyword ranking with multi-level boosts:
      * Document Title & H1 Boost
      * Section Heading (H2/H3) Boost
      * Frontmatter & Inline Tag Boost
      * Exact Phrase Substring Boost
      * Language Affinity & Coordination Factor Boost
      * Code Block / Identifier Boost
  - Extracts snippet windows centered on matching terms with keyword highlighting.
  - Sub-10ms execution latency with pure Python stdlib.
  - Supports CLI arguments: positional query, --query, --top, --tag, --format (compact|detailed|json), --json, --vault-path.

Usage:
  python scripts/search-vault.py "死锁"
  python scripts/search-vault.py "乱码"
  python scripts/search-vault.py "Go 规范" --json
  python scripts/search-vault.py --query "并发控制" --tag lang/go --format compact
"""

import sys

# Prevent Windows GBK stdout trap (MUST be active at top of script)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import math
import os
import pathlib
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# ANSI color codes
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

KNOWN_LANGUAGES = {
    "go": "lang/go",
    "cpp": "lang/cpp",
    "c++": "lang/cpp",
    "c": "lang/c",
    "golang": "lang/go",
    "python": "lang/python",
    "py": "lang/python",
    "rust": "lang/rust",
    "rs": "lang/rust",
    "typescript": "lang/typescript",
    "ts": "lang/typescript",
    "bash": "lang/bash",
    "sh": "lang/bash",
    "shell": "lang/bash",
}

# ==============================================================================
# Semantic Intent & Engineering Synonym Mapping
# ==============================================================================

INTENT_CLUSTERS = [
    {
        "id": "deadlock_blocking",
        "name": "死锁 / 阻塞",
        "triggers": {
            "死锁", "阻塞", "deadlock", "blocking", "blocked", "mutex", "lock",
            "互斥锁", "读写锁", "rwlock", "channel", "context"
        },
        "expansions": [
            "deadlock", "channel", "mutex", "lock", "concurrency", "context",
            "死锁", "阻塞", "互斥锁", "rwlock"
        ]
    },
    {
        "id": "encoding_mojibake",
        "name": "乱码 / 编码",
        "triggers": {
            "乱码", "编码", "gbk", "utf-8", "utf8", "encoding", "stdout",
            "stderr", "cp936", "unicode", "codecs", "reconfigure", "decode", "encode"
        },
        "expansions": [
            "gbk", "utf-8", "encoding", "stdout", "cp936", "unicode",
            "乱码", "编码", "reconfigure", "stderr"
        ]
    },
    {
        "id": "leak_security",
        "name": "泄露 / 安全",
        "triggers": {
            "泄露", "安全", "leak", "memory", "secret", "key", "gitleaks",
            "pre-commit", "precommit", "token", "password", "防泄露", "credential",
            "私钥", "密钥"
        },
        "expansions": [
            "leak", "memory", "secret", "key", "gitleaks", "pre-commit",
            "泄露", "安全", "防泄露", "token", "密钥"
        ]
    },
    {
        "id": "panic_exception",
        "name": "异常 / 崩溃",
        "triggers": {
            "异常", "崩溃", "panic", "crash", "exception", "error", "unwrap",
            "recover", "错误", "错误处理", "fail", "failure"
        },
        "expansions": [
            "panic", "crash", "exception", "error", "unwrap", "recover",
            "异常", "崩溃", "错误处理"
        ]
    },
    {
        "id": "concurrency_async",
        "name": "并发 / 异步",
        "triggers": {
            "并发", "异步", "concurrency", "async", "await", "goroutine",
            "tokio", "taskgroup", "channel", "协程", "multithreading", "errgroup", "thread"
        },
        "expansions": [
            "concurrency", "async", "await", "goroutine", "tokio", "taskgroup",
            "并发", "异步", "channel", "errgroup", "协程"
        ]
    },
    {
        "id": "testing_assert",
        "name": "测试 / 断言",
        "triggers": {
            "测试", "断言", "test", "pytest", "assert", "testing", "benchmark",
            "unittest", "单元测试", "基准测试", "assertions"
        },
        "expansions": [
            "test", "pytest", "assert", "testing", "benchmark",
            "测试", "断言", "单元测试"
        ]
    },
    {
        "id": "spec_standards",
        "name": "规范 / 速查",
        "triggers": {
            "规范", "速查", "标准", "standards", "rules", "cheatsheet", "rfc 2119",
            "must", "should", "约束", "准则"
        },
        "expansions": [
            "standards", "rules", "cheatsheet", "rfc 2119", "must", "should",
            "规范", "速查", "约束", "准则", "原则"
        ]
    },
    {
        "id": "career_interview",
        "name": "面试 / 高频考点",
        "triggers": {
            "面试", "高频考点", "面经", "答辩", "考点", "扣分点", "自我介绍",
            "interview", "bagu", "career", "gmp", "worker pool", "workerpool",
            "三次握手", "四次挥手", "time_wait", "mvcc", "readview"
        },
        "expansions": [
            "interview", "exam-prep", "gmp", "worker pool", "concurrency", "net/http",
            "面试", "高频考点", "背诵", "答辩", "复盘", "mvcc", "readview"
        ]
    },
    {
        "id": "frontend_ui_design",
        "name": "前端 / 界面设计",
        "triggers": {
            "前端", "ui", "ux", "design", "css", "html", "界面", "样式",
            "组件", "动效", "排版", "色彩", "token", "社论", "同质化", "前端设计"
        },
        "expansions": [
            "frontend", "ui", "design", "css", "前端", "界面", "样式",
            "组件", "token", "typography", "前端设计"
        ]
    },
    {
        "id": "system_design",
        "name": "系统设计 / 高并发",
        "triggers": {
            "系统设计", "分布式", "高并发", "架构设计",
            "system design", "architecture", "ddia"
        },
        "expansions": [
            "system design", "architecture",
            "系统设计", "高并发", "架构设计", "ddia"
        ]
    },
    {
        "id": "algorithm_patterns",
        "name": "算法 / 刷题套路",
        "triggers": {
            "算法", "刷题", "双指针", "滑动窗口", "单调栈", "动态规划", "二分", "回溯",
            "algorithm", "leetcode", "sliding window", "dp", "monotonic"
        },
        "expansions": [
            "algorithm", "leetcode", "sliding window", "dp", "two pointers",
            "算法", "滑动窗口", "双指针", "单调栈", "动态规划", "套路"
        ]
    },
    {
        "id": "cloud_native_db",
        "name": "云原生 / 数据库与容器",
        "triggers": {
            "docker", "k8s", "kubernetes", "sql", "建表", "schema", "deployment",
            "container", "容器", "镜像", "dockerfile"
        },
        "expansions": [
            "docker", "k8s", "kubernetes", "sql", "schema", "deployment",
            "容器", "建表", "镜像", "dockerfile"
        ]
    }
]


def supports_color() -> bool:
    """Check if color output is supported."""
    if os.environ.get("NO_COLOR") == "1":
        return False
    return sys.stdout.isatty() or os.environ.get("FORCE_COLOR") == "1"


def colorize(text: str, color_code: str) -> str:
    return f"{color_code}{text}{ANSI_RESET}" if supports_color() else text


def highlight_terms(text: str, terms: List[str]) -> str:
    """Highlight query terms in text using ANSI colors."""
    if not supports_color() or not terms:
        return text

    valid_terms = sorted([re.escape(t) for t in set(terms) if len(t.strip()) > 0], key=len, reverse=True)
    if not valid_terms:
        return text

    pattern = re.compile(f"({'|'.join(valid_terms)})", re.IGNORECASE)
    return pattern.sub(f"{ANSI_BOLD}{ANSI_YELLOW}\\1{ANSI_RESET}", text)


# ==============================================================================
# Tokenizer & Text Utilities
# ==============================================================================

class TokenInfo:
    def __init__(
        self,
        text: str,
        weight: float = 1.0,
        is_core: bool = True,
        is_expanded: bool = False,
        cluster_id: Optional[str] = None
    ):
        self.text = text
        self.weight = weight
        self.is_core = is_core
        self.is_expanded = is_expanded
        self.cluster_id = cluster_id

    def __repr__(self) -> str:
        return f"TokenInfo({self.text!r}, w={self.weight}, core={self.is_core}, exp={self.is_expanded})"


def tokenize(text: str) -> List[str]:
    """Tokenize text for indexing (returns flat list of indexed tokens)."""
    if not text:
        return []

    text_lower = text.lower()
    tokens: List[str] = []

    # 1. English words, numbers, code identifiers
    words = re.findall(r"[a-z0-9_\.\-]+", text_lower)
    for w in words:
        tokens.append(w)
        parts = re.split(r"[\._\-]+", w)
        if len(parts) > 1:
            for p in parts:
                if len(p) > 1 and p != w:
                    tokens.append(p)

    # 2. Chinese phrases & characters (n-grams)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", text_lower)
    for run in chinese_runs:
        tokens.append(run)
        if len(run) == 4:
            tokens.append(run[:2])
            tokens.append(run[2:])
        elif len(run) > 2:
            for i in range(len(run) - 1):
                tokens.append(run[i:i + 2])
        for ch in run:
            tokens.append(ch)

    return tokens


def parse_query_terms(query: str) -> Tuple[List[TokenInfo], Optional[str], List[str], List[Dict[str, Any]]]:
    """
    Parse a search query into weighted tokens, detect target language,
    and expand tokens using the Semantic Intent Map.

    Returns:
        tokens: List[TokenInfo]
        detected_lang: Optional[str]
        intent_expansion_words: List[str]
        active_clusters: List[Dict[str, Any]]
    """
    query_lower = query.lower().strip()
    tokens: List[TokenInfo] = []
    seen: Set[str] = set()

    def add_token(t: str, weight: float, is_core: bool, is_expanded: bool = False, cluster_id: Optional[str] = None):
        t_clean = t.strip()
        if t_clean and t_clean not in seen:
            seen.add(t_clean)
            tokens.append(TokenInfo(
                text=t_clean,
                weight=weight,
                is_core=is_core,
                is_expanded=is_expanded,
                cluster_id=cluster_id
            ))

    # 1. Detect language intent
    detected_lang: Optional[str] = None
    for word, lang_tag in KNOWN_LANGUAGES.items():
        if re.search(rf"\b{re.escape(word)}\b", query_lower) or word in query_lower.split():
            detected_lang = lang_tag
            break

    # 2. Direct English words
    words = re.findall(r"[a-z0-9_\.\-]+", query_lower)
    for w in words:
        add_token(w, weight=1.5, is_core=True)
        parts = re.split(r"[\._\-]+", w)
        if len(parts) > 1:
            for p in parts:
                if len(p) > 1:
                    add_token(p, weight=1.0, is_core=False)

    # 3. Direct Chinese runs & n-grams
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", query_lower)
    for run in chinese_runs:
        add_token(run, weight=1.8, is_core=True)
        if len(run) == 4:
            add_token(run[:2], weight=1.3, is_core=True)
            add_token(run[2:], weight=1.3, is_core=True)
        elif len(run) > 2:
            for i in range(len(run) - 1):
                add_token(run[i:i + 2], weight=1.2, is_core=True)
        for ch in run:
            add_token(ch, weight=0.3, is_core=False)

    # 4. Semantic Intent Mapping & Query Expansion
    active_clusters: List[Dict[str, Any]] = []
    intent_expansion_words: List[str] = []

    # Check for triggers in raw query and all extracted core tokens
    tokens_to_match = set(words + chinese_runs + [query_lower])

    for cluster in INTENT_CLUSTERS:
        cluster_triggered = False
        triggers = cluster["triggers"]

        # Check if any trigger word is present in query or tokens
        for trig in triggers:
            trig_lower = trig.lower()
            if trig_lower in query_lower or any(trig_lower == t or trig_lower in t for t in tokens_to_match):
                cluster_triggered = True
                break

        if cluster_triggered:
            active_clusters.append(cluster)
            cluster_id = cluster["id"]
            for exp in cluster["expansions"]:
                exp_clean = exp.strip().lower()
                if exp_clean not in seen:
                    intent_expansion_words.append(exp_clean)
                    # Expanded synonym tokens get a boost weight (0.9) to enrich recall
                    add_token(
                        exp_clean,
                        weight=0.9,
                        is_core=False,
                        is_expanded=True,
                        cluster_id=cluster_id
                    )

    return tokens, detected_lang, intent_expansion_words, active_clusters


# ==============================================================================
# Markdown Document & Section Parser
# ==============================================================================

class MarkdownSection:
    def __init__(self, heading: str, level: int, start_line: int, lines: List[str]):
        self.heading = heading.strip()
        self.level = level
        self.start_line = start_line
        self.lines = lines
        self.content = "\n".join(lines)
        self.clean_heading = re.sub(r"^#+\s*", "", self.heading).strip()
        self.tokens = tokenize(self.clean_heading + " " + self.content)
        self.token_count = len(self.tokens)


class MarkdownDocument:
    def __init__(self, path: pathlib.Path, rel_path: str, raw_content: str):
        self.path = path
        self.rel_path = rel_path.replace("\\", "/")
        self.raw_content = raw_content
        self.frontmatter: Dict[str, Any] = {}
        self.title: str = path.stem
        self.tags: List[str] = []
        self.sections: List[MarkdownSection] = []
        self.doc_tokens: List[str] = []

        self._parse()

    def _parse(self):
        lines = self.raw_content.splitlines()
        body_start_line = 0

        # Parse YAML frontmatter
        if len(lines) > 1 and lines[0].strip() == "---":
            fm_lines = []
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    body_start_line = idx + 1
                    break
                fm_lines.append(lines[idx])

            self._parse_frontmatter(fm_lines)

        # Extract title from frontmatter
        if "title" in self.frontmatter and self.frontmatter["title"]:
            self.title = str(self.frontmatter["title"]).strip("\"'")

        # Extract inline tags in body
        inline_tags = re.findall(r"(?:^|\s)#([a-zA-Z0-9_\-\/]+)", self.raw_content)
        for t in inline_tags:
            t_clean = t.lower()
            if "/" in t_clean and t_clean not in self.tags:
                self.tags.append(t_clean)

        # Parse sections (H1, H2, H3)
        current_heading = self.title
        current_level = 1
        current_start_line = body_start_line + 1
        current_lines: List[str] = []

        heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$")

        for idx in range(body_start_line, len(lines)):
            line = lines[idx]
            match = heading_pattern.match(line)
            if match:
                if current_lines or current_heading:
                    self.sections.append(MarkdownSection(
                        heading=current_heading,
                        level=current_level,
                        start_line=current_start_line,
                        lines=current_lines
                    ))
                current_level = len(match.group(1))
                current_heading = line.strip()
                current_start_line = idx + 1
                current_lines = []
                if current_level == 1 and self.title == self.path.stem:
                    self.title = match.group(2).strip()
            else:
                current_lines.append(line)

        # Save final section
        if current_lines or current_heading:
            self.sections.append(MarkdownSection(
                heading=current_heading,
                level=current_level,
                start_line=current_start_line,
                lines=current_lines
            ))

        # Extract 1-Hop Wikilinks
        raw_links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', self.raw_content)
        self.wikilinks = list(dict.fromkeys(l.strip() for l in raw_links if l.strip()))

        # Overall document tokens
        all_tokens = tokenize(self.title + " " + " ".join(self.tags))
        for sec in self.sections:
            all_tokens.extend(sec.tokens)
        self.doc_tokens = all_tokens

    def _parse_frontmatter(self, fm_lines: List[str]):
        """Simple YAML frontmatter parser without external dependencies."""
        current_key = None
        for line in fm_lines:
            line_str = line.rstrip()
            if not line_str or line_str.startswith("#"):
                continue

            list_match = re.match(r"^\s*-\s+(.+)$", line_str)
            if list_match and current_key:
                val = list_match.group(1).strip().strip("\"'")
                if current_key not in self.frontmatter or not isinstance(self.frontmatter[current_key], list):
                    self.frontmatter[current_key] = []
                self.frontmatter[current_key].append(val)
                continue

            kv_match = re.match(r"^([a-zA-Z0-9_\-]+)\s*:\s*(.*)$", line_str)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                val = kv_match.group(2).strip()
                current_key = key

                if val.startswith("[") and val.endswith("]"):
                    items = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
                    self.frontmatter[key] = items
                elif val == "" or val == "|":
                    self.frontmatter[key] = []
                else:
                    self.frontmatter[key] = val.strip("\"'")

        # Extract tags from frontmatter
        if "tags" in self.frontmatter:
            raw_tags = self.frontmatter["tags"]
            if isinstance(raw_tags, list):
                for t in raw_tags:
                    if isinstance(t, str):
                        clean_t = t.strip().lstrip("#").lower()
                        if clean_t and clean_t not in self.tags:
                            self.tags.append(clean_t)
            elif isinstance(raw_tags, str):
                for t in re.split(r"[,\s]+", raw_tags):
                    clean_t = t.strip().lstrip("#").lower()
                    if clean_t and clean_t not in self.tags:
                        self.tags.append(clean_t)


# ==============================================================================
# Search Index & BM25 Ranking Engine
# ==============================================================================

class SearchHit:
    def __init__(
        self,
        doc: MarkdownDocument,
        best_section: Optional[MarkdownSection],
        score: float,
        snippet: str,
        line_number: int
    ):
        self.doc = doc
        self.best_section = best_section
        self.score = score
        self.snippet = snippet
        self.line_number = line_number

    def to_dict(self, rank: int) -> Dict[str, Any]:
        return {
            "rank": rank,
            "title": self.doc.title,
            "path": self.doc.rel_path,
            "score": round(self.score, 2),
            "tags": self.doc.tags,
            "section": self.best_section.heading if self.best_section else self.doc.title,
            "line_number": self.line_number,
            "snippet": self.snippet,
            "one_hop_links": self.doc.wikilinks
        }


class VaultSearchEngine:
    # Content dirs per 01-Rules/VAULT-STRUCTURE.md §7.1. Excluded: 11-Agents (audit), copilot/scripts (tool assets).
    TARGET_DIRS = [
        "00-MOC", "01-Rules", "02-Fundamentals", "03-Languages", "04-Systems", "05-Tools",
        "06-Sources", "07-Academics", "08-Projects", "09-Career", "10-Daily", "99-Inbox", "Templates",
    ]
    ALLOWED_EXTENSIONS = {".md", ".go", ".py", ".ts", ".rs", ".sh", ".sql", ".yaml", ".yml"}

    def __init__(self, vault_root: pathlib.Path):
        self.vault_root = vault_root.resolve()
        self.documents: List[MarkdownDocument] = []
        self.total_docs = 0
        self.avg_doc_len = 0.0
        self.df: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}

        self._build_index()

    def _build_index(self):
        """Index all markdown files across the target directories and root."""
        doc_list: List[MarkdownDocument] = []
        total_tokens = 0
        seen_real_paths: Set[str] = set()

        def try_index_file(file_path: pathlib.Path):
            nonlocal total_tokens
            try:
                real_p = str(file_path.resolve())
                if real_p in seen_real_paths:
                    return
                seen_real_paths.add(real_p)

                rel_path = file_path.relative_to(self.vault_root).as_posix()
                content = file_path.read_text(encoding="utf-8", errors="replace")
                doc = MarkdownDocument(file_path, rel_path, content)
                doc_list.append(doc)
                total_tokens += len(doc.doc_tokens)
            except Exception:
                pass

        # Index target directories
        for target_dir in self.TARGET_DIRS:
            dir_path = self.vault_root / target_dir
            if not dir_path.is_dir():
                continue

            for file_path in dir_path.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in self.ALLOWED_EXTENSIONS:
                    try_index_file(file_path)

        # Index root markdown files (e.g. AGENTS.md, README.md)
        for root_file in self.vault_root.glob("*.md"):
            if root_file.is_file():
                try_index_file(root_file)

        self.documents = doc_list
        self.total_docs = len(doc_list)
        self.avg_doc_len = (total_tokens / self.total_docs) if self.total_docs > 0 else 1.0

        # Calculate document frequencies and IDF
        term_doc_set: Dict[str, Set[int]] = {}
        for doc_id, doc in enumerate(self.documents):
            unique_terms = set(doc.doc_tokens)
            for t in unique_terms:
                if t not in term_doc_set:
                    term_doc_set[t] = set()
                term_doc_set[t].add(doc_id)

        for t, doc_ids in term_doc_set.items():
            self.df[t] = len(doc_ids)
            self.idf[t] = math.log(1.0 + (self.total_docs - len(doc_ids) + 0.5) / (len(doc_ids) + 0.5))

    def _extract_snippet(
        self,
        section: MarkdownSection,
        query_terms: List[str],
        raw_query: str
    ) -> Tuple[str, int]:
        """Extract a clean 3~5 line context window around the most relevant match."""
        lines = section.lines
        if not lines:
            return section.heading, section.start_line

        best_line_idx = 0
        max_line_score = -1.0

        raw_query_lower = raw_query.lower().strip()
        lower_terms = [t.lower() for t in query_terms if len(t) > 0]

        for idx, line in enumerate(lines):
            line_lower = line.lower()
            line_score = 0.0

            # Exact phrase bonus
            if raw_query_lower in line_lower and len(raw_query_lower) > 1:
                line_score += 10.0

            # Term presence
            for t in lower_terms:
                if t in line_lower:
                    line_score += 2.5 if len(t) > 1 else 0.5

            if line.strip().startswith("---") or not line.strip():
                line_score -= 1.0

            if line_score > max_line_score:
                max_line_score = line_score
                best_line_idx = idx

        start_idx = max(0, best_line_idx - 1)
        end_idx = min(len(lines), best_line_idx + 3)

        snippet_lines = []
        for i in range(start_idx, end_idx):
            line = lines[i].rstrip()
            if line:
                snippet_lines.append(line)

        snippet_text = "\n".join(snippet_lines) if snippet_lines else section.clean_heading
        match_line_num = section.start_line + best_line_idx

        return snippet_text, match_line_num

    def search(
        self,
        query: str,
        top_k: int = 3,
        tag_filter: Optional[str] = None
    ) -> Tuple[List[SearchHit], float, List[str]]:
        """
        Execute search query and return ranked SearchHits along with elapsed time in ms
        and intent expansion words.
        """
        start_time = time.perf_counter()

        if not query or not query.strip():
            return [], (time.perf_counter() - start_time) * 1000.0, []

        raw_query = query.strip()
        raw_query_lower = raw_query.lower()
        token_infos, detected_lang, intent_expansion_words, active_clusters = parse_query_terms(raw_query)
        core_tokens = [ti.text for ti in token_infos if ti.is_core]

        tag_filter_clean = tag_filter.strip().lstrip("#").lower() if tag_filter else None

        hits: List[SearchHit] = []

        k1 = 1.5
        b = 0.75

        for doc in self.documents:
            # Tag filter check
            if tag_filter_clean:
                has_tag = any(tag_filter_clean in t for t in doc.tags)
                if not has_tag:
                    continue

            title_lower = doc.title.lower()
            rel_path_lower = doc.rel_path.lower()
            tags_str = " ".join(doc.tags).lower()
            doc_all_text = title_lower + " " + tags_str + " " + doc.raw_content.lower()

            # Coordination / Concept Coverage check
            # For each core token, it is considered matched if the token itself is present
            # OR if any term from its active intent cluster is present in the document.
            matched_core = 0
            for ct in core_tokens:
                if ct in doc_all_text:
                    matched_core += 1
                else:
                    # Check intent clusters
                    cluster_matched = False
                    for cluster in active_clusters:
                        if ct in cluster["triggers"] or ct in cluster["expansions"]:
                            if any(exp.lower() in doc_all_text for exp in cluster["expansions"]):
                                cluster_matched = True
                                break
                    if cluster_matched:
                        matched_core += 1

            coverage_ratio = (matched_core / len(core_tokens)) if core_tokens else 1.0

            # Language Affinity and Mismatch check
            lang_affinity_multiplier = 1.0
            doc_lang_tags = [t for t in doc.tags if t.startswith("lang/")]
            is_target_lang_doc = False

            if detected_lang:
                target_lang_name = detected_lang.replace("lang/", "")
                if detected_lang in doc.tags or target_lang_name in title_lower or f"/{target_lang_name.upper()}/" in doc.rel_path.upper():
                    lang_affinity_multiplier = 2.5
                    is_target_lang_doc = True
                elif doc_lang_tags:
                    # Mismatched language doc (e.g. asking for Go, but this is Rust/Python)
                    lang_affinity_multiplier = 0.2
                else:
                    # General / Hub doc without specific target language tag
                    lang_affinity_multiplier = 0.6

            # Document-level Title & Tag boosts
            doc_title_boost = 0.0
            doc_tag_boost = 0.0

            if raw_query_lower in title_lower:
                doc_title_boost += 20.0

            for ti in token_infos:
                t = ti.text
                w = ti.weight
                idf_val = self.idf.get(t, 1.0)
                if t in title_lower:
                    doc_title_boost += idf_val * w * 3.5
                if t in tags_str:
                    doc_tag_boost += idf_val * w * 4.0

            best_sec: Optional[MarkdownSection] = None
            best_sec_score = 0.0

            for sec in doc.sections:
                sec_score = 0.0
                sec_heading_lower = sec.clean_heading.lower()
                sec_content_lower = sec.content.lower()

                # 1. BM25 on section content & heading
                sec_term_counts: Dict[str, int] = {}
                for token in sec.tokens:
                    sec_term_counts[token] = sec_term_counts.get(token, 0) + 1

                for ti in token_infos:
                    t = ti.text
                    w = ti.weight
                    tf = sec_term_counts.get(t, 0)
                    if tf > 0:
                        idf_val = self.idf.get(t, 1.0)
                        numerator = tf * (k1 + 1.0)
                        denominator = tf + k1 * (1.0 - b + b * (sec.token_count / self.avg_doc_len))
                        sec_score += w * idf_val * (numerator / denominator)

                # 2. Heading boost
                if raw_query_lower in sec_heading_lower and len(raw_query_lower) > 1:
                    sec_score += 15.0
                for ti in token_infos:
                    t = ti.text
                    if t in sec_heading_lower:
                        sec_score += self.idf.get(t, 1.0) * ti.weight * 3.0

                # 3. Exact phrase match in section content
                if raw_query_lower in sec_content_lower and len(raw_query_lower) > 1:
                    sec_score += 8.0

                # 4. Code block bonus
                if "```" in sec.content and any(ti.text in sec_content_lower for ti in token_infos if len(ti.text) > 2):
                    sec_score += 2.0

                if sec_score > best_sec_score:
                    best_sec_score = sec_score
                    best_sec = sec

            # Combine score with coverage and language affinity
            raw_doc_score = best_sec_score + doc_title_boost + doc_tag_boost

            # Boost official standards / cheatsheets for the target language
            if is_target_lang_doc and doc.frontmatter.get("type") in ["standards", "cheatsheet"]:
                raw_doc_score += 8.0

            # Apply coordination factor
            final_score = raw_doc_score * (coverage_ratio ** 1.5) * lang_affinity_multiplier

            # Bonus if 100% core concepts matched
            if coverage_ratio >= 0.99:
                final_score += 5.0

            if final_score > 0.5:
                target_sec = best_sec if best_sec else (doc.sections[0] if doc.sections else None)
                all_highlight_terms = [ti.text for ti in token_infos]
                if target_sec:
                    snippet, line_num = self._extract_snippet(target_sec, all_highlight_terms, raw_query)
                else:
                    snippet, line_num = doc.title, 1

                hits.append(SearchHit(
                    doc=doc,
                    best_section=target_sec,
                    score=final_score,
                    snippet=snippet,
                    line_number=line_num
                ))

        # Sort by score descending
        hits.sort(key=lambda h: h.score, reverse=True)
        top_hits = hits[:top_k]

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return top_hits, elapsed_ms, intent_expansion_words


# ==============================================================================
# CLI Formatters & Output Handlers
# ==============================================================================

def print_detailed_output(
    hits: List[SearchHit],
    query: str,
    top_k: int,
    elapsed_ms: float,
    total_docs: int,
    intent_expansions: List[str],
    tag_filter: Optional[str] = None
):
    """Format and print beautiful detailed terminal output with box frames."""
    width = 78
    print(colorize("═" * width, ANSI_CYAN))
    filter_info = f" | Tag: {colorize(tag_filter, ANSI_YELLOW)}" if tag_filter else ""
    print(f" {colorize('🔍 Vault Search:', ANSI_BOLD + ANSI_WHITE)} \"{colorize(query, ANSI_GREEN)}\"{filter_info}")

    if intent_expansions:
        exp_preview = ", ".join(intent_expansions[:8])
        if len(intent_expansions) > 8:
            exp_preview += f" (+{len(intent_expansions) - 8} more)"
        print(f" {colorize('⚡ Intent Expansions:', ANSI_DIM)} {colorize(exp_preview, ANSI_DIM)}")

    print(colorize("═" * width, ANSI_CYAN))

    if not hits:
        print()
        print(colorize("  ⚠️  No relevant notes found matching query.", ANSI_YELLOW))
        print(f"     Try broadening terms or removing tag filters.")
        print()
    else:
        for idx, hit in enumerate(hits, 1):
            print()
            score_badge = colorize(f"[{hit.score:.2f} pts]", ANSI_DIM)
            rank_str = colorize(f"[{idx}]", ANSI_BOLD + ANSI_CYAN)
            title_str = colorize(hit.doc.title, ANSI_BOLD + ANSI_WHITE)
            print(f" {rank_str} {title_str} {score_badge}")

            path_str = colorize(hit.doc.rel_path, ANSI_BLUE)
            line_str = colorize(f":{hit.line_number}", ANSI_DIM)
            print(f"     📁 {path_str}{line_str}")

            if hit.doc.tags:
                tags_formatted = ", ".join(colorize(t, ANSI_MAGENTA) for t in hit.doc.tags)
                print(f"     🏷️  {tags_formatted}")

            if hit.best_section:
                sec_head = hit.best_section.heading.strip()
                print(f"     📍 {colorize(sec_head, ANSI_YELLOW)}")

            if hit.doc.wikilinks:
                links_preview = "  ".join(colorize(f"[[{l}]]", ANSI_CYAN) for l in hit.doc.wikilinks[:4])
                print(f"     🔗 {colorize('1-Hop 关联:', ANSI_BOLD)} {links_preview}")

            print(colorize("     " + "─" * (width - 5), ANSI_DIM))
            token_infos, _, _, _ = parse_query_terms(query)
            highlight_words = [ti.text for ti in token_infos] + [query]
            highlighted_snippet = highlight_terms(hit.snippet, highlight_words)
            for s_line in highlighted_snippet.splitlines():
                print(f"     │ {s_line}")
            print(colorize("     " + "─" * (width - 5), ANSI_DIM))

    print()
    footer_text = f"⚡ Found {len(hits)} hit(s) in {elapsed_ms:.1f}ms | Scanned {total_docs} files across Vault"
    print(colorize(footer_text, ANSI_DIM))
    print(colorize("═" * width, ANSI_CYAN))


def print_compact_output(
    hits: List[SearchHit],
    query: str,
    top_k: int,
    elapsed_ms: float,
    total_docs: int,
    intent_expansions: List[str],
    tag_filter: Optional[str] = None
):
    """Format and print clean, concise compact terminal output."""
    filter_info = f" [Tag: {tag_filter}]" if tag_filter else ""
    header = f"🔍 Search: \"{query}\"{filter_info} | {len(hits)} hit(s) ({elapsed_ms:.1f}ms / {total_docs} docs)"
    print(colorize(header, ANSI_BOLD + ANSI_CYAN))
    print(colorize("─" * min(80, len(header) + 10), ANSI_DIM))

    if not hits:
        print(colorize("  ⚠️  No relevant notes found.", ANSI_YELLOW))
        return

    for idx, hit in enumerate(hits, 1):
        rank_badge = colorize(f"[{idx}]", ANSI_BOLD + ANSI_CYAN)
        title_part = colorize(hit.doc.title, ANSI_BOLD + ANSI_WHITE)
        score_part = colorize(f"({hit.score:.1f} pts)", ANSI_DIM)
        print(f"{rank_badge} {title_part} {score_part}")

        path_part = colorize(f"{hit.doc.rel_path}:{hit.line_number}", ANSI_BLUE)
        sec_name = hit.best_section.clean_heading if hit.best_section else ""
        sec_part = f" | 📍 {colorize(sec_name, ANSI_YELLOW)}" if sec_name else ""
        tag_part = f" | 🏷️ {', '.join(hit.doc.tags)}" if hit.doc.tags else ""
        print(f"    📁 {path_part}{sec_part}{tag_part}")

        # Snippet preview (first 1~2 non-empty lines)
        snip_lines = [line.strip() for line in hit.snippet.splitlines() if line.strip() and not line.startswith("---")]
        if snip_lines:
            snip_preview = " ".join(snip_lines[:2])
            if len(snip_preview) > 140:
                snip_preview = snip_preview[:137] + "..."
            print(f"    💬 {colorize(snip_preview, ANSI_DIM)}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Local Search Engine & Knowledge Retriever for Coding Vault ({{VAULT_ROOT}})",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python scripts/search-vault.py "死锁"
  python scripts/search-vault.py "乱码"
  python scripts/search-vault.py "Go 规范" --json
  python scripts/search-vault.py --query "并发控制" --tag lang/go --format compact
"""
    )

    parser.add_argument("positional_query", nargs="?", default="", help="Search query string (positional)")
    parser.add_argument("-q", "--query", default="", help="Search query string (flag)")
    parser.add_argument("-n", "--top", type=int, default=3, help="Maximum number of results to return (default: 3)")
    parser.add_argument("-t", "--tag", default=None, help="Filter results by tag (e.g. lang/python, topic/error-handling)")
    parser.add_argument(
        "--format",
        choices=["compact", "detailed", "json"],
        default="detailed",
        help="Output format: detailed (default), compact, or json"
    )
    parser.add_argument("--json", action="store_true", help="Equivalent to --format json")
    parser.add_argument("-p", "--vault-path", default=None, help="Path to vault root directory")

    args = parser.parse_args()

    # Determine query
    query = (args.query or args.positional_query or "").strip()

    # Determine output format
    output_format = "json" if args.json else args.format

    # Determine vault path
    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        vault_root = pathlib.Path(__file__).resolve().parent.parent

    if not vault_root.is_dir():
        if output_format == "json":
            print(json.dumps({"error": f"Invalid vault path: {vault_root}"}, ensure_ascii=False))
        else:
            print(f"❌ Error: Invalid vault path: {vault_root}", file=sys.stderr)
        sys.exit(1)

    # Initialize Search Engine
    engine = VaultSearchEngine(vault_root)

    # If query is completely empty, show help or blank results
    if not query:
        if output_format == "json":
            print(json.dumps({
                "query": "",
                "tag_filter": args.tag,
                "format": "json",
                "total_hits": 0,
                "top": args.top,
                "execution_time_ms": 0.0,
                "searched_files": engine.total_docs,
                "intent_expansions": [],
                "results": []
            }, ensure_ascii=False, indent=2))
        else:
            parser.print_help()
        sys.exit(0)

    # Execute Search
    hits, elapsed_ms, intent_expansions = engine.search(query=query, top_k=args.top, tag_filter=args.tag)

    if output_format == "json":
        result_obj = {
            "query": query,
            "tag_filter": args.tag,
            "format": "json",
            "total_hits": len(hits),
            "top": args.top,
            "execution_time_ms": round(elapsed_ms, 2),
            "searched_files": engine.total_docs,
            "intent_expansions": intent_expansions,
            "results": [hit.to_dict(rank=idx) for idx, hit in enumerate(hits, 1)]
        }
        print(json.dumps(result_obj, ensure_ascii=False, indent=2))
    elif output_format == "compact":
        print_compact_output(
            hits=hits,
            query=query,
            top_k=args.top,
            elapsed_ms=elapsed_ms,
            total_docs=engine.total_docs,
            intent_expansions=intent_expansions,
            tag_filter=args.tag
        )
    else:  # detailed
        print_detailed_output(
            hits=hits,
            query=query,
            top_k=args.top,
            elapsed_ms=elapsed_ms,
            total_docs=engine.total_docs,
            intent_expansions=intent_expansions,
            tag_filter=args.tag
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
