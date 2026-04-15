---
name: context-budget-planner
description: Plans context window budget for long tasks before they start — estimates token consumption by phase, identifies when autocompact will trigger, and recommends where to place manual /compact checkpoints. Based on Claude Code's autoCompact.ts thresholds and circuit breaker logic. Use this skill when the user is about to start a large task (refactoring a big codebase, processing many files, long research session), asks "will this fit in context?", "when should I compact?", "how do I avoid hitting context limits?", or when a session has already hit warnings about context usage.
---

# context-budget-planner

Plans context budget for long tasks using the same thresholds Claude Code uses internally — so you can predict when autocompact will fire and decide proactively where to place checkpoints, rather than reacting after the context is nearly full.

## Claude Code's context thresholds (from autoCompact.ts)

| Threshold | Token buffer | What happens |
|---|---|---|
| Warning zone | 20,000 tokens remaining | Yellow warning shown to user |
| Error zone | 20,000 tokens remaining | Red warning shown |
| **Auto-compact trigger** | **13,000 tokens remaining** | autoCompact fires automatically |
| Blocking limit | 3,000 tokens remaining | New messages blocked |

**Effective context window** = model context window − 20,000 tokens (reserved for summary output)

Claude Code reserves 20,000 tokens for compaction output (based on p99.99 of actual compact summaries being ~17,387 tokens). For Claude Sonnet with a 200k context window, the effective usable window is ~180,000 tokens, and autocompact fires at ~167,000 tokens used.

**Circuit breaker**: After 3 consecutive autocompact failures, autocompact stops retrying for that session. If you hit this state, use `/compact` manually.

## Planning Process

### Step 1 — Estimate the task scope

Ask (or estimate from context):
- How many files will be read? (Each file read adds its token count to context)
- How many tool calls are expected? (Tool results stay in context)
- What's the expected output volume? (Generated code, analysis, etc.)
- How many turns will this take?

**Rough token estimates:**
- Average code file: 500-2,000 tokens
- Large file (>500 lines): 2,000-8,000 tokens
- Tool call result (bash output, search results): 200-2,000 tokens
- System prompt: 5,000-15,000 tokens (always present)
- Conversation history grows: ~500-1,000 tokens per turn

### Step 2 — Identify phase boundaries

Break the task into phases where the accumulated context can be estimated:

```
Phase 1: [Task description]
  - Files to read: [list]
  - Tool calls: [estimate]
  - Estimated tokens: [range]
  
Phase 2: [Task description]  
  - New files: [list]
  - Cumulative tokens by end: [range]
  
...
```

### Step 3 — Mark compact checkpoints

For each phase transition, ask: "Will we be near the autocompact threshold (13k tokens remaining) at this point?"

**Recommend a `/compact` checkpoint when:**
- About to enter a token-heavy phase (large file batch, extensive generation)
- Phase naturally produces a clean summary point (completed a feature, finished a batch)
- You've been in the session > 100 turns
- Current token estimate is above 60% of effective context window

**Skip the checkpoint when:**
- Current phase is nearly done anyway
- Compacting would lose critical in-progress state
- Token count is still well under 50% of limit

### Step 4 — Output a session plan

```markdown
## Context Budget Plan: [Task Name]

**Model**: [model]
**Effective context window**: ~[N]k tokens
**Autocompact trigger**: ~[N]k tokens used ([N]k remaining)

### Phase breakdown

| Phase | Description | Est. tokens | Cumulative | Action |
|-------|-------------|-------------|------------|--------|
| 1 | [desc] | +[N]k | [N]k ([X]%) | Continue |
| 2 | [desc] | +[N]k | [N]k ([X]%) | **Checkpoint: /compact** |
| 3 | [desc] | +[N]k | [N]k ([X]%) | Continue |

### Recommended checkpoints
- After Phase 2: Use `/compact-with-memory` to preserve decisions before compressing
- After Phase 4: Standard `/compact` if context > 70%

### Risk factors
- [Any phases with high variance in token consumption]
- [Files that might be larger than estimated]
- [Tool calls that might return large outputs]
```

## What to do when nearing limits

**At 30% remaining**: Start thinking about what can be dropped. Stop keeping large file contents in context if they're no longer actively needed.

**At 20% remaining (warning zone)**: Time to compact. Use `/compact-with-memory` if you want to preserve this session's learnings, or `/compact` for a clean summary.

**At autocompact trigger**: Claude Code will compact automatically. If you want control over what's preserved, compact manually before this point.

**After autocompact**: The conversation history is replaced with a summary. You can continue normally. If something important was in the conversation, check MEMORY.md — if you used `/compact-with-memory`, the key decisions were saved there first.

## Practical tips

**Front-load context**: Read all the files you'll need at the start of the session rather than scattered throughout. Fewer context-filling spikes, more predictable budget.

**Use agents for isolation**: Spawning a sub-agent with the Agent tool gives it a fresh context window. Complex subtasks that would consume large amounts of context can be delegated to agents that start fresh.

**Grep before read**: For large files where you only need one part, `Grep` to find the relevant section, then `Read` with offset/limit. Reads only what you need.

**Avoid re-reading**: If you've already read a file and it's in context, refer to it — don't read it again. Re-reading adds more tokens without adding more information.
