#!/usr/bin/env python3
"""
persona_generator.py — Generate CLAUDE.md persona configuration fragments.

Inspired by the undercover mode design in src/utils/undercover.ts:
- Asymmetric safety: default to most restrictive persona when detection is ambiguous
- Environment detection: git remote, cwd pattern, branch prefix, env var
- Explicit stripping rules: each persona declares what NOT to output

Usage:
    python3 persona_generator.py --interactive
    python3 persona_generator.py --detect
    python3 persona_generator.py --test-detection
    python3 persona_generator.py --interactive --output ~/my-project/CLAUDE.md
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

DETECTION_METHODS = ["env_var", "git_remote", "cwd_pattern", "branch_prefix"]

EXCLUSION_EXAMPLES = [
    "internal codenames or unreleased project names",
    "unreleased version numbers or roadmap items",
    "internal URLs, hostnames, or tool names (e.g., internal Jira, Confluence)",
    "personal names or org-internal handles",
    "credentials, tokens, or internal API keys",
    '"Generated with Claude" or AI attribution lines',
    "Slack channel names or internal ticket IDs",
    "internal architecture details not for public consumption",
]

OUTPUT_STYLES = ["verbose", "concise"]
TERMINOLOGY_LEVELS = ["internal", "external"]
ATTRIBUTION_OPTIONS = ["include", "strip", "neutral"]


@dataclass
class DetectionRule:
    method: str         # one of DETECTION_METHODS
    value: str          # the pattern to match


@dataclass
class Persona:
    name: str
    detection: DetectionRule
    output_style: str
    terminology: str
    attribution: str
    always_exclude: list[str] = field(default_factory=list)
    always_include: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

def get_git_remote() -> str:
    """Return stdout of 'git remote -v', or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def get_current_branch() -> str:
    """Return current git branch name, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def detect_active_persona(personas: list[Persona]) -> Optional[Persona]:
    """
    Return the first matching persona using detection priority order:
    1. env_var (most explicit)
    2. git_remote
    3. cwd_pattern
    4. branch_prefix

    If no match, returns the last persona (assumed most restrictive by convention).
    Mirrors the undercover.ts one-way gate: when ambiguous, fall to safer mode.
    """
    git_remote = get_git_remote()
    cwd = os.getcwd()
    branch = get_current_branch()
    env_vars = dict(os.environ)

    # Sort by detection priority
    priority = {m: i for i, m in enumerate(DETECTION_METHODS)}
    ordered = sorted(personas, key=lambda p: priority.get(p.detection.method, 99))

    for persona in ordered:
        rule = persona.detection
        if rule.method == "env_var":
            env_key, _, env_val = rule.value.partition("=")
            actual = env_vars.get(env_key.strip(), "")
            if env_val:
                if actual == env_val.strip():
                    return persona
            else:
                if actual:
                    return persona
        elif rule.method == "git_remote":
            if rule.value and rule.value in git_remote:
                return persona
        elif rule.method == "cwd_pattern":
            if rule.value and rule.value in cwd:
                return persona
        elif rule.method == "branch_prefix":
            if branch.startswith(rule.value):
                return persona

    # Asymmetric safety default: return last persona (user is told to put most restrictive last)
    if personas:
        return personas[-1]
    return None


# ---------------------------------------------------------------------------
# CLAUDE.md fragment generation
# ---------------------------------------------------------------------------

def render_persona_fragment(persona: Persona) -> str:
    detection_desc = f"{persona.detection.method}: {persona.detection.value}"
    exclude_lines = "\n".join(f"- {item}" for item in persona.always_exclude) if persona.always_exclude else "- (none specified)"
    include_lines = "\n".join(f"- {item}" for item in persona.always_include) if persona.always_include else "- (none specified)"

    return f"""\
<!-- persona: {persona.name} | detection: {persona.detection.method} | value: {persona.detection.value} -->
## Claude behavior — {persona.name} context

When this file is active, apply **{persona.name}** rules.
Detection heuristic: {detection_desc}

### Output style
{persona.output_style}

### Terminology
{persona.terminology}-facing language. {'Internal jargon and codenames are acceptable.' if persona.terminology == 'internal' else 'Use only externally appropriate terminology. Avoid internal jargon.'}

### Attribution
{'Include full attribution and AI disclosure.' if persona.attribution == 'include' else 'Strip all AI attribution lines ("Generated with Claude", etc.).' if persona.attribution == 'strip' else 'Use neutral phrasing; omit specific AI tool attribution.'}

### Never output in this context
{exclude_lines}

### Always include in this context
{include_lines}
"""


def render_full_config(personas: list[Persona]) -> str:
    header = """\
# Claude Persona Configuration
# Generated by persona_generator.py
# Inspired by src/utils/undercover.ts undercover mode design
#
# Design principles:
#   - Asymmetric safety: default activates the LAST persona (most restrictive)
#   - Detection priority: env_var > git_remote > cwd_pattern > branch_prefix
#   - Explicit stripping: each persona declares what NOT to output
#
# Place persona-specific fragments in the relevant project CLAUDE.md,
# or load globally from ~/.claude/rules/personas/

"""
    fragments = "\n---\n\n".join(render_persona_fragment(p) for p in personas)
    return header + fragments + "\n"


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{message}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value if value else default


def choose(message: str, options: list[str], default: str = "") -> str:
    options_str = "/".join(options)
    while True:
        value = prompt(f"{message} ({options_str})", default)
        if value in options:
            return value
        print(f"  Please enter one of: {options_str}")


def collect_list(message: str, examples: list[str] | None = None) -> list[str]:
    print(f"\n{message}")
    if examples:
        print("  Examples:")
        for ex in examples[:4]:
            print(f"    - {ex}")
    print("  Enter items one per line. Empty line to finish.")
    items = []
    while True:
        try:
            item = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not item:
            break
        items.append(item)
    return items


def collect_detection_rule() -> DetectionRule:
    print("\n  Detection method options:")
    print("    env_var      — e.g., PERSONA=internal-dev")
    print("    git_remote   — e.g., acme-corp.net  (substring of git remote URL)")
    print("    cwd_pattern  — e.g., /clients/       (substring of working directory path)")
    print("    branch_prefix— e.g., oss/            (branch name prefix)")

    method = choose("  Detection method", DETECTION_METHODS, "git_remote")

    if method == "env_var":
        value = prompt("  Env var (KEY or KEY=VALUE)", "PERSONA=")
    elif method == "git_remote":
        value = prompt("  Git remote substring to match", "github.com/my-org-internal")
    elif method == "cwd_pattern":
        value = prompt("  Directory path substring to match", "/clients/")
    else:
        value = prompt("  Branch name prefix to match", "oss/")

    return DetectionRule(method=method, value=value)


def run_interactive_wizard() -> list[Persona]:
    print("\n=== Claude Code Persona Wizard ===")
    print("Inspired by src/utils/undercover.ts — define 2-3 work context personas.\n")
    print("IMPORTANT: Place your MOST RESTRICTIVE persona last.")
    print("When no detection rule matches, the last persona activates (asymmetric safety).\n")

    try:
        count_str = prompt("How many personas do you want to define? (2-3)", "2")
        count = max(2, min(3, int(count_str)))
    except ValueError:
        count = 2

    personas: list[Persona] = []

    for i in range(count):
        print(f"\n--- Persona {i + 1} of {count} ---")
        name = prompt("Persona name (e.g., internal-dev, client-facing, open-source)", f"persona-{i+1}")
        print(f"\nDefine the detection rule for '{name}':")
        detection = collect_detection_rule()

        print(f"\nBehavior settings for '{name}':")
        style = choose("  Output style", OUTPUT_STYLES, "verbose" if i == 0 else "concise")
        terminology = choose("  Terminology level", TERMINOLOGY_LEVELS, "internal" if i == 0 else "external")
        attribution = choose("  Attribution", ATTRIBUTION_OPTIONS, "include" if i == 0 else "strip")

        print(f"\nContent rules for '{name}':")
        always_exclude = collect_list(
            "What should Claude NEVER output in this context?",
            examples=EXCLUSION_EXAMPLES,
        )
        always_include = collect_list(
            "What should Claude ALWAYS include in this context?",
        )

        personas.append(Persona(
            name=name,
            detection=detection,
            output_style=style,
            terminology=terminology,
            attribution=attribution,
            always_exclude=always_exclude,
            always_include=always_include,
        ))

    return personas


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_detect(personas: list[Persona] | None = None) -> None:
    """Auto-detect current context and report which persona would activate."""
    git_remote = get_git_remote()
    branch = get_current_branch()
    cwd = os.getcwd()

    print("=== Environment Detection Report ===")
    print(f"  Working directory : {cwd}")
    print(f"  Current branch    : {branch or '(not in a git repo)'}")
    print(f"  Git remotes       :\n{('    ' + git_remote.replace(chr(10), chr(10) + '    ')) if git_remote else '    (none)'}")

    print("\n  Checking environment variables for PERSONA=...")
    persona_env = os.environ.get("PERSONA", "")
    if persona_env:
        print(f"  PERSONA={persona_env}")
    else:
        print("  PERSONA not set")

    if personas:
        active = detect_active_persona(personas)
        if active:
            print(f"\n  Active persona: {active.name}")
            print(f"  Detection rule: {active.detection.method} = {active.detection.value}")
        else:
            print("\n  No persona matched and no fallback defined.")
    else:
        print("\n  No personas defined yet. Run --interactive to create them.")


def cmd_test_detection(personas: list[Persona]) -> None:
    """Test all detection rules against current environment."""
    git_remote = get_git_remote()
    cwd = os.getcwd()
    branch = get_current_branch()
    env_vars = dict(os.environ)

    print("=== Detection Rule Test ===\n")
    for persona in personas:
        rule = persona.detection
        matched = False

        if rule.method == "env_var":
            env_key, _, env_val = rule.value.partition("=")
            actual = env_vars.get(env_key.strip(), "")
            matched = (actual == env_val.strip()) if env_val else bool(actual)
        elif rule.method == "git_remote":
            matched = bool(rule.value and rule.value in git_remote)
        elif rule.method == "cwd_pattern":
            matched = bool(rule.value and rule.value in cwd)
        elif rule.method == "branch_prefix":
            matched = branch.startswith(rule.value)

        status = "MATCH" if matched else "no match"
        print(f"  [{status:8}] {persona.name:20} ({rule.method}: {rule.value})")

    active = detect_active_persona(personas)
    print(f"\n  => Active persona: {active.name if active else '(none)'}")
    if active == personas[-1] and not any(
        p != personas[-1] for p in [detect_active_persona(personas)]
    ):
        print("     (activated by asymmetric safety default — no rule matched)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate CLAUDE.md persona configuration fragments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run the interactive persona wizard.",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Auto-detect current context and report which persona would activate.",
    )
    parser.add_argument(
        "--test-detection",
        action="store_true",
        help="Test all detection rules against current environment.",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Write generated CLAUDE.md fragments to FILE (default: stdout).",
    )

    args = parser.parse_args()

    if args.detect and not args.interactive:
        cmd_detect()
        return

    if not args.interactive and not args.test_detection:
        parser.print_help()
        return

    personas = run_interactive_wizard()

    if not personas:
        print("No personas defined. Exiting.")
        return

    if args.test_detection:
        print()
        cmd_test_detection(personas)

    if args.detect:
        print()
        cmd_detect(personas)

    config = render_full_config(personas)

    if args.output:
        output_path = os.path.expanduser(args.output)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(config)
        print(f"\nConfiguration written to: {output_path}")
    else:
        print("\n=== Generated CLAUDE.md Fragments ===\n")
        print(config)
        print("Tip: Run with --output <file> to write directly to a CLAUDE.md.")


if __name__ == "__main__":
    main()
