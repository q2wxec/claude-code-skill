#!/usr/bin/env python3
"""
token_estimator.py — 估算文件/目录的 token 消耗

从 Claude Code 源码提取的估算逻辑：
- 字符数 / 4 ≈ token 数  (src/utils/tokens.ts — getAssistantMessageContentLength 注释)
- AUTOCOMPACT_BUFFER_TOKENS = 13_000  (src/services/compact/autoCompact.ts)
- MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000  (src/services/compact/autoCompact.ts)
- 模型有效窗口 = 模型上限 − 20_000

用法：
    python token_estimator.py file.ts
    python token_estimator.py src/
    python token_estimator.py src/ --model sonnet
    python token_estimator.py src/ --budget 150000  # 自定义预算
"""

import os
import sys
import argparse
from pathlib import Path

# --- 来自 autoCompact.ts 的常量 ---
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000  # 摘要预留
AUTOCOMPACT_BUFFER = 13_000            # autocompact 触发 buffer
WARNING_BUFFER = 20_000                # 用户警告 buffer
BLOCKING_BUFFER = 3_000               # 阻塞上限

# 主流模型的 context window（tokens）
MODEL_CONTEXT_WINDOWS = {
    'haiku':   200_000,
    'sonnet':  200_000,
    'opus':    200_000,
    'claude-haiku-4-5':     200_000,
    'claude-sonnet-4-6':    200_000,
    'claude-opus-4-6':      200_000,
}

# 字符 → token 估算系数（来自 tokens.ts 注释：字符数/4 ≈ tokens）
CHARS_PER_TOKEN = 4

# 系统提示词典型大小
SYSTEM_PROMPT_TOKENS = 8_000   # 典型 Claude Code system prompt

# 忽略的文件类型（二进制/无意义）
SKIP_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp',
    '.zip', '.tar', '.gz', '.whl', '.exe', '.dll', '.so',
    '.lock', '.sum', '.snap',
    '.min.js', '.min.css',
}

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.next', 'dist', 'build',
    '.venv', 'venv', '.env', 'coverage', '.nyc_output',
}


def estimate_tokens(text: str) -> int:
    """字符数 / 4 ≈ token 数（来自 tokens.ts 注释）"""
    return max(1, len(text) // CHARS_PER_TOKEN)


def should_skip(path: Path) -> bool:
    """判断是否跳过此文件"""
    if path.suffix in SKIP_EXTENSIONS:
        return True
    if path.name.endswith('.min.js') or path.name.endswith('.min.css'):
        return True
    # 超大文件（>1MB）很可能是生成物
    try:
        if path.stat().st_size > 1_000_000:
            return True
    except OSError:
        return True
    return False


def analyze_path(target: Path) -> list[dict]:
    """分析路径，返回文件列表和 token 估算"""
    results = []

    if target.is_file():
        if not should_skip(target):
            try:
                content = target.read_text(encoding='utf-8', errors='replace')
                tokens = estimate_tokens(content)
                results.append({
                    'path': str(target),
                    'size_bytes': len(content.encode('utf-8')),
                    'tokens': tokens,
                    'lines': content.count('\n'),
                })
            except Exception as e:
                results.append({
                    'path': str(target),
                    'size_bytes': 0,
                    'tokens': 0,
                    'lines': 0,
                    'error': str(e),
                })
    elif target.is_dir():
        for root, dirs, files in os.walk(target):
            # 跳过不需要的目录
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            for fname in files:
                fpath = Path(root) / fname
                if not should_skip(fpath):
                    try:
                        content = fpath.read_text(encoding='utf-8', errors='replace')
                        tokens = estimate_tokens(content)
                        results.append({
                            'path': str(fpath.relative_to(target.parent)),
                            'size_bytes': len(content.encode('utf-8')),
                            'tokens': tokens,
                            'lines': content.count('\n'),
                        })
                    except Exception:
                        pass

    return sorted(results, key=lambda x: -x['tokens'])


def get_effective_window(model: str) -> int:
    """有效窗口 = 模型窗口 - 摘要预留"""
    total = MODEL_CONTEXT_WINDOWS.get(model.lower(), 200_000)
    return total - MAX_OUTPUT_TOKENS_FOR_SUMMARY


def print_report(target: Path, model: str, custom_budget: int | None):
    files = analyze_path(target)
    total_tokens = sum(f['tokens'] for f in files)
    total_files = len(files)

    effective_window = custom_budget or get_effective_window(model)
    autocompact_threshold = effective_window - AUTOCOMPACT_BUFFER
    warning_threshold = effective_window - WARNING_BUFFER
    blocking_limit = effective_window - BLOCKING_BUFFER

    # 预估实际 context 占用（系统提示 + 对话历史基线 + 文件内容）
    context_overhead = SYSTEM_PROMPT_TOKENS + 2_000   # system prompt + 基础历史
    total_context = total_tokens + context_overhead
    pct_used = total_context / effective_window * 100

    print(f"\n{'='*60}")
    print(f"  Token 预估报告")
    print(f"  目标: {target}")
    print(f"  模型: {model}  |  有效窗口: {effective_window:,} tokens")
    print(f"{'='*60}")

    print(f"\n## 文件概览 ({total_files} 个文件)")
    print(f"  文件内容总计:  {total_tokens:>10,} tokens")
    print(f"  系统提示估算:  {context_overhead:>10,} tokens")
    print(f"  预估总 context: {total_context:>10,} tokens ({pct_used:.1f}%)")

    print(f"\n## 关键阈值")
    def threshold_bar(current, threshold, label):
        status = '✅' if current < threshold else '❌'
        print(f"  {status} {label}: {threshold:>8,}  (当前 {current:,}, {'剩余' if current < threshold else '超出'} {abs(threshold - current):,})")

    threshold_bar(total_context, warning_threshold,       "警告区       ")
    threshold_bar(total_context, autocompact_threshold,   "autocompact触发")
    threshold_bar(total_context, blocking_limit,          "阻塞上限     ")

    # 最大文件 Top 10
    if files:
        print(f"\n## Token 消耗最大文件 (Top {min(10, len(files))})")
        for f in files[:10]:
            bar_len = min(30, f['tokens'] // (max(1, total_tokens) // 30))
            bar = '█' * bar_len
            print(f"  {f['tokens']:>7,} │{bar:<30}│ {f['path']}")

    # 规划建议
    print(f"\n## 规划建议")
    if pct_used < 50:
        print(f"  ✅ 全量读取是安全的 — 只用了 {pct_used:.0f}% 有效窗口")
    elif pct_used < 75:
        print(f"  ⚠️  中度消耗 ({pct_used:.0f}%)，建议:")
        print(f"     • 分批处理，每批 ~{int(autocompact_threshold * 0.4):,} tokens")
        print(f"     • 在达到 70% 前执行 /compact")
    else:
        print(f"  ❌ 高度消耗 ({pct_used:.0f}%)，建议:")
        print(f"     • 使用 Grep 代替 Read（只读相关行）")
        print(f"     • 将大任务拆分为多个子 Agent")
        print(f"     • 每次处理 ≤{int(autocompact_threshold * 0.25):,} tokens 的文件集")

    # 分批方案
    if total_tokens > autocompact_threshold * 0.6:
        batch_size = int(autocompact_threshold * 0.4)
        batches = []
        current_batch = []
        current_size = 0
        for f in files:
            if current_size + f['tokens'] > batch_size and current_batch:
                batches.append((current_batch, current_size))
                current_batch = [f]
                current_size = f['tokens']
            else:
                current_batch.append(f)
                current_size += f['tokens']
        if current_batch:
            batches.append((current_batch, current_size))

        if len(batches) > 1:
            print(f"\n## 推荐分批方案 ({len(batches)} 批)")
            for i, (batch, size) in enumerate(batches, 1):
                print(f"  批次 {i} ({size:,} tokens, {len(batch)} 个文件):")
                for f in batch[:3]:
                    print(f"    • {f['path']}")
                if len(batch) > 3:
                    print(f"    • ... 还有 {len(batch)-3} 个文件")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='估算文件/目录的 token 消耗，辅助 context budget 规划'
    )
    parser.add_argument('target', help='文件或目录路径')
    parser.add_argument('--model', default='sonnet',
                       choices=list(MODEL_CONTEXT_WINDOWS.keys()),
                       help='目标模型（影响有效窗口计算）')
    parser.add_argument('--budget', type=int, default=None,
                       help='自定义 context 预算（tokens）')

    args = parser.parse_args()
    target = Path(args.target).expanduser()

    if not target.exists():
        print(f"路径不存在: {target}")
        sys.exit(1)

    print_report(target, args.model, args.budget)
