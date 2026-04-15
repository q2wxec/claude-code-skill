# memory-architect

将混乱的 MEMORY.md 重构为 Claude Code `autoDream` 内部使用的三层记忆架构。

## 解决的问题

随着项目进行，MEMORY.md 往往变成一个塞满内容的大文件：段落式叙述替代了指针、过期事实与新发现混杂、索引行超过 200 行导致截断。这个 skill 把它整理成 Claude Code 内部用于背景记忆蒸馏的三层结构。

## 三层结构

```
MEMORY.md          ← 永久加载的指针索引（≤200 行）
├── topic-file.md  ← 按需加载的主题知识文件
└── archive/       ← 历史上下文，不主动加载
```

**Layer 1** — MEMORY.md 只存指针，每行 ≤150 字符：
```
- [Title](file.md) — 一句话描述（何时相关）
```

**Layer 2** — 每个主题文件有 frontmatter：
```yaml
---
name: ...
description: ...
type: user | feedback | project | reference
---
```

**Layer 3** — archive/ 目录，历史决策，不加入 MEMORY.md 索引。

## 使用方式

对 Claude 说：
- `"帮我整理 MEMORY.md"`
- `"我的记忆文件太乱了，重构一下"`
- `"MEMORY.md 快 200 行了，清理一下"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/memory_audit.py` | 扫描并诊断所有记忆文件，输出健康报告 |

## 源码依据

- `src/memdir/memdir.ts`: `MAX_ENTRYPOINT_LINES=200`, `MAX_ENTRYPOINT_BYTES=25000`, `truncateEntrypointContent()`
- `src/memdir/memoryScan.ts`: `scanMemoryFiles()`, `formatMemoryManifest()`
- `src/memdir/memoryTypes.ts`: `MEMORY_TYPES`, frontmatter 规范
- `src/services/autoDream/consolidationPrompt.ts`: 4 阶段整理流程
