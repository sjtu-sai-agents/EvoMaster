# Multi-Agent Parallel Playground（多智能体并行 Playground）

基于 EvoMaster 实现的并行多智能体示例，展示如何使用 ThreadPoolExecutor 同时运行多个 Planning Agent + Coding Agent 协作工作流。

## 概述

本 playground 在 [minimal_multi_agent](../minimal_multi_agent/README_CN.md) 基础上增加了并行执行能力：

- **Planning Agent**：分析任务并制定执行计划
- **Coding Agent**：根据计划执行代码任务
- **并行执行**：通过 `execute_parallel_tasks()` 同时运行多个实验
- **Agent 隔离**：每个并行任务使用独立的 Agent 副本（通过 `copy_agent`），拥有独立的 LLM 实例和上下文，避免并发冲突

## 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         任务输入（同一任务 × N）                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  Exp 0        │           │  Exp 1        │           │  Exp 2        │
│  workspace/   │           │  workspace/   │           │  workspace/   │
│  exp_0/       │           │  exp_1/       │           │  exp_2/       │
│               │           │               │           │               │
│Planning→Coding│           │Planning→Coding│           │Planning→Coding│
└───────────────┘           └───────────────┘           └───────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  ThreadPoolExecutor 结果汇总  │
                    └───────────────────────────────┘
```

## 实现要点

### 1. Agent 副本保证并行安全

通过 `copy_agent()` 为每个并行实验创建独立的 Agent 副本：

- **独立 LLM 实例**：不共享 LLM，避免竞态条件
- **独立上下文**：各自的 `current_dialog`、`trajectory`、`_step_count`
- **共享资源**：Session、tools、skill_registry（只读）

### 2. 工作空间隔离

当 `session.local.parallel.split_workspace_for_exp: true` 时：

- 每个 exp 使用 `workspace/exp_0/`、`workspace/exp_1/` 等独立目录
- 避免并行任务间的文件冲突

### 3. 并行任务执行

使用 `BasePlayground.execute_parallel_tasks()`：

- 为每个任务包装并行索引和工作空间设置
- 按原始任务顺序返回结果

## 快速开始

### 1. 配置

编辑 `configs/minimal_multi_agent_parallel/deepseek-v3.2-example.yaml`：

```yaml
# 并行执行配置（本 playground 必需）
session:
  local:
    parallel:
      enabled: true
      max_parallel: 3
      split_workspace_for_exp: true  # 为每个 exp 隔离工作空间

agents:
  planning:
    llm: "local_sglang"
    # ...
  coding:
    llm: "local_sglang"
    # ...
```

### 2. 运行

```bash
# 使用并行多智能体运行（同一任务会启动 max_parallel 个并行实验）
python run.py --agent minimal_multi_agent_parallel \
  --config configs/minimal_multi_agent_parallel/deepseek-v3.2-example.yaml \
  --task "Write a Python program that implements the following features: Read a text file (create a sample file if it doesn't exist). Count the occurrences of each word in the file. Sort the results by frequency in descending order. Save the results to a new file named word_count.txt. Output the top 10 most common words to the terminal."
```

### 3. 查看结果

结果保存在：

```
runs/minimal_multi_agent_parallel_{timestamp}/
├── trajectories/       # Agent 执行轨迹（按 exp 区分）
├── logs/               # 执行日志
└── workspace/         # 工作空间
    ├── exp_0/          # 实验 0 的工作空间
    ├── exp_1/          # 实验 1 的工作空间
    └── exp_2/          # 实验 2 的工作空间
```

## 配置选项

| 选项 | 描述 | 默认值 |
|------|------|--------|
| `agents.planning.max_turns` | 规划最大轮数 | `10` |
| `agents.planning.enable_tools` | 启用规划工具 | `false` |
| `agents.coding.max_turns` | 编码最大轮数 | `50` |
| `agents.coding.enable_tools` | 启用编码工具 | `true` |
| `session.local.parallel.enabled` | 启用并行执行 | `true` |
| `session.local.parallel.max_parallel` | 最大并行数 | `3` |
| `session.local.parallel.split_workspace_for_exp` | 为每个 exp 隔离工作空间 | `true` |
| `skills.enabled` | 启用技能系统 | `false` |

## 目录结构

```
playground/minimal_multi_agent_parallel/
├── core/
│   ├── __init__.py
│   ├── playground.py    # MultiAgentParallelPlayground（并行工作流）
│   └── exp.py           # MultiAgentExp（planning → coding）
├── prompts/
│   ├── planning_system_prompt.txt
│   ├── planning_user_prompt.txt
│   ├── coding_system_prompt.txt
│   ├── coding_user_prompt.txt
│   └── system_prompt.txt
├── README.md
└── README_CN.md
```

## 代码流程

1. **`setup()`**：创建共享的 Planning Agent 和 Coding Agent
2. **`_create_exp(i)`**：为 exp 索引 `i` 通过 `copy_agent()` 创建副本，构建 `MultiAgentExp`
3. **`run()`**：用 `partial(exp.run, task_description=...)` 构建任务列表，调用 `execute_parallel_tasks(tasks, max_workers)`
4. **`execute_parallel_tasks`**（基类）：为每个任务包装 `set_parallel_index` 和 `setup_exp_workspace`，通过 `ThreadPoolExecutor` 执行

## 相关文档

- [EvoMaster 主 README](../../README.md)
- [Minimal Multi-Agent Playground](../minimal_multi_agent/README_CN.md)（串行版本）
- [Minimal Playground](../minimal/README_CN.md)
- [配置示例](../../configs/)
