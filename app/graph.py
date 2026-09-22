"""The LangGraph orchestrator (#15, #16): the single agent loop every
channel routes through, replacing the earlier agent loop, with
conversation state isolated per user via LangGraph's native
checkpointer.

Call build_thread_id(channel, user_id, agent_id) to get the checkpointer
key for a given identity+agent, then invoke the compiled graph with it
in config["configurable"]. See #17 for wiring the response back to the
originating channel adapter (not this module's job).
"""

import asyncio
import contextvars
import logging
import time
from collections.abc import Iterable
from typing import Annotated, TypedDict

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    convert_to_openai_messages,
    trim_messages,
)
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app import checkpoints
from app.admin import mcp as mcp_service
from app.admin import routing as routing_service
from app.config import get_settings
from app.db.models import Agent, Channel
from app.db.session import session_scope
from app.mcp import catalogue as mcp_catalogue
from app.mcp.manager import manager as mcp_manager
from app.security.hashing import channel_identifier_key
from app.tools import run_tool_loop, tools_are_supported

logger = logging.getLogger("channelagent")


class GraphState(TypedDict):
    # add_messages appends each node's returned messages to the
    # checkpointed history instead of replacing it — without this
    # reducer, every turn would overwrite the prior conversation
    # instead of continuing it, defeating the point of the checkpointer.
    messages: Annotated[list[BaseMessage], add_messages]
    # Running summary of the turns that fell out of the model's window (#86), and how
    # many messages it covers. Absent in checkpoints written before #86.
    summary: str
    summary_covers: int


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


# Share of the model's context window the conversation may fill. The rest is
# left for the reply and for any error of the token count (#47).
HISTORY_CONTEXT_SHARE = 0.75

# Tokens added around each message by the chat template (role markers), counted
# on top of the message text when the server's tokenizer is used (#87).
MESSAGE_OVERHEAD_TOKENS = 4

# The turns that fall out of the window are summarized (#86), but only once at
# least this many are new since the last summary, so a long conversation does
# not pay one extra model call per turn.
SUMMARY_BATCH = 6
SUMMARY_MAX_TOKENS = 300
SUMMARY_PROMPT = (
    "You maintain the memory of a conversation. Write a summary of at most 200 words. "
    "Keep every concrete fact the user gave (names, numbers, identifiers, dates, "
    "preferences, decisions) exactly as written, and never drop an item of the earlier "
    "summary. Leave out small talk. Write only the summary."
)
SUMMARY_HEADER = "Summary of the earlier part of this conversation: "

# Exact token counts already obtained from the server, by message id (#87), and the
# time until which a server without a usable tokenizer is not asked again.
_token_cache: dict[str, int] = {}
_TOKENIZER_RETRY_SECONDS = 300
_tokenizer_down_until = 0.0


def history_token_budget(ctx_size: int) -> int:
    return int(ctx_size * HISTORY_CONTEXT_SHARE)


def window_messages(
    messages: list[BaseMessage], budget: int, token_counter=count_tokens_approximately
) -> list[BaseMessage]:
    """The most recent turns that fit in `budget` tokens (#47).

    Starts on a human message so a reply is never sent without its question,
    and always keeps the latest message, even alone above the budget. Only
    what is sent to the model is cut: the checkpoint keeps the whole history
    and the audit trail (ActionLog) is untouched. `token_counter` defaults to
    the characters-per-token estimate of langchain; call_llm passes exact counts
    from the server's tokenizer when it answers (#87).
    """
    kept = trim_messages(
        messages,
        max_tokens=budget,
        token_counter=token_counter,
        strategy="last",
        start_on="human",
        allow_partial=False,
    )
    return kept or messages[-1:]


async def _exact_counter(client: httpx.AsyncClient, messages: list[BaseMessage]):
    """A token counter using the server's own tokenizer (`/tokenize`, #87), or the
    estimate when the server does not offer it. Each message is tokenized once,
    then remembered by its id.
    """
    global _tokenizer_down_until
    if time.monotonic() < _tokenizer_down_until:
        return count_tokens_approximately
    counts: dict[str, int] = {}
    try:
        for message in messages:
            key = message.id
            if key is not None and key in _token_cache:
                counts[key] = _token_cache[key]
                continue
            response = await client.post("/tokenize", json={"content": str(message.content)})
            response.raise_for_status()
            n_tokens = len(response.json()["tokens"]) + MESSAGE_OVERHEAD_TOKENS
            counts[key or str(id(message))] = n_tokens
            if key is not None:
                _token_cache[key] = n_tokens
    except Exception:
        _tokenizer_down_until = time.monotonic() + _TOKENIZER_RETRY_SECONDS
        logger.debug("The server's tokenizer is not usable, estimating token counts", exc_info=True)
        return count_tokens_approximately

    def counter(batch: list[BaseMessage]) -> int:
        return sum(
            counts.get(m.id or str(id(m)), 0) or count_tokens_approximately([m]) for m in batch
        )

    return counter


def _prefix_cost(counter, prefix: str) -> int:
    return counter([SystemMessage(content=prefix)]) if prefix else 0


async def _chat(client: httpx.AsyncClient, messages: list[dict], **extra) -> str:
    response = await client.post(
        "/v1/chat/completions", json={"messages": messages, "stream": False, **extra}
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


async def _chat_with_fallback(
    client: httpx.AsyncClient,
    messages: list[dict],
    model: str | None,
    default_model: str | None,
) -> str:
    """The turn's reply (#105): a model that the engine no longer has (deleted,
    renamed, or never installed) answers 400, in router mode as well as single-
    model mode; retried once against the routing default, and the fallback is
    logged, never silent. Nothing to fall back to (no default, or it *is* the
    one that failed) lets the error surface as any other failed turn (#51).
    """
    try:
        return await _chat(client, messages, **({"model": model} if model else {}))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400 and model and default_model and model != default_model:
            logger.warning(
                "Model %r is unavailable, falling back to the routing default %r",
                model, default_model,
            )
            return await _chat(client, messages, model=default_model)
        raise


async def _summarize(
    client: httpx.AsyncClient, previous: str, dropped: list[BaseMessage], **extra
) -> str | None:
    """Fold the dropped turns into the running summary with one model call (#86).
    Returns None when the call fails: the turn then goes on with the window alone.
    """
    transcript = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}" for m in dropped
    )
    text = (f"Earlier summary: {previous}\n\n" if previous else "") + transcript
    try:
        return (
            await _chat(
                client,
                [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": text}],
                max_tokens=SUMMARY_MAX_TOKENS,
                **extra,
            )
        ).strip()
    except Exception:
        logger.warning(
            "Summarizing the earlier conversation failed, using the window alone", exc_info=True
        )
        return None


# The configuration of the agent whose turn is running (#110): its system prompt and model.
# Handed to the node through a context variable and not through the graph's `configurable`,
# because LangGraph copies those values into the checkpoint's metadata, and the prompt is
# encrypted at rest for a reason.
_agent_settings: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "agent_settings", default=None
)


def _prefix(system_prompt: str | None, summary: str) -> str:
    """The one system message in front of the window: the agent's prompt, then the running
    summary. One message, because several chat templates refuse a second system message."""
    parts = [system_prompt] if system_prompt else []
    if summary:
        parts.append(SUMMARY_HEADER + summary)
    return "\n\n".join(parts)


async def call_llm(state: GraphState) -> GraphState:
    """Send the conversation so far to the configured LLM gateway and
    return its reply as a new message (add_messages appends it).

    Talks to llama-server's OpenAI-compatible /v1/chat/completions
    endpoint — works unchanged against the native Mac llama-server or a
    containerized Ollama/vLLM backend, since only LLAMA_SERVER_URL
    differs between them (see docs/ARCHITECTURE.md).

    The request holds the most recent turns that fit the budget (#47, counted
    with the server's tokenizer when it has one, #87) and, in front of them, a
    running summary of the turns that fell out of the window (#86). Both are
    only what is sent: the checkpoint keeps every message.
    """
    settings = get_settings()
    messages = state["messages"]
    summary = state.get("summary", "")
    covers = state.get("summary_covers", 0)
    update: dict = {}
    agent = _agent_settings.get() or {}
    system_prompt, model = agent.get("system_prompt"), agent.get("model")
    default_model = agent.get("default_model")
    agent_id = agent.get("agent_id")
    tools_allowed = agent.get("tools_allowed") or set()
    # A model's own context size (#105) only ever narrows the engine-wide cap
    # LLAMA_CTX_SIZE, never widens it: that cap is what every router-loaded model
    # is actually started with (see docs/ARCHITECTURE.md, "Model routing").
    ctx_size = min(agent.get("ctx_size") or settings.llama_ctx_size, settings.llama_ctx_size)
    budget = history_token_budget(ctx_size)
    extra = {"model": model} if model else {}

    async with httpx.AsyncClient(base_url=settings.llama_server_url, timeout=120) as client:
        counter = await _exact_counter(client, messages)
        room = budget - _prefix_cost(counter, _prefix(system_prompt, summary))
        window = window_messages(messages, max(room, 1), counter)
        dropped = len(messages) - len(window)
        if dropped > covers and dropped - covers >= SUMMARY_BATCH:
            folded = await _summarize(client, summary, messages[covers:dropped], **extra)
            if folded:
                summary, covers = folded, dropped
                update = {"summary": summary, "summary_covers": covers}
                room = budget - _prefix_cost(counter, _prefix(system_prompt, summary))
                window = window_messages(messages, max(room, 1), counter)
        if dropped:
            logger.info(
                "Conversation trimmed for the model: %d of %d messages sent (%d summarized)",
                len(window), len(messages), covers,
            )
        sent = window
        prefix = _prefix(system_prompt, summary)
        if prefix:
            sent = [SystemMessage(content=prefix), *window]
        openai_tools = (
            await mcp_catalogue.build_tools(mcp_manager, tools_allowed)
            if tools_allowed and await tools_are_supported(client)
            else []
        )
        if openai_tools:
            executor = mcp_catalogue.make_executor(mcp_manager, agent_id)
            reply, _rounds = await run_tool_loop(
                client, convert_to_openai_messages(sent), openai_tools, executor, **extra
            )
        else:
            reply = await _chat_with_fallback(
                client, convert_to_openai_messages(sent), model, default_model
            )

    return {"messages": [AIMessage(content=reply)], **update}


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


async def run_turn(
    channel: Channel, user_id: str, agent_id: int, text: str, *, retry: bool = False
) -> str:
    """Entry point channel adapters call after a message passes
    authorization (app/security/auth.py). Returns the assistant's reply.

    `retry` marks a message that is processed again after a failed turn (#93):
    a failed turn leaves its user message in the checkpoint, so when the last
    stored message is that same user message it is not appended a second time.
    """
    thread_id = build_thread_id(channel, user_id, agent_id)
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    async with session_scope() as session:
        agent = await session.get(Agent, agent_id)
        if agent is not None:
            routing = await routing_service.get_routing(session)
            # Only queried when the agent might actually use one (#116): most agents
            # have no tools, and every turn otherwise pays a query for nothing.
            if agent.tools:
                mcp_manager.configure(await mcp_service.enabled_configs(session))
    if agent is None:
        _agent_settings.set({})
    else:
        # Decision order (#105): the agent's own model (#110) first; only when it has
        # none are the routing rules, then the default model, consulted.
        model = agent.model or routing_service.select_model(
            text=text, rules=routing["rules"], default_model=routing["default_model"]
        )
        _agent_settings.set(
            {
                "system_prompt": agent.system_prompt,
                "model": model,
                "default_model": routing["default_model"],
                "ctx_size": routing["model_ctx_sizes"].get(model) if model else None,
                "agent_id": agent.id,
                "tools_allowed": set(agent.tools),
            }
        )
    new_messages = [HumanMessage(content=text)]
    if retry:
        state = await graph.aget_state(config)
        stored = state.values.get("messages", []) if state and state.values else []
        if stored and isinstance(stored[-1], HumanMessage) and stored[-1].content == text:
            new_messages = []
    result = await graph.ainvoke({"messages": new_messages}, config=config)
    return result["messages"][-1].content
