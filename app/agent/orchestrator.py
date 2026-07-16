"""
The Orchestrator — a LangGraph state machine that IS the personal assistant.

Graph shape (classic ReAct):

    ┌─────────┐   tool_calls?   ┌─────────┐
    │  agent  │ ──────yes────▶  │  tools  │
    │ (LLM)   │ ◀────────────── │ (exec)  │
    └─────────┘                 └─────────┘
         │ no
         ▼
        END

- The agent node calls the configured chat model (Groq/Gemini/... chain from
  app/agent/llm.py) with the user-scoped tools bound.
- The tools node executes tool calls and logs EVERY one to agent_actions —
  the UI's activity feed.
- Hard guard: MAX_AGENT_STEPS LLM turns per run; the model is told when it
  is out of budget so it wraps up instead of being cut off mid-thought.
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph, MessagesState
from sqlalchemy.orm import Session

from app.agent.context import AgentAuditLog
from app.agent.llm import get_agent_chat_model
from app.agent.tools import build_tools
from app.models.db_models import AgentAction, User

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 8  # LLM turns per run — cost guard

SYSTEM_PROMPT = """You are the user's personal AI job-application assistant. Your standing goal: \
keep their job hunt moving with minimal effort from them.

You have tools to read their preferences, search live job boards, match jobs against their \
resume, tailor their resume for a specific job (truthfully — never inventing experience), \
write cover letters, prepare application packages, and notify them.

Guidelines:
- Start from their saved preferences when the request is open-ended.
- Prefer reading stored matches (get_matches) over regenerating them; generate_matches and \
tailoring cost real money — use them when they add value, not by default.
- You PREPARE applications; the user approves and submits. Never claim you submitted anything.
- Be concrete in your final answer: job titles, companies, scores, and what you did.
- If the user has no ready resume, tell them exactly which step is missing (upload → parse → embed).
{step_note}"""


def _build_graph(model_with_tools, tools_by_name: dict, audit: AgentAuditLog):
    def agent_node(state: MessagesState):
        return {"messages": [model_with_tools.invoke(state["messages"])]}

    def tools_node(state: MessagesState):
        last = state["messages"][-1]
        outputs = []
        for call in last.tool_calls:
            tool = tools_by_name.get(call["name"])
            if tool is None:
                result = f"Unknown tool '{call['name']}'."
            else:
                try:
                    result = tool.invoke(call["args"])
                except Exception as e:  # a failed tool must not kill the run
                    logger.exception("Agent tool '%s' failed", call["name"])
                    result = f"Tool error: {e}"
            audit.record(call["name"], call["args"], str(result))
            outputs.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        return {"messages": outputs}

    def should_continue(state: MessagesState):
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def run_agent(
    db: Session,
    user: User,
    message: str,
    *,
    trigger: str = "chat",
    chat_model=None,
) -> dict:
    """
    One assistant turn: message in -> tools as needed -> final reply.
    Returns {"reply", "run_id", "actions": [{tool, input, result}...]}.
    chat_model: injectable for tests; defaults to the configured provider chain.
    """
    audit = AgentAuditLog(db, user, trigger=trigger, goal=message)
    tools = build_tools(db, user)
    tools_by_name = {t.name: t for t in tools}
    model = (chat_model or get_agent_chat_model()).bind_tools(tools)

    system = SYSTEM_PROMPT.format(
        step_note=f"- You have a budget of {MAX_AGENT_STEPS} reasoning steps; be efficient."
    )
    state = {"messages": [SystemMessage(content=system), HumanMessage(content=message)]}

    try:
        graph = _build_graph(model, tools_by_name, audit)
        # recursion_limit counts graph super-steps: agent + tools per cycle.
        result = graph.invoke(state, config={"recursion_limit": 2 * MAX_AGENT_STEPS + 1})
        reply = result["messages"][-1].content or "(no reply)"
        audit.finish("completed", reply)
    except Exception as e:
        logger.exception("Agent run %s failed", audit.run.run_id)
        audit.finish("failed", f"{type(e).__name__}: {e}")
        reply = (
            "I hit an internal error while working on that. "
            "The partial actions I took are in the activity log."
        )

    action_rows = (
        db.query(AgentAction)
        .filter(AgentAction.run_id == audit.run.run_id)
        .order_by(AgentAction.seq)
        .all()
    )
    actions = [
        {"tool": a.tool, "input": a.tool_input, "result": a.result_summary}
        for a in action_rows
    ]
    return {"reply": reply, "run_id": audit.run.run_id, "actions": actions}
