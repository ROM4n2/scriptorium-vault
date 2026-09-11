---
name: vault-save
description: Karpathy-mode session knowledge harvesting. Formats non-obvious engineering solutions and workarounds into 99-Inbox drafts or promotes directly into formal knowledge rules with pre-save deduplication.
---

# Vault-Save: Karpathy-Mode Knowledge Harvester & Ingestion Gate

Harvest non-obvious engineering solutions, environment gotchas, and architectural patterns discovered during coding sessions into `99-Inbox/` with **pre-save deduplication check**.

## The Ingestion Invariants (MUST)
1. **Novelty Check (Pre-Save Deduplication)**: Query `search_vault(query="<topic>")` before saving. If a note with >70% similarity exists, propose updating the existing note instead of creating a duplicate draft.
2. **Quality Gate (A-MAC)**: Reject trivial one-off bug fixes ("fixed typo in line 12"). MUST record: Symptom, Root Cause, Solution, and Defensive Rule.
3. **Structured YAML**: MUST include valid YAML frontmatter with `created`, `type: source-notes`, `status: draft`, `tags`, and `source`.

---

## The 3-Step Harvesting Workflow

### Step 1: Novelty & Similarity Check
```python
# Check existing knowledge
search_results = search_vault(topic_keywords)
# If identical problem already documented: Propose edit to existing note
```

### Step 2: Compose Draft File
Draft path: `{{VAULT_ROOT}}\99-Inbox\YYYY-MM-DD-{kebab-topic}.md`

```markdown
---
title: "{Concise, Searchable Title}"
created: {YYYY-MM-DD}
updated: {YYYY-MM-DD}
type: source-notes
tags:
  - lang/{lang}
  - topic/{topic}
  - category/troubleshooting
  - status/draft
status: draft
audience: both
source: "Session Discovery ({Project Name})"
---

# {Title}

## 1. 现象与成因分析 (Symptom & Root Cause)
{Describe what broke, the misleading symptoms, and why it occurred.}

## 2. 终极解决方案 (Permanent Solution & Code)
{Provide the clean, reproducible code fix.}

## 3. 防御性工程规范 (Defensive Rule)
{State the universal rule to prevent recurrence in other projects.}
```

### Step 3: Call MCP Tool
Call `save_inbox_draft(title=..., content=..., tags=...)` to write to `99-Inbox/`.
Announce to user: `✅ Knowledge harvested and persisted to 99-Inbox/ (passed A-MAC gate).`
