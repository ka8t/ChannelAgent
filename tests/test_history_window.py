"""Tests for #47: the history sent to the model stays under a token budget.

The window is counted with the same estimator the code uses; the mock LLM
records every request so "under the budget" and "latest message included"
are numbers taken from what was actually sent.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

from app import graph
from app.db.models import Channel
from app.graph import HISTORY_CONTEXT_SHARE, history_token_budget, window_messages

CTX_SIZE = 400  # budget 300 estimated tokens


def _history(turns: int, filler: int = 200) -> list:
    messages = []
    for i in range(turns):
        messages.append(HumanMessage(content=f"question {i} " + "x" * filler))
        messages.append(AIMessage(content=f"answer {i} " + "y" * filler))
    return messages


def test_budget_is_a_share_of_the_context_window():
    assert HISTORY_CONTEXT_SHARE == 0.75
    assert history_token_budget(65536) == 49152
    assert history_token_budget(400) == 300


def test_a_thread_far_above_the_budget_is_cut_under_it():
    messages = _history(1000) + [HumanMessage(content="LAST QUESTION")]
    kept = window_messages(messages, 300)
    assert len(messages) == 2001
    assert count_tokens_approximately(messages) > 100000
    assert 0 < len(kept) < 20
    assert count_tokens_approximately(kept) <= 300


def test_the_latest_message_is_always_kept_and_last():
    messages = _history(1000) + [HumanMessage(content="LAST QUESTION")]
    kept = window_messages(messages, 300)
    assert kept[-1].content == "LAST QUESTION"


def test_the_window_starts_on_a_human_message():
    kept = window_messages(_history(50) + [HumanMessage(content="now")], 300)
    assert isinstance(kept[0], HumanMessage)


def test_the_most_recent_turns_are_the_ones_kept():
    kept = window_messages(_history(100) + [HumanMessage(content="now")], 300)
    assert "question 99" in kept[-3].content and "answer 99" in kept[-2].content
    assert not any("question 0 " in m.content for m in kept)


def test_a_short_thread_is_sent_whole():
    messages = _history(2) + [HumanMessage(content="now")]
    assert window_messages(messages, 300) == messages


def test_one_message_alone_above_the_budget_is_still_sent():
    huge = HumanMessage(content="z" * 100000)
    assert window_messages([huge], 100) == [huge]
    older = _history(3)
    assert window_messages(older + [huge], 100) == [huge]


class _Recorder(BaseHTTPRequestHandler):
    requests: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path != "/v1/chat/completions":  # no tokenizer on this mock
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append(body["messages"])
        data = json.dumps({"choices": [{"message": {"content": "r" * 150}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(autouse=True)
async def _database(fresh_db):
    """A turn reads its agent's settings from the database (#110): a throwaway one."""
    from app.db.session import init_db

    await init_db()


@pytest.fixture
def llm(monkeypatch):
    _Recorder.requests = []
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLAMA_SERVER_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("LLAMA_CTX_SIZE", str(CTX_SIZE))
    from app.config import get_settings

    get_settings.cache_clear()
    yield _Recorder
    server.shutdown()
    get_settings.cache_clear()


async def test_requests_stay_under_the_budget_over_a_long_conversation(llm):
    from app.graph import SUMMARY_PROMPT

    turns = 60
    for i in range(turns):
        await graph.run_turn(Channel.TELEGRAM, "42", 1, f"message {i} " + "q" * 200)

    budget = history_token_budget(CTX_SIZE)
    # Summary calls (#86) are separate requests; the turn requests are the others.
    chat = [r for r in llm.requests if r[0]["content"] != SUMMARY_PROMPT]
    assert len(chat) == turns
    sizes = [
        count_tokens_approximately(
            [
                (HumanMessage if m["role"] == "user" else AIMessage)(content=m["content"])
                for m in sent
            ]
        )
        for sent in chat
    ]
    assert max(sizes) <= budget
    for i, sent in enumerate(chat):
        assert sent[-1]["content"].startswith(f"message {i} ")
        body = sent[1:] if sent[0]["role"] == "system" else sent
        assert body[0]["role"] == "user"
    assert len(chat[-1]) < 2 * turns - 1


async def test_the_checkpoint_keeps_the_whole_history(llm):
    turns = 30
    for i in range(turns):
        await graph.run_turn(Channel.TELEGRAM, "42", 1, f"message {i} " + "q" * 200)

    compiled = await graph.get_graph()
    thread = graph.build_thread_id(Channel.TELEGRAM, "42", 1)
    state = await compiled.aget_state({"configurable": {"thread_id": thread}})
    assert len(state.values["messages"]) == 2 * turns
    assert len(llm.requests[-1]) < 2 * turns - 1
