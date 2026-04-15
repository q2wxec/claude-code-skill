---
name: agent-squad-designer
description: Designs a custom Agent team for a specific project or workflow, following Claude Code's internal architecture patterns: minimum-permission agents, single-responsibility prompts, orchestrator-based routing. Use this skill whenever the user asks to "design agents for my project", "set up a multi-agent system", "create a team of Claude agents", "build an agent workflow", or wants to delegate different parts of their codebase to specialized agents. Also activate when someone has a complex project with clearly separable concerns and asks how to structure Claude's work.
---

# agent-squad-designer

Designs a custom Agent team based on Claude Code's internal multi-agent architecture patterns — where scheduling lives in prompts rather than code, every agent has minimum permissions, and the orchestrator delegates understanding without losing it.

## Source-grounded design principles

Claude Code's built-in agents (verification, explore, plan, general-purpose, claude-code-guide) share these traits, extracted from `loadAgentsDir.ts` and `verificationAgent.ts`:

1. **Single responsibility** — each agent has one job, stated plainly in its `whenToUse` field. No "can also do X if needed."

2. **Minimum tool permissions** — agents declare exactly which tools they need via `tools` (allowlist) or `disallowedTools` (denylist). The verification agent explicitly disallows `Edit`, `Write`, and `NotebookEdit` — it cannot modify the project even if it wanted to.

3. **Prompt as algorithm** — the orchestrator's routing decisions live in the description fields, not in conditional logic. Claude routes to an agent because its `whenToUse` matches the current task semantically.

4. **Never hand off understanding** — the orchestrator synthesizes findings from sub-agents rather than asking sub-agents to synthesize. Sub-agents report facts; the orchestrator decides what they mean.

5. **Background vs. interactive** — agents with `background: true` run as tasks the user can monitor; interactive agents run in the foreground. Use background for verification, audits, long research; foreground for anything collaborative.

## Design Process

### Step 1 — Understand the project

Ask the user (or infer from context):
- What kind of project is this? (web app, data pipeline, library, monorepo, etc.)
- What are the most common types of work? (feature dev, reviews, migrations, testing, etc.)
- Where are the natural handoff points? (e.g., "write code" → "verify code" → "review code")
- Any specialized domains? (security, performance, specific tech stacks, compliance)

### Step 2 — Identify agent candidates

For each work type, ask: "Would it be useful if Claude had a specialized version that only did this, with tighter constraints?"

Strong candidates for their own agent:
- Work that benefits from adversarial perspective (verification/review)
- Work that needs permission restriction (read-only exploration, no-commit analysis)
- Work that's clearly bounded and repeatable (test writing, doc generation)
- Work where a narrow system prompt significantly improves quality (security review, performance analysis)

Weak candidates (stay in main agent):
- One-off tasks
- Work that requires full context at all times
- Simple tasks that don't need specialized framing

### Step 3 — Design each agent

For each agent, specify:

**`agentType`**: Short identifier (e.g., `security-reviewer`, `test-writer`, `migration-planner`)

**`whenToUse` / description**: This is the routing key. Write it as: "Use this agent when [specific situation]. Pass [what input]. Expect [what output]." Be concrete enough that the orchestrator knows exactly when to delegate.

**Tool permissions**: List only what the agent actually needs.
- Read-only agents: allow `Read`, `Bash` (read-only commands), deny `Edit`, `Write`
- Analysis agents: deny `Agent` (no spawning sub-sub-agents)
- Commit agents: allow `Bash` with git write commands explicitly noted

**System prompt structure**: The verification agent's prompt is a good template:
1. Role statement ("You are a [role]. Your job is [specific goal].")
2. Anti-patterns to avoid (what this agent tends to do wrong)
3. Required constraints (what it must NOT do)
4. Strategy for the task type
5. Required output format (exact structure, so the orchestrator can parse it)
6. Pass/fail/verdict format if it's a judgment agent

**`model`**: `inherit` for most. Use `haiku` for high-frequency lightweight classification. Use `opus` for maximum reasoning depth.

**`background`**: `true` for verification, audit, analysis tasks. `false` for collaborative tasks.

### Step 4 — Design the orchestrator

The orchestrator is the main Claude agent (or a dedicated coordinator). Its job:

- Decide which agent to call for which subtask
- Provide sufficient context in each sub-agent call (brief like "a smart colleague who just walked in")
- Synthesize the results — don't just relay sub-agent output verbatim
- Retain critical decisions at the orchestrator level, never delegate synthesis

Write a brief routing guide: "For [situation], call [agent] with [context]. Expect [output]. Then [what orchestrator does with it]."

### Step 5 — Output format

Produce a design document with:

```markdown
## Agent Squad for [Project Name]

### Agents

#### [agent-type]
- **Role**: [one sentence]
- **Triggers**: [when orchestrator should call this]
- **Tools**: [allowed list or denied list]
- **Permissions**: [read-only / can commit / etc.]
- **Model**: [inherit / haiku / opus]
- **Background**: [yes/no]
- **System prompt outline**: [key sections this agent's prompt should contain]

### Orchestrator routing guide
[When to call which agent, and what the orchestrator does with each result]

### Implementation files
[Path where each agent's .md file should be created, e.g., ~/.claude/agents/security-reviewer.md]
```

Then, if the user wants, generate the actual agent `.md` files ready to place in `~/.claude/agents/` or `.claude/agents/`.

## Agent .md file format

```markdown
---
name: agent-type-name
description: When to use this agent. What to pass it. What it returns. Be specific.
model: inherit
tools: Read, Bash, Glob, Grep
background: false
---

You are a [role]. Your job is [specific goal, not general helpfulness].

[Anti-patterns this agent falls into — be explicit, these are the failure modes]

[Constraints — what this agent MUST NOT do]

[Strategy for the task]

[Required output format — exact structure]
```

## Common squad patterns

**Feature development squad**:
- `planner` — converts requirements to task breakdown (read-only, high reasoning)
- `implementer` — main dev agent (full tools)
- `test-writer` — writes tests after implementation (no prod file edits)
- `verifier` — confirms tests pass and implementation is correct (read-only + bash)

**Code quality squad**:
- `security-reviewer` — finds vulnerabilities (read-only, adversarial)
- `performance-auditor` — identifies bottlenecks (read-only, profiling tools)
- `refactor-planner` — plans refactors without executing (read-only, high reasoning)

**Data pipeline squad**:
- `schema-analyst` — reads and documents data models (read-only)
- `migration-writer` — generates migration scripts (write, no direct DB access)
- `migration-verifier` — validates migrations before apply (read + bash dry-run)
