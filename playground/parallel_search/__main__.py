"""Run Parallel search or fetch through EvoMaster's MCP tool registry."""

import argparse
import asyncio
import json
from pathlib import Path
import uuid

from evomaster.agent.tools import MCPToolManager, create_registry


async def run(args):
    config_path = Path(__file__).resolve().parents[2] / "configs/parallel_search/mcp_config.json"
    with config_path.open(encoding="utf-8") as config_file:
        servers = json.load(config_file)["mcpServers"]

    manager = MCPToolManager()
    manager.loop = asyncio.get_running_loop()
    registry = create_registry(builtin_names=[])
    try:
        for name, config in servers.items():
            await manager.add_server(name=name, **config)
        manager.register_tools(registry)

        tool_name = f"parallel_web_{args.action}"
        tool = registry.get_tool(tool_name)
        if tool is None:
            raise RuntimeError(f"Server did not provide {tool_name}")

        arguments = {"session_id": args.session_id}
        if args.action == "search":
            arguments.update(objective=args.objective, search_queries=args.query)
        else:
            arguments["urls"] = args.url

        # MCPTool.execute is synchronous; keep the manager's loop running while
        # it submits the remote call back to that loop.
        observation, _ = await asyncio.to_thread(tool.execute, None, json.dumps(arguments))
        print(observation)
    finally:
        await manager.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-id", default=uuid.uuid4().hex,
        help="Reuse this ID for related search/fetch calls (default: a new UUID).",
    )
    actions = parser.add_subparsers(dest="action", required=True)
    search = actions.add_parser("search", help="Find web sources and excerpts")
    search.add_argument("--objective", required=True)
    search.add_argument("--query", action="append", required=True, help="Repeat for multiple queries")
    fetch = actions.add_parser("fetch", help="Extract content from known URLs")
    fetch.add_argument("--url", action="append", required=True, help="Repeat for multiple URLs (up to 20)")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
