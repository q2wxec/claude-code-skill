#!/usr/bin/env python3
"""
delegation_audit.py -- Audits Agent tool delegation prompts for quality issues.

Grounded in Claude Code's agent orchestration principles from
src/constants/prompts.ts (lines 316-320):

  "Avoid duplicating work that subagents are already doing -- if you delegate
   research to a subagent, do not also perform the same searches yourself."

  "If you ARE the fork -- execute directly; do not re-delegate."

  "Brief the agent like a smart colleague who just walked into the room --
   it hasn't seen this conversation, doesn't know what you've tried."

Usage:
    python delegation_audit.py --check-prompt my_prompts.md
    python delegation_audit.py --audit-session ~/.claude/sessions/abc.jsonl
    python delegation_audit.py --generate-template code-review
    python delegation_audit.py --generate-template feature-dev
    python delegation_audit.py --generate-template debugging
    python delegation_audit.py --generate-template data-analysis
"""

import re
import sys
import json
import argparse
from pathlib import Path
from textwrap import dedent


# ---------------------------------------------------------------------------
# Detection rules
# Each rule: (name, pattern, severity, description, suggestion, points_deducted)
# ---------------------------------------------------------------------------

BAD_DELEGATION_PATTERNS = [
    (
        'context_leak_findings',
        re.compile(
            r'\b(based\s+on\s+(your\s+)?(findings|results?|research|analysis|output)|'
            r'from\s+(what|the)\s+you\s+found|as\s+you\s+(found|discovered|identified))\b',
            re.IGNORECASE
        ),
        'CRITICAL',
        'References prior findings the sub-agent cannot see',
        'Sub-agents have no conversation history. Include the actual findings inline.',
        25,
    ),
    (
        'context_leak_conversation',
        re.compile(
            r'\b(previous\s+conversation|earlier\s+discussion|as\s+(we|I)\s+discussed|'
            r'as\s+mentioned\s+(before|earlier|above)|from\s+our\s+(earlier|previous)\s+chat|'
            r'based\s+on\s+(the\s+)?(previous|earlier|prior)\s+(research|discussion|context))\b',
            re.IGNORECASE
        ),
        'CRITICAL',
        'References conversation context the sub-agent cannot access',
        'Sub-agents start fresh. Paste the relevant excerpt directly into the prompt.',
        25,
    ),
    (
        'no_file_paths_in_code_task',
        re.compile(
            r'\b(look\s+at|check|review|examine|inspect|analyze|read)\s+(the\s+)?(code|module|'
            r'function|class|file|implementation|auth|session|database|api)\b(?!.*\b[\w/\\.-]+\.\w+\b)',
            re.IGNORECASE
        ),
        'HIGH',
        'Refers to code without specifying file paths',
        'Include exact file paths (e.g. src/auth/login.ts:42) so the agent does not need to guess.',
        15,
    ),
    (
        'no_output_format',
        re.compile(
            r'^(?!.*\b(output\s+format|return\s+(a\s+)?(list|json|table|markdown|file|path|verdict|'
            r'pass|fail)|format:|respond\s+with|end\s+with|cap\s+at|max\s+\d+|limit\s+(to\s+)?\d+))',
            re.IGNORECASE | re.DOTALL
        ),
        'HIGH',
        'No output format specified',
        'Specify the exact output structure (list, JSON, markdown table, verdict line). '
        'Without this, the orchestrator cannot parse the result reliably.',
        15,
    ),
    (
        'no_length_cap',
        re.compile(
            r'^(?!.*\b(cap\s+at|max(imum)?\s+\d+|limit\s+(to\s+)?\d+|no\s+more\s+than\s+\d+|'
            r'top\s+\d+|first\s+\d+|\d+\s+(results?|items?|lines?|entries)))',
            re.IGNORECASE | re.DOTALL
        ),
        'MEDIUM',
        'No length cap on results',
        'Add a cap (e.g. "max 20 results", "cap at 50 lines") to prevent context overflow.',
        10,
    ),
    (
        'vague_goal_investigate',
        re.compile(
            r'^\s*(investigate|look\s+into|explore|check\s+out|have\s+a\s+look|'
            r'see\s+what\s+you\s+can\s+find|figure\s+out)\b',
            re.IGNORECASE | re.MULTILINE
        ),
        'HIGH',
        'Vague goal verb without specific deliverable',
        'Replace with a specific deliverable: "Find all X matching Y", '
        '"List files where Z", "Return PASS/FAIL for these checks".',
        15,
    ),
    (
        'vague_goal_general',
        re.compile(
            r'\b(do\s+your\s+best|use\s+your\s+(best\s+)?judgment|whatever\s+you\s+think|'
            r'as\s+appropriate|however\s+you\s+see\s+fit)\b',
            re.IGNORECASE
        ),
        'MEDIUM',
        'Defers to agent judgment without providing decision criteria',
        'Supply the judgment criteria explicitly: what makes a result important, '
        'what thresholds to use, what "good" looks like.',
        10,
    ),
    (
        'chained_delegation',
        re.compile(
            r'\b(also\s+(check|look|review|investigate|analyze|search)|'
            r'then\s+(also\s+)?(check|look|review)|'
            r'in\s+addition[,\s]+(also\s+)?(look|check|review))\b',
            re.IGNORECASE
        ),
        'HIGH',
        'Contains chained tasks (multiple sequential steps in one prompt)',
        'Split into separate delegation briefs. Each sub-agent does one bounded task.',
        15,
    ),
    (
        'no_context_for_judgment',
        re.compile(
            r'^(?!.*\b(because|goal\s+(is|:)|context\s*:|we\s+(need|want|are\s+trying)|'
            r'this\s+matters|why\s+this|reason\s*:|background\s*:|purpose\s*:))',
            re.IGNORECASE | re.DOTALL
        ),
        'MEDIUM',
        'No context explaining why this task matters',
        'Add a CONTEXT or GOAL section explaining the purpose. '
        'This allows the agent to make reasonable judgment calls when edge cases arise.',
        10,
    ),
    (
        're_delegation_hint',
        re.compile(
            r'\b(ask\s+another\s+agent|delegate\s+(this\s+)?to|spawn\s+(a\s+)?sub.?agent|'
            r'use\s+(an?\s+)?agent\s+to)\b',
            re.IGNORECASE
        ),
        'CRITICAL',
        'Prompt instructs the sub-agent to re-delegate',
        '"If you ARE the fork -- execute directly; do not re-delegate." '
        'Sub-agents must execute tasks themselves.',
        25,
    ),
]

# Positive signals that improve score
POSITIVE_PATTERNS = [
    ('has_goal',
     re.compile(r'\bGOAL\s*:', re.IGNORECASE),
     'Has explicit GOAL section', 5),
    ('has_scope',
     re.compile(r'\bSCOPE\s*:', re.IGNORECASE),
     'Has explicit SCOPE section', 5),
    ('has_context',
     re.compile(r'\bCONTEXT\s*:', re.IGNORECASE),
     'Has explicit CONTEXT section', 5),
    ('has_output_format',
     re.compile(r'\b(OUTPUT\s+FORMAT|RETURN\s+FORMAT)\s*:', re.IGNORECASE),
     'Has explicit OUTPUT FORMAT section', 10),
    ('has_already_tried',
     re.compile(r'\b(ALREADY\s+(TRIED|RULED\s+OUT)|SKIP\s*:|EXCLUDED?\s*:)', re.IGNORECASE),
     'Documents what has been ruled out', 5),
    ('has_file_paths',
     re.compile(r'\b[\w/\\.-]+\.(ts|js|py|go|rs|java|kt|rb|php|cs|cpp|c|h)\b'),
     'Includes specific file paths', 5),
    ('has_length_cap',
     re.compile(r'\b(cap\s+at|max(imum)?\s+\d+|no\s+more\s+than\s+\d+|top\s+\d+|\d+\s+(results?|items?))\b',
                re.IGNORECASE),
     'Specifies a length cap', 5),
    ('has_verdict_format',
     re.compile(r'\bVERDICT\s*:', re.IGNORECASE),
     'Uses explicit VERDICT format for judgment tasks', 5),
    ('has_judgment_guide',
     re.compile(r'\b(JUDGMENT\s+GUIDE|CRITERIA\s*:|FLAG\s+(if|when|any))\b', re.IGNORECASE),
     'Provides judgment criteria', 5),
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_prompt(text: str) -> dict:
    """
    Score a single delegation prompt 0-100 and return findings.
    """
    result = {
        'score': 100,
        'length': len(text),
        'word_count': len(text.split()),
        'issues': [],
        'positives': [],
        'suggestions': [],
    }

    # Penalize for bad patterns
    for name, pattern, severity, description, suggestion, penalty in BAD_DELEGATION_PATTERNS:
        matches = list(pattern.finditer(text))
        if matches:
            result['score'] = max(0, result['score'] - penalty)
            preview_match = matches[0]
            preview = text[max(0, preview_match.start()-20):preview_match.end()+20].strip()
            line_no = text[:preview_match.start()].count('\n') + 1
            result['issues'].append({
                'name': name,
                'severity': severity,
                'description': description,
                'suggestion': suggestion,
                'count': len(matches),
                'line': line_no,
                'preview': preview[:80],
            })

    # Bonus for good patterns
    for name, pattern, description, bonus in POSITIVE_PATTERNS:
        if pattern.search(text):
            result['score'] = min(100, result['score'] + bonus)
            result['positives'].append(description)

    # Penalize very short prompts (likely missing context)
    if result['word_count'] < 20:
        result['score'] = max(0, result['score'] - 20)
        result['issues'].append({
            'name': 'too_short',
            'severity': 'HIGH',
            'description': f'Prompt is very short ({result["word_count"]} words) -- likely missing context',
            'suggestion': 'Add GOAL, SCOPE, CONTEXT, and OUTPUT FORMAT sections.',
            'count': 1,
            'line': 1,
            'preview': text[:80],
        })

    result['grade'] = grade_label(result['score'])
    return result


def grade_label(score: int) -> str:
    if score >= 85:
        return 'GOOD'
    if score >= 65:
        return 'FAIR'
    if score >= 40:
        return 'POOR'
    return 'FAILING'


# ---------------------------------------------------------------------------
# Prompt file parsing
# ---------------------------------------------------------------------------

def extract_prompts_from_markdown(text: str) -> list[dict]:
    """
    Extract agent prompts from a markdown file.
    Looks for fenced code blocks labeled 'agent-prompt', 'delegation', or
    'subagent', or for H2/H3 sections followed by quoted content.
    """
    prompts = []

    # Strategy 1: fenced code blocks with agent-related labels
    code_fence = re.compile(
        r'```(?:agent-?prompt|delegation|subagent|agent)?\s*\n(.*?)```',
        re.DOTALL | re.IGNORECASE
    )
    for m in code_fence.finditer(text):
        content = m.group(1).strip()
        if len(content.split()) >= 5:
            line_no = text[:m.start()].count('\n') + 1
            prompts.append({'source': f'code block at line {line_no}', 'text': content})

    # Strategy 2: H2/H3 sections whose title contains prompt/agent/delegation
    section_header = re.compile(
        r'^#{2,3}\s+.*?(prompt|agent|delegation|brief|subagent).*?$\n+(.*?)(?=^#{2,3}\s|\Z)',
        re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    for m in section_header.finditer(text):
        content = m.group(2).strip()
        # Strip markdown formatting
        content = re.sub(r'^```\w*\n|```$', '', content, flags=re.MULTILINE).strip()
        if len(content.split()) >= 10:
            line_no = text[:m.start()].count('\n') + 1
            prompts.append({'source': f'section at line {line_no}', 'text': content})

    # Deduplicate by content
    seen = set()
    unique = []
    for p in prompts:
        key = p['text'][:100]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


# ---------------------------------------------------------------------------
# Session JSONL parsing
# ---------------------------------------------------------------------------

def extract_agent_calls_from_jsonl(path: Path) -> list[dict]:
    """
    Scan a Claude Code session JSONL for Agent tool calls.
    Returns list of {'turn': int, 'prompt': str} dicts.
    """
    calls = []
    turn = 0

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Look for tool use blocks in content arrays
                content_blocks = []

                # Handle different JSONL message shapes
                if isinstance(entry, dict):
                    # shape: {type: "message", content: [...]}
                    if 'content' in entry and isinstance(entry['content'], list):
                        content_blocks = entry['content']
                    # shape: {message: {content: [...]}}
                    elif 'message' in entry and isinstance(entry.get('message'), dict):
                        msg = entry['message']
                        if 'content' in msg and isinstance(msg['content'], list):
                            content_blocks = msg['content']
                            turn += 1

                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') != 'tool_use':
                        continue
                    tool_name = block.get('name', '')
                    if tool_name not in ('Agent', 'Task'):
                        continue
                    inp = block.get('input', {})
                    prompt = inp.get('prompt', '') or inp.get('description', '')
                    if prompt:
                        calls.append({
                            'turn': turn,
                            'jsonl_line': line_no,
                            'tool': tool_name,
                            'prompt': prompt,
                        })

    except (OSError, IOError) as e:
        print(f'Error reading {path}: {e}', file=sys.stderr)

    return calls


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

SEVERITY_ICONS = {'CRITICAL': '[CRIT]', 'HIGH': '[HIGH]', 'MEDIUM': '[WARN]', 'LOW': '[NOTE]'}
GRADE_ICONS = {'GOOD': '[OK]', 'FAIR': '[~]', 'POOR': '[!]', 'FAILING': '[X]'}


def print_prompt_report(label: str, text: str, result: dict, verbose: bool = True):
    icon = GRADE_ICONS[result['grade']]
    print(f"\n{'─'*64}")
    print(f"  {icon} {label}")
    print(f"     Score: {result['score']}/100 ({result['grade']})  |  "
          f"{result['word_count']} words")

    if result['positives']:
        print(f"     Good: {', '.join(result['positives'])}")

    if not result['issues']:
        print(f"     No delegation issues found.")
        return

    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    issues = sorted(result['issues'], key=lambda x: severity_order.get(x['severity'], 99))

    for issue in issues:
        sev = issue['severity']
        icon_s = SEVERITY_ICONS.get(sev, '[?]')
        print(f"\n  {icon_s} {issue['description']}")
        if issue.get('preview') and verbose:
            print(f"       Found: \"{issue['preview']}\"")
        print(f"       Fix:   {issue['suggestion']}")


def print_summary(results: list[dict]):
    if not results:
        return
    avg = sum(r['score'] for r in results) / len(results)
    failing = sum(1 for r in results if r['grade'] in ('POOR', 'FAILING'))
    print(f"\n{'='*64}")
    print(f"  Summary: {len(results)} prompts | avg score: {avg:.0f}/100 | "
          f"{failing} need improvement")
    if failing:
        print(f"\n  Run /delegation-rules to generate better prompt templates.")
    print(f"{'='*64}\n")


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

TEMPLATES = {
    'code-review': dedent("""\
        # Delegation Brief Template: Code Review

        ## Agent: security-reviewer

        GOAL: Identify [VULNERABILITY_TYPE] risks in [MODULE_NAME].

        SCOPE: Read these files only:
          - [path/to/file1.ts]
          - [path/to/file2.ts]
          (Do NOT read files outside this list.)

        CONTEXT: We are reviewing [MODULE_NAME] because [REASON].
          We already know [KNOWN_ISSUE] exists at [file:line].
          We need to know if this pattern appears elsewhere.

        ALREADY RULED OUT:
          - [path/to/safe_file.ts] -- uses parameterized queries throughout
          - [path/to/other.ts] -- no user input reaches this module

        OUTPUT FORMAT:
          List of findings, one per line:
            [file:line] [severity] [description]
          End with exactly one of:
            VERDICT: CRITICAL
            VERDICT: HIGH
            VERDICT: NONE
          Cap at 20 findings.

        JUDGMENT GUIDE:
          Flag: any place where user-controlled input reaches [RISK_SURFACE]
                without explicit [PROTECTION_MECHANISM].
          Skip: test files, mock implementations, read-only paths.
    """),

    'feature-dev': dedent("""\
        # Delegation Brief Template: Feature Development

        ## Agent: implementer

        GOAL: Implement [FUNCTION_NAME]([PARAMETERS]) in [file/path.ts].

        SPEC:
          Input:  [parameter descriptions with types]
          Output: [return type and shape]
          Behavior:
            - [rule 1]
            - [rule 2]
            - [edge case handling]

        CONTEXT: This function is part of [FEATURE]. It will be called by
          [CALLER] when [TRIGGER]. The existing [RELATED_FUNCTION] at
          [file:line] shows the expected code style.

        CONSTRAINTS:
          - Do NOT modify any file except [target/file.ts]
          - Do NOT change the public API of [ExistingClass]
          - Follow the coding style in [reference/file.ts]

        OUTPUT FORMAT:
          Return the complete updated contents of [file/path.ts].
          List any new imports added at the top of your response.
          End with: DONE: [function name] implemented

        ALREADY TRIED:
          - [approach that was rejected] -- failed because [reason]
    """),

    'debugging': dedent("""\
        # Delegation Brief Template: Debugging

        ## Agent: root-cause-finder

        GOAL: Identify the root cause of [ERROR_MESSAGE / SYMPTOM].

        SYMPTOM:
          Error:   [exact error text or stack trace]
          Context: [what was happening when it occurred]
          When:    [always / intermittent / under load / after deploy]

        SCOPE: Investigate these files only:
          - [path/to/suspect_file.ts] (most likely)
          - [path/to/dependency.ts]

        CONTEXT: The error started occurring after [CHANGE_EVENT].
          The system handles [DESCRIPTION_OF_FLOW].
          Normal flow: [step A] -> [step B] -> [step C]
          Broken flow: fails at [step] when [condition].

        ALREADY RULED OUT:
          - Network timeout (error occurs locally too)
          - [other_module.ts] (unchanged, same as working version)

        OUTPUT FORMAT:
          1. Root cause hypothesis (1-2 sentences)
          2. Evidence (file:line references)
          3. Recommended fix (code snippet or description)
          4. Confidence: HIGH / MEDIUM / LOW
          Cap at 500 words total.
    """),

    'data-analysis': dedent("""\
        # Delegation Brief Template: Data Analysis

        ## Agent: data-transformer

        GOAL: [Transform / Aggregate / Filter] [DATA_DESCRIPTION] and
          return [OUTPUT_DESCRIPTION].

        INPUT:
          Source: [file path or describe the data structure]
          Format: [CSV / JSON / JSONL / SQL result]
          Size:   [approximate row count]
          Key fields: [field1 (type), field2 (type), ...]

        TRANSFORMATION:
          - [Step 1: filter condition]
          - [Step 2: aggregation or join]
          - [Step 3: output shaping]

        CONTEXT: This data will be used for [PURPOSE]. We need
          [SPECIFIC_INSIGHT] to make [DECISION]. The downstream
          consumer expects [FORMAT_CONSTRAINT].

        KNOWN DATA ISSUES:
          - [field_name] has nulls in ~[N]% of rows -- treat as [default]
          - Timestamps are in [TIMEZONE], convert to UTC

        OUTPUT FORMAT:
          [JSON array / CSV / markdown table] with these columns:
            [col1], [col2], [col3]
          Cap at [N] rows.
          End with: ROWS_RETURNED: [count]
    """),
}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def cmd_check_prompt(args):
    path = Path(args.check_prompt).expanduser()
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding='utf-8', errors='replace')
    prompts = extract_prompts_from_markdown(text)

    print(f"\n{'='*64}")
    print(f"  Delegation Prompt Audit: {path.name}")
    print(f"  {len(prompts)} prompt(s) found")
    print(f"{'='*64}")

    if not prompts:
        print("\n  No agent prompts detected.")
        print("  Tip: Wrap delegation prompts in ```agent-prompt ... ``` blocks,")
        print("  or use H2/H3 sections with 'prompt' or 'agent' in the title.")
        return

    all_results = []
    for p in prompts:
        result = score_prompt(p['text'])
        all_results.append(result)
        print_prompt_report(p['source'], p['text'], result)

    print_summary(all_results)


def cmd_audit_session(args):
    path = Path(args.audit_session).expanduser()
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    calls = extract_agent_calls_from_jsonl(path)

    print(f"\n{'='*64}")
    print(f"  Session Agent Call Audit: {path.name}")
    print(f"  {len(calls)} Agent/Task call(s) found")
    print(f"{'='*64}")

    if not calls:
        print("\n  No Agent tool calls found in this session.")
        print("  Checked for 'Agent' and 'Task' tool_use blocks.")
        return

    all_results = []
    for call in calls:
        result = score_prompt(call['prompt'])
        all_results.append(result)
        label = (f"Turn {call['turn']}, JSONL line {call['jsonl_line']} "
                 f"({call['tool']})")
        print_prompt_report(label, call['prompt'], result)

    print_summary(all_results)


def cmd_generate_template(args):
    wf = args.generate_template
    if wf not in TEMPLATES:
        print(f"Unknown workflow type: {wf}", file=sys.stderr)
        print(f"Available: {', '.join(TEMPLATES.keys())}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*64}")
    print(f"  Delegation Brief Template: {wf}")
    print(f"  Replace [BRACKETED] placeholders with actual values.")
    print(f"{'='*64}\n")
    print(TEMPLATES[wf])
    print("\nTip: Items in [BRACKETS] are required. Fill every one before sending.")
    print("     Run --check-prompt on the filled template to verify quality.")


def main():
    parser = argparse.ArgumentParser(
        description='Audit Agent delegation prompts for quality issues.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--check-prompt',
        metavar='FILE',
        help='Read a markdown file containing agent prompts and audit each one.'
    )
    group.add_argument(
        '--audit-session',
        metavar='FILE.jsonl',
        help='Scan a Claude Code session JSONL for Agent tool calls and grade them.'
    )
    group.add_argument(
        '--generate-template',
        metavar='WORKFLOW',
        choices=list(TEMPLATES.keys()),
        help=f'Generate a delegation brief template. Choices: {", ".join(TEMPLATES.keys())}'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress match previews (show issues only, no quoted text).'
    )

    args = parser.parse_args()

    if args.check_prompt:
        cmd_check_prompt(args)
    elif args.audit_session:
        cmd_audit_session(args)
    elif args.generate_template:
        cmd_generate_template(args)


if __name__ == '__main__':
    main()
