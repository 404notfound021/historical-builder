"""LLM 调用封装 —— 支持硅基流动等 OpenAI 兼容 API"""

import os
import time
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    def __init__(self, config: dict):
        self.api_base = config["llm"]["api_base"]
        self.model = config["llm"]["model"]
        self.temperature = config["llm"].get("temperature", 0.3)
        self.max_tokens = config["llm"].get("max_tokens", 4096)
        self.max_retries = config["llm"].get("max_retries", 3)

        self.client = OpenAI(
            api_key=os.getenv("LLM_API_KEY"),
            base_url=self.api_base,
        )

    def chat(self, system_prompt: str, user_message: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

    def chat_with_retry(self, system_prompt: str, user_message: str) -> str:
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return self.chat(system_prompt, user_message)
            except Exception as e:
                last_error = e
                wait = 10 * (2 ** attempt)
                print(f"  [retry {attempt + 1}/{self.max_retries}] {e}，等待 {wait}s...")
                time.sleep(wait)
        raise RuntimeError(f"LLM 调用失败（已重试 {self.max_retries} 次）: {last_error}")
