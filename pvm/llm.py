"""DeepSeek chat completions in JSON mode (OpenAI-compatible API; spec §7)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from .config import Settings
from .util import PvmError


@dataclass
class LlmReply:
    data: dict
    model: str
    usage: dict = field(default_factory=dict)


class LLM:
    def __init__(self, base_url: str, api_key: str, model: str, *, transport: httpx.BaseTransport | None = None):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.transport = transport  # tests pass an httpx.MockTransport

    def json(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 8000,
             tries: int = 3) -> LlmReply:
        """One JSON object from the model. Empty or invalid output is a recoverable failure (spec §7.2)."""
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens, "stream": False,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        problem = "no attempt made"
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=15.0), transport=self.transport) as client:
            for _ in range(tries):
                try:
                    r = client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
                except httpx.HTTPError as e:
                    problem = f"network error: {e}"
                    continue
                if r.status_code in (429, 500, 502, 503):
                    problem = f"HTTP {r.status_code}"
                    continue
                if r.status_code != 200:
                    raise PvmError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
                payload = r.json()
                content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                if not content.strip():
                    problem = "empty response"  # JSON mode occasionally returns nothing; asking again helps
                    continue
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    problem = f"invalid JSON ({e})"
                    continue
                if isinstance(data, dict):
                    return LlmReply(data, payload.get("model", self.model), payload.get("usage") or {})
                problem = "the reply is not a JSON object"
        raise PvmError(f"LLM failed after {tries} tries: {problem}")


def make_llm(settings: Settings) -> LLM:
    if not settings.llm_api_key:
        raise PvmError("the planner needs PVM_LLM_API_KEY (DeepSeek) in .env")
    return LLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
