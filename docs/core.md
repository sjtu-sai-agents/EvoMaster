# Core Module

The Core module provides the workflow components: `BaseExp` and `BasePlayground`.

## Overview

```
evomaster/core/
├── exp.py          # BaseExp class
└── playground.py   # BasePlayground class
```

## BaseExp

`BaseExp` is the base class for single experiment execution.

### Class Definition

```python
class BaseExp:
    """Experiment base class

    Defines common execution logic for single experiments.
    Specific playgrounds can inherit and override methods.
    """
```

### Constructor

```python
def __init__(self, agent, config):
    """Initialize experiment

    Args:
        agent: Agent instance
        config: EvoMasterConfig instance
    """
```

### Properties

```python
@property
def exp_name(self) -> str:
    """Get Exp name (auto-inferred from class name)

    Example: SolverExp -> Solver, CriticExp -> Critic
    Subclasses can override this property.
    """
```

### Methods

#### set_run_dir(run_dir)
```python
def set_run_dir(self, run_dir: str | Path) -> None:
    """Set run directory

    Args:
        run_dir: Run directory path
    """
```

#### run(task_description, task_id)
```python
def run(self, task_description: str, task_id: str = "exp_001") -> dict:
    """Run a single experiment

    Args:
        task_description: Task description
        task_id: Task ID

    Returns:
        Result dictionary with:
        - trajectory: Execution trajectory
        - status: Completion status
        - steps: Number of steps taken
    """
```

#### save_results(output_file)
```python
def save_results(self, output_file: str):
    """Save experiment results

    Args:
        output_file: Output file path
    """
```

### Internal Methods

```python
def _extract_agent_response(self, trajectory: Any) -> str:
    """Extract agent's final response from trajectory

    Args:
        trajectory: Execution trajectory

    Returns:
        Agent's response text
    """
```

## BasePlayground

`BasePlayground` is the workflow orchestrator.

### Class Definition

```python
class BasePlayground:
    """Playground base class

    Defines common workflow lifecycle:
    1. Load configuration
    2. Initialize all components
    3. Create and run experiments
    4. Clean up resources

    Specific playgrounds can:
    - Inherit this class
    - Override _create_exp() for custom Exp class
    - Override setup() for additional initialization
    """
```

### Constructor

```python
def __init__(
    self,
    config_dir: str | Path | None = None,
    config_path: str | Path | None = None
):
    """Initialize Playground

    Args:
        config_dir: Config directory (default: configs/)
        config_path: Full config file path (overrides config_dir if provided)
    """
```

### Lifecycle Methods

#### set_run_dir(run_dir, task_id)
```python
def set_run_dir(self, run_dir: str | Path, task_id: str | None = None) -> None:
    """Set run directory and create structure

    Creates:
    - run_dir/config.yaml (config copy)
    - run_dir/logs/ (log files)
    - run_dir/trajectories/ (dialog trajectories)
    - run_dir/workspace/ or run_dir/workspaces/{task_id}/ (workspace)

    Args:
        run_dir: Run directory path
        task_id: Optional task ID for batch mode
    """
```

#### setup()
```python
def setup(self) -> None:
    """Initialize all components

    Supports both single-agent and multi-agent modes:
    - If config has `agents:`, create multiple agents
    - Otherwise, if config has `agent:`, create single agent

    Steps:
    1. Prepare LLM configuration
    2. Create Session (if not already created)
    3. Load Skills (if enabled)
    4. Create tool registry and init MCP tools
    5. Create Agent(s)
    """
```

#### run(task_description, output_file)
```python
def run(self, task_description: str, output_file: str | None = None) -> dict:
    """Run workflow

    Args:
        task_description: Task description
        output_file: Optional result file (auto-saved to trajectories/ if run_dir set)

    Returns:
        Run result dictionary
    """
```

#### cleanup()
```python
def cleanup(self) -> None:
    """Clean up resources

    For DockerSession with auto_remove=False, keeps container running
    for reuse in subsequent runs.
    """
```

### Component Creation Methods

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
    """Create Agent instance

    Each Agent uses independent LLM instance for isolated logging.

    Args:
        name: Agent name
        agent_config: Agent configuration dict
        enable_tools: Whether to enable tool calls
        llm_config: LLM config (fetched from config manager if None)
        skill_registry: Optional skill registry

    Returns:
        Agent instance
    """
```

#### _create_exp()
```python
def _create_exp(self):
    """Create Exp instance

    Subclasses can override for custom Exp class.
    """
```

### MCP Methods

#### _setup_mcp_tools()
```python
def _setup_mcp_tools(self) -> MCPToolManager | None:
    """Initialize MCP tools

    Reads MCP config file (JSON format), initializes connections,
    and registers tools.

    Returns:
        MCPToolManager instance, or None if config invalid
    """
```

#### _parse_mcp_servers(mcp_config)
```python
def _parse_mcp_servers(self, mcp_config: dict) -> list[dict]:
    """Parse MCP server configuration

    Supports standard MCP format and extended format.

    Args:
        mcp_config: MCP config dictionary

    Returns:
        List of server configurations
    """
```

### Internal Methods

```python
def _setup_llm_config(self) -> dict:
    """Prepare LLM configuration"""

def _setup_session(self) -> None:
    """Create and open Session (if not created)"""

def _setup_tools(self, skill_registry=None) -> None:
    """Create tool registry and init MCP tools"""

def _get_output_config(self) -> dict:
    """Get LLM output configuration"""

def _setup_logging(self) -> None:
    """Set up logging file path"""

def _update_workspace_path(self, workspace_path: Path) -> None:
    """Dynamically update workspace_path in config"""

def _setup_trajectory_file(self, output_file: str | Path | None = None) -> Path | None:
    """Set trajectory file path"""
```

## Usage Examples

### Custom Playground

```python
from evomaster.core import BasePlayground, BaseExp

class MyExp(BaseExp):
    def run(self, task_description: str, task_id: str = "exp_001") -> dict:
        # Custom experiment logic
        result = super().run(task_description, task_id)
        # Post-processing
        return result

class MyPlayground(BasePlayground):
    def _create_exp(self):
        return MyExp(self.agent, self.config)

    def setup(self):
        super().setup()
        # Additional initialization
        self.logger.info("Custom setup complete")
```

### Multi-Agent Playground

```python
class MultiAgentPlayground(BasePlayground):
    def setup(self):
        super().setup()
        # After setup(), multiple agents are created based on config

    def run(self, task_description: str, output_file: str | None = None) -> dict:
        self.setup()

        # Get all agents
        agents = self.agents  # Assuming stored during setup

        # Run agents in parallel using ThreadPoolExecutor
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

### Running a Playground

```python
from pathlib import Path

# Create playground
playground = MyPlayground(config_path=Path("configs/my_config/config.yaml"))

# Set run directory
playground.set_run_dir("runs/my_run_001")

# Run task
result = playground.run("Complete the following task...")

print(f"Status: {result['status']}")
print(f"Steps: {result['steps']}")
```

## Configuration File Format

### config.yaml

```yaml
# LLM Configuration
llm:
  openai:
    provider: "openai"
    model: "gpt-4"
    api_key: "your-api-key"
    temperature: 0.7

# Session Configuration
session:
  type: "local"  # or "docker"
  local:
    workspace_path: "./workspace"

# Single Agent Configuration
agent:
  max_turns: 50
  system_prompt_file: "prompts/system.txt"
  user_prompt_file: "prompts/user.txt"

# OR Multi-Agent Configuration
agents:
  Solver:
    llm: "openai"
    max_turns: 50
    enable_tools: true
  Critic:
    llm: "openai"
    max_turns: 30
    enable_tools: true

# MCP Configuration
mcp:
  enabled: true
  config_file: "mcp_config.json"

# Skills Configuration
skills:
  enabled: true
  skills_root: "evomaster/skills"

# Logging Configuration
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Agent Module](./agent.md)
- [Tools Module](./tools.md)
