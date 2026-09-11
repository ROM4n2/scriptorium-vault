#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite Database Inspector MCP Server
=====================================
Pure Python stdio JSON-RPC MCP Server.
Provides safe, zero-external-dependency introspection and querying for local
.sqlite, .db, and .sqlite3 files on Windows.

Tools:
  - list_tables: List all tables and views in a local SQLite database
  - describe_table: Get schema, column types, and indexes of a table
  - query_sqlite: Execute read-only SELECT queries with formatted Markdown table output
"""

import sys
import os
import json
import sqlite3
import pathlib
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DEFINITION = [
    {
        "name": "list_tables",
        "description": "【列出表名】获取指定 SQLite 数据库文件中的所有表名、视图与记录行数概览。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {
                    "type": "string",
                    "description": "SQLite 数据库文件的本地绝对路径或相对路径（如 '{{USER_HOME}}/.cc-switch/cc-switch.db'）"
                }
            },
            "required": ["db_path"]
        }
    },
    {
        "name": "describe_table",
        "description": "【查看表结构】获取指定 SQLite 表的字段定义、主键、类型与建表 DDL 语句。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "SQLite 数据库文件路径"},
                "table_name": {"type": "string", "description": "表名"}
            },
            "required": ["db_path", "table_name"]
        }
    },
    {
        "name": "query_sqlite",
        "description": "【只读查询数据】在 SQLite 数据库中执行 SELECT 查询，并以 Markdown 表格输出前 N 条结果。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "SQLite 数据库文件路径"},
                "query": {"type": "string", "description": "只读 SQL 查询语句（如 'SELECT * FROM mcp_servers LIMIT 5'）"},
                "limit": {"type": "integer", "description": "最大返回行数 (默认 20)", "default": 20}
            },
            "required": ["db_path", "query"]
        }
    }
]


def tool_list_tables(db_path: str) -> str:
    path = pathlib.Path(db_path).resolve()
    if not path.exists():
        return f"❌ 数据库文件不存在: {db_path}"

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
        rows = cursor.fetchall()

        if not rows:
            conn.close()
            return f"ℹ️ 数据库 `{path.name}` 为空（无用户表）。"

        lines = [f"# 🗄️ SQLite 数据库: `{path.name}`\n", "| 名称 | 类型 | 记录估算 |", "|---|---|---|"]
        for name, obj_type in rows:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM \"{name}\"")
                cnt = cursor.fetchone()[0]
            except Exception:
                cnt = "N/A"
            lines.append(f"| `{name}` | {obj_type} | {cnt} 条 |")

        conn.close()
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 打开数据库失败: {e}"


def tool_describe_table(db_path: str, table_name: str) -> str:
    path = pathlib.Path(db_path).resolve()
    if not path.exists():
        return f"❌ 数据库文件不存在: {db_path}"

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        cursor = conn.cursor()

        cursor.execute(f"PRAGMA table_info(\"{table_name}\")")
        cols = cursor.fetchall()
        if not cols:
            conn.close()
            return f"❌ 表 `{table_name}` 不存在。"

        cursor.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table_name,))
        ddl = cursor.fetchone()
        ddl_text = ddl[0] if ddl and ddl[0] else ""

        lines = [
            f"# 📋 表结构: `{table_name}`\n",
            "| 列序号 | 字段名 | 数据类型 | 非空 | 默认值 | 主键 |",
            "|---|---|---|---|---|---|"
        ]
        for cid, name, c_type, notnull, dflt, pk in cols:
            lines.append(f"| {cid} | **{name}** | `{c_type}` | {'✅' if notnull else '❌'} | `{dflt or 'NULL'}` | {'🔑 PK' if pk else ''} |")

        if ddl_text:
            lines.append(f"\n```sql\n{ddl_text}\n```")

        conn.close()
        return "\n".join(lines)
    except Exception as e:
        return f"❌ 查看结构失败: {e}"


def tool_query_sqlite(db_path: str, query: str, limit: int = 20) -> str:
    path = pathlib.Path(db_path).resolve()
    if not path.exists():
        return f"❌ 数据库文件不存在: {db_path}"

    q_strip = query.strip()
    # Read-only guard
    if not q_strip.upper().startswith("SELECT") and not q_strip.upper().startswith("PRAGMA") and not q_strip.upper().startswith("EXPLAIN"):
        return "❌ 安全限制：仅允许执行只读查询 (SELECT / PRAGMA / EXPLAIN)。"

    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute(q_strip)
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(limit)

        if not rows:
            conn.close()
            return "ℹ️ 查询成功，但结果集为空。"

        lines = [
            "| " + " | ".join(col_names) + " |",
            "| " + " | ".join(["---"] * len(col_names)) + " |"
        ]
        for row in rows:
            row_vals = [str(v).replace("\n", " ") if v is not None else "NULL" for v in row]
            lines.append("| " + " | ".join(row_vals) + " |")

        lines.append(f"\n*共展示 {len(rows)} 条记录 (上限 {limit} 条)*")
        conn.close()
        return "\n".join(lines)
    except Exception as e:
        return f"❌ SQL 执行失败: {e}"


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
                "serverInfo": {"name": "sqlite-inspector-mcp", "version": "1.0.0"}
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
            if name == "list_tables":
                res = tool_list_tables(args.get("db_path", ""))
            elif name == "describe_table":
                res = tool_describe_table(args.get("db_path", ""), args.get("table_name", ""))
            elif name == "query_sqlite":
                res = tool_query_sqlite(args.get("db_path", ""), args.get("query", ""), args.get("limit", 20))
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
