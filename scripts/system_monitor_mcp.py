#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows System, Port & Docker Monitor MCP Server
=================================================
Pure Python stdio JSON-RPC MCP Server.
Provides instant system resource telemetry, port conflict diagnosis,
and Docker/WSL2 status inspections for Windows 11 developers.

Tools:
  - check_port: Find which process/PID is listening on a given port (e.g. 3306, 6379, 8080)
  - get_system_resources: CPU, RAM, and Disk (C:, D:) usage
  - get_wsl_docker_status: Running Docker containers and WSL2 distro states
  - kill_port_process: Safely kill the process occupying a specific port
"""

import sys
import os
import json
import subprocess
import re
import shutil
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

TOOLS_DEFINITION = [
    {
        "name": "check_port",
        "description": "【端口冲突诊断】查询 Windows 本地指定端口（如 3306, 6379, 8080, 5000）被哪个进程/PID 占用，并获取进程名称。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "description": "端口号（如 3306, 6379, 8080）"
                }
            },
            "required": ["port"]
        }
    },
    {
        "name": "get_system_resources",
        "description": "【系统资源透视】获取 Windows 宿主机 CPU 核心数、内存使用率、C 盘与 D 盘剩余空间。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_wsl_docker_status",
        "description": "【容器与 WSL 状态】查询当前运行中的 Docker 容器列表（名称、镜像、端口映射、状态）与 WSL2 发行版运行状态。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "kill_port_process",
        "description": "【释放被占端口】强行终止占用指定端口的进程（如卡死的 node, go run 或 python 进程）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {
                    "type": "integer",
                    "description": "要释放的端口号"
                }
            },
            "required": ["port"]
        }
    }
]


def tool_check_port(port: int) -> str:
    """Check which process is listening on a port."""
    try:
        res = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        lines = res.stdout.splitlines()
        matches = []
        pids = set()

        for line in lines:
            if f":{port} " in line or f":{port}	" in line:
                parts = line.strip().split()
                if len(parts) >= 5 and ("LISTENING" in line or "ESTABLISHED" in line):
                    pid = parts[-1]
                    pids.add(pid)
                    matches.append(line.strip())

        if not pids:
            return f"🟢 端口 {port} 当前处于空闲状态（无进程监听）。"

        report = [f"🚨 端口 {port} 正被以下进程占用：\n"]
        for pid in pids:
            # Get process name via tasklist
            try:
                t_res = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                p_name = t_res.stdout.strip().replace('"', '').split(",")[0] if t_res.stdout.strip() else "Unknown"
            except Exception:
                p_name = "Unknown"
            report.append(f"• **进程名**: `{p_name}` | **PID**: `{pid}`")

        report.append("\n📋 网络连接明细：")
        for m in matches[:5]:
            report.append(f"  `{m}`")

        return "\n".join(report)
    except Exception as e:
        return f"❌ 查询端口失败: {e}"


def tool_get_system_resources() -> str:
    """Get system RAM, CPU, and Disk metrics."""
    try:
        # Disk spaces
        c_stat = shutil.disk_usage("C:\\")
        d_stat = shutil.disk_usage("D:\\") if os.path.exists("D:\\") else None

        c_total_gb = c_stat.total / (1024 ** 3)
        c_free_gb = c_stat.free / (1024 ** 3)
        c_used_pct = ((c_stat.total - c_stat.free) / c_stat.total) * 100

        lines = [
            "# 🖥️ Windows 系统资源监控报告\n",
            f"• **CPU 核心数**: {os.cpu_count()} 逻辑核心",
            f"• **C 盘空间**: 总计 {c_total_gb:.1f} GB | 剩余 {c_free_gb:.1f} GB ({c_used_pct:.1f}% 已用)"
        ]

        if d_stat:
            d_total_gb = d_stat.total / (1024 ** 3)
            d_free_gb = d_stat.free / (1024 ** 3)
            d_used_pct = ((d_stat.total - d_stat.free) / d_stat.total) * 100
            lines.append(f"• **D 盘空间**: 总计 {d_total_gb:.1f} GB | 剩余 {d_free_gb:.1f} GB ({d_used_pct:.1f}% 已用)")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 获取系统资源失败: {e}"


def tool_get_wsl_docker_status() -> str:
    """Check running Docker containers and WSL distros."""
    output = ["# 🐳 Docker 容器与 WSL2 运行状态\n"]

    # 1. Docker ps
    try:
        d_res = subprocess.run(
            ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5
        )
        if d_res.returncode == 0:
            output.append("## 📦 运行中的 Docker 容器：")
            output.append(d_res.stdout.strip() or "当前无运行中的容器。")
        else:
            output.append("⚠️ Docker 服务未响应或未启动。")
    except Exception as e:
        output.append(f"⚠️ Docker 状态检查失败: {e}")

    # 2. WSL list
    try:
        w_res = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True,
            text=True,
            encoding="utf-16le" if sys.platform == "win32" else "utf-8",
            errors="replace",
            timeout=5
        )
        if w_res.stdout.strip():
            output.append("\n## 🐧 WSL2 发行版状态：")
            output.append(w_res.stdout.strip())
    except Exception:
        pass

    return "\n".join(output)


def tool_kill_port_process(port: int) -> str:
    """Kill process listening on specified port."""
    try:
        res = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        pids = set()
        for line in res.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pids.add(parts[-1])

        if not pids:
            return f"ℹ️ 端口 {port} 未被占用，无需终止。"

        killed = []
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            killed.append(pid)

        return f"🎉 成功终止占用端口 {port} 的进程！PID: {', '.join(killed)}"
    except Exception as e:
        return f"❌ 终止进程失败: {e}"


def handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """JSON-RPC handler."""
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "system-monitor-mcp", "version": "1.0.0"}
            }
        }
    elif method == "notifications/initialized" or method == "initialized":
        return None
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_DEFINITION}}
    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        try:
            if tool_name == "check_port":
                res_text = tool_check_port(args.get("port", 0))
            elif tool_name == "get_system_resources":
                res_text = tool_get_system_resources()
            elif tool_name == "get_wsl_docker_status":
                res_text = tool_get_wsl_docker_status()
            elif tool_name == "kill_port_process":
                res_text = tool_kill_port_process(args.get("port", 0))
            else:
                res_text = f"❌ 未知工具: {tool_name}"

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": res_text}]}
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": f"❌ 异常: {e}"}], "isError": True}
            }
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
