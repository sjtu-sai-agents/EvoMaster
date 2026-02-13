import requests
import fitz
import io
import traceback
import os, sys
current_dir = os.path.dirname(os.path.abspath(__file__))    
sys.path.append(os.path.join(current_dir, '..', '..', '..', '..', 'api_proxy'))
print(sys.path)
from tool_api import read_pdf_api  

import asyncio
import aiohttp
async def read_pdf_from_url(url: str) -> str:
    async with aiohttp.ClientSession() as session:
        result = await read_pdf_api(session, url)
        return result

async def main():
    url = "https://arxiv.org/abs/2501.04519"
    content = await read_pdf_from_url(url)
    print(content)

if __name__ == "__main__":
    asyncio.run(main())
