#!/usr/bin/env bash
# sessionstart-compact-restore.sh — Claude Code SessionStart(matcher: compact) hook 模板
# 作用：compact 后的会话起点，把现场快照与纠正账本 open 条目作为 additionalContext
#       注入 Claude 上下文（这是唯一能真正"恢复现场"的注入口）。
#
# 为什么不是 PostCompact：PostCompact 无决策控制，其 stdout 只进 debug log、
#       不会注入 Claude 上下文（官方文档：仅 UserPromptSubmit / SessionStart /
#       PostModelSwitch 的纯文本 stdout 会进上下文）。用 PostCompact 打印提醒 = 空转。
#
# 约束：stdout MUST 只有一行 JSON（多余 echo 会破坏 JSON 解析）；无 jq 依赖；UTF-8。
set -euo pipefail

WORKDIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
WM_DIR="$WORKDIR/WORKMEMORY"
SNAPSHOT="$WM_DIR/session-snapshot.md"
CORRECTIONS="$WM_DIR/corrections.md"

# 从 stdin 读事件 JSON（失败不影响注入；本 hook 不依赖其内容）
read -r -t 2 _EVENT_JSON || true

_escape() {  # 转义为 JSON 字符串内容：\ " 换行
  sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk '{printf "%s\\n", $0}'
}

CTX=""
if [ -f "$SNAPSHOT" ]; then
  CTX="【compact 前现场快照（最近片段）】\\n$(tail -30 "$SNAPSHOT" | _escape)"
else
  CTX="【无现场快照】$SNAPSHOT 不存在——按 WORKMEMORY 读序重建现场并向用户确认后再动手。"
fi

if [ -f "$CORRECTIONS" ]; then
  OPEN_ROWS="$(grep -E '^\|.*\|[[:space:]]*open[[:space:]]*\|' "$CORRECTIONS" | tail -10 | _escape)"
  if [ -n "$OPEN_ROWS" ]; then
    CTX="$CTX\\n\\n【纠正账本 open 条目（本会话 MUST NOT 重犯）】\\n$OPEN_ROWS"
  fi
fi

CTX="$CTX\\n\\n【恢复纪律】1. 读 WORKMEMORY/INDEX.md → work.log 尾 50 行；2. 复述 breakpoint 与下一动作，经用户确认后继续。"

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$CTX"
