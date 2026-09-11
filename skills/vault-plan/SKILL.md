---
name: vault-plan
description: (Priority 1) Draft structured, bite-sized implementation plans bound to Coding Vault standards, templates, and specialized subagents. Primary planner for all coding projects. Use when asked to make a plan, write implementation plan, break down tasks, or after /vault-spark and /vault-grill.
---

# Vault-Anchored Implementation Planning

Produce structured, deterministic implementation plans where every task includes an actionable **Subagent Prompt Scaffold** ready for direct consumption by `/vault-exec`.

## Core Planning Invariants (MUST)
1. **Scope Check**: If spec covers multiple independent subsystems, break into sub-plans.
2. **File Structure & Clear Boundaries**: Map out created/modified files, line ranges, and interface signatures (`Consumes:` / `Produces:`).
3. **Bite-Sized Task Granularity**: Every step is one discrete action (2~5 minutes).
4. **TDD Baked into Every Task**: Red -> Verify Red -> Green -> Verify Green -> Commit.
5. **Subagent Prompt Scaffold per Task**: Every task MUST include an explicit prompt block for `/vault-exec` dispatch.

---

## Phase 1: Context & Omni-Search Ingestion
1. Query `omni_search(query, scope='ladder')` to extract architecture constraints.
2. Query `get_code_template` via `coding-vault-search` MCP to extract pure Go/C++/C/Python production code snippets.

---

## Phase 2: Plan Document Structure (Required Schema)

Every generated `implementation_plan.md` MUST follow this schema:

```markdown
# [Feature Name] Implementation Plan

> **Goal**: [One sentence describing what this builds]
> **Tech Stack**: [Go 1.24+ / C++20 / Python 3.11 / C11]
> **Spec Reference**: [Link to Design Spec or ADR]
> **Global Constraints**: [Version floors, no-leak regex, UTF-8 stdout, guard clauses]

---

### Task 1: [Component Name] [Role: TDD Builder]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:120-150`
- Test: `tests/test_exact_feature.py`

**Interfaces:**
- Consumes: `func ExistingHelper(ctx context.Context) (Data, error)`
- Produces: `func NewService(cfg Config) (*Service, error)`

**Subagent Prompt Scaffold (for /vault-exec):**
> "Implement Task 1: {task_title}.
> Goal: {task_goal}.
> Target Files: Create `{path_1}`, Test `{test_path}`.
> TDD Steps:
> 1. Write failing test `{test_path}` (RED).
> 2. Run `{test_cmd}` and verify failure.
> 3. Implement minimal code in `{path_1}` (GREEN).
> 4. Flatten with Guard Clauses (max 2 levels).
> Return: Summary with test execution evidence."

**Step Breakdown:**
- [ ] **Step 1: Write the failing test (RED)**
- [ ] **Step 2: Run test and verify it fails with expected message**
- [ ] **Step 3: Implement minimal production code (GREEN)**
- [ ] **Step 4: Run tests and verify all green**
- [ ] **Step 5: Refactor & Flatten with guard clauses (REFACTOR)**
- [ ] **Step 6: Git atomic commit**
```

---

## Phase 3: Downstream Dispatch
Prompt user: `Plan generated with subagent prompt scaffolds. Initialize ledger and execute with /vault-exec?`
