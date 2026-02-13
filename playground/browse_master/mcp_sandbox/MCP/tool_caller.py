## FastAPI request call tool

import requests,json
import time
import os
from typing import Dict, Any
import os,sys
current_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(current_dir, '../configs/mcp_config.json'), 'r') as f:
    config = json.load(f)

url = config['mcp_server_url']

def post_item_info(session_id:str, item:Dict[str, Any]):
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




def call_tool(tool_name: str, tool_args: dict, session_id:str=None):
    print(f"################# session id: {session_id} ########################")
    item = {
        "main_stream_type":"tool_result",
        "sub_stream_type":"",
        "content": "",
        "from_sandbox": True,
        "stream_state": 'running',
        "other_info": {"call_tool":tool_name, "call_args":tool_args}
    }
    post_item_info(session_id, item)

    if tool_name is None:
        # 列出所有工具
        try:
            t1 = time.time()
            resp = requests.get(f"{url}/get_tool")
            result = resp.json()
            t2 = time.time()
            return {
                "tool_result": result,
                "tool_elapsed_time": t2 - t1
            }
        except Exception as e:
            print(f"Request failed: {e}")
            return None
    else:
        try:
            t1 = time.time()
            resp = requests.post(
                f"{url}/call_tool/{tool_name}",
                json=tool_args
            )
            result = resp.json()
            if result["status"]:
                t2 = time.time()
                return {
                    "tool_result": result["result"],
                    "tool_elapsed_time": t2 - t1
                }
            else:
                print(f"Tool error: {result['result']}")
                return None
        except Exception as e:
            print(f"Request failed: {e}")
            return None

def code_tool(code:str, timeout=1800):
    try:
        resp = requests.post(
            f"{url}/execute",
            json={"code":code, "timeout": timeout},
        )
        result = resp.json()
        return result
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def test():
    code = """
print(browse_master("1+1=?,do not use web_parse"))
"""
    
    result = code_tool(code)
    print(result)

import time
if __name__ == "__main__":
    test()
    exit()
    # print(call_tool("web_search", {"query": "what is the multi-modal learning"}))
    # 列出所有工具
    # result = call_tool(None, None)

    # print(result)
    # import asyncio
    # # rag搜索
    # begin_time = time.time()
    # result = call_tool("rag_batch_search", {"query": ["what is the multi-modal learning", "what is the multi-modal learning"]})
    # # end_time = time.time()

    # print(result)
    

    # 联网搜索
    # result = call_tool("web_search", {"query": "original artist of I'm Losing You song"})
    # print(result)
    # print(result)
    
    # 根据link和query解析网页具体内容
    # import concurrent.futures,time
    # result_list = []
    # begin = time.time()
    # with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
    #     futures = [executor.submit(call_tool, "web_parse_qwen", {'link': 'https://www.britannica.com/technology/artificial-intelligence', 'query': "What is main content of this page?"}) for _ in range(100)]
    #     results = [future.result() for future in concurrent.futures.as_completed(futures)]
    #     for result in results:
    #         result_list.append(result)
    # import pdb; pdb.set_trace()
    # end = time.time()
    # print(f"time cost: {end - begin} seconds")
    # print(result_list)
    result = call_tool("web_parse_nano", {'link': 'https://bohr.physics.berkeley.edu/classes/221/1112/notes/covariance.pdf', 'query': "What is main content of this page?"})
    print(result)
    # 数学计算
    # result = call_tool("parse_img", {"url": "https://i-blog.csdnimg.cn/blog_migrate/f4bc39ab34337400e97ff1d7dae70be0.png","query": "what is VLLM?"})
    # print(result)
    
    # 相关论文搜索
    # result = asyncio.run(call_tool("paper_search", {"query": "large language model", "max_num": 10}))
    # print(result)
    
    # 根据文献link和query解析具体内容
    # result = asyncio.run(call_tool("paper_parse", {"link": "https://arxiv.org/abs/2403.08271", 
    #                                               "title": "Humanity's Last Exam", 
    #                                               "query": "请解析以下论文的摘要：https://arxiv.org/abs/2403.08271"}))
    # print(result)
    
    # 图片解析
    # import os
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # import asyncio
    # image_path = os.path.join(current_dir, "Test", "test.png")
    # result = asyncio.run(call_tool("image_to_text", {"image_path" : image_path}))
    # print(result)
    
    # 根据query解析图片内容
    # image_path = os.path.join(current_dir, "Test", "word.png")
    # result = asyncio.run(call_tool("ask_question_about_image", {"image_path" : image_path, "question" : "请描述图片中是什么文字，具体内容是什么"}))
    # print(result)
    
    # 图片转latex
    # image_path = os.path.join(current_dir, "Test", "latex.png")
    # result = asyncio.run(call_tool("image2latex", {"image_path" : image_path}))
    # print(result)
    
    