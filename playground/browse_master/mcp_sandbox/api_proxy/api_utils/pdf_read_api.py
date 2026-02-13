import requests
import fitz
import io
import traceback

def sync_read_pdf(url: str) -> str:
    try:
        headers = {
            "Accept": "application/pdf",
            "User-Agent": "Mozilla/5.0"
        }

        if "arxiv.org/abs/" in url:
            paper_id = url.split('/')[-1]
            url = f"https://arxiv.org/pdf/{paper_id}.pdf"

        response = None
        
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=15)
            response.raise_for_status()
        except Exception as e:
            print(f"\033[91mrequest failed: {e},{traceback.format_exc()}\033[0m")
            return "Failed to read the PDF"  

        if response is None or response.content is None or len(response.content) == 0:
            print("Content is None or empty")
            return "Failed to get the PDF content"

        try:
            pdf_bytes = io.BytesIO(response.content)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            text = ""
            for i, page in enumerate(doc):
                text += page.get_text()

            return text.strip()
        except Exception as e:
            print(f"\033[91mRead failed {e},{traceback.format_exc()}\033[0m")
            return "Failed to read the PDF"

    except Exception as e:
        print(f"\033[91mRead failed: {e},{traceback.format_exc()}\033[0m")
        return "Failed to read the PDF"

import asyncio

async def read_pdf_from_url(url: str) -> str:
    import functools
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(sync_read_pdf, url))

async def main():
    url = "https://arxiv.org/pdf/2305.14342"
    content = await read_pdf_from_url(url)
    print(content)

if __name__ == "__main__":
    asyncio.run(main())
