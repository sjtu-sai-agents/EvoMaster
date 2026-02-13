#!/usr/bin/env python3
"""
MCP适配器 - 将你的搜索API转换为MCP协议
调用你现有的 FastAPI 服务
"""

import os
import json
import asyncio
from mcp.server.fastmcp import FastMCP
import aiohttp

# 配置
MCP_PORT = int(os.getenv("MCP_PORT", "8002"))
HOST = os.getenv("HOST", "0.0.0.0")

# 你的 FastAPI 服务地址
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:1234")

# 从配置文件或环境变量读取 API key
def _load_serper_api_key():
    """从环境变量或配置文件读取 Serper API key"""
    key = os.getenv("SERPER_API_KEY")
    if key:
        return key
    # 尝试从配置文件读取
    config_path = os.path.join(os.path.dirname(__file__), "../configs/web_agent.json")
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            return config.get("serper_api_key", "")
    return ""

SERPER_API_KEY = _load_serper_api_key()

# 初始化MCP服务器
mcp = FastMCP(
    "search-tools",
    host=HOST,
    port=MCP_PORT,
)

async def make_async_request(session, url, payload, timeout=30):
    """异步HTTP请求"""
    async with session.post(url, json=payload, timeout=timeout) as response:
        response.raise_for_status()
        return await response.json()

@mcp.tool()
async def search(
    query: str,
    top_k: int = 10,
    region: str = "us",
    lang: str = "en",
    depth: int = 0
) -> str:
    """
    搜索网页内容
    
    Args:
        query: 搜索关键词
        top_k: 返回结果数量，默认10
        region: 搜索区域（us, uk, cn等）
        lang: 语言（en, zh-CN等）
        depth: 搜索深度（brief, basic, detailed）
    """
    try:
        payload = {
            "query": query,
            "serper_api_key": SERPER_API_KEY,
            "top_k": top_k,
            "region": region,
            "lang": lang,
            "depth": depth
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session, 
                f"{API_BASE_URL}/search", 
                payload
            )
        
        # 格式化输出
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，请稍后重试"
    except Exception as e:
        return f"搜索出错: {str(e)}"

@mcp.tool()
async def read_pdf(url: str) -> str:
    """
    从URL读取PDF文件内容
    
    Args:
        url: PDF文件的URL地址
    """
    try:
        payload = {"url": url}
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/read_pdf",
                payload,
                timeout=60
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，PDF文件可能较大"
    except Exception as e:
        return f"读取PDF出错: {str(e)}"

@mcp.tool()
async def fetch_web(url: str) -> str:
    """
    获取网页内容
    
    Args:
        url: 网页URL地址
    """
    try:
        payload = {"url": url}
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/fetch_web",
                payload
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，请检查URL是否有效"
    except Exception as e:
        return f"获取网页内容出错: {str(e)}"

if __name__ == "__main__":

    # 运行MCP服务器
    mcp.run(transport="streamable-http") 
