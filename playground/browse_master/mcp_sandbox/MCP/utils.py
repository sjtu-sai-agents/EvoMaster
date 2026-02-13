from flask import session
from pydantic import BaseModel
from typing import Optional, Tuple, Dict, Any
import os
import asyncio
import requests


from mcp_manager import MCPManager
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pyext import RuntimeModule, _RuntimeModule
import os,sys,json
current_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(current_dir, "../configs/mcp_config.json"), "r") as f:
    config = json.load(f)



class CodeRequest(BaseModel):
    code: str
    timeout: Optional[int] = 180  # 默认超时30秒
    session_id:str = "test_id"

class CodeResponse(BaseModel):
    output: str
    error: Optional[str]
    execution_time: float
    session_id:str 


class CodeSubmitRequest(BaseModel):
    code:str
    timeout: Optional[int] = 180
    session_id: str = "test_id"


class CodeSubmitResponse(BaseModel):
    status: str
    session_id: str



class SandboxStreamRequest(BaseModel):
    session_id:str
    item:Dict[str, Any]

class SandboxStreamResponse(BaseModel):
    session_id:str
    flag:bool


def create_lifespan(manager:MCPManager, temp_dir:str):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print("Lifespan startup")
        await manager.ready()
        yield
        print("Lifespan shutdown")
        for client in manager.client_list:
            await client.cleanup()
    return lifespan






agent_tools = ["browse_master", "info_master", "intern_s1"]
browse_comp_tools = ["batch_search_and_filter"]

def build_tools_functions(manager:MCPManager):
    initial = '''import sys, os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(os.path.dirname(current_dir)))
from tool_caller import call_tool\n'''
    code = ""
    for tool in manager.get_tools():
        schema = tool.get("input_schema")
        arg = ""
        arg_dict = "    tool_args = {"
        if schema:
            for in_arg in schema.get("properties").keys():
                default = ""
                if not (in_arg in schema.get("required", [])):
                    
                    value = schema["properties"][in_arg].get("default")
                    if isinstance(value, str):
                        default = f"='{value}'"
                    else:
                        default = "=" + str(value)
                arg += f"{in_arg}{default},"
                arg_dict += f"'{in_arg}':{in_arg},"
        arg = arg.rstrip(",")
        arg_dict = arg_dict.rstrip(",") + "}"
        if (tool['name'] not in agent_tools) and (tool['name'] not in browse_comp_tools):
            code += f"def {tool['name']}({arg}):\n{arg_dict}\n    inform_handler.post_tool_start('{tool['name']}')\n    result = call_tool('{tool['name']}', tool_args, inform_handler.session_id)\n    inform_handler.post_tool_result('{tool['name']}', result)\n    return result\n"
        
        elif tool['name'] in browse_comp_tools:
            code += f"def {tool['name']}({arg}):\n{arg_dict}\n    tool_args['session_id']=inform_handler.session_id\n    inform_handler.post_tool_start('{tool['name']}')\n    result = call_tool('{tool['name']}', tool_args, inform_handler.session_id)\n    inform_handler.post_tool_result('{tool['name']}', result)\n    return result\n"
        
        else:
            code += f"def {tool['name']}({arg}):\n{arg_dict}\n    tool_args['stream_id']=inform_handler.session_id\n    inform_handler.post_tool_start('{tool['name']}')\n    result = call_tool('{tool['name']}', tool_args, inform_handler.session_id)\n    inform_handler.post_tool_result('{tool['name']}', result)\n    return result\n"
    return initial + code



def form_item(main_stream_type:str, content:str, stream_state:str):
    default = {
        "main_stream_type":main_stream_type,
        "sub_stream_type":"",
        "content": content,
        "from_sandbox": True,
        "stream_state":stream_state,
        "other_info": {}
    }
    return default



def post_item_info(session_id:str, item:Dict[str, Any]):
    url = config['mcp_server_url']
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "session_id":session_id,
        "item":item
    }
    resp = requests.post(
        f"{url}/put_item",
        headers=headers,
        json=payload
    )
    # print(resp.json())
    # print(resp.content)
    response = resp.json()

    return response



class SessionInformHandler:
    def __init__(self, session_id:str):
        self.session_id = session_id
        self.async_inform_queue = asyncio.Queue()
        
    
    def post_tool_start(self, tool_name:str,):
        print(f'-----------{self.session_id}---------------')
        formated_item = form_item("tool_result", "", "running")
        formated_item["other_info"]["tool_name"] = tool_name

        response = post_item_info(self.session_id, formated_item)
    
    def post_tool_result(self, tool_name:str, item):
        print(f'-----------{self.session_id}---------------')
        # print(item)

        formated_item = form_item("tool_result", "", "running")
        formated_item['other_info'][tool_name] = item

        response = post_item_info(self.session_id, formated_item)
        
    



class SessionManager:
    def __init__(self, mcp_manager:MCPManager):
        self.sessions: Dict[str, _RuntimeModule] = {}
        self.mcp_manager = mcp_manager
        

    def build_lib(self):
        return build_tools_functions(self.mcp_manager)

    def get_session(self, session_id: str) -> _RuntimeModule:
        
        if session_id not in self.sessions:
            # 使用pyext.RuntimeModule创建可重复执行的模块
            code_string = self.build_lib()
            # print(code_string)
            self.sessions[session_id] = RuntimeModule.from_string(f"session_{session_id}","", "")
            # 初始化 runtime module 对应session 管理的变量和函数，异步队列收取当前代码流式返回
            self.sessions[session_id].__dict__.update(
                {"inform_handler":SessionInformHandler(session_id=session_id)}
            )

            
            exec(code_string, self.sessions[session_id].__dict__)

        return self.sessions[session_id]
    
    def clear_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
