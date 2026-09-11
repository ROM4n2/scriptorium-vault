#!/usr/bin/env bash
# ==============================================================================
# Gate 1.5: URL Credential Leak Scanner (staged diff, added lines only)
# Source block: .githooks/pre-commit lines 38-52 (原样拆出，禁止顺手优化)
# Contract: 由 .githooks/pre-commit manifest 路由层调用
#   （hooks/hooks.json, id=gate15-url），以 vault root 为 cwd 执行。
#   set -euo pipefail 承接原 pre-commit 全局头部语义（原行 9）。
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Gate 1.5: URL Credential Leak Scanner (staged diff, added lines only)
# ------------------------------------------------------------------------------
PYTHON_CMD="python"
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
fi

echo "🔍 Gate 1.5: Scanning staged diff for credential-bearing URLs..."
if ! "$PYTHON_CMD" scripts/url_safety.py --git-staged; then
    echo "❌ ERROR: Potential credential-bearing URLs detected in staged changes."
    echo "Commit aborted. Please remove tokens/keys from URLs before committing."
    exit 1
fi
echo "✅ Gate 1.5: URL credential scan passed."
