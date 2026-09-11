---
title: "会话现场保护清单 (Session Snapshot Protection, compact 前后必做)"
created: 2026-09-09
updated: 2026-09-09
type: rules
audience: both
tags:
  - category/rules
  - topic/memory
  - topic/multi-agent
status: active
authority: synthetic
claim_risk: medium
review_status: unreviewed
---

# 会话现场保护清单 (Session Snapshot Protection)

> **定位**：长会话 compact（上下文压缩）或意外中断前后的**现场保全纪律**（#4）。compact 会裁剪早期上下文——未落盘的 breakpoint、未完成项、未闭合 `WORK_START` 一旦只存在于上下文里，压缩后即失。规则本体本文件；协议宿主 [[01-Rules/CROSS-AGENT-MEMORY]]。

## 1. Compact / 中断前必做（MUST）

1. **现场快照落盘**：breakpoint（正在做什么/做到哪一步）、未完成项、下一动作、关键命令与验证基线 → 写入项目 `WORKMEMORY/`（`work.log` 追加 `NOTE` 事件 + 必要时 `NOTES-<slug>.md`），或记忆层日档。
2. **状态闭合检查**：未闭合 `WORK_START` 要么补 `WORK_END`，要么在快照中显式声明"未闭合原因 + 恢复入口"。
3. **交接卡更新**：若手头有进行中的交接卡/执行账本（`.vault-exec-ledger.json`），同步其状态字段。
4. **纠正账本先行**：未落地的用户纠正 MUST 先按 [[01-Rules/CROSS-AGENT-MEMORY]] §2.5 写入 `corrections.md`（open 行）——纠正比上下文更容易在压缩中蒸发。

## 2. Compact / 恢复后必做（MUST）

1. **读回记忆层**：重读项目 `WORKMEMORY/INDEX.md` → `work.log` 尾 50 行 → `corrections.md` 顶部 open 条目（读序同协议 §2.1）。
2. **现场重建**：从快照恢复 breakpoint 与下一动作，向用户确认后再继续，**MUST NOT** 凭压缩后的残缺记忆即行动手。
3. **勘误补记**：发现 compact 前漏写的状态，补 `NOTE` 勘误（不回改历史，协议 §2.7）。

> **注入口的硬约束（2026-09-09 核实）**：Claude Code 只有 `UserPromptSubmit` / `SessionStart` / `PostModelSwitch` 的纯文本 stdout 会注入 Claude 上下文；**`PostCompact` 无决策控制，其 stdout 仅进 debug log**。因此"压缩后自动恢复现场" MUST 走 `SessionStart` + `matcher: "compact"` 注入 `additionalContext`；用 `PostCompact` 打印恢复提醒 = 空转（`PostCompact` 只能做写盘等副作用）。

## 3. Harness 分工（现状实测）

| Harness | 机制 | 备注 |
|---|---|---|
| CodeBuddy | `.codebuddy/memory` 内建强制日档（工作记忆自动落盘） | **默认实现已就位**，无需额外 hook |
| Claude Code | 内建无强制工作记忆 → **`PreCompact` 存盘 + `SessionStart(compact)` 注入恢复** | 模板：`precompact-session-save.sh` / `sessionstart-compact-restore.sh` |
| 其余（Codex/OpenCode/Gemini） | 无 compact 事件钩子 | 依赖 §1/§2 手工纪律 + 项目级 anchor |

Claude Code 安装（写入 `~/.claude/settings.json` 的 hooks 段；`${CLAUDE_PROJECT_DIR}` 为项目根）：

```json
{
  "hooks": {
    "PreCompact": [
      { "matcher": "auto", "hooks": [
        { "type": "command",
          "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/precompact-session-save.sh" } ]
      }
    ],
    "SessionStart": [
      { "matcher": "compact", "hooks": [
        { "type": "command",
          "command": "bash ${CLAUDE_PROJECT_DIR}/.claude/hooks/sessionstart-compact-restore.sh" } ]
      }
    ]
  }
}
```

- `PreCompact` **可阻断压缩**（exit 2 或 `decision: "block"`）；本模板只做存盘副作用，始终 exit 0。
- 恢复脚本的 stdout **MUST 只有一行 JSON**（多余 echo 会破坏解析）：`{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}`。

## 4. 试点说明（🚦 用户确认门）

`{{CODE_ROOT}}` 项目应用 hook 模板属**跨仓库试点**，MUST 经用户逐项目确认后安装（预 compact hook 写项目内 `WORKMEMORY/session-snapshot.md`）；本文件仅钉协议与模板，不自动铺开。

**首个试点：示例项目（2026-09-09，用户确认后安装并验证）**

- 安装位置（项目级、随仓库可共享）：`{{PROJECT_PATH}}\.claude\settings.json` + `.claude\hooks\{precompact-session-save.sh, sessionstart-compact-restore.sh}`（已 `chmod +x`）。
- 验证：`settings.json` JSON 合法且含 `PreCompact`/`SessionStart(compact)` 两组；两脚本 `bash -n` 语法通过；**存盘→恢复端到端实跑通过**（precompact 追加快照 → restore 输出单行合法 JSON 并读回快照内容）；测试用占位快照已删除，真实 compact 时自动生成。
- 遗留建议（未执行，待用户决定）：①`WORKMEMORY/session-snapshot.md` 属工作态产物，可考虑加入 示例项目 `.gitignore`；②按协议 §2.5，示例项目 尚缺 `WORKMEMORY/corrections.md` 账本（模板 `Templates/workmemory/corrections.md` 可直接复制）；③试点产物尚未 git 提交（跨仓库提交需用户确认）。
