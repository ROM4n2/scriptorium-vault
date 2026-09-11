#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vault Knowledge Graph Analyzer for Coding Vault ({{VAULT_ROOT}})

Features:
  1. Build directed graph of vault notes based on [[...]] wikilinks.
  2. Compute graph connectivity metrics:
     - Total nodes & edges
     - In-degree & out-degree distributions
     - Isolated islands (in=0, out=0)
     - Core hub notes (in-degree >= 5)
     - Weakly connected leaf notes (in+out <= 1)
  3. Support CLI flags: --json, --verbose, --vault-path.
  4. Output clean terminal dashboard, exit code 0.
"""

import sys

# Prevent Windows GBK stdout trap
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
from collections import defaultdict
import datetime
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


def analyze_graph(vault_root: pathlib.Path) -> Dict[str, Any]:
    notes: List[pathlib.Path] = []
    rel_map: Dict[pathlib.Path, str] = {}
    stem_map: Dict[str, List[pathlib.Path]] = defaultdict(list)
    all_dirs_rel: Set[str] = set()

    for root, _, files in os.walk(vault_root):
        root_p = pathlib.Path(root)
        if is_excluded(root_p, vault_root):
            continue
        try:
            rel_d = str(root_p.relative_to(vault_root)).replace("\\", "/")
            if rel_d != ".":
                all_dirs_rel.add(rel_d)
                all_dirs_rel.add(f"{rel_d}/")
        except ValueError:
            pass

        for f in files:
            fp = root_p / f
            if is_excluded(fp, vault_root):
                continue
            if f.endswith(".md") and f not in ROOT_INFRASTRUCTURE_FILES:
                notes.append(fp)
                rel_str = str(fp.relative_to(vault_root)).replace("\\", "/")
                rel_map[fp] = rel_str
                stem_map[fp.stem].append(fp)

    # Adjacency list: node -> set of target nodes
    graph: Dict[str, Set[str]] = defaultdict(set)
    in_degree: Dict[str, int] = defaultdict(int)
    out_degree: Dict[str, int] = defaultdict(int)

    all_node_keys = set(rel_map.values())

    wikilink_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

    for fp in notes:
        src_key = rel_map[fp]
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Strip code blocks and inline code
        content_clean = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
        content_clean = re.sub(r"`[^`]*`", "", content_clean)

        for match in wikilink_re.finditer(content_clean):
            raw = match.group(1).strip()
            if not raw or raw.startswith("-f ") or raw.startswith("$") or raw == "...":
                continue
            # Strip heading anchor
            link_target = raw.split("#")[0].strip().replace("\\", "/")
            if not link_target:
                continue

            target_key: Optional[str] = None
            # Check relative to vault root
            cand = link_target if link_target.endswith(".md") else f"{link_target}.md"
            if cand in all_node_keys:
                target_key = cand
            # Check stem
            elif link_target in stem_map and stem_map[link_target]:
                matched_fp = stem_map[link_target][0]
                target_key = rel_map.get(matched_fp)
            # Check relative to file dir
            else:
                rel_cand = (fp.parent / cand).resolve()
                try:
                    rel_cand_str = str(rel_cand.relative_to(vault_root)).replace("\\", "/")
                    if rel_cand_str in all_node_keys:
                        target_key = rel_cand_str
                except ValueError:
                    pass

            if target_key and target_key != src_key:
                if target_key not in graph[src_key]:
                    graph[src_key].add(target_key)
                    out_degree[src_key] += 1
                    in_degree[target_key] += 1

    total_edges = sum(len(targets) for targets in graph.values())
    islands = [n for n in all_node_keys if in_degree[n] == 0 and out_degree[n] == 0]
    hubs = sorted(
        [{"note": n, "in_degree": in_degree[n], "out_degree": out_degree[n]} for n in all_node_keys if in_degree[n] >= 4 or out_degree[n] >= 6],
        key=lambda x: -(x["in_degree"] + x["out_degree"])
    )
    weak = [n for n in all_node_keys if in_degree[n] + out_degree[n] <= 1 and n not in islands]

    return {
        "vault_root": str(vault_root).replace("\\", "/"),
        "timestamp": datetime.datetime.now().isoformat(),
        "total_nodes": len(all_node_keys),
        "total_edges": total_edges,
        "island_count": len(islands),
        "islands": sorted(islands),
        "hub_count": len(hubs),
        "hubs": hubs,
        "weak_count": len(weak),
        "weak_nodes": sorted(weak),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault Knowledge Graph Analyzer")
    parser.add_argument("--vault-path", type=str, default=None, help="Root path of the Obsidian vault")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print verbose details")
    args = parser.parse_args()

    if args.vault_path:
        vault_root = pathlib.Path(args.vault_path).resolve()
    else:
        script_dir = pathlib.Path(__file__).resolve().parent
        vault_root = script_dir.parent if (script_dir.parent / "AGENTS.md").exists() else pathlib.Path("{{VAULT_ROOT}}").resolve()

    data = analyze_graph(vault_root)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 65)
        print(" 🕸️  VAULT KNOWLEDGE GRAPH ANALYSIS")
        print("=" * 65)
        print(f" 📂 Vault Root : {data['vault_root']}")
        print(f" ⏰ 分析时间   : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 65)
        print(" 📊 图谱拓扑指标 (Graph Topology):")
        print(f"   • 总节点数 (Nodes)     : {data['total_nodes']} 篇笔记")
        print(f"   • 总连接边 (Edges)     : {data['total_edges']} 条引用关系")
        print(f"   • 核心枢纽节点 (Hubs)  : {data['hub_count']} 个 (高入链/出链)")
        print(f"   • 孤岛节点 (Islands)   : {data['island_count']} 个 (0 引用 / 0 被引)")
        print(f"   • 弱连接节点 (Weak)    : {data['weak_count']} 个 (连接度 <= 1)")

        if data["hubs"]:
            print("\n 🌟 核心知识枢纽 TOP 5 (Top Hubs):")
            for h in data["hubs"][:5]:
                print(f"   • {h['note']} (← {h['in_degree']} 入链, → {h['out_degree']} 出链)")

        if data["islands"]:
            print("\n 🏝️  孤岛节点列表 (Islands):")
            for isl in data["islands"][:5]:
                print(f"   • {isl}")
        else:
            print("\n ✅ 全库无孤岛节点，所有笔记均有效链接于知识网络中！")

        print("=" * 65 + "\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
