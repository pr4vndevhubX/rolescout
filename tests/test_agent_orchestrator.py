"""Orchestrator graph tests — scripted fake LLM, real LangGraph wiring."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from app.agent.orchestrator import _build_graph


class ScriptedModel:
    """Returns a fixed sequence of AIMessages — deterministic 'LLM'."""

    def __init__(self, script: list[AIMessage]):
        self._script = list(script)
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return self._script.pop(0)


class FakeAudit:
    def __init__(self):
        self.records = []

    def record(self, tool, tool_input, result_summary):
        self.records.append((tool, tool_input, result_summary))


@tool
def echo(text: str) -> str:
    """Echoes text back."""
    return f"echo:{text}"


@tool
def explode() -> str:
    """Always fails."""
    raise RuntimeError("boom")


def _run(script, tools):
    model = ScriptedModel(script)
    audit = FakeAudit()
    graph = _build_graph(model, {t.name: t for t in tools}, audit)
    result = graph.invoke(
        {"messages": [SystemMessage(content="s"), HumanMessage(content="hi")]},
        config={"recursion_limit": 10},
    )
    return result, audit, model


def test_direct_answer_without_tools():
    result, audit, model = _run([AIMessage(content="just an answer")], [echo])
    assert result["messages"][-1].content == "just an answer"
    assert audit.records == []
    assert model.calls == 1


def test_tool_call_then_final_answer():
    script = [
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "1"}]),
        AIMessage(content="done: echo worked"),
    ]
    result, audit, model = _run(script, [echo])
    assert result["messages"][-1].content == "done: echo worked"
    assert model.calls == 2
    # every tool call is audited
    assert audit.records == [("echo", {"text": "hi"}, "echo:hi")]
    # the tool result travelled back to the model as a ToolMessage
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert tool_messages[0].content == "echo:hi"


def test_failing_tool_does_not_kill_the_run():
    script = [
        AIMessage(content="", tool_calls=[{"name": "explode", "args": {}, "id": "1"}]),
        AIMessage(content="recovered"),
    ]
    result, audit, _ = _run(script, [echo, explode])
    assert result["messages"][-1].content == "recovered"
    assert "Tool error" in audit.records[0][2]


def test_unknown_tool_reported_not_crashed():
    script = [
        AIMessage(content="", tool_calls=[{"name": "nope", "args": {}, "id": "1"}]),
        AIMessage(content="ok"),
    ]
    result, audit, _ = _run(script, [echo])
    assert "Unknown tool" in audit.records[0][2]
    assert result["messages"][-1].content == "ok"


def test_multiple_tool_calls_in_one_turn():
    script = [
        AIMessage(content="", tool_calls=[
            {"name": "echo", "args": {"text": "a"}, "id": "1"},
            {"name": "echo", "args": {"text": "b"}, "id": "2"},
        ]),
        AIMessage(content="both done"),
    ]
    result, audit, model = _run(script, [echo])
    assert [r[2] for r in audit.records] == ["echo:a", "echo:b"]
    assert model.calls == 2
