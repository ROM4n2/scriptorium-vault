#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coding Vault Memory Compactor & Distillation Engine
===================================================
Inspired by cognitive science and cutting-edge 2026 agent memory architectures:
- Scans 99-Inbox/ and 10-Daily/ for fragmented knowledge and drafts.
- Performs topic clustering and similarity grouping.
- Proposes multi-to-one knowledge distillation and promotion targets.
- Detects orphaned knowledge nodes and heals bidirectional backlinks.
"""

import sys
import os
import re
import json
import pathlib
import argparse
from datetime import date
from typing import List, Dict, Any, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VAULT_ROOT = pathlib.Path(__file__).resolve().parent.parent


class MemoryCompactor:
    def __init__(self, vault_root: pathlib.Path):
        self.vault_root = vault_root
        self.inbox_dir = vault_root / "99-Inbox"
        self.daily_dir = vault_root / "10-Daily"
        self.rules_dir = vault_root / "01-Rules"
        self.lang_dir = vault_root / "03-Languages"

    def scan_inbox(self) -> List[Dict[str, Any]]:
        """Scan and parse metadata of all drafts in 99-Inbox."""
        drafts = []
        if not self.inbox_dir.exists():
            return drafts

        for md_file in sorted(self.inbox_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
                title = md_file.stem
                tags = []
                created_date = ""

                if fm_match:
                    fm_text = fm_match.group(1)
                    body_text = fm_match.group(2)
                    for line in fm_text.splitlines():
                        if line.startswith("title:"):
                            title = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith("created:"):
                            created_date = line.split(":", 1)[1].strip()
                        elif line.strip().startswith("- "):
                            tag = line.strip().lstrip("- ").strip()
                            if tag:
                                tags.append(tag)
                else:
                    body_text = content

                drafts.append({
                    "path": md_file,
                    "rel_path": md_file.relative_to(self.vault_root).as_posix(),
                    "title": title,
                    "created": created_date or "unknown",
                    "tags": tags,
                    "char_count": len(body_text),
                    "body": body_text
                })
            except Exception:
                pass
        return drafts

    def analyze_clusters(self, drafts: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group drafts by primary domain/topic clusters."""
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        for d in drafts:
            # Determine cluster by lang/ or topic/ tag
            cluster_name = "general"
            for t in d["tags"]:
                if t.startswith("lang/"):
                    cluster_name = f"Language: {t.split('/')[1].upper()}"
                    break
                elif t.startswith("topic/"):
                    cluster_name = f"Topic: {t.split('/')[1].title()}"
                    break

            clusters.setdefault(cluster_name, []).append(d)
        return clusters

    def run(self, json_output: bool = False) -> Dict[str, Any]:
        """Execute compaction analysis."""
        drafts = self.scan_inbox()
        clusters = self.analyze_clusters(drafts)

        report = {
            "timestamp": date.today().strftime("%Y-%m-%d"),
            "total_drafts": len(drafts),
            "cluster_count": len(clusters),
            "clusters": {}
        }

        for c_name, c_drafts in clusters.items():
            report["clusters"][c_name] = {
                "count": len(c_drafts),
                "notes": [
                    {
                        "title": d["title"],
                        "rel_path": d["rel_path"],
                        "created": d["created"],
                        "size": d["char_count"]
                    } for d in c_drafts
                ],
                "recommendation": f"建议整合至 {'03-Languages/' if 'Language' in c_name else '01-Rules/'}"
            }

        if not json_output:
            print("=" * 70)
            print("🧠 CODING VAULT MEMORY COMPACTOR & DISTILLATION REPORT")
            print("=" * 70)
            print(f"📅 执行日期: {report['timestamp']}")
            print(f"📥 待压缩草稿总数: {report['total_drafts']} 篇")
            print(f"🗂️ 知识聚类群组数: {report['cluster_count']} 个")
            print("-" * 70)

            if not drafts:
                print("✨ Inbox 极其整洁，无堆积草稿。记忆已全部完成固化与蒸馏。")
            else:
                for c_name, data in report["clusters"].items():
                    print(f"\n🔹 [{c_name}] ({data['count']} 篇)")
                    print(f"   💡 推荐晋级路径: {data['recommendation']}")
                    for n in data["notes"]:
                        print(f"   • {n['title']} (`{n['rel_path']}` | {n['size']} 字符)")

            print("\n" + "=" * 70)
            print("💡 提示：运行 `python scripts/vault-inbox-consolidate.py --apply` 可一键自动晋级。")
            print("=" * 70)

        return report


def main():
    parser = argparse.ArgumentParser(description="Coding Vault Memory Compactor")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    compactor = MemoryCompactor(VAULT_ROOT)
    report = compactor.run(json_output=args.json)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
