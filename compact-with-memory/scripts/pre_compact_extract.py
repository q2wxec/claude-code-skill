#!/usr/bin/env python3
"""
pre_compact_extract.py — 从 Claude Code 会话 JSONL 文件提取值得记忆的内容草稿

从 Claude Code 源码提取的设计：
- 会话存储格式: JSONL, 每行一条消息 (src/utils/sessionStorage.ts)
- 记忆类型: user/feedback/project/reference (src/memdir/memoryTypes.ts)
- 压缩自定义指令: compactConversation(messages, ..., customInstructions?) (src/services/compact/compact.ts)

用法：
    python pre_compact_extract.py session.jsonl
    python pre_compact_extract.py ~/.claude/projects/<project>/sessions/<id>.jsonl
    python pre_compact_extract.py --latest  # 处理最新会话
    python pre_compact_extract.py session.jsonl --output extract.md
"""

import json
import sys
import argparse
import re
from pathlib import Path
from datetime import datetime

# 值得记忆的信号模式
DECISION_PATTERNS = [
    re.compile(r"(?:we(?:'re| are| decided| chose| went| picked| will)|i(?:'ll| will)|let'?s|going to)\s+(?:use|go with|adopt|implement|switch to|replace)\s+(.{10,80})", re.IGNORECASE),
    re.compile(r"(?:instead of|rather than|over)\s+(.{5,50})\s+(?:because|since|due to|as)", re.IGNORECASE),
    re.compile(r"(?:the reason|this is because|why we|that'?s why)\s+(.{10,100})", re.IGNORECASE),
]

FAILURE_PATTERNS = [
    re.compile(r"(?:doesn'?t work|failed|broken|won'?t work|can'?t use|avoid|don'?t use)\s+(.{10,80})", re.IGNORECASE),
    re.compile(r"(?:tried|attempted)\s+(.{10,60})\s+(?:but|however|unfortunately|though)", re.IGNORECASE),
    re.compile(r"(?:the problem|issue|bug)\s+(?:is|was|with)\s+(.{10,80})", re.IGNORECASE),
]

DISCOVERY_PATTERNS = [
    re.compile(r"(?:found out|discovered|learned|turns out|noticed|realized)\s+(?:that\s+)?(.{10,100})", re.IGNORECASE),
    re.compile(r"(?:interesting|important|note|warning|caveat):\s*(.{10,100})", re.IGNORECASE),
    re.compile(r"(?:key insight|takeaway|lesson):\s*(.{10,100})", re.IGNORECASE),
]

BLOCKER_PATTERNS = [
    re.compile(r"(?:blocked|stuck|waiting for|need to|can'?t proceed)\s+(.{10,80})", re.IGNORECASE),
    re.compile(r"(?:open question|unresolved|TODO|FIXME|need to figure out)\s*[:\-]?\s*(.{10,80})", re.IGNORECASE),
]

USER_FEEDBACK_PATTERNS = [
    re.compile(r"(?:please|don'?t|stop|always|never|prefer|want)\s+(.{10,80})", re.IGNORECASE),
    re.compile(r"(?:perfect|exactly|that'?s what|no not|wrong|incorrect)\s+(.{10,80})", re.IGNORECASE),
]


def load_jsonl(filepath: Path) -> list[dict]:
    """读取 JSONL 格式的会话文件"""
    messages = []
    try:
        with open(filepath, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"读取文件失败: {e}")
        sys.exit(1)
    return messages


def extract_text(message: dict) -> tuple[str, str]:
    """从消息中提取文本内容，返回 (role, text)"""
    role = message.get('type', 'unknown')

    # Claude Code JSONL 格式
    msg = message.get('message', {})
    if not msg:
        return role, ''

    content = msg.get('content', '')
    if isinstance(content, str):
        return role, content
    elif isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    texts.append(block.get('text', ''))
                elif block.get('type') == 'tool_result':
                    # 工具结果通常不含有意义的记忆信号
                    pass
        return role, '\n'.join(texts)

    return role, ''


def extract_signals(messages: list[dict]) -> dict:
    """从消息列表中提取记忆信号"""
    signals = {
        'decisions': [],
        'failures': [],
        'discoveries': [],
        'blockers': [],
        'user_feedback': [],
    }

    for msg in messages:
        role, text = extract_text(msg)
        if not text or len(text) < 20:
            continue

        # 只从 assistant 消息提取决策/发现/阻塞点
        if role == 'assistant':
            for pattern in DECISION_PATTERNS:
                for m in pattern.finditer(text):
                    snippet = m.group(0)[:150].strip()
                    if snippet not in signals['decisions']:
                        signals['decisions'].append(snippet)

            for pattern in FAILURE_PATTERNS:
                for m in pattern.finditer(text):
                    snippet = m.group(0)[:150].strip()
                    if snippet not in signals['failures']:
                        signals['failures'].append(snippet)

            for pattern in DISCOVERY_PATTERNS:
                for m in pattern.finditer(text):
                    snippet = m.group(0)[:150].strip()
                    if snippet not in signals['discoveries']:
                        signals['discoveries'].append(snippet)

            for pattern in BLOCKER_PATTERNS:
                for m in pattern.finditer(text):
                    snippet = m.group(0)[:150].strip()
                    if snippet not in signals['blockers']:
                        signals['blockers'].append(snippet)

        # 从用户消息提取反馈
        elif role == 'user':
            for pattern in USER_FEEDBACK_PATTERNS:
                for m in pattern.finditer(text):
                    snippet = m.group(0)[:150].strip()
                    if snippet not in signals['user_feedback']:
                        signals['user_feedback'].append(snippet)

    return signals


def generate_memory_draft(signals: dict, session_path: Path) -> str:
    """生成记忆草稿 Markdown"""
    now = datetime.now().strftime('%Y-%m-%d')
    lines = [
        f"# 会话记忆提取草稿",
        f"来源: {session_path.name}",
        f"提取时间: {now}",
        f"",
        f"> ⚠️ 这是自动提取的草稿，需要人工审核后再写入 MEMORY.md",
        f"> 删除不准确或不重要的条目，然后用 /session-dream 整理格式",
        f"",
    ]

    if signals['decisions']:
        lines.append("## 决策（project 类型）")
        lines.append("这些内容应写入 `type: project` 的主题文件")
        lines.append("")
        for s in signals['decisions'][:8]:
            lines.append(f"- {s}")
        lines.append("")

    if signals['failures']:
        lines.append("## 失败方案（feedback 类型）")
        lines.append("这些内容应写入 `type: feedback` 的主题文件，避免重蹈覆辙")
        lines.append("")
        for s in signals['failures'][:5]:
            lines.append(f"- {s}")
        lines.append("")

    if signals['discoveries']:
        lines.append("## 新发现（project/reference 类型）")
        lines.append("")
        for s in signals['discoveries'][:8]:
            lines.append(f"- {s}")
        lines.append("")

    if signals['blockers']:
        lines.append("## 当前阻塞点（project 类型）")
        lines.append("如果下次会话还需要解决这些问题，写入记忆")
        lines.append("")
        for s in signals['blockers'][:5]:
            lines.append(f"- {s}")
        lines.append("")

    if signals['user_feedback']:
        lines.append("## 用户反馈（feedback 类型）")
        lines.append("用户对工作方式的偏好和纠正")
        lines.append("")
        for s in signals['user_feedback'][:5]:
            lines.append(f"- {s}")
        lines.append("")

    total = sum(len(v) for v in signals.values())
    if total == 0:
        lines.append("_未提取到明显的记忆信号。这次会话可能不需要写入新记忆，_")
        lines.append("_或者信号表述方式不在检测模式中，建议手动回顾对话。_")

    lines.extend([
        "",
        "---",
        "## 下一步",
        "1. 删除不准确或不重要的条目",
        "2. 对剩余条目，对 Claude 说 `/session-dream` 来整理格式并写入 MEMORY.md",
        "3. 或手动参考 memory frontmatter 格式写入：",
        "   ```yaml",
        "   ---",
        "   name: 主题名称",
        "   description: 一句话描述（何时相关）",
        "   type: project | feedback | user | reference",
        "   ---",
        "   ```",
    ])

    return '\n'.join(lines)


def find_latest_session() -> Path | None:
    """查找最新的会话文件"""
    # Claude Code 会话目录
    cwd = Path.cwd()
    root = cwd
    for parent in [cwd, *cwd.parents]:
        if (parent / '.git').exists():
            root = parent
            break

    sanitized = str(root).replace('/', '-').replace('\\', '-').replace(':', '-').lstrip('-')
    sessions_dir = Path.home() / '.claude' / 'projects' / sanitized

    if not sessions_dir.exists():
        return None

    jsonl_files = list(sessions_dir.glob('*.jsonl'))
    if not jsonl_files:
        return None

    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description='从 Claude Code 会话文件提取值得记忆的内容草稿'
    )
    parser.add_argument('session', nargs='?', help='会话 JSONL 文件路径')
    parser.add_argument('--latest', action='store_true', help='处理当前项目最新会话')
    parser.add_argument('--output', '-o', help='输出文件路径（默认打印到终端）')

    args = parser.parse_args()

    if args.latest:
        session_path = find_latest_session()
        if not session_path:
            print("未找到会话文件。")
            sys.exit(1)
        print(f"处理最新会话: {session_path.name}")
    elif args.session:
        session_path = Path(args.session).expanduser()
    else:
        parser.print_help()
        sys.exit(0)

    if not session_path.exists():
        print(f"文件不存在: {session_path}")
        sys.exit(1)

    print(f"读取会话: {session_path}")
    messages = load_jsonl(session_path)
    print(f"消息数: {len(messages)}")

    signals = extract_signals(messages)
    total = sum(len(v) for v in signals.values())
    print(f"提取信号: {total} 条")

    draft = generate_memory_draft(signals, session_path)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(draft, encoding='utf-8')
        print(f"草稿已写入: {output_path}")
    else:
        print("\n" + "="*60)
        print(draft)
        print("="*60)


if __name__ == '__main__':
    main()
