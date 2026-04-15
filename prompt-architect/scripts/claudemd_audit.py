#!/usr/bin/env python3
"""
claudemd_audit.py — 静态分析 CLAUDE.md，检测 prompt cache 破坏模式

从 Claude Code 源码提取的设计原则：
- SYSTEM_PROMPT_DYNAMIC_BOUNDARY (src/constants/prompts.ts)
- systemPromptSection() vs DANGEROUS_uncachedSystemPromptSection() (src/constants/systemPromptSections.ts)
- Prompt cache TTL: 5 分钟

用法：
    python claudemd_audit.py
    python claudemd_audit.py ~/.claude/CLAUDE.md
    python claudemd_audit.py .claude/CLAUDE.md
    python claudemd_audit.py --all   # 扫描所有可能的 CLAUDE.md
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

# --- 检测规则 ---
# 每个规则: (名称, 正则, 严重级别, 说明, 修复建议)
CACHE_BUST_PATTERNS = [
    (
        'embedded_date',
        re.compile(
            r'(last\s+updated|updated\s+on|date:|as\s+of|since|updated:)\s*'
            r'(\d{4}[-/]\d{1,2}|\w+\s+\d{4}|today|yesterday|\d{1,2}/\d{1,2})',
            re.IGNORECASE
        ),
        'HIGH',
        '内嵌日期/时间戳 — 日期变化时破坏整个 cache',
        '删除日期，或移到 git 注释中'
    ),
    (
        'absolute_user_path',
        re.compile(
            r'(/Users/[^/\s]+|/home/[^/\s]+|C:\\Users\\[^\\s]+)',
        ),
        'HIGH',
        '包含用户名的绝对路径 — 跨机器不同，每次重建 cache',
        '改用 $HOME、~、或相对路径'
    ),
    (
        'dynamic_ls_output',
        re.compile(
            r'(drwx|drw-|-rwx|-rw-|total\s+\d+\s*\n|\d+\s+\w+\s+\w+\s+\d+\s+\w+\s+\d+)',
        ),
        'HIGH',
        '粘贴了 ls/dir 命令输出 — 文件系统变化时破坏 cache',
        '删除，Claude 可以自行运行 ls'
    ),
    (
        'git_branch_embedded',
        re.compile(
            r'(current\s+branch|on\s+branch|branch\s*[:=])\s*[\w/-]+',
            re.IGNORECASE
        ),
        'MEDIUM',
        '内嵌 git 分支名 — 切换分支时破坏 cache',
        '删除，Claude 可以运行 git branch 查询'
    ),
    (
        'dynamic_version_number',
        re.compile(
            r'(version|v)\s*[:=]?\s*\d+\.\d+\.\d+(-\w+)?(?!\s*\n.*#)',  # 排除代码注释中的版本
            re.IGNORECASE
        ),
        'MEDIUM',
        '硬编码版本号 — 升级后需要手动更新，可能遗忘',
        '改为从 package.json/pyproject.toml 读取，或移除'
    ),
    (
        'session_token_or_key',
        re.compile(
            r'(api[_-]?key|token|secret|password|credential)\s*[:=]\s*[\'"]?[\w\-]{10,}[\'"]?',
            re.IGNORECASE
        ),
        'CRITICAL',
        '包含 API key/Token/密码 — 安全风险 + cache 每次轮换时失效',
        '立即删除，改用环境变量'
    ),
    (
        'random_id_or_hash',
        re.compile(
            r'\b[0-9a-f]{32,}\b',  # MD5/SHA hash
        ),
        'MEDIUM',
        '包含 hash 或随机 ID — 可能每次会话不同',
        '检查是否需要，如果是临时值则删除'
    ),
    (
        'todo_comment',
        re.compile(
            r'^\s*(TODO|FIXME|HACK|XXX)\s*:',
            re.MULTILINE | re.IGNORECASE
        ),
        'LOW',
        'TODO/FIXME 注释 — 不破坏 cache，但会污染系统提示',
        '移到代码注释或 issue tracker'
    ),
    (
        'inline_code_dump',
        re.compile(
            r'```\w*\n(?:[^\n]+\n){50,}```',  # 超过 50 行的代码块
        ),
        'MEDIUM',
        '超长代码块（>50行）— 占用大量 cache token，降低效率',
        '将大段代码移到单独文件，用 @file 引用'
    ),
    (
        'machine_specific_path',
        re.compile(
            r'(/proc/|/sys/|/dev/|\\\\.\\|/private/var/)',
        ),
        'HIGH',
        '机器特定路径 — 在不同系统上无效',
        '改用通用路径或环境变量'
    ),
]

# 静态内容的正面指标（增加这些内容）
GOOD_PATTERNS = [
    ('project_structure', re.compile(r'## (Architecture|Structure|Overview)', re.IGNORECASE), '有项目架构说明'),
    ('coding_conventions', re.compile(r'## (Convention|Style|Standard)', re.IGNORECASE), '有编码规范'),
    ('tool_usage', re.compile(r'## (Tools?|Commands?|Scripts?)', re.IGNORECASE), '有工具使用指南'),
    ('relative_paths', re.compile(r'\./\w+|\.\./\w+'), '使用相对路径'),
]


def audit_file(filepath: Path) -> dict:
    """审计单个 CLAUDE.md 文件"""
    if not filepath.exists():
        return {'exists': False, 'path': str(filepath)}

    content = filepath.read_text(encoding='utf-8', errors='replace')
    lines = content.split('\n')

    result = {
        'exists': True,
        'path': str(filepath),
        'line_count': len(lines),
        'char_count': len(content),
        'estimated_tokens': len(content) // 4,
        'issues': [],
        'positives': [],
        'score': 100,  # 从 100 分开始扣分
    }

    # 检测 cache-busting 模式
    for name, pattern, severity, desc, fix in CACHE_BUST_PATTERNS:
        matches = list(pattern.finditer(content))
        if matches:
            # 找到匹配的行号
            match_lines = []
            for m in matches[:3]:
                line_no = content[:m.start()].count('\n') + 1
                match_lines.append(line_no)

            deduction = {'CRITICAL': 30, 'HIGH': 20, 'MEDIUM': 10, 'LOW': 5}[severity]
            result['score'] = max(0, result['score'] - deduction)
            result['issues'].append({
                'name': name,
                'severity': severity,
                'description': desc,
                'fix': fix,
                'count': len(matches),
                'lines': match_lines,
                'preview': content[matches[0].start():matches[0].end()][:60],
            })

    # 检测正面指标
    for name, pattern, desc in GOOD_PATTERNS:
        if pattern.search(content):
            result['positives'].append(desc)

    # 大小评估
    if result['estimated_tokens'] > 8000:
        result['issues'].append({
            'name': 'large_prompt',
            'severity': 'MEDIUM',
            'description': f'系统提示较大（~{result["estimated_tokens"]:,} tokens）— 较长的静态前缀 cache 效果更好，但超大提示词也有成本',
            'fix': '检查是否有可以移到 @file 引用的大段内容',
            'count': 1,
            'lines': [],
            'preview': '',
        })
        result['score'] = max(0, result['score'] - 5)

    return result


def find_all_claudemd() -> list[Path]:
    """查找所有可能的 CLAUDE.md 文件"""
    candidates = [
        Path.home() / '.claude' / 'CLAUDE.md',
        Path.cwd() / '.claude' / 'CLAUDE.md',
        Path.cwd() / 'CLAUDE.md',
    ]
    # 向上遍历找 git root
    for parent in Path.cwd().parents:
        if (parent / '.git').exists():
            candidates.append(parent / '.claude' / 'CLAUDE.md')
            candidates.append(parent / 'CLAUDE.md')
            break

    return [p for p in candidates if p.exists()]


def print_file_report(result: dict):
    """打印单文件报告"""
    path = result['path']
    if not result['exists']:
        print(f"  ⚪ 不存在: {path}")
        return

    score = result['score']
    score_icon = '✅' if score >= 80 else '⚠️' if score >= 60 else '❌'
    print(f"\n{'─'*60}")
    print(f"  {score_icon} {path}")
    print(f"     {result['line_count']} 行 | ~{result['estimated_tokens']:,} tokens | 得分: {score}/100")

    if result['positives']:
        print(f"     ✓ {' | '.join(result['positives'])}")

    if not result['issues']:
        print(f"     ✅ 未发现 cache-busting 问题")
        return

    # 按严重级别排序
    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    issues = sorted(result['issues'], key=lambda x: severity_order.get(x['severity'], 99))

    for issue in issues:
        severity = issue['severity']
        icon = {'CRITICAL': '🚨', 'HIGH': '❌', 'MEDIUM': '⚠️', 'LOW': '💡'}[severity]
        lines_str = f" (行 {', '.join(map(str, issue['lines'][:3]))})" if issue['lines'] else ''
        print(f"\n  {icon} [{severity}] {issue['description']}{lines_str}")
        if issue['preview']:
            print(f"       匹配: \"{issue['preview']}\"")
        print(f"       修复: {issue['fix']}")


def main():
    parser = argparse.ArgumentParser(
        description='审计 CLAUDE.md 文件的 prompt cache 效率'
    )
    parser.add_argument('file', nargs='?', help='要审计的 CLAUDE.md 路径（默认自动查找）')
    parser.add_argument('--all', action='store_true', help='审计所有找到的 CLAUDE.md')

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  CLAUDE.md Prompt Cache 审计")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if args.file:
        files = [Path(args.file).expanduser()]
    elif args.all:
        files = find_all_claudemd()
        if not files:
            print("\n  未找到任何 CLAUDE.md 文件")
            sys.exit(0)
        print(f"\n  找到 {len(files)} 个 CLAUDE.md 文件")
    else:
        # 优先级：当前项目 > 全局
        files = find_all_claudemd()
        if not files:
            print("\n  未找到 CLAUDE.md 文件")
            print("  常见位置: ~/.claude/CLAUDE.md, .claude/CLAUDE.md")
            sys.exit(0)

    results = [audit_file(f) for f in files]

    for r in results:
        print_file_report(r)

    # 汇总
    existing = [r for r in results if r['exists']]
    if len(existing) > 1:
        avg_score = sum(r['score'] for r in existing) / len(existing)
        total_issues = sum(len(r['issues']) for r in existing)
        print(f"\n{'='*60}")
        print(f"  汇总: {len(existing)} 个文件 | 平均得分: {avg_score:.0f}/100 | 总问题: {total_issues}")

    if any(r['issues'] for r in existing):
        print(f"\n  💡 运行 /prompt-architect 来获取详细重构建议")

    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
