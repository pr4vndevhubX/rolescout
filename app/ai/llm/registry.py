"""
Task routing table + provider registry — the single place where
"which model handles which task" and "which providers exist" live.

Routing philosophy (cost-aware, no-single-vendor):
- Tasks declare a TIER, not a model: "fast" for cheap structured extraction,
  "smart" for reasoning/generation (tailoring, cover letters, agent planning).
- Each provider maps tiers to its own models (see LLM_MODELS in config.py).
- The router walks the configured provider chain in priority order and fails
  over automatically — a missing/rate-limited OpenAI key never stops the app
  when Groq/Gemini/Ollama are available.
- Non-LLM work (embeddings, skill taxonomy matching) never enters this table —
  it stays on local open-source models (sentence-transformers) or plain Python.
"""

from dataclasses import dataclass

from app.core.config import (
    CONFIGURED_LLM_PROVIDERS,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    LLM_MODELS,
    OLLAMA_BASE_URL,
    OPENAI_API_KEY,
    OPENROUTER_API_KEY,
)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    api_key: str | None
    base_url: str | None          # None -> the OpenAI default endpoint
    fast_model: str
    smart_model: str


_BASE_URLS = {
    "openai": None,
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": OLLAMA_BASE_URL,
}

_API_KEYS = {
    "openai": OPENAI_API_KEY,
    "groq": GROQ_API_KEY,
    "gemini": GEMINI_API_KEY,
    "openrouter": OPENROUTER_API_KEY,
    "ollama": "ollama",  # Ollama requires no key; SDK just needs a non-empty string
}

PROVIDER_SPECS: dict[str, ProviderSpec] = {
    name: ProviderSpec(
        name=name,
        api_key=_API_KEYS[name],
        base_url=_BASE_URLS[name],
        fast_model=LLM_MODELS[name]["fast"],
        smart_model=LLM_MODELS[name]["smart"],
    )
    for name in _BASE_URLS
}


def configured_provider_specs() -> list[ProviderSpec]:
    """Provider specs for every configured provider, in failover priority order."""
    return [PROVIDER_SPECS[name] for name in CONFIGURED_LLM_PROVIDERS if name in PROVIDER_SPECS]


@dataclass(frozen=True)
class TaskRoute:
    tier: str = "fast"            # "fast" | "smart"
    temperature: float = 0.0
    max_tokens: int = 1000
    json_mode: bool = False


TASK_ROUTES: dict[str, TaskRoute] = {
    # --- structured extraction (cheap, deterministic) ---
    "resume_parse": TaskRoute(tier="fast", temperature=0.0, max_tokens=2000, json_mode=True),
    "job_fit_analysis": TaskRoute(tier="fast", temperature=0.0, max_tokens=500, json_mode=True),
    # --- generation (reasoning-heavy, runs on each provider's best model) ---
    "resume_tailoring": TaskRoute(tier="smart", temperature=0.3, max_tokens=1800, json_mode=True),
    "cover_letter": TaskRoute(tier="smart", temperature=0.5, max_tokens=900),
}
