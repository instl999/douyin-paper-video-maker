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


PLAN_ENDPOINTS = ("/api/plan/", "/api/coding/")  # Volcano's subscription plans: their text models are for AI tools only


def make_llm(settings: Settings) -> LLM:
    # The Agent/Coding Plan terms (docs, 2026-09-29): its text models must not be used through API calls, and doing so
    # risks suspension of the subscription or a ban. pvm's plan and review are API calls, so they need their own key.
    if any(part in settings.llm_base_url + "/" for part in PLAN_ENDPOINTS) or (
            settings.llm_api_key and settings.llm_api_key == settings.api_key):
        raise PvmError("pvm plan and pvm review cannot use the Agent Plan: its terms forbid API calls to its text "
                       "models (risk of suspension or a ban). Set PVM_LLM_API_KEY to a DeepSeek key, or point "
                       "PVM_LLM_BASE_URL at Ark pay-as-you-go with a key of its own")
    if not settings.llm_api_key:
        raise PvmError("pvm plan and pvm review need PVM_LLM_API_KEY (a DeepSeek key by default; the Agent Plan key "
                       "does not cover text models). Without one, write the storyboard by hand or with a coding agent "
                       "(AGENTS.md); pvm check still verifies every excerpt")
    return LLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
