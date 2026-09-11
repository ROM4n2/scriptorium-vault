#!/usr/bin/env bash
# ==============================================================================
# Gate 2: Vault Quality & Dual-Version AST Alignment Checker (--strict)
# Source block: .githooks/pre-commit lines 54-65 (原样拆出，禁止顺手优化)
# Contract: 由 .githooks/pre-commit manifest 路由层调用
#   （hooks/hooks.json, id=gate2-quality），以 vault root 为 cwd 执行。
#   set -euo pipefail 承接原 pre-commit 全局头部语义（原行 9）。
#   注：$PYTHON_CMD 探测块原位于 Gate 1.5 块（pre-commit 行 41-44），Gate 2
#   拆出后为独立进程，故按原样复制该块（python3 优先，语义零变化）。
# ==============================================================================

set -euo pipefail

PYTHON_CMD="python"
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
fi

# ------------------------------------------------------------------------------
# Gate 2: Vault Quality & Dual-Version AST Alignment Checker (--strict)
# ------------------------------------------------------------------------------
echo "🔍 Gate 2: Running Vault Quality Check & AST Alignment Gatekeeper..."

if ! "$PYTHON_CMD" scripts/vault-quality-check.py --strict; then
    echo "❌ ERROR: Vault quality checks or AST section alignment failed."
    echo "Commit aborted. Please resolve quality issues before committing."
    exit 1
fi

echo "✅ Gate 2: Quality & AST alignment check passed (--strict)."
