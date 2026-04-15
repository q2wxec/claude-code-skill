---
name: memory-architect
description: Restructures a chaotic or overgrown MEMORY.md into a clean 3-layer architecture based on how Claude Code's autoDream system organizes memory: a lightweight pointer index (always loaded), topic files (loaded on demand), and an archive layer (historical context, not proactively loaded). Use this skill whenever the user says "clean up MEMORY.md", "reorganize my memory files", "MEMORY.md is getting too long", "fix my memory structure", or when you observe that MEMORY.md exceeds 200 lines, contains full paragraphs instead of pointers, or mixes index entries with topic content.
---

# memory-architect

Restructures memory files into the 3-layer architecture that Claude Code's `autoDream` service uses internally — designed to keep the always-loaded index small while making deeper knowledge accessible on demand.

## The 3-Layer Architecture

Claude Code's memory system (`services/autoDream/`) uses this structure:

```
MEMORY.md          ← Layer 1: Always loaded, pointer-only index (~200 lines max)
├── topic-file.md  ← Layer 2: Domain knowledge, loaded when relevant
├── another-topic.md
└── archive/       ← Layer 3: Historical context, rarely needed
    └── old-decisions.md
```

**Layer 1 — MEMORY.md index**: Loaded into every conversation. Must stay under ~200 lines (lines beyond 200 get truncated). Each entry is a one-line pointer: `- [Title](file.md) — one-line hook`. No content, just pointers. This is what Claude scans to decide what to load.

**Layer 2 — Topic files**: Contain the actual knowledge. Claude loads these on demand when their pointer appears relevant. Can be as long as needed. Each file has YAML frontmatter with `name`, `description`, and `type`.

**Layer 3 — Archive**: Old decisions, superseded approaches, historical context. Not referenced from MEMORY.md unless explicitly needed. Useful for debugging ("why did we do X two months ago?") but shouldn't pollute active context.

## Restructuring Process

### Step 1 — Audit what exists

Read `MEMORY.md` and all memory files in the same directory. Catalog:
- Total line count of MEMORY.md
- Which entries are pointer-only (good) vs. have inline content (needs extraction)
- Which topic files have grown unwieldy (>200 lines) and should be split
- Which entries are clearly stale, superseded, or contradicted

### Step 2 — Classify each entry

For each piece of content, decide its layer:

| Content type | Layer |
|---|---|
| Universal facts, always-relevant rules | L1 pointer → L2 file |
| Project-specific decisions, current constraints | L1 pointer → L2 file |
| Historical "why we did X" context | L3 archive |
| Superseded approaches | L3 archive or delete |
| Contradicted facts | Delete or correct |
| Step-by-step implementation details | Delete (code is the record) |

### Step 3 — Restructure

**For MEMORY.md:**
- Keep only pointer lines (one per memory file)
- Format: `- [Descriptive Title](filename.md) — one-line hook (what makes this relevant?)`
- Keep under 200 lines total
- Group related pointers with brief section headers if helpful (e.g., `## Architecture`, `## User preferences`)
- Remove entries for deleted/archived files

**For topic files:**
- Each file gets proper frontmatter:
  ```markdown
  ---
  name: <topic name>
  description: <one-line — used to judge relevance in future conversations>
  type: user | feedback | project | reference
  ---
  ```
- `feedback` type: lead with the rule, then `**Why:**` and `**How to apply:**` lines
- `project` type: lead with the fact/decision, then `**Why:**` and `**How to apply:**`
- Consolidate near-duplicate files (same topic, slightly different angles) into one
- Convert relative dates to absolute dates ("last week" → "2026-03-15")

**For archive:**
- Create `archive/` subdirectory if it doesn't exist
- Move genuinely historical content there
- Do NOT add archive files to MEMORY.md index (they're for reference, not proactive loading)

### Step 4 — Verify

After restructuring:
- MEMORY.md under 200 lines? 
- Every pointer in MEMORY.md points to an existing file?
- Every topic file has valid frontmatter?
- No content directly in MEMORY.md (only pointers)?
- No duplicate or near-duplicate topic files?

### Step 5 — Report

Tell the user:
- Before/after line count for MEMORY.md
- How many topic files created/merged/archived/deleted
- Any contradictions found and how resolved

## Common anti-patterns to fix

**Bloated index** — MEMORY.md has paragraphs of content instead of pointers. Extract to topic files.

**One giant file** — Everything dumped into a single `memories.md`. Split by topic.

**Missing frontmatter** — Topic files without `name`/`description`/`type`. Add it — the description is what helps Claude decide whether to load the file.

**Stale facts** — Memory says "using postgres 14" but codebase shows 16. Fix at source.

**Temporal decay** — "We decided last week to use X". Convert to absolute date; also verify if decision still stands.

**Archive in index** — Historical context cluttering MEMORY.md. Move to `archive/`.
