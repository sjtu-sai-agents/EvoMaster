from asyncio import streams
import os, sys
from typing import Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

class MCPClient:
    def __init__(self, venv_path, server: str = ""):
        self.venv_path = venv_path
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.server = server
        if not self.server:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.server = os.path.join(current_dir, "mcp_server.py")

    async def connect_to_server(self):
        is_python = self.server.endswith('.py')
        is_js = self.server.endswith('.js')
        is_sse = self.server.startswith('http')
        if not (is_python or is_js or is_sse):
            raise ValueError("Server script must be a .py or .js file or a sse link")
        

        if is_sse:
            try:
                print(self.server)
                streams = await self.exit_stack.enter_async_context(sse_client(self.server))
            
                self.session = await self.exit_stack.enter_async_context(ClientSession(*streams))
                result = await self.session.initialize()
                
                response = await self.session.list_tools()
                tools = response.tools
                print("\nConnected to server with tools:", [tool.name for tool in tools])
                return result.serverInfo.name
            
            except Exception as e:
                print(f"An error occurred while connecting to the server: {e}")
                raise


        command = "python" if is_python else "node"
        env = os.environ.copy()
        if is_python:
            if self.venv_path:
                if sys.platform == 'win32':
                    python_executable = os.path.join(self.venv_path, 'Scripts', 'python.exe')
                    env['PATH'] = os.path.join(self.venv_path, 'Scripts') + os.pathsep + env['PATH']
                else:
                    python_executable = os.path.join(self.venv_path, 'bin', 'python')
                    env['PATH'] = os.path.join(self.venv_path, 'bin') + os.pathsep + env['PATH']
                if not os.path.exists(python_executable):
                    raise ValueError(f"Python interpreter not found in virtual environment: {python_executable}")
                command = python_executable
            else:
                command = "python"
        else:
            command = "node"

        server_params = StdioServerParameters(
            command=command,
            args=[self.server],
            env=env
        )
        
        try:
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            stdio, write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
            result = await self.session.initialize()
            
            response = await self.session.list_tools()
            tools = response.tools
            print("\nConnected to server with tools:", [tool.name for tool in tools])
            return result.serverInfo.name
        
        except Exception as e:
            print(f"An error occurred while connecting to the server: {e}")
            raise

    async def get_tools(self) -> list:
        response = await self.session.list_tools()
        available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]
        return available_tools

    async def use_tools(self, response_content : list) -> str:
        final_text = []

        for content in response_content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input
                
                result = await self.session.call_tool(tool_name, tool_args)

                if hasattr(content, 'text') and content.text:
                    final_text.append(content.text)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                final_text.append(result.content)
        return "\n".join(final_text)
    
    async def call_tool(self, tool_name: str, tool_args: dict) -> list:
        result = await self.session.call_tool(tool_name, tool_args)
        if result.isError:
            raise RuntimeError(str(result.content))
        else:
            results = []
            for r in result.content:
                r_dict = r.model_dump(mode="json",by_alias=True)
                match r_dict.get("type"):
                    case "text":
                        results.append(r_dict.get("text"))
                    case "image":
                        results.append(r_dict.get("data"))
                    case "resource":
                        results.append(r_dict.get("resource"))
            return results

    async def cleanup(self):
        await self.exit_stack.aclose()


# Test
async def create_client() -> MCPClient:
    client = MCPClient()
    try:
        await client.connect_to_server()
        return client
    except Exception as e:
        print(f"An error occurred while create client: {e}")
        await client.cleanup()
        raise

async def test():
    client = MCPClient()
    await client.connect_to_server()
    await client.cleanup()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())