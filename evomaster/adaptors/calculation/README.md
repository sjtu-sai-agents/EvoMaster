# Calculation path adaptor (bohr-agent-sdk)

与 _tmp/MatMaster 一致：**HTTPS 存储走 Bohrium 鉴权**；**executor** 按“同步/异步”区分：同步任务传 `None`，其余传指定镜像/机型的 Bohrium executor（鉴权从 .env 注入）。

## 注入参数

- **executor**（依配置 `mcp.calculation_executors`）：
  - 若工具名在该服务器的 `sync_tools` 中 → 传 `None`（同步执行，跑在服务端默认环境）。
  - 否则若该服务器配置了 `executor` 模板（镜像/机型）→ 传 Bohrium executor（鉴权由 `evomaster.env.inject_bohrium_executor` 从 .env 注入）。
  - 未配置或无模板 → `None`。
- **storage**：`get_bohrium_storage_config()`（来自 `evomaster.env.bohrium`），从 `.env` 的 `BOHRIUM_ACCESS_KEY`、`BOHRIUM_PROJECT_ID` 读取。
- **输入路径**：本地/workspace 文件在配置了 OSS 时上传并替换为 https URL 再调用 MCP。

## /workspace 映射

Agent 可能传入 `/workspace/Fe_bcc.cif`。本 adaptor 将 `/workspace/` 映射为当前 session 的 `workspace_path`，即 `workspace_path/Fe_bcc.cif`，再判断文件是否存在并上传 OSS。

## 依赖

- **运行环境**：与执行 `python run.py` 的进程相同。ConfigManager 在加载配置时从**项目根目录**查找并加载 `.env`，故 OSS/Bohrium 相关变量需写在**项目根目录的 .env** 中（或在该进程的 shell 里 export）。
- 环境变量：`OSS_ENDPOINT`、`OSS_BUCKET_NAME`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`（本地文件上传到 OSS 时必填）；Bohrium 鉴权见上。
- `pip install oss2`（已列入主依赖）。
