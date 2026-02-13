import asyncio
import time
from fastapi import FastAPI, HTTPException, Request
import json
import uvicorn
from typing import Dict
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import aiohttp
from fastapi.responses import JSONResponse
from models import SearchRequest, ReadPdfInfo, FetchWebContent
from api_utils.web_search_api import serper_google_search
from api_utils.pdf_read_api import read_pdf_from_url
from api_utils.fetch_web_page_api import fetch_web_content
import requests
import os


app = FastAPI()

# 初始化内存限流器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/search")
@limiter.limit("200/second")
async def search(request: Request, search_request: SearchRequest):
    try:
        result = await serper_google_search(
            search_request.query, 
            search_request.serper_api_key, 
            search_request.top_k, 
            search_request.region, 
            search_request.lang, 
            depth=search_request.depth
        )
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
    


@app.post("/read_pdf")
@limiter.limit("200/second")
async def read_pdf(request: Request, read_pdf_request: ReadPdfInfo):
    try:
        result = await read_pdf_from_url(read_pdf_request.url)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.post("/fetch_web")
@limiter.limit("200/second")
async def fetch_web(request: Request, fetch_web_request: FetchWebContent):
    try:
        result = await fetch_web_content(fetch_web_request.url)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Limit is 200 requests per second."},
        headers={"Retry-After": "1"}
    )




if __name__ == "__main__":
    import os

    PORT = os.getenv('PORT', 1234)

    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=int(PORT),
        lifespan="on",
        workers=1
    )