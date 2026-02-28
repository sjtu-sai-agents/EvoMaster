# Playground

Playground is where developers build their own research agents. Each playground defines a complete experimental workflow by inheriting EvoMaster's base components (`BasePlayground`, `BaseExp`) to implement specific scientific experiment automation.

**Developers should create their own playground in this directory to implement their research agents.**

## Existing Examples

| Playground | Type | Description | Docs |
|---|---|---|---|
| `minimal` | Single Agent | Minimal example, only inherits `BasePlayground`, ideal for learning the framework | [README](./minimal/README.md) |
| `minimal_multi_agent` | Multi-Agent | Planning + Coding dual-agent collaboration, demonstrates multi-agent workflow | [README](./minimal_multi_agent/README.md) |
| `minimal_kaggle` | Multi-Agent | Kaggle competition automation with 6 role agents (draft/debug/improve/research/knowledge/metric) | [README](./minimal_kaggle/README.md) |
| `minimal_skill_task` | Single Agent + Skills | RAG-based Analyze → Plan → Search → Summarize workflow | [README](./minimal_skill_task/README.md) |
| `x_master` | Multi-Phase Parallel | Four-phase iterative workflow: Solve → Critique → Rewrite → Select, with MCP tool support | [README](./x_master/README.md) |

## Quick Start: Create Your Playground

### 1. Create Directory Structure

```bash
mkdir -p playground/my_agent/core
mkdir -p playground/my_agent/prompts
mkdir -p configs/my_agent
```

### 2. Implement Playground Class

`playground/my_agent/core/playground.py`:

```python
import logging
from pathlib import Path
from evomaster.core import BasePlayground, register_playground

@register_playground("my_agent")
class MyPlayground(BasePlayground):
    def __init__(self, config_dir=None, config_path=None):
        if config_path is None and config_dir is None:
            config_dir = Path(__file__).parent.parent.parent.parent / "configs" / "my_agent"
        super().__init__(config_dir=config_dir, config_path=config_path)
        self.logger = logging.getLogger(self.__class__.__name__)
```

This is the minimal implementation. For multi-agent or custom experiment flows, override `setup()`, `_create_exp()`, `run()` methods. See `minimal_multi_agent` and `x_master` for examples.

### 3. Write Prompts

`playground/my_agent/prompts/system_prompt.txt`:

```
You are a research agent. Analyze, experiment, and summarize based on the task description.
```

`playground/my_agent/prompts/user_prompt.txt`:

```
Task ID: {task_id}
Description: {description}
{input_data}
```

### 4. Configuration

`configs/my_agent/config.yaml`:

```yaml
llm:
  openai:
    provider: "openai"
    model: "gpt-4"
    api_key: "your-api-key"
    temperature: 0.7
  default: "openai"

agent:
  llm: "openai"
  max_turns: 50
  enable_tools: true
  system_prompt_file: "prompts/system_prompt.txt"
  user_prompt_file: "prompts/user_prompt.txt"
  context:
    max_tokens: 128000
    truncation_strategy: "latest_half"

session:
  type: "local"
  local:
    working_dir: "./workspace"

logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

### 5. Run

```bash
python run.py --agent my_agent --task "your task description"
```

## Development Guide

### Three-Layer Architecture

```
Playground  →  Workflow orchestration, component initialization, lifecycle management
    │
   Exp       →  Single experiment execution logic
    │
  Agent      →  LLM + tool calling + context management
```

### Common Extension Patterns

**Custom Experiment Flow** — Inherit `BaseExp`, override `run()`:

```python
from evomaster.core.exp import BaseExp

class MyExp(BaseExp):
    def run(self, task_description, task_id="exp_001"):
        # Custom execution logic
        ...
```

**Multi-Agent** — Override `setup()` to create multiple agents, override `_create_exp()` to use custom Exp:

```python
def setup(self):
    llm_config = self._setup_llm_config()
    self._setup_session()
    self._setup_tools()
    agents_config = getattr(self.config, 'agents', {})
    self.agent_a = self._create_agent("a", agents_config['a'], llm_config=llm_config)
    self.agent_b = self._create_agent("b", agents_config['b'], llm_config=llm_config)
```

**MCP Tool Integration** — Enable in config:

```yaml
mcp:
  enabled: true
  config_file: "mcp_config.json"
```

**Docker Environment** — Switch session type:

```yaml
session:
  type: "docker"
  docker:
    image: "evomaster/base:latest"
    working_dir: "/workspace"
```

### Key Principles

- Reuse `BasePlayground`'s `_setup_*` and `_create_agent()` methods whenever possible
- Each Agent uses an independent LLM instance, sharing Session and Tools
- Use relative paths for prompt files (relative to playground directory)
- Use `try-finally` in `run()` to ensure `cleanup()` is called

For more details, see the [development documentation](../docs/architecture.md).
