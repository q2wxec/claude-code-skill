---
name: cache-health-check
description: >
  Audits Claude Code project configuration for prompt cache health. Detects cache-busting
  patterns across CLAUDE.md files, MCP server configs, and settings.json. Produces a scored
  health report with ranked recommendations. Use when the user asks to reduce API costs,
  improve cache hit rate, optimize token spending, diagnose expensive sessions, or investigate
  why Claude Code sessions feel slow or pricey.
---

# cache-health-check

Audits your Claude Code configuration for prompt cache efficiency. Covers the 14 state vectors
tracked by `src/services/api/promptCacheBreakDetection.ts`, scores your setup 0-100, and outputs
ranked fixes sorted by BQ-measured break frequency.

## When to trigger

- "reduce my API costs" / "lower token spending"
- "improve cache hit rate" / "why are my sessions expensive?"
- "optimize Claude Code performance"
- "diagnose cache breaks" / "cache health"
- After adding MCP servers or changing model settings

## Audit workflow

### Step 1 — Run the audit script

```bash
python3 ~/.claude/skills/cache-health-check/scripts/cache_health_audit.py
```

Produces a scored report covering all four audit domains. For machine-readable output:

```bash
python3 ~/.claude/skills/cache-health-check/scripts/cache_health_audit.py --json
```

### Step 2 — Interpret the health score

| Score | Status | Meaning |
|-------|--------|---------|
| 85–100 | Healthy | Cache breaking only from expected sources |
| 65–84 | Warning | 1–2 fixable break sources present |
| 40–64 | Degraded | Multiple break sources; measurable cost impact |
| 0–39 | Critical | Configuration is actively fighting the cache |

### Step 3 — Apply fixes by priority

The 5 most impactful fixes, ranked by BQ break frequency (2026-03-22):

**Fix 1 — Tool schema instability (77% of tool breaks)**
- Cause: MCP servers that generate dynamic tool descriptions (timestamps, session IDs,
  file counts embedded in tool `description` fields)
- Fix: Pin MCP server versions; audit tool descriptions for volatile content; prefer
  servers that return stable schemas
- Detection: `perToolHashes` vector changes between sessions

**Fix 2 — System prompt changes (CLAUDE.md)**
- Cause: Embedded dates, absolute paths, or dynamic content in CLAUDE.md
- Fix: Make CLAUDE.md purely static; move dynamic context to runtime tool calls
- Detection: `systemHash` and `systemCharCount` vectors
- Deep analysis: run `~/.claude/skills/prompt-architect/scripts/claudemd_audit.py`

**Fix 3 — Global cache strategy instability**
- Cause: Sessions that sometimes have MCP tools and sometimes don't flip between
  `tool_based` and `system_prompt` strategies, breaking the cache boundary location
- Fix: Keep MCP server set consistent; if you disable servers, use a stable subset
- Detection: `globalCacheStrategy` vector

**Fix 4 — Model string variance**
- Cause: `ANTHROPIC_MODEL` env var or `model` field varies between sessions or
  is overridden mid-session
- Fix: Pin model in `settings.json`; avoid per-project model overrides that differ
  from the global default
- Detection: `model` vector

**Fix 5 — Extra body params**
- Cause: `CLAUDE_CODE_EXTRA_BODY` env var contains session-specific values
  (timestamps, random seeds, request IDs)
- Fix: Keep extra body params fully static or remove them; never inject dynamic values
- Detection: `extraBodyHash` vector

### Step 4 — Deep CLAUDE.md analysis (optional)

For detailed CLAUDE.md restructuring recommendations, run the prompt-architect audit:

```bash
python3 ~/.claude/skills/prompt-architect/scripts/claudemd_audit.py
```

This provides full section-level classification (static vs. dynamic) and a restructured
output with the stable prefix / dynamic suffix boundary clearly marked.

## The 14 tracked state vectors

These are the fields in `PreviousState` / `PendingChanges` in `promptCacheBreakDetection.ts`.
A change in any of them may or may not break the cache depending on whether the changed
field affects the serialized prompt bytes.

| # | Vector | Break risk | Notes |
|---|--------|-----------|-------|
| 1 | `systemHash` | High | Full system prompt content hash |
| 2 | `toolsHash` | High | Aggregate hash of all tool schemas |
| 3 | `cacheControlHash` | Medium | Catches global↔org flips, 1h↔5m TTL flips |
| 4 | `perToolHashes` | High | Per-tool schema hash (77% of tool breaks) |
| 5 | `systemCharCount` | Low | Char delta — magnitude indicator only |
| 6 | `model` | High | Model string; different model = different cache |
| 7 | `fastMode` | Medium | Fast mode toggle changes effort resolution |
| 8 | `globalCacheStrategy` | High | `tool_based` vs `system_prompt` vs `none` |
| 9 | `betas` | Medium | Beta header list changes |
| 10 | `autoModeActive` | None | Latched sticky-on — should NOT break cache |
| 11 | `isUsingOverage` | None | Session-stable — should NOT break cache |
| 12 | `cachedMCEnabled` | None | Latched sticky-on — should NOT break cache |
| 13 | `effortValue` | Medium | Resolved effort: env → options → model default |
| 14 | `extraBodyHash` | Medium | `CLAUDE_CODE_EXTRA_BODY` + internal params |

Vectors 10, 11, 12 are intentionally latched — they change at most once per session
and are not expected to break the cache.

## Cache break detection thresholds

From `promptCacheBreakDetection.ts`:

- **Break condition**: `cacheReadTokens < prevCacheRead × 0.95` AND `tokenDrop ≥ 2000`
- **Excluded models**: Haiku (different caching behaviour — not tracked)
- **TTL values**: 5 minutes (default tier), 1 hour (overage tier)
- **Server-side break heuristic**: no client-side changes detected AND gap < 5 min
  → logged as "likely server-side (prompt unchanged, <5min gap)"

## Tracked query sources

Monitored: `repl_main_thread`, `compact` (maps to main thread), `sdk`,
`agent:custom`, `agent:default`, `agent:builtin`

Not tracked (short-lived forks): `speculation`, `session_memory`, `prompt_suggestion`

## Common cache-busting sources in CLAUDE.md

| Source | Example | Fix |
|--------|---------|-----|
| Embedded date | "Last updated: April 2026" | Delete it |
| Absolute path | `/Users/fxx/projects/app/` | Use relative path |
| Dynamic tool list | MCP server with session-specific tools | Pin server or remove |
| Model override | Per-project `model` different from global | Unify to one model |
| Effort toggle | `alwaysThinkingEnabled` changed mid-project | Pick one and keep it |
| Extra body params | `CLAUDE_CODE_EXTRA_BODY` with request IDs | Use static params only |
| Beta header churn | Experimental betas toggled on/off | Stabilize beta list |
