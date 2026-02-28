---
name: rag
description: Retrieval-Augmented Generation (RAG) system for semantic search and knowledge retrieval. Use when implementing knowledge-grounded AI, building document Q&A systems, or integrating LLMs with external knowledge bases. Supports vector-based similarity search using FAISS and transformer embeddings.
license: Proprietary. LICENSE.txt has complete terms
---

# RAG Implementation Guide

## Overview

This skill provides Retrieval-Augmented Generation (RAG) capabilities for semantic search and knowledge retrieval. It supports vector-based similarity search using FAISS and transformer embeddings, compatible with the agentic4mle project's RAG implementation.

## Quick Start

In this project, Operator skill scripts are executed through the `use_skill` tool's `run_script` action (see `evomaster/agent/tools/skill.py`). Therefore, this guide focuses on script invocation as the primary usage pattern.

### 1) Semantic Search (Recommended Entry: `scripts/search.py`)

#### Running Scripts via `use_skill`

Arguments are passed through `script_args` as space-separated strings (internally executed as `python /abs/path/to/script.py {script_args}`).

Example with local model (retrieve top 5 results with optional knowledge field output):

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="search.py",
  script_args="--vec_dir /path/to/vectorstore --query \"What is the main topic?\" --top_k 5 --threshold 1.5 --nodes_data /path/to/nodes_data.json --content_path content.text --output json"
)
```

Example with OpenAI embedding API (text-embedding-3-large):

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="search.py",
  script_args="--vec_dir /path/to/vectorstore --query \"What is the main topic?\" --top_k 5 --threshold 1.5 --nodes_data /path/to/nodes_data.json --output json --embedding_type openai --model text-embedding-3-large --embedding_dimensions 3072"
)
```

#### Direct Command Line Execution (Equivalent)

With local model:

```bash
python evomaster/skills/rag/scripts/search.py \
  --vec_dir /path/to/vectorstore \
  --query "What is the main topic?" \
  --top_k 5 \
  --threshold 1.5 \
  --nodes_data /path/to/nodes_data.json
```

With OpenAI embedding API:

```bash
python evomaster/skills/rag/scripts/search.py \
  --vec_dir /path/to/vectorstore \
  --query "What is the main topic?" \
  --top_k 5 \
  --threshold 1.5 \
  --nodes_data /path/to/nodes_data.json \
  --embedding_type openai \
  --model text-embedding-3-large \
  --embedding_dimensions 3072
```

### 2) Encoding Only (`scripts/encode.py`)

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="encode.py",
  script_args="--text \"What is the main topic?\" --model evomaster/skills/rag/local_models/all-mpnet-base-v2"
)
```

### 3) Task Knowledge (basic tools + search.py)

To get `data_knowledge` and `model_knowledge` for a task:

1. Get the query text: use `execute_bash` to `cat <simple_instructions_dir>/<task_name>/simple_instructions.txt` from project root, or use `str_replace_editor` with command `view` and the absolute path to that file.
2. Run `search.py` with `--query "<query from step 1>"`, `--top_k 1`, `--threshold 1.5`, `--nodes_data` pointing to the draft DB (e.g. `draft_407_75_db.json`), and `--output json`.
3. From the JSON result, take the first item in `results`; its `content` (or the node in nodes_data for that `node_id`) contains `data_knowledge` and `model_knowledge` for draft-stage DB.

## Core Components

### 1. Vector Database Structure

The vector database follows this structure:

```
MLE_DATABASE/
├── MLE75_tasksummary_v2.json          # Task summaries JSON file
├── simple_instructions/                # Simple instructions directory
│   ├── <task_name>/
│   │   └── simple_instructions.txt
│   └── ...
└── node_vectorstore/                  # Vector stores (multiple dimensions)
    ├── draft/                          # Draft stage vectorstore (768 dims)
    │   ├── faiss.index                 # FAISS index file
    │   ├── embeddings.npy              # Pre-computed embeddings
    │   ├── nodes.jsonl                 # Node ID mappings (one JSON per line)
    │   └── draft_407_75_db.json        # Full node data with knowledge content
    ├── improve/                        # Improve stage vectorstore
    │   ├── faiss.index
    │   ├── embeddings.npy
    │   ├── nodes.jsonl
    │   └── nodes_for_improve.json
    └── debug/                          # Debug stage vectorstore
        ├── faiss.index
        ├── embeddings.npy
        ├── nodes.jsonl
        └── nodes_for_debug.json
```

Note: Multiple vectorstore directories exist for different embedding dimensions. Each directory corresponds to a specific model:

- `node_vectorstore/` (768 dims) - Uses local model: `evomaster/skills/rag/local_models/all-mpnet-base-v2`
- `node_vectorstore_512/` (512 dims) - Uses `text-embedding-3-large` (512 dimensions)
- `node_vectorstore_768/` (768 dims) - Uses `text-embedding-3-large` (768 dimensions)
- `node_vectorstore_1024/` (1024 dims) - Uses `text-embedding-3-large` (1024 dimensions)
- `node_vectorstore_2048/` (2048 dims) - Uses `text-embedding-3-large` (2048 dimensions)
- `node_vectorstore_3072/` (3072 dims) - Uses `text-embedding-3-large` (3072 dimensions, default)

**Important**: Use the vectorstore directory that matches your model's output dimension. The default `node_vectorstore/` uses the local model, while other directories use OpenAI's `text-embedding-3-large` model with different dimensions.

### 2. Embedding Models

Default model location: `evomaster/skills/rag/local_models/all-mpnet-base-v2`

Supported embedding models:
- **Local model** (default, for `node_vectorstore/`): `evomaster/skills/rag/local_models/all-mpnet-base-v2` - 768 dimensions
- **text-embedding-3-large** (for `node_vectorstore_*` directories): OpenAI embedding model with configurable dimensions (512, 768, 1024, 2048, 3072)
- **sentence-transformers/all-mpnet-base-v2**: HuggingFace model, 768 dimensions
- **sentence-transformers/all-MiniLM-L6-v2**: Faster, smaller (384 dimensions)
- Any HuggingFace transformer model compatible with AutoModel

**Important**: 
- When using a local model path, ensure the model directory contains `config.json`, `model.safetensors`, and tokenizer files.
- When using `text-embedding-3-large`, ensure you use the correct vectorstore directory matching the dimension used during indexing.

### 3. Retrieval Methods

#### Similarity Search

```python
# Search with distance threshold
results = searcher.search_similar(
    query_emb,
    top_k=10,
    distance_threshold=1.5  # Filter results beyond this distance
)
```

#### Text-based Search

```python
# Direct text search (encodes and searches in one step)
results = searcher.search_by_text(
    query_text="What is the main topic?",
    top_k=5,
    distance_threshold=None
)
```

## Usage Patterns

### Pattern 1: Basic Knowledge Retrieval

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="search.py",
  script_args="--vec_dir evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve --nodes_data evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve/nodes_for_improve.json --query \"How to improve model performance?\" --top_k 5"
)
```

### Pattern 2: Multi-Stage Retrieval

```text
# improve
use_skill(skill_name="rag", action="run_script", script_name="search.py",
          script_args="--vec_dir evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve --nodes_data evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve/nodes_for_improve.json --query \"...\"")

# debug
use_skill(skill_name="rag", action="run_script", script_name="search.py",
          script_args="--vec_dir evomaster/skills/rag/MLE_DATABASE/node_vectorstore/debug --nodes_data evomaster/skills/rag/MLE_DATABASE/node_vectorstore/debug/nodes_for_debug.json --query \"...\"")
```

### Pattern 3: Custom Knowledge Extraction

Currently, `scripts/search.py` defaults to reading `nodes_data[<node_id>].content.improve_knowledge` (consistent with `agentic4mle/utils/vectorstore.py`).

If you need to read different fields during migration, the recommended approach is:
- Copy `scripts/search.py` to a new script (e.g., `search_debug.py`)
- Modify `get_knowledge()` to read fields like `bug_fix_specific / bug_fix_abstract / full_plan / code`
- Call it via `use_skill(..., script_name="search_debug.py", ...)`

## Database Interface

The database interface provides methods for building and managing vector databases. Currently, it provides a simple interface that can be extended:

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="database.py",
  script_args="--action build --output_dir ./vectorstore --model evomaster/skills/rag/local_models/all-mpnet-base-v2"
)
```

## Configuration

### Model Selection

Default model: `evomaster/skills/rag/local_models/all-mpnet-base-v2` (768 dims)

Choose embedding model based on your needs:

- **Default (local)**: `evomaster/skills/rag/local_models/all-mpnet-base-v2` (768 dims) 
  - Fast, no download needed
  - Used with `node_vectorstore/` (768 dims)
- **High accuracy (OpenAI)**: `text-embedding-3-large` with configurable dimensions (512, 768, 1024, 2048, 3072)
  - Used with corresponding `node_vectorstore_<dim>/` directories
  - Requires API access
- **Accuracy priority (HuggingFace)**: `sentence-transformers/all-mpnet-base-v2` (768 dims) - HuggingFace model
- **Speed priority**: `sentence-transformers/all-MiniLM-L6-v2` (384 dims) - Faster, smaller
- **Custom models**: Any HuggingFace AutoModel-compatible model or local model path

**Important**: Always use the vectorstore directory that matches the embedding model and dimension used during indexing.

### Distance Thresholds

Distance thresholds depend on the similarity metric:
- **L2 distance**: Lower is better (typically < 1.0 for similar items)
- **Cosine distance**: Lower is better (typically < 0.3 for similar items)
- **Inner product**: Higher is better (typically > 0.7 for similar items)

FAISS default is L2 distance. Adjust thresholds accordingly.

## Best Practices

1. **Chunk Size**: Balance context (larger) vs specificity (smaller) - typically 500-1000 tokens
2. **Overlap**: Use 10-20% overlap to preserve context at boundaries
3. **Metadata**: Include source, timestamp, and other metadata in nodes_data.json
4. **Distance Thresholds**: Set appropriate thresholds to filter irrelevant results
5. **Top-K Selection**: Start with k=5-10, adjust based on recall needs
6. **Model Selection**: Use larger models for accuracy, smaller for speed

## Common Issues

- **Poor Retrieval**: Check embedding quality, ensure proper encoding
- **Irrelevant Results**: Adjust distance thresholds, check query formulation
- **Missing Information**: Ensure documents are properly indexed
- **Slow Queries**: Use smaller embedding models, optimize FAISS index
- **Memory Issues**: Use CPU mode, reduce batch sizes

## Integration with agentic4mle

This RAG implementation is compatible with the agentic4mle project's vectorstore structure. The actual database is located at `evomaster/skills/rag/MLE_DATABASE/`:

```text
use_skill(
  skill_name="rag",
  action="run_script",
  script_name="search.py",
  script_args="--vec_dir evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve --nodes_data evomaster/skills/rag/MLE_DATABASE/node_vectorstore/improve/nodes_for_improve.json --query \"...\""
)
```

## Next Steps

- For advanced retrieval patterns, see reference.md
- For database building, see database.py interface
- For troubleshooting, check logs and distance metrics
