import json, os, sys, time, traceback
from uuid import uuid4
import tiktoken
from transformers import AutoTokenizer
import asyncio
current_dir = os.path.dirname(__file__)
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, '..'))

from utils.llm_caller import llm_call  
from pdf_read import read_pdf_from_url  


with open(f"{current_dir}/../../../../configs/paper_agent.json", "r") as f:
    paper_config = json.load(f)

def split_pdf_info(pdf_info: str, model: str):
    if "gpt" in model:
        tokenizer = tiktoken.encoding_for_model("gpt-4o")
        chunk_token_limit = 120000
    elif model == "deepseek-r1":
        tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/deepseek-r1", trust_remote_code=True)
        chunk_token_limit = 120000
    else:
        tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen-72B", trust_remote_code=True)
        chunk_token_limit = 30000
    all_tokens = tokenizer.encode(pdf_info)
    chunks = []
    start = 0
    while start < len(all_tokens):
        end = min(start + chunk_token_limit, len(all_tokens))
        chunk_tokens = all_tokens[start:end]
        chunks.append(tokenizer.decode(chunk_tokens))
        start = end
    return chunks

async def paper_qa_link(link: str, query: str, llm: str = None):
    try:
        retry_count = 0
        max_retries = 3
        pdf_info = None
        while retry_count < max_retries:
            pdf_info = await read_pdf_from_url(link)
            if pdf_info:
                break
            retry_count += 1
            await asyncio.sleep(1)

        if not pdf_info:
            return {"content":"Failed to download or parse PDF", "urls":[], "score":-1}

        prompt_template = paper_config["paperQA_prompt"]
        USE_LLM = llm if llm else paper_config["USE_MODEL"]

        try:
            print(f"use {USE_LLM} to parse PDF")
            chunks = split_pdf_info(pdf_info, USE_LLM)
            final_query = prompt_template.format(user_query=query, pdf_info=chunks[0])
            final_response = await llm_call(
                query=final_query,
                model_name=USE_LLM
            )
        except Exception as e:
            USE_LLM = paper_config["BASE_MODEL"]
            print(f"origin llm parse failed, use {USE_LLM} to parse PDF: {e}")
            chunks = split_pdf_info(pdf_info, USE_LLM)
            final_query = prompt_template.format(user_query=query, pdf_info=chunks[0])
            final_response = await llm_call(
                query=final_query,
                model_name=USE_LLM
            )
    except Exception as e:
        print(traceback.format_exc())
        final_response = "Failed to parse paper"
    final_result = {"content":final_response, "urls":[], "score":1}
    return final_result
    
async def main():
    response = await paper_qa_link(
        "https://arxiv.org/pdf/2405.12229",
        "What is the main idea of the paper?",
        llm="gpt-4o"
    )
    print(response)

if __name__ == "__main__":
    asyncio.run(main())

