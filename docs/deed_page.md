# deed.page publishing MCP example

Use deed.page's remote MCP server to publish an HTML report written by an
EvoMaster agent to a public `*.deed.page` URL, through the existing
`MCPToolManager` and `ToolRegistry`. The optional configuration uses Streamable
HTTP and sends an EvoMaster User-Agent. It does not change any existing
playground configuration.

The endpoint at `https://deed.page/mcp` needs no API key, OAuth, or account.
The first publish returns an owner token; keep it, because updating or deleting
the site requires it. This example calls tools directly; it needs neither an
LLM nor a Docker sandbox. Limits and the full tool list are described in the
[deed.page documentation](https://deed.page/docs).

## Publish and delete

From the repository root, install EvoMaster in a fresh environment:

```bash
uv venv .venv-deed-page
uv pip install --python .venv-deed-page/bin/python -e . -r playground/deed_page/requirements.txt
source .venv-deed-page/bin/activate
```

Publish an HTML file as the site's `index.html`. By default the page expires
after one hour; pass `--ttl 0` to keep it, or `--slug` to request a subdomain:

```bash
python -m playground.deed_page publish report.html
```

The output contains the public `url`, the `slug`, and, on the first publish,
the owner `token`. Delete the site with that token:

```bash
DEEDPAGE_TOKEN=deed_tok_... python -m playground.deed_page delete <slug>
```

Published pages are public to anyone with the URL. Do not publish secrets,
credentials, or private experiment data.

## Add to a playground

Copy the `deed_page` entry from
[`configs/deed_page/mcp_config.json`](../configs/deed_page/mcp_config.json)
into your playground's `mcpServers` object, retaining its existing servers. Set
the agent's `tools.mcp` to that JSON file, relative to the playground configuration
directory. See [MCP configuration](./tools.md#mcp-configuration).

The manager discovers the current schemas and registers tools such as
`deed_page_publish_site`, `deed_page_get_site`, and `deed_page_delete_site`.
No tool schemas or credentials are hardcoded in the configuration. Tell the
agent to keep the returned token if it should update the page later.
