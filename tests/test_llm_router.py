import pytest

from app.ai.llm.base import LLMProvider, LLMError
from app.ai.llm.registry import TASK_ROUTES, TaskRoute, configured_provider_specs
from app.ai.llm.router import LLMRouter, LLMRouterError


class FakeProvider(LLMProvider):
    def __init__(self, name: str = "fake", fail_times: int = 0):
        self.name = name
        self.fail_times = fail_times
        self.calls = 0

    def model_for(self, tier: str) -> str:
        return f"{self.name}-{tier}-model"

    def complete(self, *, model, prompt, system=None, temperature=0.0,
                 max_tokens=1000, json_mode=False) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise LLMError("transient failure")
        return f"response-from-{model}"


@pytest.fixture
def test_task(monkeypatch):
    monkeypatch.setitem(TASK_ROUTES, "test_task", TaskRoute(tier="fast"))


def test_unknown_task_raises():
    router = LLMRouter(provider_chain=[FakeProvider()])
    with pytest.raises(LLMRouterError, match="Unknown LLM task"):
        router.run(task="does_not_exist", prompt="hi")


def test_routes_to_tier_model(test_task):
    router = LLMRouter(backoff_base_seconds=0, provider_chain=[FakeProvider("groq")])
    assert router.run(task="test_task", prompt="hi") == "response-from-groq-fast-model"


def test_smart_tier_uses_smart_model(monkeypatch):
    monkeypatch.setitem(TASK_ROUTES, "smart_task", TaskRoute(tier="smart"))
    router = LLMRouter(backoff_base_seconds=0, provider_chain=[FakeProvider("groq")])
    assert router.run(task="smart_task", prompt="hi") == "response-from-groq-smart-model"


def test_retries_transient_failures(test_task):
    provider = FakeProvider(fail_times=1)  # fails once, succeeds second
    router = LLMRouter(max_attempts=2, backoff_base_seconds=0, provider_chain=[provider])
    assert router.run(task="test_task", prompt="hi") == "response-from-fake-fast-model"
    assert provider.calls == 2


def test_fails_over_to_next_provider(test_task):
    dead = FakeProvider("dead", fail_times=99)
    backup = FakeProvider("backup")
    router = LLMRouter(max_attempts=2, backoff_base_seconds=0, provider_chain=[dead, backup])
    assert router.run(task="test_task", prompt="hi") == "response-from-backup-fast-model"
    assert dead.calls == 2      # exhausted its attempts before failover
    assert backup.calls == 1


def test_gives_up_when_all_providers_fail(test_task):
    router = LLMRouter(
        max_attempts=2, backoff_base_seconds=0,
        provider_chain=[FakeProvider("a", fail_times=99), FakeProvider("b", fail_times=99)],
    )
    with pytest.raises(LLMRouterError, match="failed on all providers"):
        router.run(task="test_task", prompt="hi")


def test_model_override_pins_model_across_chain(test_task):
    router = LLMRouter(backoff_base_seconds=0, provider_chain=[FakeProvider("groq")])
    assert router.run(task="test_task", prompt="hi", model="custom") == "response-from-custom"


def test_conftest_env_yields_configured_provider():
    # conftest sets OPENAI_API_KEY, so at least one spec must be configured.
    specs = configured_provider_specs()
    assert any(s.name == "openai" for s in specs)
