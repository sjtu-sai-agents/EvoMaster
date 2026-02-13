import aiohttp
import asyncio
import json
import os, sys
current_dir = os.path.dirname(os.path.abspath(__file__))    
sys.path.append(os.path.join(current_dir, '..', '..', '..', '..', 'api_proxy'))
from tool_api import fetch_web_api  

async def fetch_web_content(url: str):
    async with aiohttp.ClientSession() as session:
        result = await fetch_web_api(session, url)
        return result


async def main():
    url = "https://proceedings.neurips.cc/paper_files/paper/2022"
    is_ok, html = await fetch_web_content(url)
    if is_ok:
        print(html)  # 打印前 2000 个字符
    else:
        print("❌ 获取失败")

if __name__ == "__main__":
    asyncio.run(main())
