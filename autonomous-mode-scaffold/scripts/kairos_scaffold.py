#!/usr/bin/env python3
"""
kairos_scaffold.py — Generate CLAUDE.md fragments and hooks config for autonomous operation.

Derived from the KAIROS proactive mode design in src/constants/prompts.ts:860-913.

Usage:
    python3 kairos_scaffold.py --interactive
    python3 kairos_scaffold.py --project-name "my-api" --safe-actions "run tests,lint" \
        --blocked-actions "delete files,force push" --alert-triggers "test failure"
    python3 kairos_scaffold.py --list-patterns
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent


# ---------------------------------------------------------------------------
# Built-in autonomy patterns
# ---------------------------------------------------------------------------

PATTERNS = {
    "code-review-bot": {
        "description": "Runs on every push; reviews changed files, posts inline comments.",
        "safe_actions": [
            "read any file in the repository",
            "run git log / git diff / git show",
            "run static analysis and linters",
            "create GitHub PR review comments",
            "open issues for recurring violations",
            "commit auto-fixable lint issues to a separate branch",
        ],
        "blocked_actions": [
            "merge or close pull requests",
            "delete any branch or tag",
            "modify .github/workflows/**",
            "push directly to main or master",
            "send external notifications (email, Slack) without explicit config",
        ],
        "alert_triggers": [
            "CRITICAL security vulnerability detected (OWASP Top 10)",
            "secrets or credentials found in diff",
            "test coverage drops below 80%",
            "linter exits non-zero on >20 files",
        ],
        "sleep_active_sec": 60,
        "sleep_idle_sec": 240,
    },
    "dependency-monitor": {
        "description": "Periodically checks for outdated or vulnerable dependencies.",
        "safe_actions": [
            "read package manifests (package.json, requirements.txt, Cargo.toml, go.mod)",
            "run dependency audit commands (npm audit, pip-audit, cargo audit)",
            "open a PR with minor/patch version bumps",
            "update lock files when bumping safe versions",
            "append audit results to .claude/autonomous_log.md",
        ],
        "blocked_actions": [
            "bump major version dependencies without user approval",
            "modify any source file outside package manifests",
            "delete node_modules or virtual environments",
            "run npm install / pip install in production environments",
            "publish packages to any registry",
        ],
        "alert_triggers": [
            "CVE with CVSS score >= 7.0 found",
            "dependency with known malware or typosquat detected",
            "major version breaking change available for a core dependency",
            "license incompatibility detected",
        ],
        "sleep_active_sec": 30,
        "sleep_idle_sec": 240,
    },
    "test-runner": {
        "description": "Continuously runs the test suite; auto-commits fixes for flaky tests.",
        "safe_actions": [
            "run the full test suite",
            "run tests for files changed since last commit",
            "read test output and stack traces",
            "open a PR with test fixes for clearly isolated failures",
            "annotate flaky tests with a retry decorator / skip reason",
            "update test snapshots when source change is intentional",
        ],
        "blocked_actions": [
            "delete test files",
            "skip or disable tests to make the suite pass",
            "modify production source files without a failing test to justify the change",
            "push to main / master",
            "alter CI/CD pipeline configuration",
        ],
        "alert_triggers": [
            "more than 3 test failures in a single run",
            "flaky test rate exceeds 5% over last 10 runs",
            "test suite runtime increases by more than 50%",
            "coverage drops below configured minimum",
        ],
        "sleep_active_sec": 45,
        "sleep_idle_sec": 180,
    },
    "doc-updater": {
        "description": "Keeps docs in sync with source code changes.",
        "safe_actions": [
            "read source files and existing documentation",
            "update JSDoc / docstring comments to match changed function signatures",
            "regenerate API reference docs from source annotations",
            "fix broken links in Markdown files",
            "commit documentation-only changes to a docs/ branch",
            "open a PR when documentation is out of sync",
        ],
        "blocked_actions": [
            "modify any source file logic (only comments/docs)",
            "delete documentation pages without finding a redirect target",
            "publish documentation to production hosting",
            "change version numbers in docs (must be human-approved)",
            "alter README.md in ways that change project positioning",
        ],
        "alert_triggers": [
            "public API removed without a deprecation notice in docs",
            "breaking change in function signature with no migration guide",
            "documentation build fails (broken MDX, missing image assets)",
        ],
        "sleep_active_sec": 60,
        "sleep_idle_sec": 240,
    },
}


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------

def build_autonomous_md(
    project_name: str,
    safe_actions: list[str],
    blocked_actions: list[str],
    alert_triggers: list[str],
    sleep_active_sec: int = 60,
    sleep_idle_sec: int = 240,
) -> str:
    """Return the AUTONOMOUS_MODE.md content string."""

    safe_lines = "\n".join(f"- {a}" for a in safe_actions)
    blocked_lines = "\n".join(f"- {a}" for a in blocked_actions)
    alert_lines = "\n".join(f"- {a}" for a in alert_triggers)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return dedent(f"""\
        <!-- Generated by kairos_scaffold.py on {generated_at} -->
        <!-- Project: {project_name} -->
        <!-- Append this block to your project's CLAUDE.md -->

        ## Autonomous Mode Rules

        <!-- Source: KAIROS proactive mode — src/constants/prompts.ts:860-913 -->
        <!-- Tick-based pacing; SleepTool MUST be called when idle. -->
        <!-- Prompt cache TTL = 5 min; keep sleep_idle <= 4 min to stay in cache. -->

        ### Pacing (SleepTool durations)

        - Active work session sleep: **{sleep_active_sec} seconds**
        - Idle / nothing queued sleep: **{sleep_idle_sec} seconds** (max 240 to stay within 5-min cache TTL)
        - After alert: pause autonomous work, wait for user response

        ### When user is AWAY (terminalFocus: unfocused)

        Lean autonomous. Make decisions, commit, push, open PRs — do not narrate each step.
        Only pause for: irreversible actions, external effects, ambiguous requirements.

        Permitted without asking:
        {safe_lines}

        ### When user is PRESENT (terminalFocus: focused)

        Collaborative mode. Surface choices before acting on anything beyond reads.

        - Explain what you are about to do before doing it
        - Ask before multi-file edits or any commit
        - Prefer shorter sleeps (30–60 s) so you stay responsive
        - Still respect the BLOCKED list below

        ### Always BLOCKED (never do autonomously)

        {blocked_lines}

        ### Alert triggers (wake user immediately)

        When any condition below is detected:
        1. Stop autonomous work loop
        2. Output a single concise alert block (no narration)
        3. Call SleepTool; do not resume until user responds

        {alert_lines}

        ### First wake-up protocol

        On the very first tick of a new autonomous session:
        - Greet the user briefly
        - Ask what to work on (do NOT explore or change anything unprompted)
        - After user provides a task, begin the tick → work → sleep loop

        ### No re-delegation

        If you are the executing agent, complete the task directly.
        Do not spawn sub-agents unless the task definition explicitly requires it.

        ### State recovery summary (when user returns)

        Output a compact summary block containing:
        1. Total actions taken (count by category)
        2. Files modified (list)
        3. Commits / PRs created (with links)
        4. Any blocked actions and reason they were blocked
        5. Current state vs. starting state delta
        6. What needs user decision next

        ### Operation log

        Append all autonomous actions to: `.claude/autonomous_log.md`
        Never delete or overwrite log history during an autonomous session.

        Format:
        ```
        [TIMESTAMP] ACTION: description | FILES: list | RESULT: outcome
        ```

        Example:
        ```
        [2026-04-15T14:23:01Z] ACTION: ran test suite | FILES: src/**, tests/** | RESULT: 42 passed, 0 failed
        [2026-04-15T14:25:00Z] ACTION: opened PR #47  | FILES: — | RESULT: https://github.com/org/repo/pull/47
        ```
    """)


def build_hooks_template(project_name: str, log_path: str = ".claude/autonomous_log.md") -> dict:
    """Return the hooks configuration dict."""
    return {
        "_comment": (
            "Merge the 'hooks' key into your .claude/settings.json. "
            "Generated by kairos_scaffold.py for project: " + project_name
        ),
        "hooks": {
            "PreToolUse": [
                {
                    "_comment": "Block irreversible shell commands during autonomous sessions",
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/"
                                "kairos_scaffold.py --check-command \"$CLAUDE_TOOL_INPUT_COMMAND\""
                            ),
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "_comment": "Append completed tool actions to the autonomous operation log",
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/"
                                f"kairos_scaffold.py --log-action "
                                f"--log-path \"{log_path}\" "
                                "--tool \"$CLAUDE_TOOL_NAME\" "
                                "--result-summary \"$CLAUDE_TOOL_OUTPUT_SUMMARY\""
                            ),
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "_comment": "Write session summary when Claude stops",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/"
                                f"kairos_scaffold.py --write-session-summary "
                                f"--log-path \"{log_path}\""
                            ),
                        }
                    ],
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# Side-effect helpers (--log-action, --check-command, --write-session-summary)
# These are invoked by the generated hooks at runtime.
# ---------------------------------------------------------------------------

def log_action(log_path: str, tool: str, result_summary: str) -> None:
    """Append a single action line to the operation log."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] ACTION: {tool} | FILES: — | RESULT: {result_summary}\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def check_command(command: str, blocked_patterns: list[str] | None = None) -> None:
    """
    Exit with code 2 (block) if command matches a blocked pattern.
    Prints a reason to stderr so Claude can read it.
    Called by the PreToolUse hook.
    """
    default_blocked = [
        "rm -rf",
        "git push --force",
        "git push -f",
        "DROP TABLE",
        "DROP DATABASE",
        "truncate",
        "> /dev/null 2>&1 && rm",
    ]
    patterns = blocked_patterns or default_blocked

    cmd_lower = command.lower()
    for pattern in patterns:
        if pattern.lower() in cmd_lower:
            print(
                f"[kairos_scaffold] BLOCKED: command matches blocked pattern '{pattern}'.\n"
                f"Command: {command}",
                file=sys.stderr,
            )
            sys.exit(2)


def write_session_summary(log_path: str) -> None:
    """Append a session-end marker to the operation log."""
    path = Path(log_path)
    if not path.exists():
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = f"\n--- SESSION END [{timestamp}] ---\n\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(marker)


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    display_default = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{display_default}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value if value else default


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def interactive_wizard() -> dict:
    print("\n=== Autonomous Mode Scaffold — Interactive Wizard ===")
    print("Source: KAIROS proactive mode (src/constants/prompts.ts:860-913)\n")
    print("Answer 6 questions to define your autonomy boundaries.\n")

    project_name = ask("1. Project name", default="my-project")

    print(
        "\n2. What can the agent do WITHOUT asking when you are away?\n"
        "   (comma-separated; e.g., 'run tests, lint code, commit passing builds')"
    )
    safe_raw = ask("   Safe actions", default="run tests,lint code,read any file")
    safe_actions = parse_csv(safe_raw)

    print(
        "\n3. What is ALWAYS blocked — even when you are away?\n"
        "   (e.g., 'delete files,force push to main,send emails,drop tables')"
    )
    blocked_raw = ask("   Blocked actions", default="delete files,force push,send emails")
    blocked_actions = parse_csv(blocked_raw)

    print(
        "\n4. What conditions should IMMEDIATELY wake you up / pause autonomous work?\n"
        "   (e.g., 'test failure,security vulnerability found,disk > 90%')"
    )
    alert_raw = ask("   Alert triggers", default="test suite failure,security vulnerability detected")
    alert_triggers = parse_csv(alert_raw)

    print(
        "\n5. Sleep duration during ACTIVE work sessions (seconds, recommended 30–60)."
    )
    sleep_active = int(ask("   Active sleep seconds", default="60"))

    print(
        "\n6. Sleep duration when IDLE / nothing queued (seconds, max 240 to stay in 5-min cache TTL)."
    )
    sleep_idle = int(ask("   Idle sleep seconds", default="240"))

    return {
        "project_name": project_name,
        "safe_actions": safe_actions,
        "blocked_actions": blocked_actions,
        "alert_triggers": alert_triggers,
        "sleep_active_sec": sleep_active,
        "sleep_idle_sec": min(sleep_idle, 240),
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_outputs(config: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / "AUTONOMOUS_MODE.md"
    hooks_path = output_dir / "hooks_template.json"

    md_content = build_autonomous_md(
        project_name=config["project_name"],
        safe_actions=config["safe_actions"],
        blocked_actions=config["blocked_actions"],
        alert_triggers=config["alert_triggers"],
        sleep_active_sec=config.get("sleep_active_sec", 60),
        sleep_idle_sec=config.get("sleep_idle_sec", 240),
    )

    hooks_content = build_hooks_template(project_name=config["project_name"])

    md_path.write_text(md_content, encoding="utf-8")
    hooks_path.write_text(
        json.dumps(hooks_content, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nGenerated files in: {output_dir.resolve()}")
    print(f"  {md_path.name}        — append to your project CLAUDE.md")
    print(f"  {hooks_path.name}  — merge hooks into .claude/settings.json")
    print()
    print("Next steps:")
    print(f"  cat {md_path} >> CLAUDE.md")
    print(f"  # Manually merge {hooks_path} into .claude/settings.json")


def list_patterns() -> None:
    print("\n=== Built-in Autonomy Patterns ===\n")
    for name, pattern in PATTERNS.items():
        print(f"  {name}")
        print(f"    {pattern['description']}")
        print(f"    Safe actions  : {len(pattern['safe_actions'])} defined")
        print(f"    Blocked       : {len(pattern['blocked_actions'])} defined")
        print(f"    Alert triggers: {len(pattern['alert_triggers'])} defined")
        print(
            f"    Sleep (active/idle): {pattern['sleep_active_sec']}s / {pattern['sleep_idle_sec']}s"
        )
        print()
    print("Use a pattern with: --pattern <name>")
    print("Example: python3 kairos_scaffold.py --pattern code-review-bot")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate CLAUDE.md fragments and hooks config for autonomous Claude Code operation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            Examples:
              Interactive wizard:
                python3 kairos_scaffold.py --interactive

              Non-interactive:
                python3 kairos_scaffold.py \\
                  --project-name "my-api" \\
                  --safe-actions "run tests,lint,commit passing builds" \\
                  --blocked-actions "delete files,force push,send emails" \\
                  --alert-triggers "test failure,security vulnerability"

              Use a built-in pattern:
                python3 kairos_scaffold.py --pattern dependency-monitor

              List patterns:
                python3 kairos_scaffold.py --list-patterns
        """),
    )

    # Generation modes
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="Run interactive wizard")
    mode.add_argument("--list-patterns", action="store_true", help="Show built-in autonomy patterns")
    mode.add_argument("--pattern", choices=list(PATTERNS.keys()), help="Use a built-in pattern")

    # Non-interactive inputs
    parser.add_argument("--project-name", default="my-project", help="Project name")
    parser.add_argument(
        "--safe-actions",
        default="",
        help="Comma-separated actions allowed without asking (unfocused mode)",
    )
    parser.add_argument(
        "--blocked-actions",
        default="",
        help="Comma-separated actions that are always blocked",
    )
    parser.add_argument(
        "--alert-triggers",
        default="",
        help="Comma-separated conditions that trigger an immediate user alert",
    )
    parser.add_argument(
        "--sleep-active",
        type=int,
        default=60,
        help="SleepTool duration during active work (seconds, default 60)",
    )
    parser.add_argument(
        "--sleep-idle",
        type=int,
        default=240,
        help="SleepTool duration when idle (seconds, max 240, default 240)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write output files (default: current directory)",
    )

    # Runtime hook helpers (invoked by generated hooks, not by users directly)
    parser.add_argument("--log-action", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--log-path", default=".claude/autonomous_log.md", help=argparse.SUPPRESS)
    parser.add_argument("--tool", default="unknown", help=argparse.SUPPRESS)
    parser.add_argument("--result-summary", default="", help=argparse.SUPPRESS)
    parser.add_argument("--check-command", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--write-session-summary", action="store_true", help=argparse.SUPPRESS)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # --- Runtime hook helpers ---

    if args.log_action:
        log_action(args.log_path, args.tool, args.result_summary)
        return

    if args.check_command is not None:
        check_command(args.check_command)
        return

    if args.write_session_summary:
        write_session_summary(args.log_path)
        return

    # --- User-facing modes ---

    if args.list_patterns:
        list_patterns()
        return

    if args.pattern:
        p = PATTERNS[args.pattern]
        config = {
            "project_name": args.project_name,
            "safe_actions": p["safe_actions"],
            "blocked_actions": p["blocked_actions"],
            "alert_triggers": p["alert_triggers"],
            "sleep_active_sec": p["sleep_active_sec"],
            "sleep_idle_sec": p["sleep_idle_sec"],
        }
        write_outputs(config, Path(args.output_dir))
        return

    if args.interactive:
        config = interactive_wizard()
        write_outputs(config, Path(args.output_dir))
        return

    # Non-interactive with explicit flags
    safe_actions = parse_csv(args.safe_actions) if args.safe_actions else [
        "read any file",
        "run tests",
        "lint code",
    ]
    blocked_actions = parse_csv(args.blocked_actions) if args.blocked_actions else [
        "delete files",
        "force push to main",
        "send external notifications",
    ]
    alert_triggers = parse_csv(args.alert_triggers) if args.alert_triggers else [
        "test suite failure",
        "security vulnerability detected",
    ]

    config = {
        "project_name": args.project_name,
        "safe_actions": safe_actions,
        "blocked_actions": blocked_actions,
        "alert_triggers": alert_triggers,
        "sleep_active_sec": args.sleep_active,
        "sleep_idle_sec": min(args.sleep_idle, 240),
    }

    write_outputs(config, Path(args.output_dir))


if __name__ == "__main__":
    main()
