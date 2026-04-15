# agent-squad-designer

为特定项目设计定制 Agent 团队，遵循 Claude Code 内部的最小权限 + 单一职责架构模式。

## 解决的问题

在 Claude Code 中运行多 Agent 工作流时，常见问题是：Agent 权限过大、职责不清、调度逻辑写死在代码里而不是 prompt 里、sub-agent 的输出没有被 orchestrator 正确综合。这个 skill 帮你按照 Claude Code 内置 Agent 的设计模式来规划 Agent 团队。

## 核心设计原则（来自 Claude Code 源码）

1. **单一职责** — 每个 Agent 只做一件事，`whenToUse` 字段就是路由键
2. **最小权限** — 用 `tools`（白名单）或 `disallowedTools`（黑名单）精确控制
3. **Prompt 即算法** — 调度逻辑在 description 字段里，不在代码里
4. **不下放理解** — orchestrator 自己综合 sub-agent 结果，不让 sub-agent 代替它决策
5. **background 标记** — 验证、审计类任务用 `background: true`，协作类用前台

## Claude Code 内置 Agent 模式参考

| Agent | 权限模式 | model |
|---|---|---|
| Explore | disallow: Edit, Write, Agent | haiku（速度） |
| Plan | disallow: Edit, Write, Agent | inherit（推理） |
| Verification | disallow: Edit, Write, Agent, Notebook | inherit（对抗性） |

## 使用方式

对 Claude 说：
- `"为我的项目设计 Agent 团队"`
- `"帮我规划多 Agent 工作流"`
- `"创建一组 Claude agents 分工协作"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/agent_scaffold.py` | 根据描述生成 Agent .md 文件模板 |

## Agent .md 文件放置位置

- 全局 Agent（所有项目可用）：`~/.claude/agents/<name>.md`
- 项目 Agent（仅当前项目）：`.claude/agents/<name>.md`

## 源码依据

- `src/tools/AgentTool/loadAgentsDir.ts`: Agent 定义结构（frontmatter schema）
- `src/tools/AgentTool/built-in/verificationAgent.ts`: 最小权限 + adversarial prompt 模式
- `src/tools/AgentTool/built-in/exploreAgent.ts`: read-only + haiku 速度优化
- `src/utils/systemPrompt.ts`: agent prompt 在 proactive mode 中的组装方式
