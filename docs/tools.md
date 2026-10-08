# Tools Module

The Tools module provides the tool system for Agent, including builtin tools and MCP integration.

## Overview

```
evomaster/agent/tools/
├── base.py           # BaseTool, ToolRegistry
├── builtin/          # Builtin tools
│   ├── bash.py       # BashTool
│   ├── editor.py     # EditorTool
│   ├── think.py      # ThinkTool
│   └── finish.py     # FinishTool
├── skill.py          # SkillTool
└── mcp/              # MCP integration
    ├── mcp.py            # MCPTool
    ├── mcp_connection.py # Connection handling
    └── mcp_manager.py    # MCPToolManager
```

## BaseTool

Abstract base class for all tools.

### Class Definition

```python
class BaseTool(ABC):
    """Tool base class

    Each tool needs:
    1. Define params class (inherit BaseToolParams)
    2. Implement execute method
    """

    # Tool name
    name: ClassVar[str]

    # Params class
    params_class: ClassVar[type[BaseToolParams]]
```

### Methods

```python
@abstractmethod
def execute(self, session: BaseSession, args_json: str) -> tuple[str, dict[str, Any]]:
    """Execute tool

    Args:
        session: Environment session
        args_json: JSON string of parameters

    Returns:
        (observation, info) tuple
        - observation: Result returned to Agent
        - info: Additional information
    """

def parse_params(self, args_json: str) -> BaseToolParams:
    """Parse parameters from JSON string"""

def get_tool_spec(self) -> ToolSpec:
    """Get tool specification for LLM function calling"""
```

## BaseToolParams

Base class for tool parameters.

```python
class BaseToolParams(BaseModel):
    """Tool params base class

    Subclasses should define:
    - name: ClassVar[str] - Tool name (exposed to LLM)
    - __doc__: Tool description (as function description)
    """

    name: ClassVar[str]
```

## ToolRegistry

Tool registry for managing all available tools.

```python
class ToolRegistry:
    """Tool registry center"""

    def register(self, tool: BaseTool) -> None:
        """Register a tool"""

    def register_many(self, tools: list[BaseTool]) -> None:
        """Batch register tools"""

    def unregister(self, name: str) -> None:
        """Unregister a tool"""

    def get_tool(self, name: str) -> BaseTool | None:
        """Get tool by name"""

    def get_all_tools(self) -> list[BaseTool]:
        """Get all registered tools"""

    def get_tool_names(self) -> list[str]:
        """Get all tool names"""

    def get_tool_specs(self) -> list[ToolSpec]:
        """Get all tool specs for LLM"""

    # MCP-related methods
    def get_mcp_tools(self) -> list[BaseTool]:
        """Get all MCP tools"""

    def get_builtin_tools(self) -> list[BaseTool]:
        """Get all builtin tools (non-MCP)"""

    def get_tools_by_server(self, server_name: str) -> list[BaseTool]:
        """Get tools from a specific MCP server"""

    def get_mcp_server_names(self) -> list[str]:
        """Get all MCP server names"""
```

### Factory Functions

```python
def create_registry(
    builtin_names: list[str] | None = None,
    skill_registry: SkillRegistry | None = None,
    openclaw_bridge: object | None = None,
    enabled_skills: list[str] | None = None,
) -> ToolRegistry:
    """Create tool registry with selective builtin tool registration

    Args:
        builtin_names: List of builtin tool names to register.
            - None or ["*"] -> register all builtin tools
            - [] -> register no builtins (skills/MCP only)
            - ["execute_bash", "finish"] -> register only specified tools
        skill_registry: Optional SkillRegistry, if provided registers SkillTool
        openclaw_bridge: Optional OpenclawBridge instance, passed to SkillTool
        enabled_skills: Optional list of skill names to expose to agent
    """

def create_default_registry(skill_registry: SkillRegistry | None = None) -> ToolRegistry:
    """Create default tool registry with all builtin tools

    Convenience wrapper around create_registry(builtin_names=["*"], ...).

    Args:
        skill_registry: Optional SkillRegistry, if provided registers SkillTool
    """
```

## Builtin Tools

### BashTool

Execute bash commands.

```python
class BashToolParams(BaseToolParams):
    """Execute a bash command in the environment.

    Example:
        {"command": "ls -la"}
        {"command": "python script.py", "timeout": 60}
    """
    name: ClassVar[str] = "execute_bash"
    command: str = Field(description="The bash command to execute")
    timeout: int | None = Field(default=None, description="Timeout in seconds")
```

### EditorTool

View, create, and edit files.

```python
class EditorToolParams(BaseToolParams):
    """View, create, and edit files using str_replace_editor.

    Commands:
    - view: View file contents with line numbers
    - create: Create a new file
    - str_replace: Replace text in file (old_str must be unique)
    - insert: Insert text after a line
    - undo_edit: Undo last edit
    """
    name: ClassVar[str] = "str_replace_editor"
    command: Literal["view", "create", "str_replace", "insert", "undo_edit"]
    path: str = Field(description="File path")
    # Optional fields for different commands...
```

### ThinkTool

Think about the problem (does not affect environment).

```python
class ThinkToolParams(BaseToolParams):
    """Think about the problem. Does not affect the environment."""
    name: ClassVar[str] = "think"
    thought: str = Field(description="Your thought about the current problem")
```

### FinishTool

Signal task completion.

```python
class FinishToolParams(BaseToolParams):
    """Signal that you have completed the task."""
    name: ClassVar[str] = "finish"
    result: str = Field(description="Final result or answer")
    success: bool = Field(default=True, description="Whether task completed successfully")
```

## SkillTool

Tool for interacting with the Skill system.

```python
class SkillToolParams(BaseToolParams):
    """Use skills to get information or execute operations.

    Actions:
    - get_info: Get detailed info about a skill
    - get_reference: Get reference documentation
    - run_script: Run a script from Operator skill
    """
    name: ClassVar[str] = "use_skill"
    action: Literal["get_info", "get_reference", "run_script"]
    skill_name: str = Field(description="Skill name")
    reference_name: str | None = Field(default=None, description="Reference name for get_reference")
    script_name: str | None = Field(default=None, description="Script name for run_script")
    script_args: str | None = Field(default=None, description="Script arguments")
```

## MCP Integration

### MCPTool

Wrapper for MCP server tools.

```python
class MCPTool(BaseTool):
    """MCP tool wrapper

    Wraps remote MCP tools as local tools.
    Tool names are prefixed with server name: {server}_{tool_name}
    """

    def __init__(
        self,
        mcp_connection: MCPConnection,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        remote_tool_name: str | None = None,
    ):
        """Initialize MCP tool

        Args:
            mcp_connection: MCP connection instance
            tool_name: Prefixed tool name (e.g., "github_create_issue")
            tool_description: Tool description
            input_schema: Tool input schema
            remote_tool_name: Original tool name on MCP server
        """

    # Attributes
    _is_mcp_tool: bool = True
    _mcp_server: str | None = None
    _mcp_loop: asyncio.AbstractEventLoop | None = None
```

### MCPToolManager

Manager for MCP server connections and tools.

```python
class MCPToolManager:
    """MCP tool manager

    Manages MCP server connections and tool registration.
    Uses hybrid approach:
    - External: Register to unified ToolRegistry
    - Internal: Independently manage MCP connections and tools

    Responsibilities:
    1. Manage MCP server connections
    2. Create MCPTool instances
    3. Organize tools by server
    4. Register to ToolRegistry
    5. Lifecycle management (add/remove servers)
    """

    async def add_server(self, name: str, transport: str, **connection_kwargs) -> None:
        """Add MCP server

        Args:
            name: Server name
            transport: Transport type ("stdio", "http", "sse")
            **connection_kwargs: Connection arguments
        """

    def register_tools(self, tool_registry: ToolRegistry) -> None:
        """Register all MCP tools to ToolRegistry"""

    async def remove_server(self, server_name: str) -> None:
        """Remove MCP server and its tools"""

    async def reload_server(self, server_name: str) -> None:
        """Reload MCP server tools (hot reload)"""

    async def cleanup(self) -> None:
        """Clean up all MCP connections"""

    def get_tool_names(self) -> list[str]:
        """Get all MCP tool names"""

    def get_server_names(self) -> list[str]:
        """Get all MCP server names"""

    def get_tools_by_server(self, server_name: str) -> list[MCPTool]:
        """Get tools from specific server"""

    def get_stats(self) -> dict[str, Any]:
        """Get statistics"""
```

### MCP Configuration

For an optional remote search server and a runnable search/fetch example, see
[Parallel Search MCP](./parallel_search.md).

#### mcp_config.json

```json
{
  "mcpServers": {
    "sandbox": {
      "transport": "sse",
      "url": "http://localhost:8001/sse"
    },
    "search": {
      "command": "python",
      "args": ["mcp_servers/search_server.py"],
      "env": {
        "API_KEY": "your-key"
      }
    },
    "github": {
      "transport": "http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer token"
      }
    }
  }
}
```

## Usage Examples

### Creating Custom Tool

```python
from evomaster.agent.tools import BaseTool, BaseToolParams
from pydantic import Field
from typing import ClassVar, Any

class MyToolParams(BaseToolParams):
    """My custom tool description.

    Does something useful.
    """
    name: ClassVar[str] = "my_tool"
    input_data: str = Field(description="Input data to process")
    option: bool = Field(default=False, description="Optional flag")

class MyTool(BaseTool):
    name: ClassVar[str] = "my_tool"
    params_class: ClassVar[type[BaseToolParams]] = MyToolParams

    def execute(self, session, args_json: str) -> tuple[str, dict[str, Any]]:
        params = self.parse_params(args_json)

        # Execute logic
        result = f"Processed: {params.input_data}"

        return result, {"status": "success"}

# Register tool
registry = create_registry()
registry.register(MyTool())
```

You can also create a registry with only specific builtin tools:

```python
# Only register bash and finish tools, plus custom tool
registry = create_registry(builtin_names=["execute_bash", "finish"])
registry.register(MyTool())
```

### Using MCP Tools

```python
from evomaster.agent.tools import MCPToolManager

# Create manager
manager = MCPToolManager()

# Add server
await manager.add_server(
    name="github",
    transport="stdio",
    command="python",
    args=["mcp_servers/github_server.py"]
)

# Register to ToolRegistry
registry = create_registry()
manager.register_tools(registry)

# Now all MCP tools are available as github_* tools
print(registry.get_tool_names())
# ['execute_bash', 'str_replace_editor', 'think', 'finish', 'github_create_issue', ...]
```

## Related Documentation

- [Architecture Overview](./architecture.md)
- [Agent Module](./agent.md)
- [Skills Module](./skills.md)
