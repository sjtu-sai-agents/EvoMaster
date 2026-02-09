# EvoMaster
<p align="center">
  【<a href="./README.md">English</a> | <a href="./README-zh.md">简体中文</a>】
</p>

<div align="center">

**构建通向自主演进科研（Autonomous Scientific Research）的通用智能体基座**

*让科学智能体开发更简单、模块化且功能强大，加速“AI for Science”的变革进程。*

[项目介绍](#introduction) • [核心特性](#key-features) • [SciMaster 生态](#scimaster-series) • [路线图](#roadmap)

</div>

---

## 📢代码即将发布

> **注意：** EvoMaster 的源代码正处于发布前的筹备阶段。为了确保最佳的开发体验，我们正在对文档进行最后完善，并对代码逻辑进行优化。请关注我们的 [路线图](#roadmap) 以获取发布时间表。

---

## <a id="introduction"></a>📖 项目介绍

**EvoMaster** 是一个轻量级但功能强大的框架，专为研究人员和开发者设计，旨在助力大家快速构建属于自己的科学智能体（Scientific Agents）。

尽管大型语言模型（LLMs）已展现出惊人的推理能力，但将其应用于复杂的科学领域往往需要繁琐的工程化工作——包括管理工具调用、技能组合、记忆存储以及多智能体协同等。EvoMaster 正是为了弥合这一差距而生。它提供了一套高度兼容且可扩展的基础设施，通过封装底层的复杂性，让你能专注于解决核心的科学问题。

无论你是想构建一个用于规划合成路径的化学家智能体，还是一个用于分析蛋白质结构的生物学家智能体，EvoMaster 都能作为下一代科学发现的基础设施，为你提供坚实支撑。

## <a id="key-features"></a>✨ 核心特性

### 1. ♾️ 通用兼容性

EvoMaster 旨在与其他技术实现无缝协作。它支持并适配当前智能体领域的主流技术栈。

* **多智能体协作 (Multi-Agent Collaboration)：** 快速管理多个智能体之间的交互与协作。
* **工具与技能 (Tool Usage & Skills)：** 原生支持[MCP](https://www.anthropic.com/news/model-context-protocol)工具调用及动态 [技能（Skills）](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) 加载。

### 2. ⚡ 极速开发

代码复杂度不应成为创新的阻碍。EvoMaster 的设计理念是便携与易用。

* **极简样例代码：** 仅需 **约 100 行代码** 即可启动一个自定义智能体。
* **模块化设计：** 即插即用的组件设计，让你无需重写核心逻辑即可快速进行定制化开发。

### 3. 🔬 SciMaster 生态系统

无需从零开始。EvoMaster 让你能够直接访问最先进的科学智能体，并将其架构应用到新的领域中。

* **开箱即用：** 快速部署 **[SciMaster](https://scimaster.bohrium.com/chat/)** 系列中的成熟智能体。
* **领域迁移：** 轻松将成功的SciMaster系列智能体迁移至生物学、材料科学等其他科学领域。

---

## <a id="scimaster-series"></a>🌌 SciMaster 生态

EvoMaster 是前沿科学智能体 **SciMaster** 背后的驱动引擎。代码发布后，你将能够运行并修改这些业界知名的研究型智能体：

| 智能体名称 | 领域 / 专长 | 论文 / 链接 |
| --- | --- | --- |
| **ML-Master 2.0** | 自主机器学习 (Autonomous Machine Learning) | [ArXiv:2601.10402](https://arxiv.org/abs/2601.10402) |
| **ML-Master** | 自主机器学习 (Autonomous Machine Learning) | [ArXiv:2506.16499](https://arxiv.org/abs/2506.16499) |
| **X-Master** | 通用科学智能体 (General Scientific Agent) | [ArXiv:2507.05241](https://arxiv.org/abs/2507.05241) |
| **PhysMaster** | 物理研究与推理 (Physics Research & Reasoning) | [ArXiv:2512.19799](https://arxiv.org/abs/2512.19799) |

(更多 SciMaster 系列智能体敬请期待...)

---

## <a id="roadmap"></a>🗺️ 路线图

我们将分阶段开源 EvoMaster 及其生态系统，以确保代码质量和稳定性。

[ ] **第一阶段：核心框架 (预计时间：2026年2月底)**

* 发布 `EvoMaster` 基础框架代码。
* 提供基础文档及简易智能体示例。

[ ] **第二阶段：智能体矩阵 (预计时间：2026年3月底)**

* 基于 EvoMaster 开源 **SciMaster 系列**（ML-Master 2.0, PhysMaster 等）的实现代码。

[ ] **第三阶段：Bohrium 工具库 (未来规划)**

* 集成 **[Bohrium Tool Library](https://www.bohrium.com/)**。
* 原生支持便捷访问托管在 Bohrium 平台上的 **30,000+** 个科学工具和 API。



## 🏗️ 项目架构

```
EvoMaster/
├── evomaster/              # 核心库
│   ├── agent/              # Agent 组件（Agent, Session, Tools）
│   ├── core/               # 工作流（Exp, Playground）
│   ├── env/                # 环境（Docker, Local）
│   ├── skills/             # 技能系统（Knowledge, Operator）
│   └── utils/              # 工具（LLM, Types）
├── playground/             # Playground 实现
│   ├── minimal/            # 基础单智能体
│   ├── minimal_kaggle/     # Kaggle 自动化
│   ├── minimal_multi_agent/# Planning + Coding 多智能体
│   ├── minimal_skill_task/ # RAG 工作流
│   └── x_master/           # X-Master 四阶段工作流
├── configs/                # 配置文件
└── docs/                   # 文档
```

## 📚 文档

| 文档 | 描述 |
|------|------|
| [架构概述](./docs/zh/architecture.md) | 系统架构和设计 |
| [Agent 模块](./docs/zh/agent.md) | Agent, Context, Session 接口 |
| [Core 模块](./docs/zh/core.md) | BaseExp, BasePlayground 接口 |
| [Tools 模块](./docs/zh/tools.md) | 工具系统和 MCP 集成 |
| [Skills 模块](./docs/zh/skills.md) | 技能系统接口 |
| [LLM 模块](./docs/zh/llm.md) | LLM 抽象层 |

## 🎮 Playgrounds

| Playground | 描述 | 文档 |
|------------|------|------|
| `minimal` | 基础单智能体 | [README](./playground/minimal/README_CN.md) |
| `minimal_kaggle` | Kaggle 竞赛自动化 | [README](./playground/minimal_kaggle/README_CN.md) |
| `minimal_multi_agent` | Planning + Coding 多智能体 | [README](./playground/minimal_multi_agent/README_CN.md) |
| `minimal_skill_task` | RAG 分析→搜索→总结工作流 | [README](./playground/minimal_skill_task/README_CN.md) |
| `x_master` | 四阶段并行工作流 | [README](./playground/x_master/README_CN.md) |

## 🚀 快速开始

### 使用您的 API Key

打开位于 `configs/[playground name]` 的配置文件并填写相应的空白处。例如，如果您想使用 Deepseek-V3.2 运行 `minimal_multi_agent`，请打开 `configs/minimal_multi_agent/deepseek-v3.2-example.yaml` 并修改如下内容：

```bash
  local_sglang:
    provider: "deepseek"
    model: "deepseek-v3.2"
    api_key: "dummy"
    base_url: "http://192.168.2.110:18889/v1"
```

如果您的模型 API 支持 OpenAI 格式，也可以使用 `openai` 配置。请记得同时修改后续 Agent 的 LLM 配置。

### 使用环境变量 (.env)

您也可以使用环境变量进行配置。这种方式更加安全和灵活：

1. **从模板创建 `.env` 文件：**
   ```bash
   cp .env.template .env
   ```

2. **编辑 `.env` 文件**并填写您的 API 密钥和配置值：
   ```bash
   # 示例：设置您的 DeepSeek API 密钥
   DEEPSEEK_API_KEY="your-api-key-here"
   DEEPSEEK_API_BASE="http://127.0.0.1:18889/v1"
   ```

3. **运行您的命令：**
   
   系统会自动从项目根目录加载 `.env` 文件，因此您可以直接运行：
   ```bash
   python run.py --agent minimal --task "你的任务描述"
   ```
   
   或者，您也可以使用 `dotenv` CLI 工具：
   ```bash
   dotenv run python run.py --agent minimal --task "你的任务描述"
   ```

### 基本使用

```bash
cd EvoMaster
python run.py --agent minimal --task "你的任务描述"
```

### 使用自定义配置

```bash
python run.py --agent minimal --config configs/minimal/config.yaml --task "你的任务描述"
```

### 从文件读取任务

```bash
python run.py --agent minimal --task task.txt
```

### 交互模式

```bash
python run.py --agent minimal --interactive
```

## 📋 示例

### 单智能体（Minimal）
```bash
python run.py --agent minimal --config configs/minimal/deepseek-v3.2-example.yaml --task "Discover a pattern: Given sequence 1, 4, 9, 16, 25... find the formula"
```

### 多智能体系统
```bash
python run.py --agent minimal_multi_agent --config configs/minimal_multi_agent/deepseek-v3.2-example.yaml --task "Write a Python program that implements the following features: Read a text file (create a sample file if it doesn't exist). Count the occurrences of each word in the file. Sort the results by frequency in descending order. Save the results to a new file named word_count.txt. Output the top 10 most common words to the terminal."
```

### X-Master 工作流
```bash
# 安装 mcp_sandbox 环境
pip install -r playground/x_master/mcp_sandbox/requirements.txt
python run.py --agent x_master --task "Which condition of Arrhenius's sixth impossibility theorem do critical-level views violate?\n\nAnswer Choices:\nA. Egalitarian Dominance\nB. General Non-Extreme Priority\nC. Non-Elitism\nD. Weak Non-Sadism\nE. Weak Quality Addition"
```

### Kaggle 自动化
```bash
pip install -r playground/minimal_kaggle/requirements.txt
python run.py --agent minimal_kaggle --config configs/minimal_kaggle/deepseek-v3.2-example.yaml --task playground/minimal_kaggle/data/public/description.md
```

## 📦 安装

### 使用 pip

```bash
# 克隆仓库
git clone https://github.com/sjtu-sai-agents/EvoMaster.git
cd EvoMaster

# 安装依赖
pip install -r requirements.txt

# 在 configs/ 中配置 LLM API 密钥
```

### 使用 uv

[uv](https://docs.astral.sh/uv/) 是一个快速的 Python 包安装器。可以使用以下任一方式：

```bash
# 选项 1：从 pyproject.toml + uv.lock 同步（推荐）
uv sync

# 选项 2：从 requirements.txt 安装
uv pip install -r requirements.txt
```

创建虚拟环境并使用 uv 运行：`uv venv && source .venv/Scripts/activate`（Windows）或 `source .venv/bin/activate`（Linux/macOS），然后运行 `uv sync`。
## 🤝 引用

如果你在研究中使用了 EvoMaster 或 SciMaster 系列智能体，欢迎给我们一个 Star 和引用（BibTeX 将在论文正式发布后更新）。

## 📬 联系方式

* **SciMaster 平台:** [https://scimaster.bohrium.com/chat/](https://scimaster.bohrium.com/chat/)
* **Bohrium 平台:** [https://www.bohrium.com/](https://www.bohrium.com/)