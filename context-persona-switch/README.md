# context-persona-switch

基于 Claude Code 源码中 `src/utils/undercover.ts` 的 undercover mode 设计，帮助用户为不同工作场景构建自动切换的 Claude 行为规则。

---

## 核心来源

`src/utils/undercover.ts` 实现了一种"隐蔽模式"：当 Claude Code 运行在内部环境时，自动剥离内部代号、未发布版本、内部工具名称和 AI 归因信息。该模块的设计思路直接可以迁移为通用的多 persona 系统。

关键实现细节：
- `CLAUDE_CODE_UNDERCOVER=1` 强制开启，无强制关闭选项
- `getRepoClassCached()` 返回 `'internal' | 'external' | 'none' | null`，通过读取 git remote 判断
- 安全默认值为 ON（隐蔽模式），而非 OFF
- 剥离规则明确列举：内部代号、未发布版本、内部仓库/工具/频道、AI 归因

---

## 设计原则

### 1. 不对称安全（Asymmetric Safety）
进入限制性 persona 容易（环境信号触发），退出需要显式覆盖。当检测结果模糊时，默认激活约束最多的 persona，而非最宽松的。

### 2. 环境自动检测（Environment Detection First）
Persona 从 git remote、工作目录、分支名称或环境变量自动激活，不需要每次会话手动配置。

### 3. 显式剥离规则（Explicit Stripping Rules）
每个 persona 声明"不输出什么"，而不仅仅是"输出什么"。排除清单比包含清单更重要。

### 4. 单向门原则（One-Way Gate）
类似 undercover.ts 没有 force-OFF，persona 系统默认走向更安全的输出。只有明确的环境信号才能切换到更宽松的 persona。

---

## 4 种检测方法

| 方法 | 示例 | 可靠性 | 配置成本 |
|---|---|---|---|
| 环境变量 | `PERSONA=internal-dev` | 显式，最可靠 | 低（手动设置） |
| Git remote 模式 | remote 包含 `acme-corp.net` | 自动，无需干预 | 无（仓库本身携带） |
| 目录路径模式 | cwd 匹配 `*/clients/*` | 自动，需路径规范 | 需要目录命名规范 |
| 分支名前缀 | 分支以 `oss/` 开头 | 半自动 | 需要分支命名规范 |

检测优先级从上到下，第一个匹配的规则生效。无匹配时激活最严格的 persona。

---

## 示例 Persona 对照表

| 维度 | internal-dev | client-facing | open-source |
|---|---|---|---|
| **激活信号** | remote 含内部域名 | cwd 含 `/clients/` | 分支前缀 `oss/` |
| **输出风格** | 详细、技术化 | 精炼、正式 | 中性、社区友好 |
| **术语层级** | 内部行话允许 | 仅外部术语 | 通用术语 |
| **归因** | 完整保留 | 按合同要求 | 剥除公司引用 |
| **排除项** | 客户信息、凭证 | 内部代号、路线图、内部 URL | 公司名、内部项目名 |
| **包含项** | 内部文档链接 | 客户文档引用 | 开源许可信息 |

---

## 使用方式

### 触发短语

以下任意一种表达都会触发本技能：

- "帮我为不同仓库设置不同的 Claude 行为"
- "我需要在内部项目和客户项目里用不同的语气"
- "怎么让 Claude 自动检测当前是内部还是外部工作模式"
- "我想要 context-aware persona switching"
- "不同 repo 用不同规则"
- "帮我设计多 persona 系统"

### 快速开始

1. 直接和 Claude 对话，描述你的 2-3 个工作场景
2. 或运行交互式生成器：
   ```bash
   python3 ~/.claude/skills/context-persona-switch/scripts/persona_generator.py --interactive
   ```
3. 检测当前环境的 persona：
   ```bash
   python3 ~/.claude/skills/context-persona-switch/scripts/persona_generator.py --detect
   ```
4. 将生成的 CLAUDE.md 片段放到对应项目目录

### 输出位置建议

```
~/.claude/rules/personas/internal-dev.md    # 全局内部开发规则
~/.claude/rules/personas/client-facing.md  # 全局客户交付规则
<project>/.claude/CLAUDE.md                # 项目级覆盖
```

---

## 与 undercover.ts 的映射关系

| undercover.ts 概念 | Persona 系统等价物 |
|---|---|
| `CLAUDE_CODE_UNDERCOVER=1` | `PERSONA=<name>` 环境变量 |
| Repo remote allowlist 检查 | Git remote 模式匹配 |
| 默认 ON（安全） | 默认激活最严格 persona |
| 无强制 OFF | 无覆盖到最宽松 persona 的路径 |
| 剥除内部代号 | Persona 排除清单 — 内部名称 |
| 剥除 AI 归因 | Persona 归因规则 — 剥除 |

---

## 文件结构

```
~/.claude/skills/context-persona-switch/
├── SKILL.md                    # 技能主文件（Claude 加载）
├── README.md                   # 本文档（中文说明）
└── scripts/
    └── persona_generator.py    # 交互式 CLAUDE.md 生成器
```
