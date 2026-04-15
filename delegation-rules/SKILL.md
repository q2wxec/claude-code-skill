---
name: delegation-rules
description: Generates a delegation rules document for multi-agent workflows, covering what to keep at orchestrator level vs. what to delegate, and how to write self-contained sub-agent prompts. Use this skill when the user asks to "design multi-agent systems", "delegate work to sub-agents", "improve agent prompt quality", "design orchestrator/worker patterns", "write better sub-agent prompts", or "avoid duplicating work in agents". Also activate when someone is building an orchestrator that spawns workers and wants to avoid re-doing work the sub-agents already handle.
---

# delegation-rules

Generates a delegation rules document grounded in Claude Code's agent orchestration design — where the orchestrator retains understanding, sub-agents protect the main context window, and every delegation brief is self-contained.

## Source-grounded principles

From `src/constants/prompts.ts` (lines 316-320) and the Agent tool design:

1. **Never duplicate what sub-agents do** — "Avoid duplicating work that subagents are already doing — if you delegate research to a subagent, do not also perform the same searches yourself."

2. **If you are the fork — execute directly** — "If you ARE the fork — execute directly; do not re-delegate." Sub-agents must not spawn further sub-agents for the same task.

3. **Sub-agents protect the main context window** — Agent tool runs in fork mode: tool output stays out of the orchestrator's context unless the orchestrator explicitly reads the result. This is the core reason to delegate.

4. **Brief like a smart colleague** — "Brief the agent like a smart colleague who just walked into the room — it hasn't seen this conversation, doesn't know what you've tried." Every sub-agent prompt must be fully self-contained.

5. **Synthesize before delegating downstream** — The orchestrator synthesizes findings. It never hands raw sub-agent output to another sub-agent and asks it to "figure out what this means."

## What to keep at orchestrator level

**Never delegate these:**

| Work type | Why it stays with the orchestrator |
|---|---|
| Synthesis of multiple agent results | Only the orchestrator has all results in context |
| Final decision between options | Requires full picture; sub-agents see only their slice |
| User communication about progress | Requires awareness of overall state |
| Understanding of the overall goal | Cannot be re-derived by a sub-agent from a brief |
| Context that spans multiple delegations | Sub-agents are stateless; the orchestrator is the thread |

## What can be delegated

**Safe to delegate (sub-agents do one of these):**

| Delegation type | Example prompt shape |
|---|---|
| Research with clear output format | "Find all usages of function X in this codebase. Return a list of `file:line` pairs. Cap at 50 results." |
| Implementation with clear spec | "Implement function `parseConfig(input: string): Config` in `src/config.ts`. Inputs/outputs defined below. Return the final file content." |
| Verification with binary verdict | "Run these specific checks: [list]. Return PASS / FAIL / PARTIAL with evidence for each." |
| Exploration with structured output | "List all files matching `**/*.test.ts`. Return file paths, one per line." |
| Targeted analysis | "Read `src/auth/session.ts` and list every place user input touches the database without parameterization. Return file:line + code snippet." |

## Delegation anti-patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| "Based on your findings, now..." | Sub-agent has no prior findings | Include the findings explicitly in the prompt |
| "As we discussed earlier..." | Sub-agents don't see conversation history | Paste the relevant excerpt |
| "Investigate the auth module" | No deliverable specified | Specify: what to look for, what format to return |
| No file paths, only vague descriptions | Agent must re-discover what orchestrator already knows | Include exact paths, function names, line numbers |
| No output format | Orchestrator can't parse the result reliably | Specify format and length cap |
| "Look into this, use your judgment" | No context for judgment calls | State the goal, constraints, and what "good" looks like |
| Re-delegating within a sub-agent | Infinite fork chains, context explosion | Sub-agents execute; only orchestrator delegates |

## Prompt quality checklist

Before sending a prompt to a sub-agent:

- [ ] The agent has no conversation history — tell it everything it needs
- [ ] State what you've already tried or ruled out
- [ ] Specify the output format exactly (list, JSON, markdown table, verdict line)
- [ ] Set a length cap ("cap at N results", "max 500 words")
- [ ] Include the reason this matters (enables judgment calls)
- [ ] Use file paths and function names — never vague descriptions
- [ ] No "based on previous research" — paste the research

## Design process

### Step 1 — Identify workflow type

Ask the user or infer from context:
- Code review — orchestrator coordinates read-only reviewers
- Feature development — orchestrator coordinates planner / implementer / verifier
- Debugging — orchestrator coordinates log-reader / reproducer / fixer
- Data analysis — orchestrator coordinates data-fetcher / transformer / summarizer

### Step 2 — Map the work

For the workflow, list every distinct work unit. Then classify each:

**Stays at orchestrator:** synthesis, decisions, user communication
**Delegates:** bounded tasks with clear inputs, outputs, and success criteria

### Step 3 — Draft delegation briefs

For each delegated task, produce a brief template:

```
GOAL: [one sentence — what this agent must produce]
CONTEXT: [what the orchestrator already knows that's relevant]
ALREADY TRIED: [what's been ruled out]
SCOPE: [exact files / functions / data ranges to look at]
OUTPUT FORMAT: [exact structure]
LENGTH CAP: [max N results / words]
JUDGMENT GUIDE: [what "good enough" means for this task]
```

### Step 4 — Output

Produce a delegation rules document containing:
1. **Orchestrator responsibilities** — what it never delegates
2. **Delegation map** — work type → sub-agent type → brief template
3. **Prompt quality checklist** — customized to the workflow
4. **Anti-patterns for this workflow** — specific failure modes to avoid
5. **Example before/after** — one bad prompt rewritten as a good one

## Before/after example

**Bad prompt (code review workflow):**
```
Review the authentication code and check for security issues.
Based on what you find, also look at how sessions are managed.
```

Issues: vague scope, no output format, chained delegation, no context.

**Good prompt:**
```
GOAL: Identify SQL injection risks in the user authentication path.
SCOPE: Read these files only: src/auth/login.ts, src/db/userQueries.ts
CONTEXT: We use raw string concatenation in queryUser() — confirmed at line 47 of userQueries.ts.
         We want to know if this pattern appears elsewhere in the auth path.
ALREADY RULED OUT: src/auth/oauth.ts uses parameterized queries throughout — skip it.
OUTPUT FORMAT: List of file:line + code snippet for each risk found. Max 20 results.
               End with: VERDICT: CRITICAL / HIGH / NONE
JUDGMENT GUIDE: Flag anything where user-controlled input reaches a DB query without
                explicit parameterization or escaping.
```

## Workflow-specific templates

Use `scripts/delegation_audit.py --generate-template <workflow-type>` to generate
a ready-to-fill delegation brief template for:
- `code-review` — coordinating read-only security and quality reviewers
- `feature-dev` — planner / implementer / verifier chain
- `debugging` — reproducer / root-cause / fixer chain
- `data-analysis` — fetcher / transformer / summarizer chain
