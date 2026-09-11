#!/usr/bin/env bash
# precompact-session-save.sh — Claude Code PreCompact hook 模板（#4 会话现场保护）
# 作用：compact 前把会话现场快照追加到项目 WORKMEMORY/session-snapshot.md，
#       供 compact 后读回重建现场。安装与分工见 01-Rules/SESSION-SNAPSHOT-PROTECTION.md。
# 配对：恢复侧是 SessionStart(matcher: compact) 的 sessionstart-compact-restore.sh
#       （PostCompact 的 stdout 不进 Claude 上下文，不能承担恢复注入）。
# 约束：UTF-8、追加制、无敏感字面量（密钥扫描兜底）。
set -euo pipefail

# 用法：项目内安装时把 WORKDIR 改为项目根（或由 harness 注入 cwd）。
WORKDIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
WM_DIR="$WORKDIR/WORKMEMORY"
SNAPSHOT="$WM_DIR/session-snapshot.md"
NOW="$(date '+%Y-%m-%d %H:%M')"

mkdir -p "$WM_DIR"

if [ ! -f "$SNAPSHOT" ]; then
  printf '# Session Snapshots（compact 前自动追加，追加制勿删历史）\n\n' > "$SNAPSHOT"
fi

cat >> "$SNAPSHOT" <<EOF

## [$NOW] PreCompact snapshot
- breakpoint: <一句话：正在做什么、做到哪一步>
- 未完成项: <逐条一行；无则写 none>
- 下一动作: <恢复后的第一个具体动作>
- 验证基线: <测试命令与最近通过数；无则写 none>
- 未闭合 WORK_START: <有则写原因与恢复入口，无则写 none>
EOF

echo "[precompact] snapshot appended: $SNAPSHOT"
