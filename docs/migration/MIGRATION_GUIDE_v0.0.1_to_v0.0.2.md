# EvoMaster v0.0.2 版本更新说明及快速迁移指南


---

## 一、架构级变更

### 1. 配置系统重构：从全局单 LLM 到 per-agent 配置

旧架构中 `agent`（单数）只能关联一套全局 LLM；新版改为 `agents`（复数），每个 agent 独立声明自己的 LLM、Tools、Skills。

| 维度 | v0.0.1 (旧) | v0.0.2 (新) |
|------|-----------|---------------------|
| 配置字段 | `agent: {...}` | `agents: { name: {...} }` |
| LLM 绑定 | 全局 `llm.default` | 每个 agent 可指定 `llm: "openai"` |
| 工具启用 | `enable_tools: true/false` | `tools: { builtin: [...], mcp: "..." }` |
| Skills | 全局 `skills.enabled` | 每个 agent 可指定 `skills: ["rag"]` 或 `"*"` |

核心文件变更：
- `evomaster/config.py`：新增 `ToolConfig`、移除 `SkillConfig/KnowledgeSkillConfig/OperatorSkillConfig`；新增 `get_agent_config(name)`、`get_agents_config()`、`get_agent_llm_config(name)`、`get_agent_tools_config(name)`、`get_agent_skills_config(name)` 等 per-agent 配置读取方法。
- `EvoMasterConfig.agent` → `EvoMasterConfig.agents`（字段改名）
- `EvoMasterConfig.skill` → `EvoMasterConfig.tools`（ToolConfig 替代 SkillConfig）

### 2. Playground 基类重构：多 Agent 槽位系统

- 新增 `AgentSlots` 容器类，支持 `dict` 访问与属性访问（`self.agents.planning_agent`）。
- `self.agent`（单个）→ `self.agents`（AgentSlots），向后兼容：`self.agent = self.agents.get_random_agent()`。
- 基类 `setup()` 流程简化为：`_setup_session()` → `_setup_agents()` → `（_setup_exps()）`。
- 新增 `_setup_agents()` 方法：自动遍历 `agents` 配置，为每个 agent 创建实例并注册到 `self.agents`。
- 新增 `copy_agent()` 方法：深拷贝 Agent（独立 LLM + 独立上下文，共享 session/tools），支持并行实验。

### 3. 工具注册系统重构：支持按名称筛选

- 新增 `create_registry(builtin_names, skill_registry)` 函数，替代原 `create_default_registry()`。
- 支持 `builtin_names=["execute_bash", "finish"]` 精确控制注册哪些 builtin 工具。
- Agent 新增 `enabled_tool_names` 参数：控制暴露给 LLM 的工具列表，与"代码中可调用的工具"解耦。
- 所有工具始终注册到 registry（代码可手动调用），仅通过 `enabled_tool_names` 过滤 LLM 可见的工具。

### 4. Skills 统一化

- **移除** `KnowledgeSkill` 和 `OperatorSkill` 二元分类。
- **统一为** `Skill` 类（原 `OperatorSkill` 重命名）。
- `SkillMetaInfo` 移除 `skill_type` 字段。
- `SkillRegistry` 新增 `skills` 参数支持按名称过滤加载；新增 `create_subset()` 方法。

---

## 二、新增功能

### 1. 并行实验执行

- `evomaster/env/local.py`：新增 `ResourceAllocator` 类，支持按并行索引自动分配 GPU/CPU 资源。
- `LocalSession`：新增线程本地存储（`_thread_local`），支持 `set_parallel_index()`、`set_workspace_path()` 等线程安全操作。
- `LocalEnv`：新增 `setup_exp_workspace()` 方法，支持 `split_workspace_for_exp` 模式（每个实验独立工作目录）。
- `LocalSessionConfig`：新增 `parallel` 配置字段（`enabled`、`max_parallel`、`split_workspace_for_exp`）。
- `BasePlayground`：新增 `execute_parallel_tasks()` 方法（通过 `ThreadPoolExecutor` 并行执行多个 exp）。

### 2. 多模态支持（图片输入）

- `evomaster/utils/llm.py`：新增 `encode_image_to_base64()`、`get_image_media_type()`、`build_multimodal_content()` 函数。
- `evomaster/utils/types.py`：`BaseMessage.content` 类型扩展为 `str | list[dict] | None`，支持多模态内容块。
- `TaskInstance`：新增 `images: list[str]` 字段。
- `AnthropicLLM`：新增 `_convert_content_for_anthropic()` 静态方法，自动将 OpenAI 格式多模态内容转换为 Anthropic 格式。
- `ContextManager` / `SimpleTokenCounter`：适配多模态内容的 token 估算（图片 ~750 tokens）。
- `run.py`：新增 `--images` 命令行参数。


### 3. ML-Master Playground

- 新增 `playground/ml_master/`：面向机器学习竞赛（如 Kaggle）的完整工作流。
  - 三阶段 Exp：`DraftExp`（初稿）→ `DebugExp`（调试）→ `ImproveExp`（改进）。
  - UCT 搜索管理器（`core/utils/uct.py`）：基于 Monte Carlo Tree Search 的实验方案搜索。
  - 数据预览工具（`core/utils/data_preview.py`）：自动生成数据集概览。
  - 可视化模块（`vis/`）：树形结构 Web 可视化。

### 4. 多 Agent 并行 Playground 示例

- 新增 `playground/minimal_multi_agent_parallel/`：演示如何使用 `copy_agent()` + `ThreadPoolExecutor` 并行运行多个实验。

---

## 三、重要修改

### 配置文件格式变更

- `enable_tools: true/false` → `tools: { builtin: ["*"], mcp: "" }`
- 全局 `mcp:` 配置 → per-agent `tools.mcp` 配置（保留全局 `mcp:` 作为高级选项）
- `agent:` → `agents:` (配置文件中的字段名)



### X-Master Playground

- `_setup_agents()` 使用新的 `_create_agent()` 签名（`llm_config` 替代 `llm_config_dict`）。
- Exp 不再在 `setup()` 中预创建，改为运行时通过 `_create_exp()` + `copy_agent()` 动态创建。
- 支持并行执行（移除了之前的 TODO 注释）。

### 依赖变更

- 新增 `.env.template` 模板文件。

---

## 四、移除 / 弃用

| 移除项 | 说明 |
|--------|------|
| `KnowledgeSkill` 类 | 统一为 `Skill` |
| `OperatorSkill` 类 | 统一为 `Skill` |
| `SkillConfig` / `KnowledgeSkillConfig` / `OperatorSkillConfig` | 被 per-agent skills 配置取代 |
| `ConfigManager.get_skill_config()` | 不再需要 |
| `BasePlayground._setup_llm_config()` | 被 `_setup_agent_llm(name)` 取代 |
| `_create_agent()` 的 `enable_tools` 和 `llm_config_dict` 参数 | 被 `tool_config` / `llm_config` / `skill_config` 取代 |
| `enable_tools: true/false` 配置字段 | 被 `tools: { builtin: [...] }` 取代 |

---

# v0.0.1 到 v0.0.2 快速迁移指南

Evomaster v0.0.2版本进一步优化了代码和配置文件，让开发者能适配更多个性化需求和复用更多代码，同时弃用了一些接口，本指南可用于快速迁移到分支的新架构。

## 第 1 步：迁移配置文件 (config.yaml)

### 1.1 `agent` → `agents`，每个 agent 声明 LLM

**旧写法 (v0.0.1):**
```yaml
llm:
  openai:
    provider: "openai"
    model: "gpt-4"
    api_key: "${OPENAI_API_KEY}"
  default: "openai"

agents:
  planning:
    llm: "openai"
    max_turns: 10
    enable_tools: false     # <-- 旧写法
    context: ...
  coding:
    llm: "openai"
    max_turns: 50
    enable_tools: true      # <-- 旧写法
    context: ...
```

**新写法 (v0.0.2):**
```yaml
llm:
  openai:
    provider: "openai"
    model: "gpt-4"
    api_key: "${OPENAI_API_KEY}"
  default: "openai"

agents:
  planning:
    llm: "openai"           # per-agent LLM 绑定
    max_turns: 10
    tools:                   # <-- 新写法：精确控制工具
      builtin: []            # 不需要任何工具
    context: ...
  coding:
    llm: "openai"
    max_turns: 50
    tools:
      builtin: ["*"]         # 启用全部 builtin 工具
    context: ...
```

### 1.2 工具配置：`enable_tools` → `tools`

| 旧 | 新 | 说明 |
|----|-----|------|
| `enable_tools: true` | `tools: { builtin: ["*"] }`或`tools: "default"`  | 启用全部bulitin工具 |
| `enable_tools: false` | `tools: { builtin: [] }` | 禁用全部工具 |
| 无对应 | `tools: { builtin: ["execute_bash", "finish"], mcp:"mcp_config.json" }` | 仅启用指定工具和指定MCP |
| 全局 `mcp:` 配置 | `tools: { mcp: "mcp_config.json" }` | per-agent MCP |
| 不配置 `tools` 键 | 默认 `builtin: ["*"], mcp: ""` | 全部 builtin |

### 1.3 Skills 配置

| 旧 | 新 | 说明 |
|----|-----|------|
| 全局 `skills: { enabled: true, skills_root: "..." }` | per-agent `skills: ["rag"]` | 从全局开关改为每个 agent 独立声明所需 skill |
| `skills.enabled: true` + 所有 agent 共享同一 registry | 每个 agent 的 `skills:` 字段独立 | 不同 agent 可加载不同的 skill 子集 |
| 无对应 | `skills: "*"` 或 `skills: ["*"]` | 加载全部 skills（等价旧版 `enabled: true`） |
| 无对应 | `skills: ["rag", "pdf"]` | 仅加载指定名称的 skills |
| 无对应 | 不配置 `skills` 键 / `skills:` (空值) | 该 agent 不加载任何 skill |

**旧写法:** 全局配置 + 在 Playground 中手动加载
```yaml
# config.yaml
skills:
  enabled: true
  skills_root: "./evomaster/skills"
```
```python
# playground.py 中手动加载
config_dict = self.config.model_dump()
skills_config = config_dict.get("skills", {})
skill_registry = None
if skills_config.get("enabled", False):
    skills_root = Path(skills_config.get("skills_root", "evomaster/skills"))
    skill_registry = SkillRegistry(skills_root)           # 全量加载，所有 agent 共享

self._setup_tools(skill_registry)                         # 手动传给工具注册

# 每个 agent 创建时也要手动传
self._create_agent(..., skill_registry=skill_registry)
```

**新写法:** per-agent 配置，基类自动处理
```yaml
# config.yaml
agents:
  search:
    llm: "openai"
    skills:            # 该 agent 加载全部 skills
      - "*"
  summarize:
    llm: "openai"
    skills:            # 该 agent 仅加载 rag 和 pdf
      - "rag"
      - "pdf"
  plan:
    llm: "openai"
    # 不配置 skills → 不加载任何 skill
```
```python
# playground.py — 无需手动处理 skills
def setup(self):
    self._setup_session()
    self._setup_agents()   # 基类自动按 agent 配置加载各自的 skill_registry
```

## 第 2 步：迁移 Playground 代码

### 2.1 Agent 存储：从独立属性到 AgentSlots

**旧写法:**
```python
class MyPlayground(BasePlayground):
    def __init__(self, ...):
        super().__init__(...)
        self.planning_agent = None
        self.coding_agent = None
        self.mcp_manager = None

    def setup(self):
        llm_config_dict = self._setup_llm_config()
        self._setup_session()

        # 手动加载 skills
        skill_registry = None
        config_dict = self.config.model_dump()
        skills_config = config_dict.get("skills", {})
        if skills_config.get("enabled", False):
            skills_root = Path(skills_config.get("skills_root", "evomaster/skills"))
            skill_registry = SkillRegistry(skills_root)

        # 手动创建工具
        self._setup_tools(skill_registry)

        # 手动遍历 agents 配置并创建
        agents_config = getattr(self.config, 'agents', {})
        if 'planning' in agents_config:
            planning_config = agents_config['planning']
            self.planning_agent = self._create_agent(
                name="planning",
                agent_config=planning_config,
                enable_tools=planning_config.get('enable_tools', False),
                llm_config_dict=llm_config_dict,
                skill_registry=skill_registry,
            )
        if 'coding' in agents_config:
            coding_config = agents_config['coding']
            self.coding_agent = self._create_agent(
                name="coding",
                agent_config=coding_config,
                enable_tools=coding_config.get('enable_tools', True),
                llm_config_dict=llm_config_dict,
                skill_registry=skill_registry,
            )
```

**新写法:**
```python
class MyPlayground(BasePlayground):
    def __init__(self, ...):
        super().__init__(...)
        # 1. 声明 agent 槽位（IDE 补全友好）
        self.agents.declare("planning_agent", "coding_agent")
        self.mcp_manager = None

    def setup(self):
        # 2. 两行搞定！基类自动处理 LLM/Tools/Skills
        self._setup_session()
        self._setup_agents()
        # 基类自动将配置中的每个 agent 创建并注册到 self.agents
        # 命名规则: config 中的 "planning" → self.agents.planning_agent
```

### 2.2 `_create_agent()` 参数变更

**旧签名:**
```python
self._create_agent(
    name="solver",
    agent_config=solver_config,
    enable_tools=solver_config.get('enable_tools', False),
    llm_config_dict=llm_config_dict,
    skill_registry=skill_registry,
)
```

**新签名:**
```python
self._create_agent(
    name="solver",
    agent_config=solver_config,     # 可选，不传则自动从配置获取
    llm_config=llm_config,          # 可选，不传则自动从配置获取
    tool_config=tool_config,        # 可选，不传则自动从配置获取
    skill_config=skill_config,      # 可选，不传则自动从配置获取
)
```

如果使用 `_setup_agents()` 则无需手动调用 `_create_agent()`。

### 2.3 访问 Agent

**旧写法:**
```python
# 直接通过属性
self.planning_agent.run(task)
self.coding_agent.run(task)
```

**新写法:**
```python
# 通过 AgentSlots（同样支持属性访问）
self.agents.planning_agent.run(task)
self.agents.coding_agent.run(task)
```


## 第 3 步：迁移 Skills 引用

**旧写法:**
```python
from evomaster.skills import KnowledgeSkill, OperatorSkill

# 检查类型
if isinstance(skill, OperatorSkill):
    ...
elif isinstance(skill, KnowledgeSkill):
    ...
```

**新写法:**
```python
from evomaster.skills import Skill

# 统一类型，不再区分
if isinstance(skill, Skill):
    ...
```



