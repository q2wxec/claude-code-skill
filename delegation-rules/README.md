# delegation-rules

为多 Agent 工作流生成委托规则文档，帮助设计清晰的 orchestrator/worker 边界，并编写高质量的自包含 sub-agent prompt。

## 核心来源

**`src/constants/prompts.ts` lines 316-320 — Agent tool guidance：**

> "Avoid duplicating work that subagents are already doing — if you delegate research to a subagent, do not also perform the same searches yourself."
>
> "If you ARE the fork — execute directly; do not re-delegate."

Sub-agent 运行在 fork 模式下：工具输出留在 sub-agent 的上下文中，不会自动流回 orchestrator。这就是委托的核心价值 —— 保护主上下文窗口不被海量结果淹没。

## "不下放理解" 原则

这是最容易违反的规则，也是最重要的一条。

**错误模式：**
1. Orchestrator 把 sub-agent A 的原始输出直接传给 sub-agent B，让 B "综合一下"
2. Orchestrator 说 "based on your findings from before" — sub-agent 没有 "before"，它刚进房间
3. Orchestrator 让 sub-agent 做 "最终决定" — 决定权永远在 orchestrator

**正确模式：**
1. Sub-agent A 返回事实
2. **Orchestrator 自己综合** A 的结果（在自己的上下文中）
3. 带着综合后的理解，给 sub-agent B 写一份新的自包含 brief

## 可委托 vs. 不可委托

| 类型 | 可委托？ | 原因 |
|------|---------|------|
| 代码库搜索（返回 file:line 列表） | 是 | 输出格式清晰，不需要跨任务上下文 |
| 单文件实现（输入/输出定义清楚） | 是 | 完全自包含，成功标准明确 |
| 验证检查（PASS/FAIL/PARTIAL） | 是 | 只读，结果是二元的 |
| 模式探索（列出所有匹配 X 的文件） | 是 | 独立、有界、可重复 |
| 多个 agent 结果的综合 | 否 | 只有 orchestrator 有全部结果 |
| A/B 方案的最终选择 | 否 | 需要全局视图 |
| 向用户汇报进度 | 否 | 需要知道整体状态 |
| "理解整体目标" | 否 | 不能被 sub-agent 从 brief 中重建 |
| 跨多次委托的上下文持有 | 否 | Sub-agent 是无状态的，orchestrator 是线索 |

## Agent prompt 质量：改写示例

### 改写前（差）

```
Review the authentication module for security issues.
Based on what you find, also check if session handling is affected.
Use your judgment about what's important.
```

**问题清单：**
- 没有具体文件路径
- "基于你的发现" — sub-agent 没有之前的发现
- 没有输出格式
- 没有长度限制
- "用你的判断" — 没有给判断提供上下文
- 链式委托（检查 + 再检查）

### 改写后（好）

```
GOAL: Find SQL injection risks in the user login path.

SCOPE: Read these files only:
  - src/auth/login.ts
  - src/db/userQueries.ts

CONTEXT: We confirmed raw string concatenation in queryUser() at
  src/db/userQueries.ts:47. We need to know if this pattern exists
  elsewhere in the login path.

ALREADY RULED OUT: src/auth/oauth.ts — uses parameterized queries
  throughout, skip it.

OUTPUT FORMAT: List of file:line + code snippet (max 20 results).
  End with exactly one of:
  VERDICT: CRITICAL
  VERDICT: HIGH
  VERDICT: NONE

JUDGMENT GUIDE: Flag any place where user-controlled input reaches
  a DB query without explicit parameterization or escaping.
```

**改进点：** 精确文件范围、显式上下文、排除已知结果、明确输出格式、长度限制、判断标准。

## Prompt 质量核查清单

发送给 sub-agent 之前，逐项确认：

- [ ] Agent 没看过对话历史 — 把需要的全部告诉它
- [ ] 已明确说明你尝试过什么 / 排除了什么
- [ ] 输出格式已精确指定（列表、JSON、markdown 表格、verdict 行）
- [ ] 已设置长度上限（"最多 N 条"、"不超过 500 字"）
- [ ] 已说明这件事为什么重要（帮助 agent 做判断调用）
- [ ] 使用了文件路径和函数名，而非模糊描述
- [ ] 没有 "基于之前的研究" — 直接把研究粘贴进来

## 使用触发短语

对 Claude 说以下任意一句话时，此 skill 会被激活：

- "帮我设计多 Agent 工作流"
- "怎么把工作委托给 sub-agent"
- "我的 agent prompt 写得不好，怎么改进"
- "设计 orchestrator/worker 模式"
- "避免 orchestrator 和 sub-agent 重复工作"
- "help me design multi-agent systems"
- "how to delegate to sub-agents"
- "improve agent prompt quality"
- "orchestrator worker pattern"

## 附带脚本

| 脚本 | 功能 |
|------|------|
| `scripts/delegation_audit.py` | 审计现有 Agent prompt 质量，生成委托 brief 模板 |

```bash
# 检查一个包含 agent prompts 的 markdown 文件
python scripts/delegation_audit.py --check-prompt my_prompts.md

# 扫描 Claude Code session JSONL 中的 Agent 调用
python scripts/delegation_audit.py --audit-session ~/.claude/sessions/abc.jsonl

# 生成指定工作流类型的委托 brief 模板
python scripts/delegation_audit.py --generate-template code-review
python scripts/delegation_audit.py --generate-template feature-dev
python scripts/delegation_audit.py --generate-template debugging
python scripts/delegation_audit.py --generate-template data-analysis
```

## 源码依据

- `src/constants/prompts.ts` lines 316-320: Agent tool orchestration rules
- `src/tools/AgentTool/loadAgentsDir.ts`: Agent frontmatter schema, fork mode design
- `src/tools/AgentTool/built-in/verificationAgent.ts`: Self-contained brief pattern, VERDICT format
- `src/tools/AgentTool/built-in/exploreAgent.ts`: Bounded scope + structured output pattern
