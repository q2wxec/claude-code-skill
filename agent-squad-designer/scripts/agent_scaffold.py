#!/usr/bin/env python3
"""
agent_scaffold.py — 生成 Claude Code Agent .md 文件模板

从 Claude Code 源码提取的 Agent 定义结构：
- frontmatter schema (src/tools/AgentTool/loadAgentsDir.ts)
- 内置 Agent 模式 (built-in/verificationAgent.ts, exploreAgent.ts, planAgent.ts)
- MEMORY_TYPES (src/memdir/memoryTypes.ts)

用法：
    python agent_scaffold.py --name security-reviewer --role "安全漏洞检测" --readonly
    python agent_scaffold.py --name test-writer --role "测试用例编写" --tools "Read,Bash,Write"
    python agent_scaffold.py --interactive
    python agent_scaffold.py --list-examples
"""

import argparse
import sys
from pathlib import Path
from textwrap import dedent

# --- 来自 loadAgentsDir.ts 的有效值 ---
VALID_MODELS = ['inherit', 'haiku', 'sonnet', 'opus',
                'claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-6']
VALID_MEMORY_SCOPES = ['user', 'project', 'local']
VALID_PERMISSION_MODES = ['default', 'acceptEdits', 'bypassPermissions', 'plan']
VALID_EFFORT = ['low', 'medium', 'high', 'max', 'none']

# 工具集预设（来自内置 Agent 模式）
TOOL_PRESETS = {
    'readonly': {
        'tools': ['Read', 'Bash', 'Glob', 'Grep'],
        'disallowedTools': ['Edit', 'Write', 'Agent', 'NotebookEdit', 'ExitPlanMode'],
        'desc': '只读模式（来自 Explore/Plan/Verification Agent 模式）'
    },
    'codewrite': {
        'tools': ['Read', 'Bash', 'Glob', 'Grep', 'Edit', 'Write'],
        'disallowedTools': ['Agent'],
        'desc': '代码编写模式'
    },
    'full': {
        'tools': [],  # 空 = 继承全部
        'disallowedTools': [],
        'desc': '完整权限模式'
    },
    'search': {
        'tools': ['Read', 'Bash', 'Glob', 'Grep'],
        'disallowedTools': ['Edit', 'Write', 'Agent', 'NotebookEdit'],
        'desc': '搜索/分析模式（haiku 模型推荐）'
    },
}

# 内置 Agent 参考模式
BUILTIN_EXAMPLES = {
    'verification': {
        'description': '实现验证专家。验证工作完成后调用此 Agent。传入：原始任务描述、修改的文件列表、采用的方案。返回：PASS/FAIL/PARTIAL 判定和证据。',
        'disallowedTools': ['Edit', 'Write', 'NotebookEdit', 'Agent', 'ExitPlanMode'],
        'model': 'inherit',
        'background': True,
        'role': '你是一个验证专家。你的工作不是确认实现有效——而是尝试破坏它。',
        'source': 'verificationAgent.ts',
    },
    'explore': {
        'description': '代码库探索专家。用于快速查找文件（glob 模式）、搜索代码（关键词）、回答代码库问题。调用时指定彻底程度：quick/medium/very thorough。',
        'disallowedTools': ['Edit', 'Write', 'Agent', 'NotebookEdit'],
        'model': 'haiku',
        'background': False,
        'role': '你是一个文件搜索专家。专注于快速导航和探索代码库。',
        'source': 'exploreAgent.ts',
    },
    'plan': {
        'description': '软件架构规划专家。需要规划实现策略时使用。返回：分步实现计划、关键文件、架构权衡。',
        'disallowedTools': ['Edit', 'Write', 'Agent', 'NotebookEdit'],
        'model': 'inherit',
        'background': False,
        'role': '你是一个软件架构师和规划专家。探索代码库并设计实现方案。',
        'source': 'planAgent.ts',
    },
}


def generate_agent_md(
    name: str,
    description: str,
    role: str,
    tools: list[str] | None = None,
    disallowed_tools: list[str] | None = None,
    model: str = 'inherit',
    background: bool = False,
    memory: str | None = None,
    max_turns: int | None = None,
    extra_instructions: str = '',
) -> str:
    """生成 Agent .md 文件内容"""

    # 构建 frontmatter
    frontmatter_lines = [
        '---',
        f'name: {name}',
        f'description: {description}',
        f'model: {model}',
    ]

    if tools:
        frontmatter_lines.append(f'tools: {", ".join(tools)}')

    if disallowed_tools:
        frontmatter_lines.append(f'disallowedTools: {", ".join(disallowed_tools)}')

    if background:
        frontmatter_lines.append('background: true')

    if memory:
        frontmatter_lines.append(f'memory: {memory}')

    if max_turns:
        frontmatter_lines.append(f'maxTurns: {max_turns}')

    frontmatter_lines.append('---')
    frontmatter = '\n'.join(frontmatter_lines)

    # 判断是否是只读模式（用于生成对应的约束说明）
    is_readonly = disallowed_tools and any(t in disallowed_tools for t in ['Edit', 'Write'])

    # 构建系统提示模板
    readonly_section = dedent("""
    === 严格限制：只读模式 ===
    你被禁止：
    - 创建、修改或删除任何文件
    - 运行 git write 操作（add、commit、push）
    - 安装依赖
    - 任何改变系统状态的操作

    你的角色仅限于：分析和报告。
    """).strip() if is_readonly else ''

    output_format = dedent("""
    ## 输出格式

    每个检查项使用以下格式：
    ```
    ### 检查: [检查内容]
    **执行命令:** [实际运行的命令]
    **观察到的输出:** [实际终端输出]
    **结果: PASS/FAIL**
    ```

    以这一行结束（由调用方解析）：
    VERDICT: PASS
    或
    VERDICT: FAIL
    或
    VERDICT: PARTIAL
    """).strip() if is_readonly else dedent("""
    ## 输出格式

    - 简洁、结构化输出
    - 重要发现单独标注
    - 如有代码修改，列出修改的文件
    """).strip()

    system_prompt = f"""{role}

{readonly_section}
{'─' * 40 if readonly_section else ''}

## 策略

[在此描述 Agent 分析/处理任务的具体策略]

## 反模式识别

[在此列出此 Agent 容易陷入的错误模式，以及如何避免]

{extra_instructions}

{output_format}"""

    return f"{frontmatter}\n\n{system_prompt.strip()}"


def interactive_mode():
    """交互式 Agent 设计向导"""
    print("\n=== Claude Code Agent 设计向导 ===\n")

    name = input("Agent 名称 (snake-case, 如 security-reviewer): ").strip()
    if not name:
        print("名称不能为空")
        sys.exit(1)

    print("\n描述将作为路由键，orchestrator 根据此判断何时调用。")
    print("格式建议: '用于[什么时候]。传入:[什么参数]。返回:[什么结果]。'")
    description = input("when_to_use 描述: ").strip()

    role = input("\n一句话 role 定义 (如'你是一个安全分析专家'): ").strip()

    print("\n工具集预设:")
    for key, preset in TOOL_PRESETS.items():
        print(f"  {key}: {preset['desc']}")
    preset_choice = input("选择预设 (或直接回车跳过): ").strip()

    tools = None
    disallowed_tools = None
    if preset_choice in TOOL_PRESETS:
        p = TOOL_PRESETS[preset_choice]
        tools = p['tools'] or None
        disallowed_tools = p['disallowedTools'] or None
    else:
        custom_tools = input("自定义 tools (逗号分隔，空=继承全部): ").strip()
        if custom_tools:
            tools = [t.strip() for t in custom_tools.split(',')]
        custom_deny = input("disallowedTools (逗号分隔): ").strip()
        if custom_deny:
            disallowed_tools = [t.strip() for t in custom_deny.split(',')]

    print(f"\n模型选项: {', '.join(VALID_MODELS)}")
    model = input("model (默认 inherit): ").strip() or 'inherit'

    background = input("后台运行? (y/N): ").strip().lower() == 'y'

    print(f"\n记忆范围 (可选): {', '.join(VALID_MEMORY_SCOPES)}")
    memory = input("memory scope (回车=不启用): ").strip() or None

    content = generate_agent_md(
        name=name,
        description=description,
        role=role,
        tools=tools,
        disallowed_tools=disallowed_tools,
        model=model,
        background=background,
        memory=memory,
    )

    # 确定保存位置
    print("\n保存位置:")
    print("  1. ~/.claude/agents/ (全局，所有项目可用)")
    print("  2. .claude/agents/ (当前项目)")
    print("  3. 仅打印到终端")
    choice = input("选择 (1/2/3): ").strip()

    if choice == '1':
        save_dir = Path.home() / '.claude' / 'agents'
    elif choice == '2':
        save_dir = Path.cwd() / '.claude' / 'agents'
    else:
        print(f"\n{'─'*60}")
        print(content)
        print(f"{'─'*60}")
        return

    save_dir.mkdir(parents=True, exist_ok=True)
    output_path = save_dir / f"{name}.md"

    if output_path.exists():
        overwrite = input(f"\n{output_path} 已存在，覆盖? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("已取消")
            return

    output_path.write_text(content, encoding='utf-8')
    print(f"\n✅ Agent 文件已创建: {output_path}")
    print(f"\n下一步：")
    print(f"  1. 编辑 {output_path} 完善系统提示")
    print(f"  2. 在 Claude Code 中使用: Agent({{subagent_type: '{name}', prompt: '...'}})")


def main():
    parser = argparse.ArgumentParser(
        description='生成 Claude Code Agent .md 文件模板'
    )
    parser.add_argument('--name', help='Agent 名称')
    parser.add_argument('--description', help='when_to_use 描述')
    parser.add_argument('--role', help='一句话 role 定义')
    parser.add_argument('--preset', choices=list(TOOL_PRESETS.keys()),
                       help='工具集预设')
    parser.add_argument('--tools', help='允许的工具（逗号分隔）')
    parser.add_argument('--readonly', action='store_true',
                       help='只读模式（等同于 --preset readonly）')
    parser.add_argument('--model', default='inherit', choices=VALID_MODELS)
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--memory', choices=VALID_MEMORY_SCOPES)
    parser.add_argument('--output', help='输出文件路径')
    parser.add_argument('--interactive', action='store_true', help='交互式向导')
    parser.add_argument('--list-examples', action='store_true',
                       help='列出内置 Agent 参考模式')

    args = parser.parse_args()

    if args.list_examples:
        print("\n=== 内置 Agent 参考模式 ===\n")
        for name, ex in BUILTIN_EXAMPLES.items():
            print(f"## {name} (来自 {ex['source']})")
            print(f"   model: {ex['model']}, background: {ex['background']}")
            print(f"   role: {ex['role'][:80]}")
            print(f"   description: {ex['description'][:100]}")
            print()
        return

    if args.interactive:
        interactive_mode()
        return

    if not args.name or not args.description or not args.role:
        print("错误：--name, --description, --role 是必需参数")
        print("或使用 --interactive 进入交互向导")
        print("或使用 --list-examples 查看参考模式")
        sys.exit(1)

    # 处理工具集
    if args.readonly or args.preset == 'readonly':
        preset = TOOL_PRESETS['readonly']
        tools = preset['tools']
        disallowed = preset['disallowedTools']
    elif args.preset:
        preset = TOOL_PRESETS[args.preset]
        tools = preset['tools'] or None
        disallowed = preset['disallowedTools'] or None
    else:
        tools = [t.strip() for t in args.tools.split(',')] if args.tools else None
        disallowed = None

    content = generate_agent_md(
        name=args.name,
        description=args.description,
        role=args.role,
        tools=tools,
        disallowed_tools=disallowed,
        model=args.model,
        background=args.background,
        memory=args.memory,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding='utf-8')
        print(f"✅ Agent 文件已写入: {output_path}")
    else:
        print(content)


if __name__ == '__main__':
    main()
