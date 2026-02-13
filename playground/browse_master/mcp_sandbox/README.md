# Code Execution Server

This repository provides a basic implementation of a **code execution server**, designed primarily for **Xmaster** ([paper](https://arxiv.org/abs/2507.05241), [code](https://github.com/sjtu-sai-agents/X-Master)) and **Browse Master** ([paper](https://arxiv.org/abs/2508.09129) [code](https://github.com/sjtu-sai-agents/Browse-Master)). The full implementation is used in [SciMaster](https://scimaster.bohrium.com). 

Due to the proprietary nature of the full code, this repository only includes an **open-source framework** and the **basic components** required for code execution. It also includes a simple **network search tool** implementation.

> **⚠️ Warning**: This is a basic code execution server without virtualization or safety protections. For added security, consider running it within **Docker** or **Apptainer** containers as necessary.


---

## 🛠️ Setup

### Environment

Clone this repository and navigate to the project directory and install the required dependencies:

```bash
cd mcp_sandbox/
pip install -r requirements.txt
```

### Tools

- setup the serper key in `configs/web_agent.json`
- setup the models' api key in `configs/llm_call.json`



---

## 🚀 Deploy the Code Execution Server

### Step 1: Start the API Server

We will first start the API server used by the tools. This API server proxies all search-related services, including:

- [Serper](https://serper.dev/)'s Google Search Service
- A series of Model APIs

Navigate to the api_proxy directory and start the API server:
```bash
cd api_proxy
python api_server.py
```

### Step 2: Deploy the Server

Deploy the server by running the following script in the `MCP` directory:

```bash
cd MCP
bash deploy_server.sh
```

---

## 📝 Usage

### Sending a Request

To send a request to the server, use the following `curl` command:

```bash
curl -X POST "http://<your-server-url>/execute" \
     -H "Content-Type: application/json" \
     -d '{"code": "<your code here>"}'
```

### ⚡ Benchmarking

For benchmarking, you can run the following command to test the server's performance:

```bash
bash benchmarking/pressure.sh 100 100 10 benchmarking/script.lua http://127.0.0.1:30008
```

Example output:

```
Running 10s test @ http://127.0.0.1:30008/execute
  100 threads and 100 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency    50.21ms   47.15ms 296.96ms   53.20%
    Req/Sec    24.13     13.58   130.00     54.99%
  23185 requests in 10.10s, 4.27MB read
Requests/sec:   2295.61
Transfer/sec:    432.74KB
```

---


