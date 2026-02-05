# Env - 执行环境管理

Env 是 EvoMaster 的环境组件，负责管理执行环境和作业调度。

## 目录结构

- `base.py` - Env 抽象基类，定义标准接口
- `local.py` - LocalEnv 实现，在本地直接执行命令

## 核心类

### BaseEnv（base.py）
Env 的抽象基类，定义所有 Env 实现必须提供的接口：

- `setup()` / `teardown()` - 环境生命周期管理
- `get_session()` - 获取 Session 用于执行命令
- `submit_job(command, job_type)` - 提交作业
- `get_job_status(job_id)` - 查询作业状态
- `cancel_job(job_id)` - 取消作业

### LocalEnv（local.py）
本地环境实现，无需 Docker 或集群：

- 在本地直接执行命令
- 同步作业执行
- 支持作业状态查询
- 适合开发和测试阶段

### LocalSession（local.py）
本地 Session 实现：

- 使用 subprocess 直接执行命令
- 支持文件上传/下载（实际为本地复制）
- 工作在本地文件系统

## 使用示例

### 基础使用

```python
from evomaster.env import LocalEnv, LocalEnvConfig

# 创建本地环境
config = LocalEnvConfig(name="my_env")
env = LocalEnv(config)

# 设置环境
env.setup()

try:
    # 获取 Session 直接执行命令
    session = env.get_session()
    result = session.exec_bash("python --version")
    print(result["stdout"])

    # 提交作业
    job_id = env.submit_job("python -c 'print(123)'", job_type="debug")

    # 查询作业状态
    status = env.get_job_status(job_id)
    print(status)

finally:
    env.teardown()
```

### 使用上下文管理器

```python
with LocalEnv() as env:
    session = env.get_session()
    result = session.exec_bash("ls -la")
    print(result["stdout"])
```

## 设计特点

1. **简易实现** - 本地直接执行，无复杂依赖
2. **标准接口** - BaseEnv 定义统一的环境接口
3. **后向兼容** - 可轻松替换为 Docker、Kubernetes 等实现
4. **作业管理** - 支持作业提交、状态查询、取消等操作
5. **上下文管理** - 实现了 Python 上下文管理器接口

## 配置参数

### EnvConfig（基础配置）
- `name` - 环境名称
- `session_config` - Session 配置

### LocalEnvConfig（本地环境配置）
- 继承 EnvConfig 的所有配置
- 默认使用本地 Session

## 后续扩展

可在此基础上实现：
- `DockerEnv` - 使用 Docker 容器
- `KubernetesEnv` - 使用 Kubernetes 集群
- `RemoteEnv` - 连接远程服务器
- `RayEnv` - 使用 Ray 分布式框架
