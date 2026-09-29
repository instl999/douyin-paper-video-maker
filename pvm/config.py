"""Settings from environment variables and the repo's .env file (environment wins)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .util import ROOT, read_text

AGENT_PLAN_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"
AGENT_PLAN_TTS_URL = "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional"

# Agent Plan quotas for image/voice models (docs, 2026-09): only daily (= half of monthly) and monthly limits apply.
PLAN_TIERS = {
    "small": {"monthly": 20_000, "daily": 10_000},
    "medium": {"monthly": 100_000, "daily": 50_000},
    "large": {"monthly": 250_000, "daily": 125_000},
    "max": {"monthly": 500_000, "daily": 250_000},
}

# Keys are checked in this order. ARK_API_KEY is what Volcano's Codex setup guide exports for Agent Plan.
API_KEY_VARS = ("AGENT_PLAN_API_KEY", "ARK_AGENT_PLAN_API_KEY", "AGENT_API_KEY", "ARK_API_KEY")


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    api_key_var: str | None
    ark_base_url: str
    image_provider: str
    image_model: str
    image_concurrency: int
    tts_engine: str
    tts_url: str
    tts_speaker: str
    tts_speed: int
    tts_instruction: str
    edge_voice: str
    edge_rate: str
    plan_tier: str
    afp_monthly_budget: int
    afp_daily_budget: int | None  # explicit override; otherwise quota.daily_allowance() paces the month
    afp_per_image: int  # planning figure from the spec (§12); revalidate against the account
    image_attempts: int  # retry budget per image, OCR failures included (spec §8.7)
    contact_email: str | None
    s2_api_key: str | None
    openalex_api_key: str | None
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    style: str
    x264_preset: str
    crf: int
    bgm: str
    allow_system_fonts: bool
    ai_label: str  # visible AI-content label; "none" disables it (see spec §13.2 before doing that)

    @property
    def tier_limits(self) -> dict[str, int]:
        return PLAN_TIERS.get(self.plan_tier, PLAN_TIERS["small"])

    def resolved_tts_engine(self) -> str:
        if self.tts_engine in ("ark", "edge"):
            return self.tts_engine
        return "ark" if self.api_key else "edge"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = {**load_dotenv(ROOT / ".env"), **os.environ}

    def get(name: str, default: str = "") -> str:
        value = env.get(name, "")
        return value.strip() if value and value.strip() else default

    def get_int(name: str, default: int) -> int:
        try:
            return int(get(name, str(default)))
        except ValueError:
            return default

    api_key, api_key_var = None, None
    for var in API_KEY_VARS:
        if get(var):
            api_key, api_key_var = get(var), var
            break

    # LLM: a DeepSeek key of its own wins; otherwise the Agent Plan key covers the planner too, because the plan
    # includes DeepSeek text models (verified 2026-09-28: deepseek-v4-pro-beta, v4.1-flash, v4-flash-beta).
    ark_base = get("PVM_ARK_BASE_URL", AGENT_PLAN_BASE_URL).rstrip("/")
    llm_key = get("PVM_LLM_API_KEY") or None
    if llm_key or not api_key:
        llm_base, llm_model = get("PVM_LLM_BASE_URL", "https://api.deepseek.com"), get("PVM_LLM_MODEL", "deepseek-chat")
    else:
        llm_key = api_key
        llm_base, llm_model = get("PVM_LLM_BASE_URL", ark_base), get("PVM_LLM_MODEL", "deepseek-v4-pro-beta")

    tier = get("PVM_PLAN_TIER", "small").lower()
    monthly_default = PLAN_TIERS.get(tier, PLAN_TIERS["small"])["monthly"]
    daily_override = get("PVM_AFP_DAILY_BUDGET")
    return Settings(
        api_key=api_key,
        api_key_var=api_key_var,
        ark_base_url=ark_base,
        image_provider=get("PVM_IMAGE_PROVIDER", "ark").lower(),
        image_model=get("PVM_IMAGE_MODEL", "doubao-seedream-5.0-lite"),
        image_concurrency=max(1, get_int("PVM_IMAGE_CONCURRENCY", 2)),
        tts_engine=get("PVM_TTS_ENGINE", "auto").lower(),
        tts_url=get("PVM_TTS_URL", AGENT_PLAN_TTS_URL),
        tts_speaker=get("PVM_TTS_SPEAKER", "zh_male_jieshuoxiaoming_uranus_bigtts"),
        tts_speed=get_int("PVM_TTS_SPEED", 10),
        tts_instruction=get("PVM_TTS_INSTRUCTION", ""),
        edge_voice=get("PVM_EDGE_VOICE", "zh-CN-YunxiNeural"),
        edge_rate=get("PVM_EDGE_RATE", "+10%"),
        plan_tier=tier,
        afp_monthly_budget=get_int("PVM_AFP_MONTHLY_BUDGET", monthly_default),
        afp_daily_budget=get_int("PVM_AFP_DAILY_BUDGET", 0) if daily_override else None,
        afp_per_image=get_int("PVM_AFP_PER_IMAGE", 99),
        image_attempts=max(1, get_int("PVM_IMAGE_ATTEMPTS", 3)),
        contact_email=get("PVM_CONTACT_EMAIL") or None,
        s2_api_key=get("SEMANTIC_SCHOLAR_API_KEY") or None,
        openalex_api_key=get("OPENALEX_API_KEY") or None,
        llm_base_url=llm_base.rstrip("/"),
        llm_api_key=llm_key,
        llm_model=llm_model,
        style=get("PVM_STYLE", "paper-cut"),
        x264_preset=get("PVM_X264_PRESET", "veryfast"),
        crf=get_int("PVM_CRF", 20),
        bgm=get("PVM_BGM", "none"),
        allow_system_fonts=get("PVM_ALLOW_SYSTEM_FONTS", "0").lower() in ("1", "true", "yes"),
        ai_label=get("PVM_AI_LABEL", "含AI生成内容"),
    )
