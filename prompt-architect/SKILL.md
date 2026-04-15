---
name: prompt-architect
description: Audits and restructures CLAUDE.md and system prompt configuration for maximum prompt cache efficiency, following Claude Code's internal SYSTEM_PROMPT_DYNAMIC_BOUNDARY pattern. Use this skill when the user asks to "optimize my CLAUDE.md", "reduce token costs", "improve cache hit rate", "restructure my system prompt", or "why is my context so expensive?" Also activate when someone mentions their CLAUDE.md has grown unwieldy or when working on a project where Claude is called frequently and token costs matter.
---

# prompt-architect

Audits your CLAUDE.md and prompt configuration for cache efficiency, following Claude Code's internal prompt assembly architecture — where static content is separated from dynamic content to maximize how much gets served from Anthropic's prompt cache.

## How Claude Code structures system prompts

From `src/constants/prompts.ts` and `src/constants/systemPromptSections.ts`:

Claude Code's system prompt has a **static prefix** (cached, reused across turns) and a **dynamic suffix** (recomputed each turn, cache-breaking). The boundary is `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` — everything before it stays stable and benefits from caching; everything after it changes and must be rebuilt.

Two types of prompt sections:
- `systemPromptSection()` — computed once, cached until `/clear` or `/compact`. Use for stable content.
- `DANGEROUS_uncachedSystemPromptSection()` — recomputed every turn, breaks cache when it changes. Use only for content that genuinely varies per-turn (e.g., current file state, terminal focus, date).

**Priority order** (from `buildEffectiveSystemPrompt()`):
1. `overrideSystemPrompt` — replaces everything (loop mode)
2. Coordinator system prompt (if coordinator mode active)
3. Agent system prompt (replaces or appends to default, depending on mode)
4. `--system-prompt` flag (custom prompt)
5. Default system prompt (standard Claude Code prompt)
6. `appendSystemPrompt` — always appended at the end

**Cache economics**: Prompt cache has a 5-minute TTL. Content that changes between turns — timestamps, current directory listings, dynamic file contents — forces the entire suffix after the change point to be rebuilt. One volatile piece of content early in the prompt can invalidate the cache for everything that follows.

## Audit Process

### Step 1 — Read all prompt sources

Collect everything that goes into the system prompt:
- `~/.claude/CLAUDE.md` (global, always loaded)
- Project `.claude/CLAUDE.md` (project-level)
- Any `--system-prompt` flags or overrides
- Hooks that inject content into the prompt

### Step 2 — Classify each section

For each piece of content, ask: "Does this change between turns in a live session?"

**Static (cache-friendly):**
- Coding style guidelines
- Architecture decisions
- Tool usage rules
- Git commit format
- Language preferences
- Framework conventions
- Anything written once and rarely updated

**Dynamic (cache-breaking):**
- Current date or time (changes every minute/day)
- Absolute file paths that include usernames or environment-specific roots
- Directory listings (`ls output`)
- Currently open files
- Git status output
- Environment variable values that vary by machine/session
- Random identifiers or session tokens

### Step 3 — Identify cache-busting anti-patterns

Common CLAUDE.md mistakes that break cache:

| Anti-pattern | Example | Fix |
|---|---|---|
| Embedded timestamp | "Last updated: March 2026" | Remove or move to a comment outside the prompt |
| Absolute paths | `/Users/fxx/projects/myapp/` | Use relative paths or `$PROJECT_ROOT` references |
| Dynamic content | "Current branch: feature/xyz" | Remove — Claude can read this when needed |
| Frequently-rotated tokens | API key references | Use environment variables, don't embed |
| Large tool output dumps | Pasting `ls -la` results | Remove — Claude can run this when needed |

### Step 4 — Restructure recommendations

Produce a restructured CLAUDE.md split into sections:

**Stable prefix** (put here — will be cached):
```markdown
# [Project Name]

## Architecture
[stable architecture facts]

## Coding conventions
[style rules that don't change]

## Tool usage
[how to use project-specific tools]
```

**Dynamic suffix** (if unavoidable — goes after a clear separator):
```markdown
---
<!-- Dynamic section — changes per-session or per-environment -->

[anything that varies: current task context, environment-specific paths, etc.]
```

Better yet: eliminate the dynamic section entirely. Anything Claude can discover by running a command doesn't need to be in the prompt.

### Step 5 — Output

Produce:
1. **Cache audit report** — what you found, classified as static/dynamic/anti-pattern
2. **Estimated impact** — roughly how much of the current prompt is cache-stable vs. volatile
3. **Restructured CLAUDE.md** — the rewritten version with stable content first
4. **Quick wins** — the 2-3 changes with highest cache impact

## CLAUDE.md hierarchy and layering

Claude Code loads CLAUDE.md files from multiple levels:
- `~/.claude/CLAUDE.md` — global (user-level, loaded for every project)
- `.claude/CLAUDE.md` — project-level (loaded for the current project)
- Sub-directory `CLAUDE.md` files — loaded when working in that directory

**Layering principle**: Put the most stable, universal content at the highest level (`~/.claude/CLAUDE.md`). Project-specific conventions go in `.claude/CLAUDE.md`. The global file changes least often, so its cache prefix stays valid longest.

## What makes a great CLAUDE.md

A good CLAUDE.md reads like a briefing for a new engineer joining the project:
- What is this project and what does it do?
- What conventions should I follow that aren't obvious from the code?
- What should I avoid doing (past mistakes, current constraints)?
- What tools/commands do I need to know about?

It does NOT include:
- Things already visible in the code (Claude can read files)
- Step-by-step instructions for common tasks (Claude can reason about these)
- Dynamic state (branch name, current task, open files)
- Large blocks of reference material (use `@file` imports for those)
