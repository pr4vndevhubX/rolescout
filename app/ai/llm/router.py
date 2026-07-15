"""
LLMRouter — the only entry point application code uses to talk to any LLM.

    from app.ai.llm import llm_router
    text = llm_router.run(task="resume_parse", prompt=..., system=...)

Responsibilities:
- Resolve the task to (tier, params) from the registry.
- Walk the configured provider chain in priority order (Groq -> Gemini ->
  OpenRouter -> OpenAI -> Ollama by default) and FAIL OVER between providers,
  so a rate-limited free tier or missing paid key never takes the app down.
- Retry transient failures per provider with exponential backoff.
- Raise a single, predictable exception type (LLMRouterError).
"""

import logging
import time

from app.ai.llm.base import LLMProvider, LLMError
from app.ai.llm.registry import TASK_ROUTES, configured_provider_specs
from app.ai.llm.providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class LLMRouterError(Exception):
    """Raised when a task cannot be completed on any configured provider."""


class LLMRouter:
    def __init__(
        self,
        max_attempts: int = 2,
        backoff_base_seconds: float = 1.0,
        provider_chain: list[LLMProvider] | None = None,
    ):
        """
        max_attempts: attempts PER PROVIDER before failing over to the next.
        provider_chain: explicit providers (tests); default = build from config.
        """
        self._providers: dict[str, LLMProvider] = {}
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._chain_override = provider_chain

    def _chain(self) -> list[LLMProvider]:
        if self._chain_override is not None:
            return self._chain_override
        chain = []
        for spec in configured_provider_specs():
            if spec.name not in self._providers:
                self._providers[spec.name] = OpenAICompatibleProvider(spec)
            chain.append(self._providers[spec.name])
        return chain

    def run(
        self,
        *,
        task: str,
        prompt: str,
        system: str | None = None,
        **overrides,
    ) -> str:
        """
        Executes `task` with its configured route. Keyword overrides
        (temperature, max_tokens, json_mode, model) apply per call.
        A `model` override pins the model name on every provider tried.
        """
        route = TASK_ROUTES.get(task)
        if route is None:
            raise LLMRouterError(
                f"Unknown LLM task: '{task}'. Register it in app/ai/llm/registry.py"
            )

        chain = self._chain()
        if not chain:
            raise LLMRouterError("No LLM provider configured — set one key in .env")

        last_error: Exception | None = None
        for provider in chain:
            model = overrides.get("model") or provider.model_for(route.tier)
            params = {
                "model": model,
                "temperature": overrides.get("temperature", route.temperature),
                "max_tokens": overrides.get("max_tokens", route.max_tokens),
                "json_mode": overrides.get("json_mode", route.json_mode),
            }

            for attempt in range(1, self._max_attempts + 1):
                try:
                    return provider.complete(prompt=prompt, system=system, **params)
                except LLMError as e:
                    last_error = e
                    if attempt < self._max_attempts:
                        delay = self._backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            "LLM task '%s' on %s attempt %d/%d failed: %s — retrying in %.1fs",
                            task, provider.name, attempt, self._max_attempts, e, delay,
                        )
                        time.sleep(delay)

            logger.warning(
                "LLM task '%s': provider '%s' exhausted after %d attempts — failing over",
                task, provider.name, self._max_attempts,
            )

        tried = ", ".join(p.name for p in chain)
        raise LLMRouterError(
            f"LLM task '{task}' failed on all providers ({tried}): {last_error}"
        ) from last_error


# Module-level singleton — providers and their HTTP clients are reused app-wide.
llm_router = LLMRouter()
