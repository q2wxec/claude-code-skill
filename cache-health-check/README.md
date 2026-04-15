# cache-health-check

Claude Code 项目的提示缓存健康审计工具。

## 核心来源

`src/services/api/promptCacheBreakDetection.ts`

该模块跟踪 14 个状态向量，检测哪些配置变化导致了提示缓存中断（cache break），并将原因归类为客户端变化或服务端变化。

---

## 14 个被追踪的状态向量

| # | 向量名 | 中断风险 | 说明 |
|---|--------|---------|------|
| 1 | `systemHash` | 高 | 系统提示（system prompt）内容的完整哈希 |
| 2 | `toolsHash` | 高 | 所有工具 schema 的聚合哈希 |
| 3 | `cacheControlHash` | 中 | 捕获 global↔org 切换、1小时↔5分钟 TTL 切换 |
| 4 | `perToolHashes` | 高 | 每个工具的单独 schema 哈希（工具中断的 77%） |
| 5 | `systemCharCount` | 低 | 系统提示的字符数变化——仅作幅度指示 |
| 6 | `model` | 高 | 模型字符串；不同模型 = 不同缓存空间 |
| 7 | `fastMode` | 中 | 快速模式开关影响 effort 解析 |
| 8 | `globalCacheStrategy` | 高 | `tool_based` / `system_prompt` / `none` |
| 9 | `betas` | 中 | beta 请求头列表 |
| 10 | `autoModeActive` | 无 | AFK 模式——粘性锁定，不应引发中断 |
| 11 | `isUsingOverage` | 无 | 超额状态——会话内稳定，不应引发中断 |
| 12 | `cachedMCEnabled` | 无 | 缓存 microcompact 头——粘性锁定，不应引发中断 |
| 13 | `effortValue` | 中 | 解析后的 effort 值：env → options → 模型默认 |
| 14 | `extraBodyHash` | 中 | `CLAUDE_CODE_EXTRA_BODY` 和 anthropic_internal 参数 |

向量 10、11、12 被设计为"锁定"状态——每个会话最多变化一次，预期不会引发缓存中断。

---

## 缓存 TTL 值

| 层级 | TTL |
|------|-----|
| 默认层（标准用户） | **5 分钟** (`CACHE_TTL_5MIN_MS = 5 * 60 * 1000`) |
| 超额层（Overage tier） | **1 小时** (`CACHE_TTL_1HOUR_MS = 60 * 60 * 1000`) |

如果相邻两次请求的间隔超过对应 TTL，缓存将自然过期——这属于正常行为，不计入"中断"统计。

---

## 中断检测阈值

来自 `promptCacheBreakDetection.ts`：

```
缓存中断 = cacheReadTokens < prevCacheRead × 0.95
           AND tokenDrop ≥ MIN_CACHE_MISS_TOKENS (2000)
```

- 排除模型：Haiku（缓存行为不同，不纳入追踪）
- 服务端中断启发式判断：客户端无变化 AND 间隔 < 5 分钟 → 记录为"可能是服务端（提示未变，<5分钟间隔）"

---

## 被追踪的查询来源

**追踪的来源：**
- `repl_main_thread`（`compact` 映射到此）
- `sdk`
- `agent:custom`、`agent:default`、`agent:builtin`

**不追踪（短生命周期分叉代理）：**
- `speculation`、`session_memory`、`prompt_suggestion`（1-3 轮即结束，不值得追踪）

---

## Top 5 缓存中断原因（按 BQ 频率排序）

| 排名 | 原因 | 触发向量 | BQ 频率 |
|------|------|---------|---------|
| 1 | 工具 schema 变化（MCP 服务端动态描述） | `perToolHashes` | ~77% 的工具中断 |
| 2 | 系统提示变化（CLAUDE.md 含动态内容） | `systemHash` | 常见 |
| 3 | 全局缓存策略不稳定（MCP 有无不一致） | `globalCacheStrategy` | 中等 |
| 4 | 模型字符串变化（跨会话切换模型） | `model` | 低但影响大 |
| 5 | Extra body 参数含动态值 | `extraBodyHash` | 低但可完全避免 |

---

## CLAUDE.md 中常见的缓存破坏来源

| 来源 | 示例 | 修复方法 |
|------|------|---------|
| 嵌入日期 | "Last updated: April 2026" | 删除 |
| 绝对路径 | `/Users/fxx/projects/app/` | 改用相对路径 |
| 动态工具列表 | MCP 服务端每次返回不同工具 | 固定服务端版本或移除 |
| 模型覆盖 | 项目级 `model` 与全局不同 | 统一使用一个模型 |
| Effort 切换 | `alwaysThinkingEnabled` 频繁改变 | 选定后保持不变 |
| Extra body 参数 | `CLAUDE_CODE_EXTRA_BODY` 含请求 ID | 仅使用静态参数 |
| Beta 头变化 | 实验性 beta 频繁开关 | 稳定 beta 列表 |

---

## 使用方法

### 触发短语

- "减少 API 费用" / "降低 token 开销"
- "提高缓存命中率" / "为什么我的会话很贵？"
- "优化 Claude Code 性能"
- "诊断缓存中断" / "cache health"
- 添加 MCP 服务端后 / 修改模型设置后

### 运行审计脚本

```bash
# 标准报告（人类可读）
python3 ~/.claude/skills/cache-health-check/scripts/cache_health_audit.py

# 机器可读 JSON 输出
python3 ~/.claude/skills/cache-health-check/scripts/cache_health_audit.py --json
```

脚本自动发现以下配置文件：
- `~/.claude/settings.json`
- `~/.claude/settings.local.json`
- `.claude/settings.json`（当前项目）
- `~/.claude/CLAUDE.md`
- `.claude/CLAUDE.md`（当前项目）
- `CLAUDE.md`（当前目录）

### 深度 CLAUDE.md 分析

如需对 CLAUDE.md 进行逐节分类（静态/动态/反模式），使用 prompt-architect 技能：

```bash
python3 ~/.claude/skills/prompt-architect/scripts/claudemd_audit.py
```

`cache_health_audit.py` 只做 CLAUDE.md 的快速扫描（Top 3 模式）；
`claudemd_audit.py` 提供完整的重构建议和稳定前缀 / 动态后缀分离方案。

---

## 健康评分解读

| 分数 | 状态 | 含义 |
|------|------|------|
| 85–100 | 健康 | 缓存仅在预期来源中断 |
| 65–84 | 警告 | 存在 1–2 个可修复的中断来源 |
| 40–64 | 退化 | 多个中断来源；有可测量的成本影响 |
| 0–39 | 危急 | 配置正在积极损害缓存效率 |

---

## 技能文件结构

```
~/.claude/skills/cache-health-check/
├── SKILL.md                         # 技能定义（英文，供 Claude 读取）
├── README.md                        # 本文档（中文参考）
└── scripts/
    └── cache_health_audit.py        # 审计脚本（stdlib only，Python 3）
```
