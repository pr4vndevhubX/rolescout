"""
LangChain chat model for the agent — built from the SAME provider chain as
the classic LLM router, so the agent inherits the no-single-vendor policy:
whichever of Groq/Gemini/OpenRouter/OpenAI/Ollama is configured first becomes
the primary brain, the rest are automatic fallbacks.
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.ai.llm.registry import configured_provider_specs


def _chat_model_for_spec(spec, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=spec.smart_model,          # agent planning always runs on the smart tier
        api_key=spec.api_key or "not-needed",
        base_url=spec.base_url,
        temperature=temperature,
        timeout=90,
        max_retries=1,
    )


@lru_cache(maxsize=4)
def get_agent_chat_model(temperature: float = 0.0):
    """Primary chat model with the remaining providers as LangChain fallbacks."""
    specs = configured_provider_specs()
    if not specs:
        raise RuntimeError("No LLM provider configured — set one key in .env")

    primary = _chat_model_for_spec(specs[0], temperature)
    fallbacks = [_chat_model_for_spec(s, temperature) for s in specs[1:]]
    return primary.with_fallbacks(fallbacks) if fallbacks else primary
