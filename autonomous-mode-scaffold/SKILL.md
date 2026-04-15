# Skill: Autonomous Mode Scaffold

## Trigger Phrases

Activate this skill when users mention:
- "set up autonomous agent", "configure Claude to work while I'm away"
- "离场自主工作", "无人值守模式", "后台自动运行"
- "always-on background agent", "configure background monitoring"
- "let Claude work autonomously", "autonomous mode"

## Core Source

Design principles extracted from KAIROS proactive mode:
`src/constants/prompts.ts:860-913` — tick-based autonomous agent system prompt.

---

## What This Skill Produces

1. **Autonomy Design Document** — presence detection strategy + boundary definition
2. **CLAUDE.md fragments** — behavior rules for focused/unfocused contexts
3. **Hooks config template** — start/stop autonomous mode, append-only operation log
4. **SleepTool pacing guidance** — based on 5-minute prompt cache TTL

---

## The 3 Questions (Define Before Going Autonomous)

Before configuring any autonomous agent, answer these exactly:

**Q1 — What CAN it do without asking?**
Examples: read files, run tests, lint code, commit passing changes, open PRs, update deps minor versions

**Q2 — What is ALWAYS blocked?**
Examples: delete files, force-push to main, send emails, charge API credits, modify .env files, drop database tables

**Q3 — What triggers a wake-up alert?**
Examples: test suite failure, security vulnerability found, breaking API change detected, disk usage > 90%

---

## Autonomy Boundary Template (5 Categories)

| Category | Description | Default posture |
|---|---|---|
| **reads-only** | Any read, grep, list, status op | Always allowed |
| **safe-writes** | New files, append-only logs, new branches | Allowed when unfocused |
| **reversible-changes** | Edits, commits, PR creation | Allowed when unfocused; ask when focused |
| **irreversible-changes** | Deletes, merges to main, publishes | Always ask, even when unfocused |
| **external-effects** | Emails, webhooks, API calls with side effects | Always blocked unless explicitly whitelisted |

---

## Presence Awareness: terminalFocus States

The KAIROS system uses `terminalFocus` signal to adjust behavior:

### `unfocused` (user away) — Lean Autonomous
- Make decisions independently
- Commit, push, create PRs without asking
- Skip narration; write milestones to log only
- Only pause for: irreversible actions, external effects, ambiguous requirements
- Sleep between ticks; do not busy-loop

### `focused` (user watching) — Collaborative
- Surface choices before acting
- Ask before large or multi-file changes
- Show progress inline
- Prefer shorter sleep durations (user may respond quickly)

---

## Tick → Work → Sleep Loop

```
TICK received
  │
  ├─ First tick? → Greet, ask what to work on. STOP.
  │
  ├─ Has task?
  │    ├─ YES → Execute work unit
  │    │         Write result to operation log
  │    │         Check alert triggers
  │    │         Call SleepTool (never emit "nothing to do" text)
  │    │
  │    └─ NO  → Call SleepTool immediately
  │
  └─ Alert triggered? → Notify user, pause autonomous work
```

**SleepTool pacing rule:** Prompt cache TTL is 5 minutes. Sleep durations:
- Active work session: 30–60 seconds
- Idle monitoring: 3–4 minutes (stay under 5-min TTL to preserve cache)
- Long idle (nothing queued): 4 minutes max, then re-evaluate

---

## Operation Log Pattern (Append-Only)

Never delete or overwrite the log while autonomous. Format:

```
[2026-04-15T14:23:01Z] ACTION: ran test suite | FILES: src/**, tests/** | RESULT: 42 passed, 0 failed
[2026-04-15T14:23:45Z] ACTION: committed fix  | FILES: src/auth.ts | RESULT: sha=abc123
[2026-04-15T14:25:00Z] ACTION: opened PR #47  | FILES: — | RESULT: https://github.com/org/repo/pull/47
```

Log path: `.claude/autonomous_log.md` (relative to project root)

---

## State Recovery Summary (When User Returns)

When user reconnects after autonomous session, output a compact summary:
1. Total actions taken (count by category)
2. Files modified (list)
3. Commits/PRs created (with links)
4. Any blocked actions and why
5. Current state vs. starting state
6. What needs user decision next

Do NOT re-narrate every step. One concise block only.

---

## No Re-Delegation Rule

From KAIROS: "If you ARE the fork — execute directly; do not re-delegate."

This means: when operating autonomously, do the work yourself. Do not spawn sub-agents unless the original task definition explicitly requires multi-agent work. Re-delegation inflates cost and adds latency with no benefit.

---

## Generating the Scaffold

Use the included script for interactive setup:

```bash
# Interactive wizard
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py --interactive

# Non-interactive
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py \
  --project-name "my-api" \
  --safe-actions "run tests,lint,commit passing builds" \
  --blocked-actions "delete files,force push,send emails" \
  --alert-triggers "test failure,security vuln detected"

# See common patterns
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py --list-patterns
```

Output files written to current directory:
- `AUTONOMOUS_MODE.md` — append to your project's CLAUDE.md
- `hooks_template.json` — merge into `.claude/settings.json` hooks section

---

## CLAUDE.md Fragment Structure

The generated fragment follows this template:

```markdown
## Autonomous Mode Rules

### When user is AWAY (terminalFocus: unfocused)
- [safe actions listed here]

### When user is PRESENT (terminalFocus: focused)
- Collaborative mode: surface choices, ask before large changes

### Always BLOCKED (never do autonomously)
- [blocked actions listed here]

### Alert triggers (wake user immediately)
- [trigger conditions listed here]

### Operation log
Append all autonomous actions to: .claude/autonomous_log.md
Format: [TIMESTAMP] ACTION: description | FILES: list | RESULT: outcome
```

---

## Security Checklist Before Enabling Autonomous Mode

- [ ] Blocked list includes all irreversible file operations
- [ ] External API calls are either blocked or rate-limited
- [ ] No secrets in CLAUDE.md fragment (use env var references only)
- [ ] Operation log path is inside project (not system-wide)
- [ ] Alert triggers cover data loss scenarios
- [ ] Focused/unfocused boundary is clearly defined for this project
