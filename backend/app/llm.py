import json
from typing import Protocol

from openai import OpenAI


class LLM(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def chat_json(self, system: str, user: str) -> dict: ...


class OpenAILLM:
    def __init__(self, api_key: str, chat_model: str, embedding_model: str):
        self.client = OpenAI(api_key=api_key)
        self.chat_model = chat_model
        self.embedding_model = embedding_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 100):
            resp = self.client.embeddings.create(model=self.embedding_model, input=texts[i : i + 100])
            vectors.extend(d.embedding for d in resp.data)
        return vectors

    def chat_json(self, system: str, user: str) -> dict:
        resp = self.client.chat.completions.create(
            model=self.chat_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return json.loads(resp.choices[0].message.content or "{}")
