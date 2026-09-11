---
name: vault-exec
description: Execute implementation plans by dispatching fresh, context-isolated specialized subagents per task (TDD, Refactorer, DBA) with maker-checker review cycles and zero main-thread context bloat.
---

# Vault-Exec: Multi-Subagent Deterministic Execution Engine

Execute implementation plans (`implementation_plan.md` or `.vault-exec-ledger.json`) by dispatching fresh, context-isolated subagents for each task.

## 🚨 The Zero-Edit Iron Rule (HARD GATE)
> **The Orchestrator Main Thread MUST NOT directly edit, write, or modify production source code.**
> All implementation and refactoring code MUST be written by fresh, context-isolated subagents dispatched via `invoke_subagent`.
> The Orchestrator's ONLY responsibility is: **State Tracking (Ledger), Task Dispatching, Maker-Checker Review Oversight, and Git Commits**.

---

## The 3-Stage Task Execution State Machine

For each Task in the implementation plan, follow this strict loop:

```
           ┌──────────────────────────────────────────────┐
           │ Task Initialized (Status: IN_PROGRESS)      │
           └──────────────────────┬───────────────────────┘
                                  │
                                  ▼
      [Step 1: Dispatch Implementer Subagent (TDD Builder)]
      invoke_subagent(
        TypeName="self",
        Role="TDD Implementer - Task N",
        Prompt="<Self-contained prompt scaffold from vault-plan>"
      )
                                  │
                                  ▼ (Implementer returns code & test evidence)
      [Step 2: Dispatch Reviewer Subagent (Maker-Checker)]
      invoke_subagent(
        TypeName="self",
        Role="Code Reviewer - Task N",
        Prompt="Review Task N against 01-Rules/ and verify all tests pass..."
      )
                                  │
                                  ▼ (Reviewer returns PASS / REVISE)
      [Step 3: Atomic Git Commit & Ledger Update]
      - git commit -m "feat(<scope>): complete Task N"
      - python scripts/vault_exec_state.py complete-task --task-id <id> --reviewer PASS
```

---

## Standard Subagent Dispatch Scaffolds

### Implementer Scaffold (`子代理-TDD-BUILDER`):
```python
invoke_subagent(
    Subagents=[{
        "TypeName": "self",
        "Role": f"TDD Builder - Task {task_id}",
        "Prompt": f"""You are the dedicated TDD Builder for Task {task_id}: {task_name}.
Goal: Implement the required logic strictly following The Iron Law of TDD.

Target Files:
- Create: {target_files}
- Tests: {test_files}

Instructions:
1. Write the failing test first (RED).
2. Run test command: `{test_cmd}` and verify failure.
3. Implement minimal code to pass (GREEN).
4. Refactor with Guard Clauses (max 2 levels indentation).
5. Output final summary with test execution evidence.
"""
    }]
)
```

### Reviewer Scaffold (`子代理复核角色（自建）`):
```python
invoke_subagent(
    Subagents=[{
        "TypeName": "self",
        "Role": f"Reviewer - Task {task_id}",
        "Prompt": f"""You are the independent Code Reviewer for Task {task_id}.
Inspect the changes made by the Implementer against Coding Vault standards:
1. Verify all unit tests pass with zero failures.
2. Check for race conditions, Goroutine leaks, unhandled errors, and YAGNI violations.
3. Return: 'PASS' if clean, or 'REVISE: <reasons>' if fixes are required.
"""
    }]
)
```

---

## State Ledger CLI Integration
- Initialize Ledger: `python scripts/vault_exec_state.py init --plan-file implementation_plan.md`
- Start Task: `python scripts/vault_exec_state.py start-task --task-id Task-1`
- Complete Task: `python scripts/vault_exec_state.py complete-task --task-id Task-1 --commit <hash> --reviewer PASS`
- Resume from Breakpoint: `python scripts/vault_exec_state.py resume`
- Inspect Pipeline Status: `python scripts/vault_exec_state.py status`
