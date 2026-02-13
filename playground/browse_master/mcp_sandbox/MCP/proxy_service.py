from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

import httpx
import hashlib
from pydantic import BaseModel
import os
from utils import CodeRequest

START_PORT = int(os.getenv("START_PORT"))
NUM_WORKERS = int(os.getenv("NUM_WORKERS"))

app = FastAPI()
BACKEND_PORTS = range(START_PORT, START_PORT + NUM_WORKERS )  # 16个后端实例

PROXY_TIMEOUT = 36000


def get_port_by_session_id(session_id: str):
    target_port = START_PORT + int(hashlib.md5(session_id.encode()).hexdigest(), 16) % NUM_WORKERS
    return target_port


@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    # print(request.__dict__)
    session_id = request.headers.get("session_id")
    print(f"!!!!!!!!!!!!!!!!!!!!{session_id}!!!!!!!!!!!!!!!!!!!!!!!!!")
    if not session_id:
        session_id = str(uuid4())
        # return JSONResponse(status_code=400, content={"error": "Missing session_id in headers"})

    port = get_port_by_session_id(session_id)
    target_url = f"http://127.0.0.1:{port}/{path}"

    async with httpx.AsyncClient(timeout=None) as client:
        try:
            headers = dict(request.headers)

            if request.method == "POST":
                body = await request.body()
                response = await client.post(target_url, content=body, headers=headers)
                return JSONResponse(
                    status_code=response.status_code,
                    content=response.json()
                )

            elif request.method == "GET":
                # 注意这里要保留原始流式响应
                
                async def stream_response():
                    async with httpx.AsyncClient(timeout=None) as client:
                        async with client.stream("GET", target_url, headers=headers, params=request.query_params) as response:
                            async for chunk in response.aiter_raw():
                                yield chunk

                return StreamingResponse(
                    stream_response(),
                    media_type="application/json"  # 或 text/event-stream
                )

        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=30007)