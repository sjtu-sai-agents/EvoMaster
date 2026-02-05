# 1. 基础镜像
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

# 2. 避免安装过程中的交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# # 3. 替换为阿里云源（可选，为了国内下载加速，如果不需要可删除这行）
# RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
#     sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 4. 安装添加 PPA 所需的工具和常用工具
RUN apt-get update && apt-get install -y \
    software-properties-common \
    vim \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 5. 添加 deadsnakes PPA (这里包含 Python 的各种新旧版本)
RUN add-apt-repository ppa:deadsnakes/ppa

# 6. 安装 Python 3.12 及其开发库
# 注意：python3.12-dev 和 python3.12-venv 对于后续安装 pip 包非常重要
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3.12-venv \
    && rm -rf /var/lib/apt/lists/*

# 7. 安装 pip (专门为 Python 3.12)
# Ubuntu 的 python3-pip 包通常对应系统默认的 3.10，所以我们用脚本安装最新 pip 到 3.12
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# 8. 设置默认 Python 版本 (修改软链接)
# 这样输入 python 或 python3 都会自动指向 python3.12
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1

# # 9. 配置 pip 默认使用清华源加速 (可选，强烈推荐)
# RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 10. 设置工作目录
WORKDIR /data/xinyu
