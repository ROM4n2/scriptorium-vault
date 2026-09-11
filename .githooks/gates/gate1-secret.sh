#!/usr/bin/env bash
# ==============================================================================
# Gate 1: Secret Key Leak Scanner (staged diff)
# Source block: .githooks/pre-commit lines 16-36 (原样拆出，禁止顺手优化)
# Contract: 由 .githooks/pre-commit manifest 路由层调用
#   （hooks/hooks.json, id=gate1-secret），以 vault root 为 cwd 执行。
#   set -euo pipefail 承接原 pre-commit 全局头部语义（原行 9）。
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Gate 1: Secret Key Leak Scanner
# ------------------------------------------------------------------------------
FORBIDDEN_PATTERN='(sk-[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)[[:space:]]*[=:][[:space:]]*["'"'"'][A-Za-z0-9_./+=-]{8,}["'"'"']|[a-z][a-z0-9+.-]*://[^/[:space:]:@]+:[^/[:space:]:@]+@)'

if git rev-parse --verify HEAD >/dev/null 2>&1; then
    AGAINST=HEAD
else
    # Initial commit: diff against empty tree object
    AGAINST=$(git hash-object -t tree /dev/null)
fi

# ⚠️ 不要用多个 -S 预过滤：git 的多个 -S 是 **AND 语义**（文件必须同时改变
# 所有 token 的出现次数才进入 diff），叠加多个前缀会让本门永远放行（假绿门，
# 2026-09-11 加固测试实测抓出）。全量 staged diff + grep 才是正确姿势。
# 测试目录豁免：scripts/tests/** 的 fixture 刻意包含假凭据（门行为测试本身），
# pathspec 排除后仍会扫描其余全部暂存文件。
MATCHES=$(git diff --cached -p "$AGAINST" -- . ':(exclude)scripts/tests/**' 2>/dev/null | grep -nE "$FORBIDDEN_PATTERN" || true)

if [ -n "$MATCHES" ]; then
    echo "❌ ERROR: Potential secret keys detected in staged changes:"
    echo "$MATCHES"
    echo "Commit aborted. Please remove secret keys before committing."
    exit 1
fi
echo "✅ Gate 1: Secret key leak scan passed."
