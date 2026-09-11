#!/usr/bin/env bash
# ==============================================================================
# post-write-sync-agents.sh
# Validates AGENTS.md integrity, size limits, multi-agent symlinks,
# and performs Inbox SLA monitoring via vault-inbox-triage.py.
# ==============================================================================

set -euo pipefail

VAULT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$VAULT_DIR"

echo "=== [Hook] Multi-Agent Spec, Symlink & Inbox Verification ==="

TARGET_FILE="AGENTS.md"
MAX_BYTES=10240
ERRORS=0

# 1. Check AGENTS.md existence and size
if [[ ! -f "$TARGET_FILE" ]]; then
  echo "❌ ERROR: $TARGET_FILE does not exist!"
  exit 1
fi

# Get size in bytes
SIZE=$(wc -c < "$TARGET_FILE" | tr -d ' ')
LINES=$(wc -l < "$TARGET_FILE" | tr -d ' ')

if (( SIZE > MAX_BYTES )); then
  echo "⚠️ WARNING: $TARGET_FILE size (${SIZE} bytes) exceeds maximum limit (${MAX_BYTES} bytes / 10KB)!"
  ERRORS=$((ERRORS + 1))
else
  echo "✅ AGENTS.md size check passed: ${SIZE} bytes (${LINES} lines) <= ${MAX_BYTES} bytes"
fi

# 2. Check 5 symlinks
SYMLINKS=("CLAUDE.md" "GEMINI.md" ".cursorrules" ".windsurfrules" "CONVENTIONS.md")

for link in "${SYMLINKS[@]}"; do
  if [[ -L "$link" ]]; then
    target=$(readlink "$link" || true)
    if [[ "$target" == *"AGENTS.md"* ]]; then
      echo "✅ Symlink verified: $link -> $target"
    else
      echo "❌ Symlink invalid target: $link -> $target (expected AGENTS.md)"
      ERRORS=$((ERRORS + 1))
    fi
  elif [[ -f "$link" ]]; then
    # --- Self-heal (Release Plan Task 5) -------------------------------------
    # A Windows clone with core.symlinks=false materializes the symlink blob
    # as a plain text file containing the literal target ("AGENTS.md").
    # Repair ladder:
    #   1) content already identical to AGENTS.md -> valid downgraded form, keep;
    #   2) `git checkout -- <file>` restores a real symlink on symlink-capable
    #      checkouts;
    #   3) otherwise copy AGENTS.md content (downgraded content copy).
    if cmp -s "$TARGET_FILE" "$link"; then
      echo "ℹ️ $link is a regular file with content identical to $TARGET_FILE (downgraded form, kept)"
      continue
    fi
    healed_symlink=0
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      if git checkout -- "$link" 2>/dev/null && [[ -L "$link" ]]; then
        link_target="$(readlink "$link" || true)"
        if [[ "$link_target" == *"AGENTS.md"* ]]; then
          echo "🔧 Self-healed: $link restored as symlink -> $link_target"
          healed_symlink=1
        fi
      fi
    fi
    if (( healed_symlink == 0 )); then
      if cp "$TARGET_FILE" "$link"; then
        echo "⚠️ downgraded to content copy (enable Developer Mode + core.symlinks true for real symlinks): $link"
      else
        echo "❌ ERROR: failed to heal $link (could not copy from $TARGET_FILE)"
        ERRORS=$((ERRORS + 1))
      fi
    fi
  else
    echo "❌ ERROR: $link is missing!"
    ERRORS=$((ERRORS + 1))
  fi
done

# 3. Inbox SLA Monitoring & Backlog Triage
echo "-------------------------------------------------------"
echo "📥 [Hook] Running Inbox SLA & Backlog Triage..."
PYTHON_CMD="python"
if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
fi

if "$PYTHON_CMD" scripts/vault-inbox-triage.py; then
  echo "✅ Inbox triage check completed."
else
  echo "⚠️ WARNING: Inbox triage script encountered an issue."
fi

echo "======================================================="
if (( ERRORS > 0 )); then
  echo "❌ Verification completed with $ERRORS error(s)."
  exit 1
else
  echo "🎉 All agent specifications, symlinks, and inbox monitors are healthy!"
  exit 0
fi

