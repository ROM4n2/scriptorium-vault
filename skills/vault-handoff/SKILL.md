---
name: vault-handoff
description: Session wrap-up, correction harvesting, knowledge capture, and agent handoff generator. Phase 0 asks "did the user correct you?" and lands corrections into WORKMEMORY/corrections.md; captures breakpoint state, git status, test evidence, and generates a token-budgeted 1-click continuation card (v2 protocol, #3 + #11).
---

# Vault-Handoff: Session Wrap-up & 1-Click Agent Handoff (v2)

Capture working state at the end of a session, land user corrections before they evaporate, harvest uncommitted learnings to `99-Inbox/`, verify clean git status, and generate a token-budgeted continuation card for the next agent session.

> 协议依据：`CROSS-AGENT-MEMORY.md` §2.5（CORRECTION 事件 + corrections.md 账本）。Phase 0 与 Phase 1 的产出都进 `WORKMEMORY/corrections.md` 与 `work.log`（vault 宿主 = `11-Agents/corrections.md`）。

## The 5-Phase Handoff Protocol (v2)

### Phase 0: Corrections Check（必问，先于一切收尾）
Ask the user, verbatim intent: *「这次会话里，你有没有纠正过我的做法、结论或方向？」*
- **有纠正 → MUST 三步**：
  1. 逐条把纠正写入交接卡 `## Corrections` 节（原话 1 行 + 已做/未做）；
  2. 项目 `WORKMEMORY/corrections.md` 账本追加一行（状态 `open`）+ `work.log` 追加 `CORRECTION` 事件（事件头规范见协议 §2.3）；
  3. 已在会话中落实的纠正 → 状态 `resolved`；**禁止**为"好看"把未验证的纠正标成 `closed`。
- **成熟纠正**（非项目特例、可泛化为规则/规范）：导流 `/vault-save` 或 `save_inbox_draft`，账本「蒸馏去向」回填 `vault://<路径>` 后置 `closed`。
- 用户明确说没有 → 记录 "no corrections" 一行即可，不跳过提问本身。

### Phase 1: Karpathy Ingestion Check (Harvest Before Exit)
Ask: *Did this session discover any non-obvious bugs, workarounds, or reusable patterns?*
- If yes: Call `save_inbox_draft` MCP or run `/vault-save` to persist draft in `99-Inbox/`.
- If no: Proceed to Phase 2.

### Phase 2: Ground-Truth State Capture
1. Git Status: `git status --short` & `git log -n 1 --oneline`
2. Test Evidence: Run test suite (`pytest`, `go test ./...`) and record passing count.
3. Ledger Status: Inspect `.vault-exec-ledger.json` for remaining tasks.

### Phase 3: 1-Click Continuation Card Generation（v2 预算分节）
交接卡 MUST 遵守 token 预算：**≈75 词 ≈ 100 token**。必带节压缩到事实句；一切长内容用指针节导流，不内联。

**预算表**：

| 节 | 上限 | 纪律 |
|---|---|---|
| 1. Breakpoint & Git State | ≤5 行 | 分支/commit/测试基线三事实 |
| 2. Completed vs Remaining | ≤10 行 | 一行一项，动词开头 |
| 3. Unresolved Corrections | ≤5 行 | 原话 1 行 + 未做原因；无纠正写 "none" |
| 指针节 | ≤3 条 | 细节/测试输出/长清单 → `10-Daily`、`11-Agents/logs`、文件路径指针 |

```markdown
# 🤝 Agent Handoff & Continuation Card (v2)

### 1. 📍 Breakpoint & Git State
- **Branch / Last Commit**: `{git_branch}` @ `{commit_hash} {commit_message}`
- **Test Baseline**: ✅ {pass_count} passing

### 2. ✅ Completed vs ⏳ Remaining
- ✅ {task}: {one-line evidence}
- ⏳ {next_task}: {one-line next action}

### 3. 🔁 Unresolved Corrections
- {用户原话} → 已做: {…} / 未做: {原因}（账本行已 open）
- none

### 4. 🔗 Pointers（细节不内联，只给指针）
- 测试输出: `10-Daily/{YYYY-MM-DD}.md#L{n}`
- 审计明细: `11-Agents/logs/{YYYY-MM}.md`
- 账本: `WORKMEMORY/corrections.md`（open 条目 MUST 先读）

### 5. 🚀 1-Click Continuation Prompt
> "Resume `{project_name}` at `{next_task}`. Read `WORKMEMORY/INDEX.md`,
> `corrections.md` (open rows first), then `python scripts/vault_exec_state.py resume`."
```

### Phase 4: Output & Exit
Deliver handoff card to user, confirm every Phase 0 correction has a ledger row, and conclude session gracefully.
