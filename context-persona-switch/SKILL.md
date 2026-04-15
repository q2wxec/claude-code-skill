# Context Persona Switch

A skill for designing context-aware persona switching in Claude Code, inspired by the undercover mode architecture in `src/utils/undercover.ts`.

## Design Principles (from undercover.ts)

**Asymmetric safety**: Entering a restricted persona is easy (environment signals it); exiting requires explicit override. The system defaults to the more restrictive mode when context is ambiguous.

**Environment detection first**: Personas activate from git remotes, working directory patterns, branch prefixes, or env vars — not from manual prompts each session.

**Explicit stripping rules**: Each persona declares what to omit, not just what to include. The undercover mode strips internal codenames, unreleased versions, attribution, and AI mentions. Your personas should define equivalent lists.

**One-way gate default**: When detection is ambiguous, fall to the persona with the strictest output constraints. Never default to the most permissive persona.

---

## When This Skill Activates

Use this skill when users:
- Work across internal and public repositories in the same session
- Need different tone/terminology for client-facing vs internal output
- Want to strip specific content categories based on deployment context
- Ask for "different behaviors for different repos" or "context-aware Claude"

---

## Process

### Step 1 — Audit Current Behavior

Before designing personas, ask:
- What does Claude currently output that might be context-inappropriate?
- Are there internal names, credentials, or unreleased details that leak into external contexts?
- Does attribution (e.g., "Generated with Claude") need to vary by context?
- What terminology differences exist across your work contexts?

### Step 2 — Define Contexts

Ask the user to describe 2–3 distinct work contexts. Common patterns:

| Context type | Typical triggers | Output characteristics |
|---|---|---|
| Internal team work | Private git remote, `/internal/` in path | Verbose, internal names OK, full attribution |
| Client delivery | Client repo remote, `/clients/` in path | Polished, external terminology, strip internal refs |
| Open source contribution | `github.com/public` remote, `oss/` branch | Neutral, no company refs, community-appropriate tone |

Gather for each context:
1. A short name (used as the persona identifier)
2. What git remote pattern, directory path, branch prefix, or env var signals this context
3. Preferred output style (verbose/concise)
4. Terminology level (internal jargon allowed vs external-only)
5. Attribution rules
6. What to always exclude

### Step 3 — Design Persona Rules

For each context, produce a persona block using this template:

```
## [PERSONA-NAME] mode (active when: [detection heuristic])

### Behavior
- Output style: [detailed/concise]
- Terminology: [internal/external facing]
- Attribution: [include/strip]

### Always exclude
- [list of forbidden content for this context]

### Always include
- [required elements for this context]
```

**Exclusion list guidance** — prompt users with these categories:
- Internal codenames or project names not yet public
- Unreleased version numbers or roadmap items
- Internal URLs, hostnames, or tool names
- Personal names or org-internal handles
- Credentials, tokens, internal API keys (always excluded everywhere)
- "Generated with Claude" or AI attribution lines
- Slack channel names, Jira ticket IDs, internal doc links

### Step 4 — Generate Detection Heuristics

Each persona needs at least one detection rule. Ordered by reliability:

1. **Env var** (most explicit): `PERSONA=client-facing` — set in project `.env` or shell profile
2. **Git remote pattern**: `git remote -v` output contains `github.com/acme-internal` → internal persona
3. **Directory path pattern**: working directory contains `/clients/` or `/oss/` → switches persona
4. **Branch name prefix**: branch starts with `client/`, `release/`, `oss/` → switches persona

Detection should use the first matching rule in the order above. If no rule matches, activate the most restrictive persona (asymmetric safety default).

### Step 5 — Output CLAUDE.md Fragments

Generate ready-to-paste CLAUDE.md configuration. Each fragment goes into the relevant project's CLAUDE.md, or into a `~/.claude/rules/personas/` directory loaded conditionally.

**Fragment structure:**

```markdown
<!-- persona: [NAME] | detection: [METHOD] | value: [PATTERN] -->
## Claude behavior — [PERSONA-NAME] context

When this file is active, apply [PERSONA-NAME] rules.

### Output style
[verbose/concise description]

### Terminology
[specifics on internal vs external language]

### Attribution
[include full / strip entirely / use neutral form]

### Never output in this context
- [item 1]
- [item 2]
- ...

### Always include in this context
- [item 1]
- ...
```

Offer to run `scripts/persona_generator.py --interactive` to generate the fragments automatically.

---

## Reference: Detection Priority Table

| Method | Example | Reliability | Setup cost |
|---|---|---|---|
| Env var | `PERSONA=internal-dev` | Explicit, manual | Low |
| Git remote | remote contains `acme-corp.net` | Automatic | None after initial config |
| Directory path | cwd matches `*/clients/*` | Automatic | Path discipline required |
| Branch prefix | branch starts with `oss/` | Semi-automatic | Branch naming convention |

---

## Reference: Undercover Mode Mapping

The original `undercover.ts` design maps directly to persona concepts:

| undercover.ts concept | Persona equivalent |
|---|---|
| `CLAUDE_CODE_UNDERCOVER=1` env var | `PERSONA=<name>` env var |
| Repo remote allowlist check | Git remote pattern match |
| Default ON (safe) | Default to most restrictive persona |
| No force-OFF | No override to most permissive without explicit env var |
| Strip internal codenames | Persona exclusion list — internal names |
| Strip attribution | Persona attribution rule — strip |

---

## Quick Reference Checklist

Before finalizing persona design, verify:

- [ ] Each persona has at least one detection heuristic
- [ ] Each persona has an explicit exclusion list (not just "be professional")
- [ ] Default fallback is the most restrictive persona
- [ ] Detection rules are checked in priority order (env var first)
- [ ] Personas do not overlap — a given environment activates exactly one
- [ ] CLAUDE.md fragments are scoped to the correct project directories
