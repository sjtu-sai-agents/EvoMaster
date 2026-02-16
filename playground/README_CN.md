# Playground

Playground 是开发者构建自己科研智能体的工作区。每个 playground 定义了一个完整的实验工作流，通过继承 EvoMaster 的基础组件（`BasePlayground`、`BaseExp`）来实现特定的科学实验自动化。

**开发者应该在此目录下创建自己的 playground，实现自己的科研智能体。**

## 现有示例

| Playground | 类型 | 说明 | 文档 |
|---|---|---|---|
| `minimal` | 单智能体 | 最简示例，仅继承 `BasePlayground`，适合快速了解框架 | [README](./minimal/README.md) |
| `minimal_multi_agent` | 多智能体 | Planning + Coding 双智能体协作，演示多 Agent 工作流 | [README](./minimal_multi_agent/README.md) |
| `minimal_kaggle` | 多智能体 | Kaggle 竞赛自动化，含 6 个角色 Agent（draft/debug/improve/research/knowledge/metric） | [README](./minimal_kaggle/README.md) |
| `minimal_skill_task` | 单智能体 + Skills | 基于 RAG 技能的 Analyze → Plan → Search → Summarize 工作流 | [README](./minimal_skill_task/README.md) |
| `x_master` | 多阶段并行 | 四阶段迭代工作流 Solve → Critique → Rewrite → Select，支持 MCP 工具 | [README](./x_master/README.md) |

## 快速开始：创建你的 Playground

### 1. 创建目录结构

```bash
mkdir -p playground/my_agent/core
mkdir -p playground/my_agent/prompts
mkdir -p configs/my_agent
```

### 2. 实现 Playground 类

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

这是最小实现。如果需要多智能体或自定义实验流程，可以覆盖 `setup()`、`_create_exp()`、`run()` 等方法，参考 `minimal_multi_agent` 和 `x_master`。

### 3. 编写提示词

`playground/my_agent/prompts/system_prompt.txt`:

```
你是一个科研智能体。请根据任务描述进行分析、实验和总结。
```

`playground/my_agent/prompts/user_prompt.txt`:

```
任务 ID：{task_id}
描述：{description}
{input_data}
```

### 4. 配置

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

### 5. 运行

```bash
python run.py --agent my_agent --task "你的任务描述"
```

## 开发指南

### 三层架构

```
Playground  →  工作流编排、组件初始化、生命周期管理
    │
   Exp       →  单次实验执行逻辑
    │
  Agent      →  LLM + 工具调用 + 上下文管理
```

### 常用扩展模式

**自定义实验流程** — 继承 `BaseExp`，覆盖 `run()`:

```python
from evomaster.core.exp import BaseExp

class MyExp(BaseExp):
    def run(self, task_description, task_id="exp_001"):
        # 自定义执行逻辑
        ...
```

**多智能体** — 覆盖 `setup()` 创建多个 Agent，覆盖 `_create_exp()` 使用自定义 Exp:

```python
def setup(self):
    llm_config = self._setup_llm_config()
    self._setup_session()
    self._setup_tools()
    agents_config = getattr(self.config, 'agents', {})
    self.agent_a = self._create_agent("a", agents_config['a'], llm_config=llm_config)
    self.agent_b = self._create_agent("b", agents_config['b'], llm_config=llm_config)
```

**MCP 工具集成** — 在配置中启用:

```yaml
mcp:
  enabled: true
  config_file: "mcp_config.json"
```

**Docker 环境** — 切换 Session 类型:

```yaml
session:
  type: "docker"
  docker:
    image: "evomaster/base:latest"
    working_dir: "/workspace"
```

### 关键原则

- 尽量复用 `BasePlayground` 的 `_setup_*` 和 `_create_agent()` 方法
- 每个 Agent 使用独立 LLM 实例，共享 Session 和 Tools
- 提示词文件使用相对路径（相对于 playground 目录）
- `run()` 中使用 `try-finally` 确保 `cleanup()` 被调用

更多细节请参考 [开发文档](../docs/zh/architecture.md)。
