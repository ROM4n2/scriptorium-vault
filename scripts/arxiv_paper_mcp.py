#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArXiv Computer Science Paper Ingest MCP Server
==============================================
Pure Python stdio JSON-RPC MCP Server.
Allows AI Agents to search, fetch, and structure distributed systems
and AI engineering papers directly into 06-Sources/Papers/.

Tools:
  - search_arxiv: Search papers on ArXiv by keywords (e.g. 'raft consensus', 'lsm tree')
  - get_paper_summary: Fetch full abstract, authors, and summary by ArXiv ID (e.g. '1407.7797')
"""

import sys
import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DEFINITION = [
    {
        "name": "search_arxiv",
        "description": "【检索学术论文】在 ArXiv 上搜索计算机系统、分布式共识或 AI 相关的经典/前沿论文。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "论文搜索关键词，如 'raft consensus', 'distributed lock', 'lsm tree'"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回最多结果数 (默认 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_paper_summary",
        "description": "【提取论文精要】根据 ArXiv 编号（如 '1407.7797'）提取论文元数据、作者与摘要，用于研读笔记沉淀。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "arxiv_id": {
                    "type": "string",
                    "description": "ArXiv 论文编号，如 '1407.7797' 或 URL"
                }
            },
            "required": ["arxiv_id"]
        }
    }
]


def tool_search_arxiv(query: str, max_results: int = 5) -> str:
    try:
        q_enc = urllib.parse.quote(query.strip())
        url = f"http://export.arxiv.org/api/query?search_query=all:{q_enc}&start=0&max_results={max_results}"
        req = urllib.request.Request(url, headers={"User-Agent": "CodingVault-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        if not entries:
            return f"ℹ️ 未在 ArXiv 上找到匹配关键词 '{query}' 的论文。"

        lines = [f"# 📑 ArXiv 论文检索结果: '{query}'\n"]
        for idx, entry in enumerate(entries, 1):
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            paper_id = entry.find("atom:id", ns).text.strip().split("/abs/")[-1]
            published = entry.find("atom:published", ns).text.strip()[:10]
            summary = entry.find("atom:summary", ns).text.strip()[:200].replace("\n", " ") + "..."

            lines.append(f"### [{idx}] {title}")
            lines.append(f"- 🆔 **ArXiv ID**: `{paper_id}` | 📅 **发表日期**: {published}")
            lines.append(f"- 📝 **摘要精简**: {summary}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 检索 ArXiv 失败: {e}"


def tool_get_paper_summary(arxiv_id: str) -> str:
    try:
        clean_id = arxiv_id.strip().split("/")[-1].replace(".pdf", "")
        url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "CodingVault-MCP/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)

        if entry is None:
            return f"❌ 未找到 ID 为 `{clean_id}` 的论文。"

        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        published = entry.find("atom:published", ns).text.strip()[:10]
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
        summary = entry.find("atom:summary", ns).text.strip()

        doc = f"""---
title: "{title}"
created: {published}
updated: {published}
type: source-notes
tags:
  - source/paper
  - topic/distributed-systems
  - category/notes
status: draft
audience: both
source: "ArXiv:{clean_id}"
---

# 📑 {title}

- **ArXiv 编号**: `{clean_id}`
- **作者**: {', '.join(authors[:5])}
- **发表日期**: {published}

---

## 📖 核心摘要 (Abstract)

{summary}

---

## 🔍 关键算法与架构机制 (研读提炼)
- [ ] 核心状态机与转移条件
- [ ] 边界一致性与故障恢复
"""
        return doc
    except Exception as e:
        return f"❌ 提取论文失败: {e}"


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "arxiv-paper-mcp", "version": "1.0.0"}
            }
        }
    elif method in ("notifications/initialized", "initialized"):
        return None
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_DEFINITION}}
    elif method == "tools/call":
        name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            if name == "search_arxiv":
                res = tool_search_arxiv(args.get("query", ""), args.get("max_results", 5))
            elif name == "get_paper_summary":
                res = tool_get_paper_summary(args.get("arxiv_id", ""))
            else:
                res = f"❌ 未知工具: {name}"
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": f"❌ 异常: {e}"}], "isError": True}}
    else:
        if req_id is not None:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return None


def main():
    for line in sys.stdin:
        l = line.strip()
        if not l:
            continue
        try:
            req = json.loads(l)
            resp = handle_request(req)
            if resp:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
