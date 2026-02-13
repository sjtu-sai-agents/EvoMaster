#!/usr/bin/env python3
"""
Browse-Master MCP适配器 - 将搜索API转换为MCP协议
调用现有的 FastAPI 服务
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
    "browse-master-search-tools",
    host=HOST,
    port=MCP_PORT,
)

async def make_async_request(session, url, payload, timeout=30):
    """异步HTTP请求"""
    async with session.post(url, json=payload, timeout=timeout) as response:
        response.raise_for_status()
        return await response.json()

@mcp.tool()
async def web_search(query: str, top_k: int = 10) -> str:
    """
    使用Google搜索引擎搜索网页信息
    
    Args:
        query: 搜索关键词
        top_k: 返回结果数量，默认10
    """
    try:
        payload = {
            "query": query,
            "serper_api_key": SERPER_API_KEY,
            "top_k": top_k
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session, 
                f"{API_BASE_URL}/search", 
                payload
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，请稍后重试"
    except Exception as e:
        return f"搜索出错: {str(e)}"

@mcp.tool()
async def web_parse(link: str, user_prompt: str, llm: str = "gpt-4o") -> str:
    """
    解析和分析网页内容
    
    Args:
        link: 网页URL链接
        user_prompt: 关于网页内容的具体查询或分析请求
        llm: 使用的LLM模型，默认gpt-4o
    """
    try:
        payload = {
            "link": link,
            "user_prompt": user_prompt,
            "llm": llm
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/web_parse",
                payload,
                timeout=60
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，请检查URL是否有效"
    except Exception as e:
        return f"解析网页内容出错: {str(e)}"

@mcp.tool()
async def batch_search_and_filter(keyword: str) -> str:
    """
    批量搜索并过滤结果
    
    Args:
        keyword: 搜索关键词
    """
    try:
        payload = {
            "keyword": keyword
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/batch_search_and_filter",
                payload,
                timeout=120
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时，搜索可能需要较长时间"
    except Exception as e:
        return f"批量搜索出错: {str(e)}"

@mcp.tool()
async def generate_keywords(seed_keyword: str) -> str:
    """
    生成多个搜索关键词
    
    Args:
        seed_keyword: 种子关键词
    """
    try:
        payload = {
            "seed_keyword": seed_keyword
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/generate_keywords",
                payload
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时"
    except Exception as e:
        return f"生成关键词出错: {str(e)}"

@mcp.tool()
async def check_condition(content: str, condition: str) -> str:
    """
    评估内容是否满足指定条件
    
    Args:
        content: 要评估的内容
        condition: 评估条件
    """
    try:
        payload = {
            "content": content,
            "condition": condition
        }
        
        async with aiohttp.ClientSession() as session:
            result = await make_async_request(
                session,
                f"{API_BASE_URL}/check_condition",
                payload
            )
        
        return json.dumps(result, ensure_ascii=False, indent=2)
        
    except aiohttp.ClientError as e:
        return f"HTTP请求错误: {str(e)}"
    except asyncio.TimeoutError:
        return "请求超时"
    except Exception as e:
        return f"条件检查出错: {str(e)}"

@mcp.tool()
async def pdf_read(url: str) -> str:
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

if __name__ == "__main__":
    # 运行MCP服务器
    mcp.run(transport="streamable-http")