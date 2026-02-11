# Multi-Agent Parallel Playground

A parallel multi-agent playground based on EvoMaster, demonstrating how to run multiple Planning Agent + Coding Agent workflows concurrently using ThreadPoolExecutor.

## Overview

This playground extends [minimal_multi_agent](../minimal_multi_agent/README.md) with parallel execution capabilities:

- **Planning Agent**: Analyzes the task and creates an execution plan
- **Coding Agent**: Executes code tasks based on the plan
- **Parallel Execution**: Multiple experiments run simultaneously via `execute_parallel_tasks()`
- **Agent Isolation**: Each parallel task uses independent agent copies (via `copy_agent`) with separate LLM instances and context to avoid conflicts

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Task Input (same task × N)                       │
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
│ Planning→Coding│           │ Planning→Coding│           │ Planning→Coding│
└───────────────┘           └───────────────┘           └───────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  ThreadPoolExecutor Results   │
                    └───────────────────────────────┘
```

## Key Implementation Details

### 1. Agent Copy for Parallel Safety

Each parallel experiment gets its own agent copies via `copy_agent()`:

- **Independent LLM instances**: No shared LLM to avoid race conditions
- **Independent context**: Separate `current_dialog`, `trajectory`, `_step_count`
- **Shared resources**: Session, tools, skill_registry (read-only)

### 2. Workspace Isolation

When `session.local.parallel.split_workspace_for_exp: true`:

- Each exp uses `workspace/exp_0/`, `workspace/exp_1/`, etc.
- Prevents file conflicts between parallel runs

### 3. Parallel Task Execution

Uses `BasePlayground.execute_parallel_tasks()`:

- Wraps tasks with parallel index and workspace setup
- Returns results in original task order

## Quick Start

### 1. Configure

Edit `configs/minimal_multi_agent_parallel/deepseek-v3.2-example.yaml`:

```yaml
# Parallel execution settings (required for this playground)
session:
  local:
    parallel:
      enabled: true
      max_parallel: 3
      split_workspace_for_exp: true  # Isolate workspace per exp

agents:
  planning:
    llm: "local_sglang"
    # ...
  coding:
    llm: "local_sglang"
    # ...
```

### 2. Run

```bash
# Run with parallel multi-agent (uses same task × max_parallel experiments)
python run.py --agent minimal_multi_agent_parallel \
  --config configs/minimal_multi_agent_parallel/deepseek-v3.2-example.yaml \
  --task "Write a Python program that implements the following features: Read a text file (create a sample file if it doesn't exist). Count the occurrences of each word in the file. Sort the results by frequency in descending order. Save the results to a new file named word_count.txt. Output the top 10 most common words to the terminal."
```

### 3. View Results

Results are saved in:

```
runs/minimal_multi_agent_parallel_{timestamp}/
├── trajectories/       # Agent execution trajectories (per exp)
├── logs/               # Execution logs
└── workspace/          # Workspaces
    ├── exp_0/          # Experiment 0 workspace
    ├── exp_1/          # Experiment 1 workspace
    └── exp_2/          # Experiment 2 workspace
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `agents.planning.max_turns` | Max planning turns | `10` |
| `agents.planning.enable_tools` | Enable planning tools | `false` |
| `agents.coding.max_turns` | Max coding turns | `50` |
| `agents.coding.enable_tools` | Enable coding tools | `true` |
| `session.local.parallel.enabled` | Enable parallel execution | `true` |
| `session.local.parallel.max_parallel` | Max parallel workers | `3` |
| `session.local.parallel.split_workspace_for_exp` | Isolate workspace per exp | `true` |
| `skills.enabled` | Enable skill system | `false` |

## Directory Structure

```
playground/minimal_multi_agent_parallel/
├── core/
│   ├── __init__.py
│   ├── playground.py    # MultiAgentParallelPlayground (parallel workflow)
│   └── exp.py           # MultiAgentExp (planning → coding)
├── prompts/
│   ├── planning_system_prompt.txt
│   ├── planning_user_prompt.txt
│   ├── coding_system_prompt.txt
│   ├── coding_user_prompt.txt
│   └── system_prompt.txt
├── README.md
└── README_CN.md
```

## Code Flow

1. **`setup()`**: Creates shared Planning Agent and Coding Agent
2. **`_create_exp(i)`**: Creates `MultiAgentExp` with `copy_agent()` copies for exp index `i`
3. **`run()`**: Builds task list with `partial(exp.run, task_description=...)`, then calls `execute_parallel_tasks(tasks, max_workers)`
4. **`execute_parallel_tasks`** (base class): Wraps each task with `set_parallel_index` and `setup_exp_workspace`, runs via `ThreadPoolExecutor`

## Related

- [EvoMaster Main README](../../README.md)
- [Minimal Multi-Agent Playground](../minimal_multi_agent/README.md) (sequential version)
- [Minimal Playground](../minimal/README.md)
- [Configuration Examples](../../configs/)
