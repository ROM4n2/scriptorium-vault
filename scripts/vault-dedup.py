#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Content Deduplication & Similarity Detection Script for Coding Vault ({{VAULT_ROOT}})

Features:
  1. Extract normalized plain text from all markdown notes (stripping frontmatter, code blocks, markup).
  2. Compute pairwise similarity using SequenceMatcher.
  3. Filter and report note pairs with similarity >= threshold (default: 0.70 / 70%).
  4. Support CLI flags: --threshold, --json, --verbose, --vault-path.
  5. UTF-8 stdout protection, clean output, exit code 0.
"""

import sys

# Prevent Windows GBK stdout trap
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import datetime
from difflib import SequenceMatcher
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

EXCLUDED_DIRS: Set[str] = {
    ".git",
    ".obsidian",
    ".claudian",
    ".smart-env",
    ".agents",
    ".opencode",
    ".claude",
    ".githooks",
    "node_modules",
    "scripts",
    "copilot",
    "Templates",
    "00-MOC",
    ".trash",
    "11-Agents/logs",
}

ROOT_INFRASTRUCTURE_FILES: Set[str] = {
    "AGENTS.md",
    "README.md",
    "项目档案.md",
    "项目档案-V2.md",
    "MULTI-AGENT-LIMITATIONS-AND-RISKS.md",
    "PHASE4-IMPLEMENTATION-PLAN.md",
    "PHASE5-VALIDATION-PLAN.md",
    "PHASE6-AUTOMATION-PLAN.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".windsurfrules",
}


def is_excluded(path: pathlib.Path, vault_root: pathlib.Path) -> bool:
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    for p in rel.parts:
        if p in EXCLUDED_DIRS:
            return True
    return False


def extract_normalized_text(filepath: pathlib.Path) -> str:
    """Extracts normalized text from note content for similarity comparison."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    # Strip YAML frontmatter
    content = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    # Strip code blocks
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    # Strip wikilinks brackets [[Note|Alias]] -> Alias or Note
    content = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", content)
    # Strip markdown syntax symbols
    content = re.sub(r"[#*`_>~\-+=|]", " ", content)
    # Normalize whitespaces
    content = re.sub(r"\s+", " ", content)
    return content.strip().lower()


def compute_similarity(text1: str, text2: str, threshold: float = 0.0) -> float:
    """Computes similarity ratio between two texts with exact length-bound early pruning."""
    if not text1 or not text2:
        return 0.0
    len1, len2 = len(text1), len(text2)
    # Theoretical maximum ratio of SequenceMatcher is (2 * min(len1, len2)) / (len1 + len2)
    if threshold > 0 and (2.0 * min(len1, len2)) / (len1 + len2) < threshold:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def is_dual_version_pair(file_a: str, file_b: str) -> bool:
    """Check if two files form an RFC 2119 Dual-Version standard/cheatsheet pair."""
    stem_a = pathlib.PurePosixPath(file_a).stem.upper()
    stem_b = pathlib.PurePosixPath(file_b).stem.upper()
    dir_a = pathlib.PurePosixPath(file_a).parent
    dir_b = pathlib.PurePosixPath(file_b).parent
    if dir_a != dir_b:
        return False
    is_std_a, is_cs_a = "STANDARDS" in stem_a, "CHEATSHEET" in stem_a
    is_std_b, is_cs_b = "STANDARDS" in stem_b, "CHEATSHEET" in stem_b
    return (is_std_a and is_cs_b) or (is_cs_a and is_std_b)


def get_dedup_recommendation(sim: float, is_dual: bool) -> str:
    """Provide structured recommendation based on similarity percentage and relation."""
    if is_dual:
        return "ℹ️ RFC 2119 双版本标准/速查对（天然存在章节与内容重叠，属标准架构设计）"
    elif sim >= 0.95:
        return "🔴 极高重复率 (>=95%)：内容几乎完全相同，建议直接合并或删除冗余副本"
    elif sim >= 0.85:
        return "🟠 高度相似 (>=85%)：核心内容高度重合，建议比对差异并提取为共享规范/规则"
    elif sim >= 0.70:
        return "🟡 中度相似 (>=70%)：存在较多重叠段落，建议核查是否存在重复定义并建立关联链接"
    else:
        return "🟢 低度相似 (<70%)：局部概念相近，正常独立笔记"


def find_duplicates(vault_root: pathlib.Path, threshold: float = 0.70) -> List[Dict[str, Any]]:
    files: List[pathlib.Path] = []
    texts: List[str] = []

    for root, _, filenames in os.walk(vault_root):
        root_path = pathlib.Path(root)
        if is_excluded(root_path, vault_root):
            continue
        for f in filenames:
            if not f.endswith(".md") or f in ROOT_INFRASTRUCTURE_FILES:
                continue
            fp = root_path / f
            if is_excluded(fp, vault_root):
                continue
            txt = extract_normalized_text(fp)
            # Only compare notes with meaningful text length (> 80 chars)
            if len(txt) > 80:
                files.append(fp)
                texts.append(txt)

    duplicates: List[Dict[str, Any]] = []
    n = len(files)
    for i in range(n):
        for j in range(i + 1, n):
            sim = compute_similarity(texts[i], texts[j], threshold=threshold)
            if sim >= threshold:
                rel_a = str(files[i].relative_to(vault_root)).replace("\\", "/")
                rel_b = str(files[j].relative_to(vault_root)).replace("\\", "/")
                is_dual = is_dual_version_pair(rel_a, rel_b)
                rec = get_dedup_recommendation(sim, is_dual)
                duplicates.append({
                    "file_a": rel_a,
                    "file_b": rel_b,
                    "similarity": round(sim, 4),
                    "percentage": f"{sim * 100:.1f}%",
                    "is_dual_version": is_dual,
                    "recommendation": rec,
                })

    duplicates.sort(key=lambda x: x["similarity"], reverse=True)
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault Content Deduplication & Similarity Analyzer")
    parser.add_argument("--threshold", type=float, default=0.70, help="Similarity threshold (0.0 - 1.0, default 0.70)")
    parser.add_argument("--vault-path", type=str, default=None, help="Root path of the Obsidian vault")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose comparison details")
    args = parser.parse_args()

    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        script_dir = pathlib.Path(__file__).resolve().parent
        vault_root = script_dir.parent if (script_dir.parent / "AGENTS.md").exists() else pathlib.Path("{{VAULT_ROOT}}").resolve()

    dupes = find_duplicates(vault_root, threshold=args.threshold)

    result = {
        "vault_root": str(vault_root).replace("\\", "/"),
        "timestamp": datetime.datetime.now().isoformat(),
        "threshold": args.threshold,
        "duplicate_count": len(dupes),
        "duplicates": dupes,
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 65)
        print(" 📑 VAULT CONTENT DEDUPLICATION REPORT")
        print("=" * 65)
        print(f" 📂 Vault Root : {vault_root}")
        print(f" 🎯 相似度阈值 : {args.threshold * 100:.0f}%")
        print(f" ⏰ 检查时间   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 65)

        if not dupes:
            print(" ✅ 未发现高于阈值的重复/高相似笔记内容。知识库保持高度紧凑与去重状态！")
        else:
            print(f" ⚠️  发现 {len(dupes)} 对高相似度笔记（相似度 >= {args.threshold * 100:.0f}%）：\n")
            for idx, item in enumerate(dupes, 1):
                dual_tag = " [RFC 双版本]" if item["is_dual_version"] else ""
                print(f"   【#{idx}】相似度: {item['percentage']}{dual_tag}")
                print(f"     ├── 笔记 A: {item['file_a']}")
                print(f"     └── 笔记 B: {item['file_b']}")
                print(f"     💡 建议:   {item['recommendation']}\n")

        print("=" * 65 + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
