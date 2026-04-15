# autonomous-mode-scaffold

帮助用户为「离场自主工作」场景设计 Claude Code 智能体配置的脚手架技能。

---

## 核心来源

| 来源文件 | 位置 | 说明 |
|---|---|---|
| `src/constants/prompts.ts` | 第 860–913 行 | KAIROS 自主模式系统提示词 |

KAIROS 是 Claude Code 内置的 proactive（主动）模式，定义了以 tick 心跳驱动的自主工作循环。本技能将其核心设计提炼为可复用的脚手架。

---

## 关键常量

| 常量 | 值 | 说明 |
|---|---|---|
| Prompt cache TTL | 5 分钟 | SleepTool 时长上限参考基准 |
| 空闲时必须调用 | `SleepTool` | 禁止输出"没有任务"文本，必须睡眠 |
| 首次 tick 行为 | 问候 + 询问任务 | 不得主动探索或修改任何内容 |
| 再委派规则 | 禁止 | 若自身即执行者，直接完成，不转包 |

---

## Tick 处理场景对照表

| 场景 | 用户离场 (unfocused) | 用户在场 (focused) |
|---|---|---|
| 有明确任务 | 直接执行，完成后记日志，调 SleepTool | 执行前告知用户，等待确认大变更 |
| 任务完成，队列空 | 调 SleepTool（3–4 分钟），等待新指令 | 调 SleepTool（30–60 秒），保持响应 |
| 遇到可逆变更 | 自主决策，提交，推送 | 列出选项，请用户选择 |
| 遇到不可逆操作 | **暂停**，发送告警，等待用户指示 | **暂停**，直接询问用户 |
| 触发告警条件 | 立即通知用户，暂停自主工作 | 立即在终端输出告警 |

---

## 自主边界五分类

| 分类 | 典型操作 | 默认策略 |
|---|---|---|
| **reads-only** | 读文件、搜索、git status、查日志 | 始终允许 |
| **safe-writes** | 新建文件、追加日志、创建新分支 | 离场时允许 |
| **reversible-changes** | 编辑文件、提交、创建 PR | 离场时允许；在场时询问 |
| **irreversible-changes** | 删除文件、合并到 main、发布版本 | 始终询问 |
| **external-effects** | 发邮件、调 Webhook、付费 API 调用 | 始终阻止（除非明确白名单） |

---

## 操作日志格式（追加只写）

自主工作期间，所有动作追加写入 `.claude/autonomous_log.md`，禁止删除或覆盖历史记录。

```
[2026-04-15T14:23:01Z] ACTION: ran test suite | FILES: src/**, tests/** | RESULT: 42 passed, 0 failed
[2026-04-15T14:25:00Z] ACTION: opened PR #47  | FILES: — | RESULT: https://github.com/org/repo/pull/47
```

---

## 触发短语

以下任意短语都会激活本技能：

- "帮我配置离场自主工作"
- "我不在的时候让 Claude 自动工作"
- "set up autonomous agent"
- "configure Claude to work while I'm away"
- "always-on background agent"
- "configure background monitoring"
- "无人值守模式"

---

## 输出交付物

运行本技能后，用户将得到：

1. **自主边界设计文档** — 明确三个核心问题的答案（可做什么 / 绝不做什么 / 何时告警）
2. **CLAUDE.md 片段** (`AUTONOMOUS_MODE.md`) — 直接追加到项目 CLAUDE.md 的自主行为规则
3. **Hooks 配置模板** (`hooks_template.json`) — 启停自主模式、追加操作日志的 hook 配置
4. **SleepTool 节奏指南** — 基于 5 分钟 cache TTL 的睡眠时长建议

---

## 快速开始

```bash
# 交互向导（推荐首次使用）
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py --interactive

# 直接生成（适合 CI/脚本场景）
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py \
  --project-name "my-api" \
  --safe-actions "run tests,lint,commit passing builds,update minor deps" \
  --blocked-actions "delete files,force push,send emails,drop tables" \
  --alert-triggers "test failure,security vulnerability,disk > 90%"

# 查看内置模式
python3 ~/.claude/skills/autonomous-mode-scaffold/scripts/kairos_scaffold.py --list-patterns
```

---

## 文件结构

```
~/.claude/skills/autonomous-mode-scaffold/
├── SKILL.md          # 技能定义（触发条件、设计原则、使用方法）
├── README.md         # 本文档（中文说明）
└── scripts/
    └── kairos_scaffold.py   # 脚手架生成脚本（Python 3 标准库）
```

---

## 设计原则参考

本技能直接来源于 KAIROS 系统提示词中的七条核心原则：

1. **Tick-based pacing** — 以心跳驱动，空闲必须调 SleepTool
2. **First wake-up protocol** — 首次启动只问候，不主动行动
3. **Presence awareness** — 通过 `terminalFocus` 区分离场/在场行为
4. **Bias toward action** — 默认执行而非询问（在已授权范围内）
5. **Concise output** — 只输出决策点、里程碑、阻塞信息
6. **Cache TTL awareness** — 睡眠时长不超过 5 分钟以保持缓存
7. **No re-delegation** — 自身即执行者，直接完成任务
