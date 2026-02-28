# 没有server代码的要sse部署
设置conda的shell钩子
eval "$(/root/miniconda3/bin/conda shell.bash hook)"
重新加载bash配置
source ~/.bashrc

## fmp server
export FMP_API_KEY=k7akB7EWZBqNtgggXDCUgpDjBjkjb1sq
python -m src.server --sse --port 8000

# 有server代码的
## 第一步：接入工具
### 本地client导入 
在 server 目录下新建目录，每个目录有一个用fastmcp装饰的工具实例。
以 server/PubChem-MCP-Server/pubchem_server.py 为例，里面定义了一个mcp工具
```
@mcp.tool()
async def search_pubchem_by_name(name: str, max_results: int = 5) -> List[Dict[str, Any]]:
    logging.info(f"Searching for compounds with name: {name}, max_results: {max_results}")
    """
    Search for chemical compounds on PubChem using a compound name.

    Args:
        name: Name of the chemical compound
        max_results: Maximum number of results to return (default: 5)

    Returns:
        List of dictionaries containing compound information
    """
    try:
        results = await asyncio.to_thread(search_by_name, name, max_results)
        return results
    except Exception as e:
        return [{"error": f"An error occurred while searching: {str(e)}"}]
```

文件定义好之后需要在 config/server_list.json中指定对应的py文件路径(在这里是server/PubChem-MCP-Server/pubchem_server.py)，同时一些简单的mcp服务可以直接在mcp_server.py文件中定义，默认会从中导入


### sse client 导入
在 config/server_list.json 里面加入需要的sse链接即可
```
[
    "server/Agents-Server/agents_server.py",
    "server/BASE-TOOL-Server/base_tool_server.py",
    "https://dpa-uuid1750659890.app-space.dplink.cc/sse?token=b42b991d062341fba15a9f7975e190b0"
]
```

## 第二步：进入docker
docker exec -it backend_server_final /bin/bash
tmux attach -t server
1. 找到对应运行的server窗口，停止当前的服务
pkill -f tool_server_session.py

2. 重启
cd /mnt/tool_backends/MCP
bash deploy_server.sh


## 第三步：测试是否成功部署
退出docker，在外侧运行对应工具的测试文件
```
python /home/ubuntu/shuotang/git_repo/Agent/tool_backends/test.py
```