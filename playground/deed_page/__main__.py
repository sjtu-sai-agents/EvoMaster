"""Publish or delete a deed.page site through EvoMaster's MCP tool registry."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from evomaster.agent.tools import MCPToolManager, create_registry


async def run(args):
    config_path = Path(__file__).resolve().parents[2] / "configs/deed_page/mcp_config.json"
    with config_path.open(encoding="utf-8") as config_file:
        servers = json.load(config_file)["mcpServers"]

    if args.action == "publish":
        tool_name = "deed_page_publish_site"
        arguments = {"files": {"index.html": Path(args.file).read_text(encoding="utf-8")}}
        if args.slug:
            arguments["slug"] = args.slug
        if args.ttl:
            arguments["ttl_seconds"] = args.ttl
    else:
        token = os.environ.get("DEEDPAGE_TOKEN")
        if not token:
            raise SystemExit("Set DEEDPAGE_TOKEN to the token returned by the first publish")
        tool_name = "deed_page_delete_site"
        arguments = {"slug": args.slug, "token": token}

    manager = MCPToolManager()
    manager.loop = asyncio.get_running_loop()
    registry = create_registry(builtin_names=[])
    try:
        for name, config in servers.items():
            await manager.add_server(name=name, **config)
        manager.register_tools(registry)

        tool = registry.get_tool(tool_name)
        if tool is None:
            raise RuntimeError(f"Server did not provide {tool_name}")

        # MCPTool.execute is synchronous; keep the manager's loop running while
        # it submits the remote call back to that loop.
        observation, _ = await asyncio.to_thread(tool.execute, None, json.dumps(arguments))
        print(observation)
    finally:
        await manager.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    publish = actions.add_parser("publish", help="Publish an HTML file as index.html")
    publish.add_argument("file", help="HTML file to publish")
    publish.add_argument("--slug", help="Optional subdomain to claim")
    publish.add_argument(
        "--ttl", type=int, default=3600,
        help="Seconds until the page expires (default: 3600; 0 keeps it).",
    )
    delete = actions.add_parser("delete", help="Delete a site using DEEDPAGE_TOKEN")
    delete.add_argument("slug", help="Slug returned by publish")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
