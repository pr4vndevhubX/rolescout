"""
One provider class for every OpenAI-compatible API.

OpenAI, Groq, Google Gemini, OpenRouter, and Ollama all expose the same
chat-completions wire format, so a single class parameterized by
(base_url, api_key, models) covers all of them. This file is the only place
in the codebase allowed to import the openai SDK.
"""

from openai import OpenAI, OpenAIError

from app.ai.llm.base import LLMProvider, LLMError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, spec) -> None:
        """spec: an app.ai.llm.registry.ProviderSpec."""
        self.name = spec.name
        self._fast_model = spec.fast_model
        self._smart_model = spec.smart_model
        # One client per provider instance; reused across all requests.
        # timeout: without it the SDK waits up to 10 minutes on a stuck
        # connection — the router's retry/failover should kick in far sooner.
        # max_retries=0: retrying is the router's job, not the SDK's.
        self._client = OpenAI(
            api_key=spec.api_key or "not-needed",  # Ollama ignores the key
            base_url=spec.base_url,                 # None -> api.openai.com
            timeout=90.0,
            max_retries=0,
        )

    def model_for(self, tier: str) -> str:
        return self._smart_model if tier == "smart" else self._fast_model

    def complete(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        json_mode: bool = False,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": model,
            "temperature": temperature,
            # max_tokens (not max_completion_tokens): the one spelling every
            # compatible backend (Groq/Gemini/Ollama/OpenRouter) accepts.
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except OpenAIError as e:
            raise LLMError(f"{self.name} completion failed (model={model}): {e}") from e

        content = response.choices[0].message.content
        if content is None:
            raise LLMError(f"{self.name} returned empty content (model={model})")
        return content
