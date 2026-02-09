
# EvoMaster


<p align="center">
  【<a href="./README.md">English</a> | <a href="./README-zh.md">简体中文</a>】
</p>

<div align="center">

**The Universal Infrastructure for Building Evolving Autonomous Scientific Research Agents.**

*Accelerating the "AI for Science" revolution by making intelligent agent development accessible, modular, and powerful.*

[Introduction](#introduction) • [Key Features](#key-features) • [SciMaster Series](#scimaster-series) • [Roadmap](#roadmap)

</div>

---

## 📢Code Coming Soon

> **Note:** The source code for EvoMaster is currently in preparation for release. We are finalizing the documentation and polishing the core logic to ensure the best developer experience. Please check our [Roadmap](#roadmap) for the release timeline.

---

## <a id="introduction"></a>📖 Introduction

**EvoMaster** is a lightweight yet powerful framework designed to enable researchers and developers to rapidly build their own scientific agents.

While Large Language Models (LLMs) have demonstrated remarkable reasoning capabilities, applying them to complex scientific domains often requires intricate engineering—managing tools, skills, memory, and multi-agent coordination. EvoMaster bridges this gap. It provides a highly compatible and extensible infrastructure that abstracts away the complexity, allowing you to focus on the scientific problem at hand.

Whether you are building a chemist agent to plan synthesis paths or a biologist agent to analyze proteins, EvoMaster serves as the foundational infrastructure for the next generation of scientific discovery.

## <a id="key-features"></a>✨ Key Features

### 1. ♾️ Universal Compatibility

EvoMaster is built to play well with others. It supports and adapts to the mainstream technologies defining the current Agent landscape.

* **Multi-Agent Collaboration:** Seamlessly manage interactions between multiple agents.
* **Tool Usage & Skills:** Native support for [MCP](https://www.anthropic.com/news/model-context-protocol) tool calling and dynamic [skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview).

### 2. ⚡ Rapid Development

Complexity shouldn't be a barrier to innovation. EvoMaster is designed for portability and ease of use.

* **Minimal Boilerplate:** Spin up a custom agent with **just ~100 lines of code**.
* **Modular Design:** Plug-and-play components allow for quick customization without rewriting core logic.

### 3. 🔬 The SciMaster Ecosystem

Don't start from scratch. EvoMaster grants you immediate access to state-of-the-art scientific agents and allows you to apply their architectures to new domains.

* **Out-of-the-box Access:** Quickly deploy agents from the **[SciMaster](https://scimaster.bohrium.com/chat/)** series.
* **Domain Adaptation:** Easily retarget successful SciMaster series agents from to other scientific fields such as Biology, Material Science, etc.

---

## <a id="scimaster-series"></a>🌌 SciMaster Ecosystem

EvoMaster is the engine behind the cutting-edge **SciMaster** family of agents. Upon release, you will be able to run and modify these renowned research agents:

| Agent Name | Domain / Focus | Paper / Link |
| --- | --- | --- |
| **ML-Master 2.0** | Autonomous Machine Learning | [ArXiv:2601.10402](https://arxiv.org/abs/2601.10402) |
| **ML-Master** | Autonomous Machine Learning | [ArXiv:2506.16499](https://arxiv.org/abs/2506.16499) |
| **X-Master** | General Scientific Agent | [ArXiv:2507.05241](https://arxiv.org/abs/2507.05241) |
| **PhysMaster** | Physics Research & Reasoning | [ArXiv:2512.19799](https://arxiv.org/abs/2512.19799) |


(More SciMaster Series Agents comming soon...)

---

## <a id="roadmap"></a>🗺️ Roadmap

We are committed to open-sourcing EvoMaster and its ecosystem in stages to ensure quality and stability.

[ ] **Phase 1: The Core (Expected: End of Feb 2026)**
* Release of `EvoMaster` base framework code.
* Basic documentation and easy agent examples.


 [ ] **Phase 2: The Agents (Expected: End of Mar 2026)**
* Open source implementation of the **SciMaster Series** (ML-Master 2.0, PhysMaster, etc.) based on EvoMaster.


[ ] **Phase 3: The Bohrium Tools (Future)**
* Integration with the **[Bohrium Tool Library](https://www.bohrium.com/)**.
* Native support for easily accessing over **30,000+** scientific tools and APIs hosted on the Bohrium platform.


## 🏗️ Project Architecture

```
EvoMaster/
├── evomaster/              # Core library
│   ├── agent/              # Agent components (Agent, Session, Tools)
│   ├── core/               # Workflow (Exp, Playground)
│   ├── env/                # Environment (Docker, Local)
│   ├── skills/             # Skill system (Knowledge, Operator)
│   └── utils/              # Utilities (LLM, Types)
├── playground/             # Playground implementations
│   ├── minimal/            # Basic single-agent
│   ├── minimal_kaggle/     # Kaggle automation
│   ├── minimal_multi_agent/# Planning + Coding agents
│   ├── minimal_skill_task/ # RAG-based workflow
│   └── x_master/           # X-Master 4-phase workflow
├── configs/                # Configuration files
└── docs/                   # Documentation
```

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Architecture Overview](./docs/architecture.md) | System architecture and design |
| [Agent Module](./docs/agent.md) | Agent, Context, Session APIs |
| [Core Module](./docs/core.md) | BaseExp, BasePlayground APIs |
| [Tools Module](./docs/tools.md) | Tool system and MCP integration |
| [Skills Module](./docs/skills.md) | Skill system APIs |
| [LLM Module](./docs/llm.md) | LLM abstraction layer |

## 🎮 Playgrounds

| Playground | Description | Documentation |
|------------|-------------|---------------|
| `minimal` | Basic single-agent playground | [README](./playground/minimal/README.md) |
| `minimal_kaggle` | Kaggle competition automation | [README](./playground/minimal_kaggle/README.md) |
| `minimal_multi_agent` | Planning + Coding agents | [README](./playground/minimal_multi_agent/README.md) |
| `minimal_skill_task` | RAG-based Analyze→Search→Summarize | [README](./playground/minimal_skill_task/README.md) |
| `x_master` | 4-phase parallel workflow | [README](./playground/x_master/README.md) |

## 🚀 Quick Start

### Use your API key
Open the config file at `configs/[playground name]` and fill in the corresponding blank. For example, if you want to run minimal_multi_agent with Deepseek-V3.2, open `configs/minimal_multi_agent/deepseek-v3.2-example.yaml` and modify:
```bash
  local_sglang:
    provider: "deepseek"
    model: "deepseek-v3.2"
    api_key: "dummy"
    base_url: "http://192.168.2.110:18889/v1"
```
You can also use the `openai` config if your API supports OpenAI's format. Remember to modify the llm configuration of the following Agent at the same time

### Using Environment Variables (.env)

Alternatively, you can use environment variables for configuration. This approach is more secure and flexible:

1. **Create `.env` file from template:**
   ```bash
   cp .env.template .env
   ```

2. **Edit `.env` file** and fill in your API keys and configuration values:
   ```bash
   # Example: Set your DeepSeek API key
   DEEPSEEK_API_KEY="your-api-key-here"
   DEEPSEEK_API_BASE="http://127.0.0.1:18889/v1"
   ```

3. **Run your command:**
   
   The system will automatically load `.env` file from the project root, so you can simply run:
   ```bash
   python run.py --agent minimal --task "Your task description"
   ```
   
   Alternatively, you can use `dotenv` CLI tool:
   ```bash
   dotenv run python run.py --agent minimal --task "Your task description"
   ```

### Basic Usage

```bash
cd EvoMaster
python run.py --agent minimal --task "Your task description"
```

### With Custom Config

```bash
python run.py --agent minimal --config configs/minimal/config.yaml --task "Your task"
```

### From Task File

```bash
python run.py --agent minimal --task task.txt
```

### Interactive Mode

```bash
python run.py --agent minimal --interactive
```

## 📋 Examples

### Single Agent (Minimal)
```bash
python run.py --agent minimal --config configs/minimal/deepseek-v3.2-example.yaml --task "Discover a pattern: Given sequence 1, 4, 9, 16, 25... find the formula"
```

### Multi-Agent System
```bash
python run.py --agent minimal_multi_agent --config configs/minimal_multi_agent/deepseek-v3.2-example.yaml --task "Write a Python program that implements the following features: Read a text file (create a sample file if it doesn't exist). Count the occurrences of each word in the file. Sort the results by frequency in descending order. Save the results to a new file named word_count.txt. Output the top 10 most common words to the terminal."
```

### X-Master Workflow
```bash
# install environment for mcp_sandbox
pip install -r playground/x_master/mcp_sandbox/requirements.txt
python run.py --agent x_master --task "Which condition of Arrhenius's sixth impossibility theorem do critical-level views violate?\n\nAnswer Choices:\nA. Egalitarian Dominance\nB. General Non-Extreme Priority\nC. Non-Elitism\nD. Weak Non-Sadism\nE. Weak Quality Addition"
```

### Kaggle Automation
```bash
pip install -r playground/minimal_kaggle/requirements.txt
python run.py --agent minimal_kaggle --config configs/minimal_kaggle/deepseek-v3.2-example.yaml --task playground/minimal_kaggle/data/public/description.md
```

## 📦 Installation

### With pip

```bash
# Clone repository
git clone https://github.com/sjtu-sai-agents/EvoMaster.git
cd EvoMaster

# Install dependencies
pip install -r requirements.txt

# Configure LLM API keys in configs/
```

### With uv

[uv](https://docs.astral.sh/uv/) is a fast Python package installer. Use either:

```bash
# Option 1: sync from pyproject.toml + uv.lock (recommended)
uv sync

# Option 2: install from requirements.txt
uv pip install -r requirements.txt
```

Create a venv and run with uv: `uv venv && source .venv/Scripts/activate` (Windows) or `source .venv/bin/activate` (Linux/macOS), then `uv sync`.

## 🤝 Citation

If you use EvoMaster or the SciMaster series agents in your research, please feel free to give us a star and citatiton (BibTeX will be updated upon the release of the paper).


## 📬 Contact

* **SciMaster Platform:** [https://scimaster.bohrium.com/chat/](https://scimaster.bohrium.com/chat/)
* **Bohrium Platform:** [https://www.bohrium.com/](https://www.bohrium.com/)
