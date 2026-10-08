"""DeepSeek chat completions in JSON mode (OpenAI-compatible API; spec §7)."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import httpx

from . import quota
from .config import Settings
from .util import PvmError

PLAN_ENDPOINTS = ("/api/plan/", "/api/coding/")  # Volcano's subscription plans, which bill text in AFP

# AFP per 10,000 tokens (input, output) on the Agent Plan (docs, 2026-09-29). List prices: deepseek-v4.1-flash is at
# half price until 2026-10-30, so the ledger overstates it until then. Unlisted models count at the highest text rate.
PLAN_TEXT_RATES = {
    "deepseek-v4.1-flash": (2.5, 2.5),
    "deepseek-v4-flash": (0.5, 0.5),
    "deepseek-v4-pro": (5.5, 5.5),
}
UNLISTED_TEXT_RATE = (10.0, 10.0)


@dataclass
class LlmReply:
    data: dict
    model: str
    usage: dict = field(default_factory=dict)


class LLM:
    def __init__(self, base_url: str, api_key: str, model: str, *, transport: httpx.BaseTransport | None = None):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model
        self.transport = transport  # tests pass an httpx.MockTransport
        on_plan = any(part in self.base_url + "/" for part in PLAN_ENDPOINTS)
        self.rates = PLAN_TEXT_RATES.get(model.removesuffix("-beta"), UNLISTED_TEXT_RATE) if on_plan else None

    def _record(self, usage: dict, project: str | None) -> None:
        """Every answered call on the plan costs AFP, failed attempts included."""
        if not self.rates or not usage:
            return
        tokens_in, tokens_out = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        afp = (tokens_in * self.rates[0] + tokens_out * self.rates[1]) / 10_000
        quota.record(math.ceil(afp), kind="text", project=project, model=self.model,
                     note=f"{tokens_in} in, {tokens_out} out")

    def json(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 8000,
             tries: int = 3, project: str | None = None) -> LlmReply:
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
                self._record(payload.get("usage") or {}, project)
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
        raise PvmError("pvm plan and pvm review need an LLM key: AGENT_PLAN_API_KEY (deepseek-v4.1-flash on the plan) "
                       "or PVM_LLM_API_KEY (DeepSeek's API). Without one, write the storyboard by hand or with a "
                       "coding agent (AGENTS.md); pvm check still verifies every excerpt")
    return LLM(settings.llm_base_url, settings.llm_api_key, settings.llm_model)
