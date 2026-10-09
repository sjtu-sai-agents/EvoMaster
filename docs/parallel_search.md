# Parallel Search MCP example

Use Parallel's remote MCP server to search the web and extract page excerpts
through EvoMaster's existing `MCPToolManager` and `ToolRegistry`. The optional
configuration uses Streamable HTTP and sends an EvoMaster User-Agent. It does
not change any existing playground configuration.

The [anonymous endpoint](https://docs.parallel.ai/integrations/mcp/search-mcp)
is free for exploration and light use, with lower rate limits and no Parallel
API key or OAuth required. Anonymous searches use server-managed `fast` mode.
This example calls tools directly; it needs neither an LLM nor a Docker sandbox.
Running an agent with these tools still requires your usual model configuration
and any model inference costs.

## Run search and fetch

From the repository root, install EvoMaster in a fresh environment:

```bash
uv venv .venv-parallel
uv pip install --python .venv-parallel/bin/python -e . -r playground/parallel_search/requirements.txt
source .venv-parallel/bin/activate
```

The example requirements select MCP SDK 1.x, matching EvoMaster's current
`streamablehttp_client` API.

Run a search with a focused objective and one or more keyword queries:

```bash
python -m playground.parallel_search --session-id 0123456789abcdef0123456789abcdef search \
  --objective "Find the official Python documentation for asyncio TaskGroup" \
  --query "Python asyncio TaskGroup documentation"
```

The output contains source URLs and text excerpts. Read a result in more detail
with `fetch` (repeat `--url` for up to 20 pages):

```bash
python -m playground.parallel_search --session-id 0123456789abcdef0123456789abcdef fetch \
  --url "https://docs.python.org/3/library/asyncio-task.html"
```

Use a fresh session ID for each research conversation and reuse it for related
calls. The CLI generates one if `--session-id` is omitted. Server errors and rate
limit messages can also appear in the tool output.

## Add to a playground

Copy the `parallel` entry from
[`configs/parallel_search/mcp_config.json`](../configs/parallel_search/mcp_config.json)
into your playground's `mcpServers` object, retaining its existing servers. Set
the agent's `tools.mcp` to that JSON file, relative to the playground configuration
directory. See [MCP configuration](./tools.md#mcp-configuration).

The manager discovers the current schemas and registers `parallel_web_search`
and `parallel_web_fetch`. No tool schemas or authentication credentials are
hardcoded in the configuration. Both the CLI and playground configuration use
the same HTTP transport; the CLI dispatches through the registered EvoMaster
tools and closes the connection on exit.
