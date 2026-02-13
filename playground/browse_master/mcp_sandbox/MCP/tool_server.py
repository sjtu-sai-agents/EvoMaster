import json
import os
import sys
import asyncio
from flask import jsonify
from narwhals import from_dict
import uvicorn
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse

from contextlib import asynccontextmanager
import logging
from typing import Optional, Tuple
import traceback
import sys
import threading
from pyext import RuntimeModule

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from mcp_manager import MCPManager
from utils import create_lifespan, form_item, form_item
from utils import SessionManager, post_item_info
from functools import partial
from io_manage import ThreadOutputManager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from utils import CodeRequest, CodeResponse, SandboxStreamRequest, SandboxStreamResponse, SessionInformHandler
from utils import CodeSubmitRequest, CodeSubmitResponse
import threading
import time
import types
import builtins
import httpx

current_dir = os.path.dirname(os.path.abspath(__file__))
temp_dir = os.path.join(current_dir, "temp")
os.makedirs(temp_dir, exist_ok=True)

sys.path.append(temp_dir)





async def put_item_with_session_id(session_id:str, item:Dict[str, Any]):
    inform_handler:SessionInformHandler = session_manager.sessions[session_id].__dict__['inform_handler']

    try:
        await inform_handler.async_inform_queue.put(item)
        flag = True

    except Exception as e:

        flag = False
    return flag








# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)





logger = logging.getLogger(__name__)    
manager = MCPManager()
session_manager = SessionManager(manager)
app = FastAPI(lifespan=create_lifespan(manager, temp_dir))



@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/get_tool")
async def get_tools():
    return manager.get_tools()

@app.get("/get_tool/{agent_name}")
async def get_tools(agent_name: str):
    if (not agent_tools.get(agent_name)) or (not agent_tools[agent_name]):
        return manager.get_tools()
    return agent_tools[agent_name]


@app.post("/del_session")
async def del_session(session_id:str):
    
    try:
        session_manager.clear_session(session_id)
        return {"status": "success"}
    except:
        return {"status":"failed"}

@app.post("/put_item", response_model=SandboxStreamResponse)
async def put_item(request:SandboxStreamRequest):
    session_id, item = request.session_id, request.item

    inform_handler:SessionInformHandler = session_manager.sessions[session_id].__dict__['inform_handler']
    try:
        await inform_handler.async_inform_queue.put(item)
        flag = True
    except Exception as e:
        flag = False

    return SandboxStreamResponse(
        session_id=request.session_id,
        flag=flag
    )


@app.post("/stream_put_item")
async def stream_put_item(request:Request):

    buffer = ""
    total_count = 0
    errors = []

    try:
        async for chunk in request.stream():
            text_chunk = chunk.decode("utf-8")
            buffer += text_chunk

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    session_id = data.get("session_id", "unknown")
                    item = data.get("item", {})

                    # 处理逻辑（你自己的函数）
                    await put_item_with_session_id(session_id, item)

                    total_count += 1

                except json.JSONDecodeError as e:
                    errors.append({"line": line, "error": "JSONDecodeError"})
                except Exception as e:
                    errors.append({"line": line, "error": str(e)})

        return JSONResponse({
            "status": "ok",
            "processed_items": total_count,
            "errors": errors
        })

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/get_mcp_result/{session_id}",)
async def get_mcp_result(session_id:str, request:Request):
    try:
        inform_handler:SessionInformHandler = session_manager.sessions[session_id].__dict__['inform_handler']
    except Exception as e:
        raise HTTPException(status_code=404, detail="Session not found")
    
    async def event_generator():
        while True:
            try:
                item = await inform_handler.async_inform_queue.get()
                
                yield json.dumps(item)+'\n'
                if (not item.get("sub_stream_type")) and (item.get("stream_state") == "end"):
                    
                    break
            except asyncio.CancelledError:
                break
    return StreamingResponse(event_generator(), media_type="application/json")




@app.post("/call_tool/{tool_name}")
async def create_tool_task(tool_name: str, tool_args: Dict):
    print(f"=============={tool_name}===============")
    tool_names = manager.get_toolnames()
    if tool_name not in tool_names:
        raise HTTPException(404, "Tool not found")
    

    result = None
    status = False

    try:
        result = await manager.call_tool(
            tool_name,
            tool_args
        )
        status = True
        
        
        final_result = []
        for item in result:
            try:
                json_obj = json.loads(item)
                final_result.append(json_obj)
            except Exception as e:
                final_result.append(item)
        result = final_result

    except Exception as e:
        # await log_to_counter_service(tool_name, False)
        result = f"Error: {str(e)}\n\n{traceback.format_exc()}\n\ntool name: {tool_name}\n\n tool args: {tool_args}"
        # post_info(result, "tool")
        print(result)
        status = False
        
    finally:
        return {"status": status, "result": result[0]}



output_manager = ThreadOutputManager()
execution_semaphore = asyncio.Semaphore(2000)  # 每个worker限制50个并发
executor = ThreadPoolExecutor(max_workers=1000)  # 每个worker使用少量线程



async def execute_python_code(code: str, session_id:str, timeout: int) -> Tuple[str, Optional[str], float]:
    """执行Python代码并返回输出、错误和执行时间"""
    loop = asyncio.get_event_loop()
    start_time = loop.time()

    try:
        execution_time, output, error = await loop.run_in_executor(executor, _execute_code_safely, code, session_id, timeout)
    except Exception as e:
        error = f"Execution failed: {str(e)}"
        output = ""
        logger.error(f"Unexpected error: {error}", exc_info=True)
        execution_time = loop.time() - start_time
        
    return output, error, execution_time

def _execute_code_safely(code: str, session_id:str, timeout: int) -> Tuple[str, Optional[str]]:
    """在沙箱环境中安全执行代码，并控制实际执行超时"""
    logger.info(f"Executing in thread {threading.current_thread().ident}, process {os.getpid()}")

    module = session_manager.get_session(session_id)
    capture = output_manager.get_capture()

    module.__dict__.update({
        'print': lambda *args, **kwargs: capture.write(
            ' '.join(str(arg) for arg in args) + ('\n' if kwargs.get('end', '\n') else '')
        ),
        'open': restricted_open,
        '__builtins__': __builtins__,
        'sys': type('sys', (), {
            'stdout': capture,
            'stderr': capture,
            'stdin': None,
        })(),
    })

    
    error = None
    output_value = None
    error_value = None

    start_time = time.time()

    single_executor = ThreadPoolExecutor(max_workers=1)

    def run_code():
        # module.
        start_item = form_item("tool_result", "", "start")
        post_item_info(session_id, start_item)
        exec(code, module.__dict__)
        return capture.get_stdout(), capture.get_stderr()

    try:
        # 提交代码执行任务，并设置超时
        future = single_executor.submit(run_code)
        output_value, error_value = future.result(timeout=timeout)

    except FutureTimeoutError:
        error = f"Execution timed out after {timeout} seconds"
        logger.warning(f"Code execution timeout: {timeout}s")
        error_value = error

    except SystemExit as se:
        error = f"Code called sys.exit({se.code})"
        if not capture.stderr.closed:
            capture.stderr.write(error)
        logger.warning(f"Code triggered SystemExit: {error}\n\n-----\n{code}")
        error_value = error

    except Exception as e:
        error = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        error = error.replace(
            """Traceback (most recent call last):\n  File "<string>", line 1, in <module>\n""",
            ""
        )
        if not capture.stderr.closed:
            capture.stderr.write(error)
        logger.warning(f"Code execution error: {error}\n\n-----\n{code}")
        error_value = error

    finally:
        # 确保所有写操作完成后再关闭
        if not capture.stdout.closed or not capture.stderr.closed:
            if output_value is None:
                output_value = capture.get_stdout()
            if error_value is None or error_value != error:
                error_value = capture.get_stderr()
            # capture.close()
            # print("????")

    # print('-------------------')
    end_item = form_item("tool_result", "", "end")
    code_result_content = output_value if not error_value else error_value
    code_result_item = form_item("code_result", code_result_content, "running")
    post_item_info(session_id, code_result_item)
    post_item_info(session_id, end_item)
    execution_time = time.time() - start_time
    logger.info(f"Executing in thread {threading.current_thread().ident}, process {os.getpid()} finished")
    return execution_time, output_value, error_value if error_value else None

def restricted_open(*args, **kwargs):
    mode = args[1] if len(args) > 1 else kwargs.get('mode', 'r')
    if any(m in mode.lower() for m in ('w', 'a', '+')):
        raise IOError("File write operations are disabled")
    return builtins.open(*args, **kwargs)


def redirect_stderr(stream):
    """重定向stderr到指定流"""
    return _RedirectStream(sys.stderr, stream)

class _RedirectStream:
    """用于重定向流的上下文管理器"""
    def __init__(self, original_stream, target_stream):
        self.original_stream = original_stream
        self.target_stream = target_stream
        
    def __enter__(self):
        self.old_stream = sys.stderr
        sys.stderr = self.target_stream
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr = self.old_stream

@app.post("/execute", response_model=CodeResponse)
async def execute_code_handler(request: CodeRequest):

    # print(request.dict())

    """处理代码执行请求"""
    if not request.code.strip():
        raise HTTPException(
            status_code=400,
            detail="Code cannot be empty"
        )
    
    logger.info(f"Executing code snippet (timeout: {request.timeout}s)")
    
    try:
        output, error, exec_time = await execute_python_code(
            request.code,
            request.session_id,
            request.timeout
        )
        
        logger.info(
            f"Code execution completed in {exec_time:.2f}s. "
            f"Output length: {len(output)}, Error: {bool(error)}"
        )
        
        return CodeResponse(
            output=output,
            error=error,
            execution_time=exec_time,
            session_id=request.session_id
        )
        
    except Exception as e:
        logger.error(f"Unexpected server error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@app.post("/submit", response_model=CodeSubmitResponse)
async def sumbit_code_handler(request: CodeSubmitRequest, background_tasks:BackgroundTasks):
    """处理代码执行请求"""
    if not request.code.strip():
        raise HTTPException(
            status_code=400,
            detail="Code cannot be empty"
        )
    logger.info(f"Submitting code snippet (timeout: {request.timeout}s)")
    try:

        background_tasks.add_task(execute_python_code, request.code, request.session_id, request.timeout)
        logger.info(f"Task sumbitted (timeout: {request.timeout}s)")
        return CodeSubmitResponse(
            status="success",
            session_id=request.session_id
        )

    except Exception as e:
        logger.error(f"Unexpected server error: {str(e)}", exc_info=True)
        # raise HTTPException(
        #     status_code=500,
        #     detail=f"Internal server error: {str(e)}"
        # )
        return CodeSubmitResponse(
            status="fail",
            session_id=request.session_id
        )


    



if __name__ == "__main__":
    import os

    PORT = os.getenv('PORT', 40001)

    uvicorn.run(
        "tool_server:app", 
        host="0.0.0.0", 
        port=int(PORT),
        lifespan="on",
        workers=1
        # reload=True
    )