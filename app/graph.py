"""The LangGraph orchestrator (#15, #16): the single agent loop every
channel routes through, replacing the legacy Hermes agent loop, with
conversation state isolated per user via LangGraph's native
checkpointer.

Call build_thread_id(channel, user_id, agent_id) to get the checkpointer
key for a given identity+agent, then invoke the compiled graph with it
in config["configurable"]. See #17 for wiring the response back to the
originating channel adapter (not this module's job).
"""

import asyncio
import logging
from collections.abc import Iterable
from typing import Annotated, TypedDict

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, convert_to_openai_messages
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app import checkpoints
from app.config import get_settings
from app.db.models import Channel
from app.security.hashing import channel_identifier_key

logger = logging.getLogger("channelagent")


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
    return thread_id_from_key(channel, channel_identifier_key(channel, user_id), agent_id)


def thread_id_from_key(channel: Channel, identity_key: str, agent_id: int) -> str:
    """The same id from an identity key already computed (ChannelIdentity.
    external_id is exactly that key), so code that only has the database row,
    such as a user purge (#50), builds the identical thread id.
    """
    return f"{channel.value}_{identity_key}_{agent_id}"


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


# The compiled graph and its checkpointer are created on first use (#49): the
# checkpointer owns an aiosqlite connection, which belongs to the event loop
# that opened it. Reopened when the configured file changes, closed by
# close_graph() (application shutdown, and between tests).
_state: dict = {}
_lock = asyncio.Lock()


async def get_graph():
    path = checkpoints.checkpoint_db_path()
    async with _lock:
        if _state.get("path") != path:
            await _close_locked()
            saver = await checkpoints.open_saver(path)
            graph = build_graph().compile(checkpointer=saver)
            _state.update(path=path, saver=saver, graph=graph)
            logger.info("Conversation checkpoints stored in %s", path)
        return _state["graph"]


async def _close_locked() -> None:
    saver = _state.get("saver")
    _state.clear()
    if saver is not None:
        try:
            await saver.conn.close()
        except Exception:
            logger.debug("Closing the checkpoint database raised, ignoring", exc_info=True)


async def close_graph() -> None:
    async with _lock:
        await _close_locked()


async def threads_with_history(thread_ids: Iterable[str]) -> int:
    """How many of these conversations have a stored checkpoint. A checkpoint
    that cannot be read counts: it exists, and that is the case an admin
    resets (#63).
    """
    ids = list(thread_ids)
    if not ids:
        return 0
    await get_graph()
    saver = _state["saver"]
    found = 0
    for thread_id in ids:
        try:
            found += await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is not None
        except Exception:
            found += 1
    return found


async def delete_threads(thread_ids: Iterable[str]) -> int:
    """Delete the checkpoints of these conversations. Returns how many thread
    ids were processed (a thread with no checkpoint is not an error).
    """
    ids = list(thread_ids)
    if not ids:
        return 0
    await get_graph()
    saver = _state["saver"]
    for thread_id in ids:
        await saver.adelete_thread(thread_id)
    return len(ids)


async def run_turn(channel: Channel, user_id: str, agent_id: int, text: str) -> str:
    """Entry point channel adapters call after a message passes
    authorization (app/security/auth.py). Returns the assistant's reply.
    """
    thread_id = build_thread_id(channel, user_id, agent_id)
    graph = await get_graph()
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=text)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content
