import asyncio
import openai
import os
import sys,json
current_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(current_dir, '..', '..', '..', '..','configs', 'llm_call.json'), 'r') as f:
    config = json.load(f)


async def llm_call(query: str, model_name: str = "qwen-72b", max_retries: int = 3):
    retry_count = 0
    while retry_count < max_retries:
        try:
            client = openai.AsyncOpenAI(
                api_key=config[model_name]["authorization"],
                base_url=config[model_name]["url"]
            )
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": query}]
            )
            content = response.choices[0].message.content
            if isinstance(content, str) and content.strip():
                return content
            else:
                raise ValueError("Invalid content received, not a non-empty string")

        except Exception as e:
            retry_count += 1
            print(f"Attempt {retry_count} failed: {e}")
            if retry_count == max_retries:
                raise RuntimeError(f"llm_call_async failed after {max_retries} retries.") from e
            await asyncio.sleep(1)
    return None


if __name__ == "__main__":
    print(asyncio.run(llm_call("What is the Nerf?",model_name="gpt-4o")))
