# Core 模块

Core 模块提供工作流组件：`BaseExp` 和 `BasePlayground`。

## 概述

```
evomaster/core/
├── exp.py          # BaseExp 类
└── playground.py   # BasePlayground 类
```

## BaseExp

`BaseExp` 是单次实验执行的基类。

### 类定义

```python
class BaseExp:
    """实验基类

    定义单次实验的通用执行逻辑。
    具体 playground 可以继承并覆盖相关方法。
    """
```

### 构造函数

```python
def __init__(self, agent, config):
    """初始化实验

    Args:
        agent: Agent 实例
        config: EvoMasterConfig 实例
    """
```

### 属性

```python
@property
def exp_name(self) -> str:
    """获取 Exp 名称（自动从类名推断）

    例如: SolverExp -> Solver, CriticExp -> Critic
    子类可以覆盖此属性。
    """
```

### 方法

#### set_run_dir(run_dir)
```python
def set_run_dir(self, run_dir: str | Path) -> None:
    """设置 run 目录

    Args:
        run_dir: Run 目录路径
    """
```

#### run(task_description, task_id)
```python
def run(self, task_description: str, task_id: str = "exp_001") -> dict:
    """运行一次实验

    Args:
        task_description: 任务描述
        task_id: 任务 ID

    Returns:
        结果字典，包含：
        - trajectory: 执行轨迹
        - status: 完成状态
        - steps: 执行步数
    """
```

#### save_results(output_file)
```python
def save_results(self, output_file: str):
    """保存实验结果

    Args:
        output_file: 输出文件路径
    """
```

### 内部方法

```python
def _extract_agent_response(self, trajectory: Any) -> str:
    """从轨迹中提取 Agent 的最终回答

    Args:
        trajectory: 执行轨迹

    Returns:
        Agent 的回答文本
    """
```

## BasePlayground

`BasePlayground` 是工作流编排器。

### 类定义

```python
class BasePlayground:
    """Playground 基类

    定义工作流的通用生命周期管理：
    1. 加载配置
    2. 初始化所有组件
    3. 创建并运行实验
    4. 清理资源

    具体 playground 可以：
    - 继承此类
    - 覆盖 _create_exp() 以使用自定义 Exp 类
    - 覆盖 setup() 以添加额外初始化逻辑
    """
```

### 构造函数

```python
def __init__(
    self,
    config_dir: str | Path | None = None,
    config_path: str | Path | None = None
):
    """初始化 Playground

    Args:
        config_dir: 配置目录（默认为 configs/）
        config_path: 配置文件完整路径（如果提供，会覆盖 config_dir）
    """
```

### 生命周期方法

#### set_run_dir(run_dir, task_id)
```python
def set_run_dir(self, run_dir: str | Path, task_id: str | None = None) -> None:
    """设置 run 目录并创建目录结构

    创建以下目录结构：
    - run_dir/config.yaml（配置文件副本）
    - run_dir/logs/（日志文件）
    - run_dir/trajectories/（对话轨迹）
    - run_dir/workspace/ 或 run_dir/workspaces/{task_id}/（工作空间）

    Args:
        run_dir: Run 目录路径
        task_id: 可选的任务 ID，用于批量任务场景
    """
```

#### setup()
```python
def setup(self) -> None:
    """初始化所有组件

    支持单 agent 和多 agent 两种模式：
    - 如果配置中有 `agents:`，则创建多个 agent
    - 否则，如果配置中有 `agent:`，则创建单个 agent

    步骤：
    1. 准备 LLM 配置
    2. 创建 Session（如果尚未创建）
    3. 加载 Skills（如果启用）
    4. 创建工具注册表并初始化 MCP 工具
    5. 创建 Agent(s)
    """
```

#### run(task_description, output_file)
```python
def run(self, task_description: str, output_file: str | None = None) -> dict:
    """运行工作流

    Args:
        task_description: 任务描述
        output_file: 可选的结果文件（如果设置了 run_dir 则自动保存到 trajectories/）

    Returns:
        运行结果字典
    """
```

#### cleanup()
```python
def cleanup(self) -> None:
    """清理资源

    对于 DockerSession，如果 auto_remove=False，则保留容器不关闭 session，
    以便在后续运行中复用同一个容器。
    """
```

### 组件创建方法

#### _create_agent(name, agent_config, enable_tools, llm_config, skill_registry)
```python
def _create_agent(
    self,
    name: str,
    agent_config: dict,
    enable_tools: bool = True,
    llm_config: dict | None = None,
    skill_registry: SkillRegistry | None = None,
) -> Agent:
    """创建 Agent 实例

    每个 Agent 使用独立的 LLM 实例，确保日志记录独立。

    Args:
        name: Agent 名称
        agent_config: Agent 配置字典
        enable_tools: 是否启用工具调用
        llm_config: LLM 配置（如果为 None，则从配置管理器获取）
        skill_registry: 可选的技能注册表

    Returns:
        Agent 实例
    """
```

#### _create_exp()
```python
def _create_exp(self):
    """创建 Exp 实例

    子类可以覆盖此方法使用自定义 Exp 类。
    """
```

### MCP 方法

#### _setup_mcp_tools()
```python
def _setup_mcp_tools(self) -> MCPToolManager | None:
    """初始化 MCP 工具

    从 MCP 配置文件（JSON 格式）读取服务器列表，初始化连接并注册工具。

    Returns:
        MCPToolManager 实例，如果配置无效则返回 None
    """
```

#### _parse_mcp_servers(mcp_config)
```python
def _parse_mcp_servers(self, mcp_config: dict) -> list[dict]:
    """解析 MCP 服务器配置

    支持标准 MCP 格式和扩展格式。

    Args:
        mcp_config: MCP 配置字典

    Returns:
        服务器配置列表
    """
```

### 内部方法

```python
def _setup_llm_config(self) -> dict:
    """准备 LLM 配置"""

def _setup_session(self) -> None:
    """创建并打开 Session（如果尚未创建）"""

def _setup_tools(self, skill_registry=None) -> None:
    """创建工具注册表并初始化 MCP 工具"""

def _get_output_config(self) -> dict:
    """获取 LLM 输出配置"""

def _setup_logging(self) -> None:
    """设置日志文件路径"""

def _update_workspace_path(self, workspace_path: Path) -> None:
    """动态更新配置中的 workspace_path"""

def _setup_trajectory_file(self, output_file: str | Path | None = None) -> Path | None:
    """设置轨迹文件路径"""
```

## 使用示例

### 自定义 Playground

```python
from evomaster.core import BasePlayground, BaseExp

class MyExp(BaseExp):
    def run(self, task_description: str, task_id: str = "exp_001") -> dict:
        # 自定义实验逻辑
        result = super().run(task_description, task_id)
        # 后处理
        return result

class MyPlayground(BasePlayground):
    def _create_exp(self):
        return MyExp(self.agent, self.config)

    def setup(self):
        super().setup()
        # 额外初始化
        self.logger.info("Custom setup complete")
```

### 多 Agent Playground

```python
class MultiAgentPlayground(BasePlayground):
    def setup(self):
        super().setup()
        # setup() 后会根据配置创建多个 agent

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        self.setup()

        # 获取所有 agents
        agents = self.agents  # 假设在 setup 中存储

        # 使用 ThreadPoolExecutor 并行运行 agents
        from concurrent.futures import ThreadPoolExecutor

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(self._run_single_agent, agent, task_description)
                for agent in agents
            ]
            results = [f.result() for f in futures]

        self.cleanup()
        return {"results": results}
```

### 运行 Playground

```python
from pathlib import Path

# 创建 playground
playground = MyPlayground(config_path=Path("configs/my_config/config.yaml"))

# 设置 run 目录
playground.set_run_dir("runs/my_run_001")

# 运行任务
result = playground.run("完成以下任务...")

print(f"状态: {result['status']}")
print(f"步数: {result['steps']}")
```

## 配置文件格式

### config.yaml

```yaml
# LLM 配置
llm:
  openai:
    provider: "openai"
    model: "gpt-4"
    api_key: "your-api-key"
    temperature: 0.7

# Session 配置
session:
  type: "local"  # 或 "docker"
  local:
    workspace_path: "./workspace"

# 单 Agent 配置
agent:
  max_turns: 50
  system_prompt_file: "prompts/system.txt"
  user_prompt_file: "prompts/user.txt"

# 或 多 Agent 配置
agents:
  Solver:
    llm: "openai"
    max_turns: 50
    enable_tools: true
  Critic:
    llm: "openai"
    max_turns: 30
    enable_tools: true

# MCP 配置
mcp:
  enabled: true
  config_file: "mcp_config.json"

# Skills 配置
skills:
  enabled: true
  skills_root: "evomaster/skills"

# 日志配置
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## 相关文档

- [架构概述](./architecture.md)
- [Agent 模块](./agent.md)
- [Tools 模块](./tools.md)
