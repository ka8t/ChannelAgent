"""The LangGraph orchestrator (#15, #16): the single agent loop every
channel routes through, replacing the legacy Hermes agent loop, with
conversation state isolated per user via LangGraph's native
checkpointer.

Call build_thread_id(channel, user_id, agent_id) to get the checkpointer
key for a given identity+agent, then invoke the compiled graph with it
in config["configurable"]. See #17 for wiring the response back to the
originating channel adapter (not this module's job).
"""

from typing import Annotated, TypedDict

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, convert_to_openai_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.config import get_settings
from app.db.models import Channel
from app.security.hashing import channel_identifier_key


class GraphState(TypedDict):
    # add_messages appends each node's returned messages to the
    # checkpointed history instead of replacing it — without this
    # reducer, every turn would overwrite the prior conversation
    # instead of continuing it, defeating the point of the checkpointer.
    messages: Annotated[list[BaseMessage], add_messages]


def build_thread_id(channel: Channel, user_id: str, agent_id: int) -> str:
    """thread_id scheme, extended by #37 for multiple agents per user:
    {channel}_{identity_key}_{agent_id} — e.g. telegram_123_4,
    email_{hash}_4. Same deterministic identity key as the Auth Node
    (app/security/auth.py) so a given (identity, agent) pair always
    maps to the same conversation thread, and two agents belonging to
    the same user never share one.
    """
    return f"{channel.value}_{channel_identifier_key(channel, user_id)}_{agent_id}"


async def call_llm(state: GraphState) -> GraphState:
    """Send the conversation so far to the configured LLM gateway and
    return its reply as a new message (add_messages appends it).

    Talks to llama-server's OpenAI-compatible /v1/chat/completions
    endpoint — works unchanged against the native Mac llama-server or a
    containerized Ollama/vLLM backend, since only LLAMA_SERVER_URL
    differs between them (see docs/ARCHITECTURE.md).
    """
    settings = get_settings()
    payload_messages = convert_to_openai_messages(state["messages"])
    async with httpx.AsyncClient(base_url=settings.llama_server_url, timeout=120) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"messages": payload_messages, "stream": False},
        )
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]

    return {"messages": [AIMessage(content=reply)]}


def build_graph() -> StateGraph:
    graph = StateGraph(GraphState)
    graph.add_node("call_llm", call_llm)
    graph.add_edge(START, "call_llm")
    graph.add_edge("call_llm", END)
    return graph


# Process-wide MemorySaver: fine for a single-container deployment where
# restart-durability isn't required yet. Revisit (persistent checkpointer
# backend) if that assumption changes — see epic #3.
_checkpointer = MemorySaver()
compiled_graph = build_graph().compile(checkpointer=_checkpointer)


async def run_turn(channel: Channel, user_id: str, agent_id: int, text: str) -> str:
    """Entry point channel adapters call after a message passes
    authorization (app/security/auth.py). Returns the assistant's reply.
    """
    thread_id = build_thread_id(channel, user_id, agent_id)
    result = await compiled_graph.ainvoke(
        {"messages": [HumanMessage(content=text)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content
