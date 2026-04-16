# claude-code-skill

基于 Claude Code 源码逆向工程提炼的 Skill 集合。

每个 skill 均有对应的源码锚点，从 Anthropic 内部工程决策中提取通用模式，解决 Claude Code 真实使用痛点。

## 背景

2026-03-31，`@anthropic-ai/claude-code` v2.1.88 npm 包因 Bun 构建 bug 意外携带了完整 source map，约 **512,000 行 TypeScript 源码**曝光。本项目从中提取有价值的设计模式，转化为可复用的 skill。



---

## Skill 清单

### 记忆与上下文管理

| Skill                                            | 触发场景                      | 源码锚点                             |
| ------------------------------------------------ | ----------------------------- | ------------------------------------ |
| [memory-architect](./memory-architect/)             | 重构混乱的 MEMORY.md          | `services/autoDream/` 三层记忆架构 |
| [compact-with-memory](./compact-with-memory/)       | 压缩上下文前提取记忆          | `autoCompact.ts` 摘要 prompt       |
| [session-dream](./session-dream/)                   | 手动触发记忆蒸馏              | `autoDream/consolidationPrompt.ts` |
| [context-budget-planner](./context-budget-planner/) | 长任务开始前规划 context 预算 | `autoCompact.ts` 4 层触发阈值      |

### Prompt 与缓存优化

| Skill                                    | 触发场景               | 源码锚点                                                        |
| ---------------------------------------- | ---------------------- | --------------------------------------------------------------- |
| [prompt-architect](./prompt-architect/)     | 审计/重构 CLAUDE.md    | `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`、`systemPromptSections.ts` |
| [cache-health-check](./cache-health-check/) | 诊断 prompt cache 中断 | `promptCacheBreakDetection.ts` 14 个失效向量                  |

### 多 Agent 架构

| Skill                                        | 触发场景                              | 源码锚点                                         |
| -------------------------------------------- | ------------------------------------- | ------------------------------------------------ |
| [agent-squad-designer](./agent-squad-designer/) | 为项目设计定制 Agent 团队             | 6 个内置 Agent 的 system prompt + 工具权限白名单 |
| [delegation-rules](./delegation-rules/)         | 生成 orchestrator/worker 委托规则文档 | `src/constants/prompts.ts` Agent tool guidance |

### 场景切换与自主模式

| Skill                                                | 触发场景               | 源码锚点                                         |
| ---------------------------------------------------- | ---------------------- | ------------------------------------------------ |
| [context-persona-switch](./context-persona-switch/)     | 多工作场景行为规则切换 | `undercover.ts`、`USER_TYPE` 分支逻辑        |
| [autonomous-mode-scaffold](./autonomous-mode-scaffold/) | 设计离场自主工作配置   | `src/constants/prompts.ts:860-913` KAIROS 模式 |

---

## Skill 优先级

| 优先级         | Skill                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------ |
| P0（核心高频） | `compact-with-memory`、`memory-architect`、`agent-squad-designer`                                |
| P1（常用优化） | `prompt-architect`、`session-dream`、`context-budget-planner`                                    |
| P2（进阶使用） | `autonomous-mode-scaffold`、`delegation-rules`、`context-persona-switch`、`cache-health-check` |

---

## 目录结构

```
claude-code-skill/
├── <skill-name>/
│   ├── SKILL.md       # skill 定义（触发条件、工作流程、示例输出）
│   ├── README.md      # 人类可读说明
│   └── scripts/       # 可独立运行的辅助脚本
└── README.md          # 本文件
```

## 安装到 Claude Code

将需要的 skill 目录复制到 `~/.claude/skills/`，Claude Code 会根据对话内容自动匹配调用：

```bash
cp -r agent-squad-designer ~/.claude/skills/
cp -r compact-with-memory ~/.claude/skills/
# ... 其他 skill
```
