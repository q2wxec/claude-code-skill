#!/usr/bin/env python3
"""
session_extract.py — 从 Claude Code 会话 JSONL 文件提取对话文本

用于离线分析会话内容，查看助手和用户的完整对话历史。
当需要回顾「上次做了什么」时非常有用。

用法：
    python session_extract.py session.jsonl
    python session_extract.py ~/.claude/projects/<project>/<id>.jsonl
    python session_extract.py --latest                      # 当前项目最新会话
    python session_extract.py session.jsonl --role assistant  # 只看助手消息
    python session_extract.py session.jsonl --grep "决策"   # 过滤关键词
    python session_extract.py --list                        # 列出所有会话
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime


def load_jsonl(filepath: Path) -> list[dict]:
    """读取 JSONL 格式的会话文件"""
    messages = []
    with open(filepath, encoding='utf-8', errors='replace') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # 跳过损坏的行
    return messages


def extract_text(message: dict) -> str:
    """从消息中提取纯文本"""
    msg = message.get('message', {})
    if not msg:
        return ''

    content = msg.get('content', '')
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get('type', '')
            if btype == 'text':
                text = block.get('text', '').strip()
                if text:
                    parts.append(text)
            elif btype == 'tool_use':
                name = block.get('name', 'tool')
                inp = block.get('input', {})
                if isinstance(inp, dict):
                    # 只显示最重要的工具调用摘要
                    if name in ('Bash', 'bash'):
                        cmd = inp.get('command', '')[:100]
                        parts.append(f"[Bash: {cmd}]")
                    elif name in ('Read', 'Write', 'Edit'):
                        path = inp.get('file_path', inp.get('path', ''))
                        parts.append(f"[{name}: {path}]")
                    else:
                        parts.append(f"[{name}]")
            elif btype == 'tool_result':
                content_val = block.get('content', '')
                if isinstance(content_val, str) and content_val.strip():
                    # 工具结果截断到前 200 字符
                    preview = content_val.strip()[:200]
                    if len(content_val.strip()) > 200:
                        preview += '...'
                    parts.append(f"[Result: {preview}]")
                elif isinstance(content_val, list):
                    for item in content_val:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text = item.get('text', '').strip()[:200]
                            if text:
                                parts.append(f"[Result: {text}]")
                            break
        return '\n'.join(parts).strip()
    return ''


def get_timestamp(message: dict) -> str:
    """从消息中提取时间戳"""
    # Claude Code 在某些消息中附带 timestamp
    ts = message.get('timestamp')
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt.strftime('%H:%M:%S')
        except Exception:
            return ts[:19] if len(ts) >= 19 else ts
    return ''


def print_conversation(messages: list[dict], role_filter: str | None = None,
                       grep: str | None = None, max_chars: int = 1000):
    """格式化打印对话内容"""
    role_icons = {
        'user': '👤',
        'assistant': '🤖',
        'system': '⚙️',
    }

    printed = 0
    for msg in messages:
        role = msg.get('type', 'unknown')

        if role_filter and role != role_filter:
            continue

        text = extract_text(msg)
        if not text:
            continue

        if grep and grep.lower() not in text.lower():
            continue

        ts = get_timestamp(msg)
        icon = role_icons.get(role, '❓')
        ts_str = f" [{ts}]" if ts else ""

        # 截断过长的消息
        display_text = text
        was_truncated = False
        if len(text) > max_chars:
            display_text = text[:max_chars]
            was_truncated = True

        print(f"\n{icon} {role.upper()}{ts_str}")
        print("─" * 40)
        print(display_text)
        if was_truncated:
            print(f"... [截断，原文 {len(text):,} 字符]")

        printed += 1

    return printed


def find_session_dir() -> Path | None:
    """查找当前项目的会话目录"""
    cwd = Path.cwd()
    root = cwd
    for parent in [cwd, *cwd.parents]:
        if (parent / '.git').exists():
            root = parent
            break

    sanitized = str(root).replace('/', '-').replace('\\', '-').replace(':', '-').lstrip('-')
    sessions_dir = Path.home() / '.claude' / 'projects' / sanitized
    if sessions_dir.exists():
        return sessions_dir

    # fallback: 全局
    global_dir = Path.home() / '.claude' / 'projects'
    if global_dir.exists():
        return global_dir

    return None


def list_sessions(sessions_dir: Path):
    """列出所有会话文件"""
    jsonl_files = sorted(sessions_dir.glob('**/*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not jsonl_files:
        print("未找到会话文件")
        return

    print(f"\n找到 {len(jsonl_files)} 个会话文件 (最新 20 个):")
    print(f"{'时间':<20} {'大小':>8} {'文件名'}")
    print("─" * 60)
    for f in jsonl_files[:20]:
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        size = f.stat().st_size
        size_str = f"{size // 1024}K" if size > 1024 else f"{size}B"
        print(f"{mtime:<20} {size_str:>8} {f.name}")


def find_latest_session() -> Path | None:
    """查找最新的会话文件"""
    sessions_dir = find_session_dir()
    if not sessions_dir:
        return None
    jsonl_files = list(sessions_dir.glob('**/*.jsonl'))
    if not jsonl_files:
        return None
    return max(jsonl_files, key=lambda p: p.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description='从 Claude Code 会话 JSONL 文件提取和查看对话内容'
    )
    parser.add_argument('session', nargs='?', help='会话 JSONL 文件路径')
    parser.add_argument('--latest', action='store_true', help='处理当前项目最新会话')
    parser.add_argument('--list', action='store_true', help='列出所有会话文件')
    parser.add_argument('--role', choices=['user', 'assistant', 'system'],
                       help='只显示特定角色的消息')
    parser.add_argument('--grep', help='过滤包含关键词的消息')
    parser.add_argument('--max-chars', type=int, default=1000,
                       help='每条消息最大显示字符数（默认 1000）')
    parser.add_argument('--stats', action='store_true', help='只显示统计信息')

    args = parser.parse_args()

    if args.list:
        sessions_dir = find_session_dir()
        if sessions_dir:
            list_sessions(sessions_dir)
        else:
            print("未找到会话目录")
        return

    if args.latest:
        session_path = find_latest_session()
        if not session_path:
            print("未找到会话文件")
            sys.exit(1)
        print(f"最新会话: {session_path.name}")
    elif args.session:
        session_path = Path(args.session).expanduser()
    else:
        parser.print_help()
        return

    if not session_path.exists():
        print(f"文件不存在: {session_path}")
        sys.exit(1)

    messages = load_jsonl(session_path)

    # 统计
    role_counts = {}
    total_chars = 0
    for msg in messages:
        role = msg.get('type', 'unknown')
        role_counts[role] = role_counts.get(role, 0) + 1
        total_chars += len(extract_text(msg))

    mtime = datetime.fromtimestamp(session_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n📁 {session_path.name}")
    print(f"   最后修改: {mtime}")
    print(f"   消息总数: {len(messages)}")
    for role, count in sorted(role_counts.items()):
        print(f"   {role}: {count}")
    print(f"   文本总量: ~{total_chars // 4:,} tokens")

    if args.stats:
        return

    print(f"\n{'='*60}")
    n = print_conversation(messages, args.role, args.grep, args.max_chars)
    print(f"\n{'='*60}")
    print(f"显示了 {n} 条消息")
    if args.grep:
        print(f"(已过滤: 包含 '{args.grep}')")


if __name__ == '__main__':
    main()
