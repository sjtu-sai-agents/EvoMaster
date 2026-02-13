import aiohttp
import asyncio
import json
import os, sys
import functools
import requests


current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(os.path.dirname(current_dir)))

FAILED_INFO = "Failed to fetch web page"

with open(f"{current_dir}/../../configs/web_agent.json", "r") as f:
    config = json.load(f)
    serper_api_key = config["serper_api_key"]


def sync_fetch_html(url: str, timeout=10) -> tuple[bool, str]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1'
    }

    session = requests.Session()
    try:
        response = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.encoding = 'utf-8'
        response.raise_for_status()

        return (True, response.text)

    except Exception as e:
        print(f"[error] request {url} failed：{e}")
        return (False, FAILED_INFO)
    finally:
        session.close()


async def download_htmlpage(url: str, timeout=10) -> tuple[bool, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(sync_fetch_html, url, timeout))

async def get_web_content_api(url: str):
    api_url = "https://scrape.serper.dev"
    payload = {
        "url": url,
        "includeMarkdown": True
    }
    headers = {
        'X-API-KEY': serper_api_key,
        'Content-Type': 'application/json'
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.post(api_url, json=payload, headers=headers) as response:
                result = await response.json()
    except Exception as e:
        print(f"\033[91mAPI request failed: {e}\033[0m")
        return FAILED_INFO

    return result.get("markdown") or result.get("text") or FAILED_INFO


async def fetch_web_content(url: str):
    is_download, result = await download_htmlpage(url)
    if not is_download or not result:
        print(f"\033[91mFailed to crawl web content, using API: {url}\033[0m")
        result = await get_web_content_api(url)
    if FAILED_INFO in result:
        return False, FAILED_INFO
    return True, result


async def main():
    url = "https://www.kdjingpai.com/scimaster/"
    is_ok, html = await fetch_web_content(url)
    if is_ok:
        print(html)  
    else:
        print("❌ Failed to fetch web content.")

if __name__ == "__main__":
    asyncio.run(main())
