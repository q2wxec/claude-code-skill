#!/usr/bin/env python3
"""
cache_health_audit.py — Claude Code prompt cache health auditor.

Analyzes Claude Code configuration files for patterns that cause prompt cache
breaks, as tracked by src/services/api/promptCacheBreakDetection.ts.

Usage:
    python3 cache_health_audit.py          # human-readable report
    python3 cache_health_audit.py --json   # machine-readable JSON

Exit codes:
    0 — healthy (score >= 85)
    1 — warning (score 65-84)
    2 — degraded (score 40-64)
    3 — critical (score < 40)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    domain: str          # settings | mcp | claudemd
    severity: str        # critical | high | medium | low | ok
    vector: str          # which of the 14 tracked vectors this affects
    message: str
    recommendation: str
    penalty: int         # points deducted from 100


@dataclass
class AuditResult:
    score: int
    status: str
    findings: list[Finding]
    recommendations: list[str]
    estimated_tokens_saved_per_day: int
    files_checked: list[str]
    mcp_server_count: int
    claudemd_files_found: list[str]


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

HOME = Path.home()
CWD = Path.cwd()

SETTINGS_CANDIDATES = [
    HOME / ".claude" / "settings.json",
    HOME / ".claude" / "settings.local.json",
    CWD / ".claude" / "settings.json",
]

CLAUDEMD_CANDIDATES = [
    HOME / ".claude" / "CLAUDE.md",
    CWD / ".claude" / "CLAUDE.md",
    CWD / "CLAUDE.md",
]


def find_existing(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.exists() and p.is_file()]


# ---------------------------------------------------------------------------
# Settings.json analysis
# ---------------------------------------------------------------------------

def load_json_file(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def audit_settings(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    merged: dict = {}

    for p in paths:
        data = load_json_file(p)
        if data and isinstance(data, dict):
            _deep_merge(merged, data)

    if not merged:
        findings.append(Finding(
            domain="settings",
            severity="low",
            vector="model",
            message="No settings.json files found or all are invalid JSON.",
            recommendation="Create ~/.claude/settings.json with at least a pinned 'model' field.",
            penalty=5,
        ))
        return findings

    env: dict = merged.get("env", {})
    if not isinstance(env, dict):
        env = {}

    # --- CLAUDE_CODE_EXTRA_BODY ---
    extra_body = env.get("CLAUDE_CODE_EXTRA_BODY", "")
    if extra_body:
        # Check for obviously dynamic values: timestamps, UUIDs, integers as seeds
        dynamic_patterns = [
            r"\d{10,}",          # unix timestamps / long ints
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",  # UUID
            r"\$\{",             # shell variable expansion
        ]
        has_dynamic = any(re.search(p, extra_body, re.IGNORECASE) for p in dynamic_patterns)
        if has_dynamic:
            findings.append(Finding(
                domain="settings",
                severity="high",
                vector="extraBodyHash",
                message="CLAUDE_CODE_EXTRA_BODY contains what looks like dynamic values "
                        "(timestamps, UUIDs, or shell expansions).",
                recommendation="Keep CLAUDE_CODE_EXTRA_BODY fully static. Never embed "
                               "request IDs, seeds, or timestamps. Each distinct value "
                               "forces a full cache miss on the extraBodyHash vector.",
                penalty=15,
            ))
        else:
            findings.append(Finding(
                domain="settings",
                severity="medium",
                vector="extraBodyHash",
                message="CLAUDE_CODE_EXTRA_BODY is set. Verify it is session-stable "
                        "(same value every time Claude Code starts).",
                recommendation="Audit CLAUDE_CODE_EXTRA_BODY contents. If any field "
                               "changes between sessions, remove it or make it static.",
                penalty=8,
            ))

    # --- model field ---
    top_model = merged.get("model", "")
    env_model = env.get("ANTHROPIC_MODEL", "")
    if not top_model and not env_model:
        findings.append(Finding(
            domain="settings",
            severity="medium",
            vector="model",
            message="No 'model' field found in settings.json or ANTHROPIC_MODEL env var. "
                    "Model defaults may vary across Claude Code versions.",
            recommendation="Pin the model explicitly: add 'model': 'claude-sonnet-4-5' (or "
                           "your preferred model) to ~/.claude/settings.json. The 'model' "
                           "vector breaks cache whenever the resolved model string changes.",
            penalty=10,
        ))
    else:
        findings.append(Finding(
            domain="settings",
            severity="ok",
            vector="model",
            message=f"Model is pinned ({top_model or env_model}).",
            recommendation="",
            penalty=0,
        ))

    # --- alwaysThinkingEnabled ---
    always_thinking = merged.get("alwaysThinkingEnabled")
    if always_thinking is None:
        # Not set — default behaviour, that's fine
        pass
    elif isinstance(always_thinking, bool):
        findings.append(Finding(
            domain="settings",
            severity="low",
            vector="effortValue",
            message=f"alwaysThinkingEnabled is set to {always_thinking}. "
                    "This is fine as long as you never toggle it mid-project.",
            recommendation="Avoid toggling alwaysThinkingEnabled between sessions within "
                           "the same project. Each toggle changes effortValue, breaking "
                           "the cache.",
            penalty=3,
        ))

    # --- MCP servers ---
    mcp_servers = merged.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}

    # mcpServers may also appear under globalShortcuts or other keys; check top-level only
    server_count = len(mcp_servers)
    if server_count > 5:
        findings.append(Finding(
            domain="mcp",
            severity="high",
            vector="toolsHash / perToolHashes",
            message=f"{server_count} MCP servers configured. High server count increases "
                    "the chance that at least one returns dynamic tool schemas.",
            recommendation="Audit each MCP server for schema stability. Remove or disable "
                           "servers you don't use actively. Consider using --mcp-config "
                           "per project rather than global MCP config.",
            penalty=20,
        ))
    elif server_count > 3:
        findings.append(Finding(
            domain="mcp",
            severity="medium",
            vector="toolsHash / perToolHashes",
            message=f"{server_count} MCP servers configured. Medium risk of tool schema instability.",
            recommendation="Check MCP server tool descriptions for embedded dynamic content "
                           "(file counts, timestamps, session IDs in description fields).",
            penalty=10,
        ))
    elif server_count > 0:
        findings.append(Finding(
            domain="mcp",
            severity="low",
            vector="toolsHash / perToolHashes",
            message=f"{server_count} MCP server(s) configured.",
            recommendation="Confirm tool descriptions are fully static between sessions.",
            penalty=3,
        ))

    # --- Dynamic vs static MCP server types ---
    dynamic_server_keywords = ["filesystem", "directory", "files", "folder", "browse"]
    dynamic_servers = []
    for name, config in mcp_servers.items():
        name_lower = name.lower()
        if any(k in name_lower for k in dynamic_server_keywords):
            dynamic_servers.append(name)
        # Check command/args for filesystem indicators
        if isinstance(config, dict):
            cmd = " ".join(str(x) for x in config.get("args", []))
            if any(k in cmd.lower() for k in dynamic_server_keywords):
                if name not in dynamic_servers:
                    dynamic_servers.append(name)

    if dynamic_servers:
        findings.append(Finding(
            domain="mcp",
            severity="high",
            vector="perToolHashes",
            message=f"Potentially dynamic MCP servers detected: {', '.join(dynamic_servers)}. "
                    "File/directory servers often expose tools whose schemas include "
                    "environment-specific paths or counts.",
            recommendation="Inspect these servers' tool definitions. If they embed paths "
                           "like '/Users/fxx/...' or file counts in tool descriptions, "
                           "each new session will produce a different perToolHashes value.",
            penalty=15,
        ))

    return findings


def _deep_merge(base: dict, override: dict) -> None:
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


def count_mcp_servers(paths: list[Path]) -> int:
    merged: dict = {}
    for p in paths:
        data = load_json_file(p)
        if data and isinstance(data, dict):
            _deep_merge(merged, data)
    mcp = merged.get("mcpServers", {})
    return len(mcp) if isinstance(mcp, dict) else 0


# ---------------------------------------------------------------------------
# CLAUDE.md quick scan (top 3 patterns only)
# Full analysis: use prompt-architect skill
# ---------------------------------------------------------------------------

# Pattern: embedded dates (months, year-month combos, "last updated" phrases)
_DATE_PATTERNS = [
    re.compile(r"\b(january|february|march|april|may|june|july|august|september|"
               r"october|november|december)\s+\d{4}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b"),                       # 2026-04-15
    re.compile(r"\blast\s+updated\b", re.IGNORECASE),
    re.compile(r"\bas\s+of\s+(today|now|\d{4})", re.IGNORECASE),
]

# Pattern: absolute user-specific paths
_ABS_PATH_PATTERNS = [
    re.compile(r"/(?:Users|home)/[^/\s]+/"),        # Unix home-relative paths
    re.compile(r"[A-Z]:\\\\Users\\\\[^\\\\]+\\\\"),  # Windows paths (escaped)
    re.compile(r"[A-Z]:/Users/[^/\s]+/"),            # Windows paths (forward slash)
]

# Pattern: long inline code blocks (>30 lines = tool output dumps)
_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def audit_claudemd(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []

    for path in paths:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        label = str(path).replace(str(HOME), "~")
        file_findings = _scan_claudemd(content, label)
        findings.extend(file_findings)

    return findings


def _scan_claudemd(content: str, label: str) -> list[Finding]:
    findings: list[Finding] = []

    # 1. Embedded dates
    date_hits: list[str] = []
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(content):
            date_hits.append(m.group(0)[:50])
    if date_hits:
        findings.append(Finding(
            domain="claudemd",
            severity="high",
            vector="systemHash",
            message=f"{label}: Embedded date-like strings found: "
                    + ", ".join(f'"{h}"' for h in date_hits[:3])
                    + ("..." if len(date_hits) > 3 else ""),
            recommendation=f"Remove date strings from {label}. Dates change over time — "
                           "even if you mean 'last updated', the string will eventually "
                           "differ between your CLAUDE.md and the cached version, forcing "
                           "a systemHash miss on every session after the update.",
            penalty=20,
        ))

    # 2. Absolute paths
    abs_hits: list[str] = []
    for pattern in _ABS_PATH_PATTERNS:
        for m in pattern.finditer(content):
            abs_hits.append(m.group(0)[:60])
    if abs_hits:
        findings.append(Finding(
            domain="claudemd",
            severity="high",
            vector="systemHash",
            message=f"{label}: Absolute user-specific paths found: "
                    + ", ".join(f'"{h}"' for h in abs_hits[:3])
                    + ("..." if len(abs_hits) > 3 else ""),
            recommendation=f"Replace absolute paths in {label} with relative paths or "
                           "environment variable references (e.g. $PROJECT_ROOT). "
                           "Machine-specific paths break the cache for anyone who "
                           "uses the same CLAUDE.md on a different machine or user account.",
            penalty=15,
        ))

    # 3. Long inline code blocks (>30 lines)
    for m in _CODE_BLOCK_RE.finditer(content):
        block_lines = m.group(1).count("\n")
        if block_lines > 30:
            findings.append(Finding(
                domain="claudemd",
                severity="medium",
                vector="systemHash / systemCharCount",
                message=f"{label}: Code block with {block_lines} lines found. "
                        "Large blocks suggest pasted tool output (ls, git log, etc.).",
                recommendation=f"Remove large inline code blocks from {label}. "
                               "If this is reference material, use @file imports instead. "
                               "If it's tool output, remove it — Claude can run the command.",
                penalty=10,
            ))
            break  # one finding per file for this pattern

    return findings


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

STATUS_LABELS = {
    (85, 101): "Healthy",
    (65, 85): "Warning",
    (40, 65): "Degraded",
    (0, 40): "Critical",
}


def score_findings(findings: list[Finding]) -> int:
    penalty = sum(f.penalty for f in findings if f.severity != "ok")
    return max(0, 100 - penalty)


def status_for_score(score: int) -> str:
    for (lo, hi), label in STATUS_LABELS.items():
        if lo <= score < hi:
            return label
    return "Critical"


def top_recommendations(findings: list[Finding], n: int = 3) -> list[str]:
    actionable = [f for f in findings if f.recommendation and f.severity != "ok"]
    actionable.sort(key=lambda f: f.penalty, reverse=True)
    return [f.recommendation for f in actionable[:n]]


def estimate_tokens_saved(findings: list[Finding]) -> int:
    """
    Rough estimate: each high/critical finding that is fixed saves ~1000 tokens
    per cache break, assuming an average of 5 breaks/day for affected vectors.
    """
    high_count = sum(1 for f in findings if f.severity in ("high", "critical"))
    return high_count * 1000 * 5


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

SEVERITY_SYMBOLS = {
    "critical": "[!!]",
    "high": "[!] ",
    "medium": "[~] ",
    "low": "[-] ",
    "ok": "[v] ",
}

SCORE_BARS = {
    (85, 101): "####################",
    (65, 85): "################    ",
    (40, 65): "########            ",
    (0, 40): "####                ",
}


def render_report(result: AuditResult) -> str:
    lines: list[str] = []

    def hr(char: str = "-", width: int = 72) -> str:
        return char * width

    lines.append(hr("="))
    lines.append("  Claude Code — Prompt Cache Health Report")
    lines.append(hr("="))
    lines.append("")

    # Score
    bar = next((b for (lo, hi), b in SCORE_BARS.items() if lo <= result.score < hi), "")
    lines.append(f"  Score : {result.score:3d}/100  [{bar}]")
    lines.append(f"  Status: {result.status}")
    lines.append(f"  Est. tokens saved/day if fixed: ~{result.estimated_tokens_saved_per_day:,}")
    lines.append("")

    # Files checked
    lines.append(hr())
    lines.append("Files checked:")
    for f in result.files_checked:
        lines.append(f"  {f}")
    lines.append(f"  MCP servers found: {result.mcp_server_count}")
    lines.append("")

    # Findings grouped by domain
    for domain in ("settings", "mcp", "claudemd"):
    	domain_findings = [f for f in result.findings if f.domain == domain]
    	if not domain_findings:
    		continue
    	domain_labels = {"settings": "Settings / Env vars", "mcp": "MCP Servers", "claudemd": "CLAUDE.md"}
    	lines.append(hr())
    	lines.append(f"  {domain_labels[domain]}")
    	lines.append(hr())
    	for finding in domain_findings:
    		sym = SEVERITY_SYMBOLS.get(finding.severity, "    ")
    		lines.append(f"{sym} [{finding.vector}]")
    		# Wrap message at ~68 chars
    		for chunk in _wrap(finding.message, 68):
    			lines.append(f"     {chunk}")
    		if finding.recommendation:
    			rec_chunks = _wrap(finding.recommendation, 64)
    			lines.append(f"     Fix: {rec_chunks[0]}")
    			for chunk in rec_chunks[1:]:
    				lines.append(f"       {chunk}")
    		lines.append("")

    # Top recommendations
    lines.append(hr("="))
    lines.append("  Top Recommendations")
    lines.append(hr("="))
    for i, rec in enumerate(result.recommendations, 1):
        rec_chunks = _wrap(rec, 66)
        lines.append(f"  {i}. {rec_chunks[0]}")
        for chunk in rec_chunks[1:]:
            lines.append(f"     {chunk}")
        lines.append("")

    # Exit hint
    status_map = {"Healthy": 0, "Warning": 1, "Degraded": 2, "Critical": 3}
    code = status_map.get(result.status, 3)
    lines.append(hr())
    lines.append(f"  Exit code: {code}  (0=healthy, 1=warning, 2=degraded, 3=critical)")
    lines.append(hr("="))

    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines or [""]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_audit() -> AuditResult:
    settings_files = find_existing(SETTINGS_CANDIDATES)
    claudemd_files = find_existing(CLAUDEMD_CANDIDATES)

    files_checked = [str(p).replace(str(HOME), "~") for p in settings_files + claudemd_files]

    all_findings: list[Finding] = []
    all_findings.extend(audit_settings(settings_files))
    all_findings.extend(audit_claudemd(claudemd_files))

    score = score_findings(all_findings)
    status = status_for_score(score)
    recs = top_recommendations(all_findings, n=3)
    tokens_saved = estimate_tokens_saved(all_findings)
    mcp_count = count_mcp_servers(settings_files)

    return AuditResult(
        score=score,
        status=status,
        findings=all_findings,
        recommendations=recs,
        estimated_tokens_saved_per_day=tokens_saved,
        files_checked=files_checked,
        mcp_server_count=mcp_count,
        claudemd_files_found=[str(p).replace(str(HOME), "~") for p in claudemd_files],
    )


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(f) for f in findings]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit Claude Code configuration for prompt cache health.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of human-readable report.",
    )
    args = parser.parse_args()

    result = run_audit()

    if args.json:
        output = {
            "score": result.score,
            "status": result.status,
            "estimated_tokens_saved_per_day": result.estimated_tokens_saved_per_day,
            "files_checked": result.files_checked,
            "mcp_server_count": result.mcp_server_count,
            "claudemd_files_found": result.claudemd_files_found,
            "findings": findings_to_dicts(result.findings),
            "top_recommendations": result.recommendations,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(render_report(result))

    status_to_exit = {"Healthy": 0, "Warning": 1, "Degraded": 2, "Critical": 3}
    sys.exit(status_to_exit.get(result.status, 3))


if __name__ == "__main__":
    main()
