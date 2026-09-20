"""Tests for #39: searching the audit trail.

One dataset (7 rows, 2 users, 3 agents, 2 channels, both directions),
queried through the service function, through GET /logs and through the
admin console, plus a spy test proving the API and the console call the
same service function.

Row ids follow insertion order, which is also chronological order:

 id user agent channel  dir       created (UTC)         text
  1   1    1    telegram inbound  2026-09-10 08:00:00   Please remind me to buy milk
  2   1    1    telegram outbound 2026-09-10 08:00:05   Sure, I will remind you about the milk
  3   1    2    email    inbound  2026-09-12 09:30:00   Quarterly report draft attached
  4   2    3    telegram inbound  2026-09-15 12:00:00   What is the weather in Paris?
  5   2    3    telegram outbound 2026-09-15 12:00:03   It is sunny in Paris.
  6   1    1    telegram inbound  2026-09-20 07:00:00   MILK again, do not forget
  7   2    3    email    inbound  2026-09-20 10:00:00   Invoice for the milk delivery
"""

import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from app.db.models import Channel, Direction

ROWS = [
    (1, 1, "telegram", "inbound", datetime(2026, 9, 10, 8, 0, 0, tzinfo=UTC),
     "Please remind me to buy milk"),
    (1, 1, "telegram", "outbound", datetime(2026, 9, 10, 8, 0, 5, tzinfo=UTC),
     "Sure, I will remind you about the milk"),
    (1, 2, "email", "inbound", datetime(2026, 9, 12, 9, 30, 0, tzinfo=UTC),
     "Quarterly report draft attached"),
    (2, 3, "telegram", "inbound", datetime(2026, 9, 15, 12, 0, 0, tzinfo=UTC),
     "What is the weather in Paris?"),
    (2, 3, "telegram", "outbound", datetime(2026, 9, 15, 12, 0, 3, tzinfo=UTC),
     "It is sunny in Paris."),
    (1, 1, "telegram", "inbound", datetime(2026, 9, 20, 7, 0, 0, tzinfo=UTC),
     "MILK again, do not forget"),
    (2, 3, "email", "inbound", datetime(2026, 9, 20, 10, 0, 0, tzinfo=UTC),
     "Invoice for the milk delivery"),
]


@pytest.fixture
async def populated(fresh_db):
    from app.db.models import ActionLog, Agent, User
    from app.db.session import init_db, session_scope

    await init_db()
    async with session_scope() as session:
        alice, bob = User(display_name="Alice"), User(display_name="Bob")
        session.add_all([alice, bob])
        await session.flush()
        session.add_all([
            Agent(user_id=alice.id, name="default"),
            Agent(user_id=alice.id, name="work"),
            Agent(user_id=bob.id, name="default"),
        ])
        await session.flush()
        for user_id, agent_id, channel, direction, created_at, text in ROWS:
            session.add(ActionLog(
                user_id=user_id, agent_id=agent_id, channel=Channel(channel),
                direction=Direction(direction), text=text, created_at=created_at,
            ))
        await session.commit()


async def _search(**filters) -> list[int]:
    from app.admin import service
    from app.db.session import session_scope

    async with session_scope() as session:
        return [e.id for e in await service.search_action_logs(session, **filters)]


# --- service function ---


async def test_no_filter_returns_everything_newest_first(populated):
    assert await _search() == [7, 6, 5, 4, 3, 2, 1]


async def test_each_single_filter(populated):
    assert await _search(user_id=2) == [7, 5, 4]
    assert await _search(agent_id=2) == [3]
    assert await _search(channel=Channel.EMAIL) == [7, 3]
    assert await _search(direction=Direction.OUTBOUND) == [5, 2]


async def test_user_plus_keyword_returns_only_matching_rows(populated):
    # The acceptance criterion: two filters combined. User 2 also has a
    # "milk" row (id 7) and user 1 has non-milk rows, neither may leak in.
    assert await _search(user_id=1, keyword="milk") == [6, 2, 1]


async def test_three_filters_combined(populated):
    ids = await _search(channel=Channel.TELEGRAM, direction=Direction.INBOUND, keyword="paris")
    assert ids == [4]


async def test_keyword_is_case_insensitive_and_matches_decrypted_text(populated):
    assert await _search(keyword="MILK") == await _search(keyword="milk") == [7, 6, 2, 1]
    assert await _search(keyword="  Milk  ") == [7, 6, 2, 1]


async def test_ciphertext_is_never_what_the_keyword_is_matched_against(populated):
    from app.config import get_settings

    db_file = get_settings().database_url.split("///", 1)[1]
    raw = [r[0] for r in sqlite3.connect(db_file).execute("select text from action_logs")]
    assert all(t.startswith("gAAAA") for t in raw), "the column really holds ciphertext"
    assert await _search(keyword="gAAAA") == []


async def test_blank_keyword_means_no_keyword(populated):
    assert await _search(keyword="   ") == [7, 6, 5, 4, 3, 2, 1]
    assert await _search(keyword="") == [7, 6, 5, 4, 3, 2, 1]


async def test_no_match_returns_empty_list(populated):
    assert await _search(user_id=1, keyword="paris") == []
    assert await _search(user_id=99) == []


async def test_date_window_is_since_inclusive_until_exclusive(populated):
    row3 = datetime(2026, 9, 12, 9, 30, 0, tzinfo=UTC)
    day = datetime(2026, 9, 12, tzinfo=UTC)
    end = datetime(2026, 9, 16, tzinfo=UTC)
    assert await _search(since=day, until=end) == [5, 4, 3]
    assert await _search(since=row3, until=end) == [5, 4, 3]
    assert await _search(since=row3 + timedelta(seconds=1), until=end) == [5, 4]
    assert await _search(since=day, until=row3) == [], "until is exclusive"
    assert await _search(since=day, until=row3 + timedelta(seconds=1)) == [3]


async def test_naive_datetimes_are_utc_and_aware_ones_are_converted(populated):
    assert await _search(since=datetime(2026, 9, 20, 7, 0, 0)) == [7, 6]
    paris = timezone(timedelta(hours=2))
    # 09:00 at UTC+2 is 07:00 UTC, so row 6 (07:00 UTC) is still included.
    assert await _search(since=datetime(2026, 9, 20, 9, 0, 0, tzinfo=paris)) == [7, 6]
    # Read as UTC (timezone ignored) it would wrongly drop row 6.
    assert await _search(since=datetime(2026, 9, 20, 9, 0, 0)) == [7]


async def test_limit_and_offset_page_through_matches(populated):
    assert await _search(keyword="milk", limit=2) == [7, 6]
    assert await _search(keyword="milk", limit=2, offset=2) == [2, 1]
    assert await _search(keyword="milk", limit=2, offset=4) == []
    assert await _search(limit=3, offset=1) == [6, 5, 4]
    pages: list[int] = []
    for offset in range(4):
        pages += await _search(keyword="milk", limit=1, offset=offset)
    assert pages == await _search(keyword="milk")


@pytest.mark.parametrize("limit", [0, -1, 501])
async def test_limit_out_of_range_is_rejected(populated, limit):
    with pytest.raises(ValueError, match="limit"):
        await _search(limit=limit)


async def test_negative_offset_is_rejected(populated):
    with pytest.raises(ValueError, match="offset"):
        await _search(offset=-1)


async def test_keyword_search_crosses_batch_boundaries_and_stops_early(populated, monkeypatch):
    from app.admin import service
    from app.db.session import session_scope

    monkeypatch.setattr(service, "_LOG_SEARCH_BATCH", 2)
    assert await _search(keyword="milk") == [7, 6, 2, 1]
    assert await _search(keyword="milk", offset=1, limit=2) == [6, 2]

    async with session_scope() as session:
        original = session.execute
        calls = 0

        async def counting(*args, **kwargs):
            nonlocal calls
            calls += 1
            return await original(*args, **kwargs)

        monkeypatch.setattr(session, "execute", counting)
        found = await service.search_action_logs(session, keyword="milk", limit=1)
    assert [e.id for e in found] == [7]
    assert calls == 1, "the newest row already matches: no further batch may be read"


# --- Admin API: GET /logs ---


@pytest.fixture
async def api(populated, monkeypatch):
    from app.api.app import app
    from app.config import get_settings

    monkeypatch.setenv("API_SERVER_KEY", "test-key")
    get_settings.cache_clear()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield client


AUTH = {"Authorization": "Bearer test-key"}


async def test_api_requires_the_key(api):
    assert (await api.get("/logs")).status_code == 401
    assert (await api.get("/logs", headers={"Authorization": "Bearer wrong"})).status_code == 401


async def test_api_two_filters_return_only_matching_rows_with_decrypted_text(api):
    r = await api.get("/logs", params={"user_id": 1, "keyword": "milk"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert [e["id"] for e in body] == [6, 2, 1]
    assert body[2]["text"] == "Please remind me to buy milk"
    assert set(body[0]) == {
        "id", "user_id", "agent_id", "channel", "direction", "text", "created_at",
    }
    assert body[0]["channel"] == "telegram" and body[0]["direction"] == "inbound"


async def test_api_channel_direction_and_date_filters(api):
    r = await api.get("/logs", params={"channel": "email", "direction": "inbound"}, headers=AUTH)
    assert [e["id"] for e in r.json()] == [7, 3]
    r = await api.get("/logs", params={"since": "2026-09-20T09:00:00+02:00"}, headers=AUTH)
    assert [e["id"] for e in r.json()] == [7, 6]
    r = await api.get(
        "/logs", params={"since": "2026-09-12", "until": "2026-09-16"}, headers=AUTH
    )
    assert [e["id"] for e in r.json()] == [5, 4, 3]


async def test_api_paging(api):
    r = await api.get("/logs", params={"keyword": "milk", "limit": 2, "offset": 2}, headers=AUTH)
    assert [e["id"] for e in r.json()] == [2, 1]


@pytest.mark.parametrize(
    "params",
    [{"channel": "fax"}, {"direction": "sideways"}, {"limit": 0}, {"limit": 501},
     {"offset": -1}, {"user_id": "abc"}, {"since": "not-a-date"}],
)
async def test_api_rejects_invalid_parameters(api, params):
    assert (await api.get("/logs", params=params, headers=AUTH)).status_code == 422


# --- Admin console ---


def _script(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _label="": next(it))


async def test_console_search_combines_filters(populated, monkeypatch, capsys):
    from app.admin import cli

    # user, agent, channel, direction, from, to, keyword, limit
    _script(monkeypatch, "1", "", "", "", "", "", "milk", "")
    await cli._menu_logs()
    out = capsys.readouterr().out
    assert "3 result(s)" in out
    assert "#6 " in out and "#2 " in out and "#1 " in out
    assert "#7 " not in out and "#3 " not in out
    assert "MILK again, do not forget" in out


async def test_console_to_date_includes_the_whole_day(populated, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "", "", "", "", "2026-09-20", "2026-09-20", "", "")
    await cli._menu_logs()
    out = capsys.readouterr().out
    assert "2 result(s)" in out and "#7 " in out and "#6 " in out and "#5 " not in out


async def test_console_reports_no_match_and_limit_reached(populated, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "1", "", "", "", "", "", "paris", "")
    await cli._menu_logs()
    assert "No matching logs." in capsys.readouterr().out

    _script(monkeypatch, "", "", "", "", "", "", "", "2")
    await cli._menu_logs()
    out = capsys.readouterr().out
    assert "2 result(s)" in out and "limit reached" in out


@pytest.mark.parametrize(
    "answers",
    [
        ("abc", "", "", "", "", "", "", ""),
        ("", "", "fax", "", "", "", "", ""),
        ("", "", "", "sideways", "", "", "", ""),
        ("", "", "", "", "20/09/2026", "", "", ""),
        ("", "", "", "", "", "", "", "abc"),
        ("", "", "", "", "", "", "", "0"),
        ("", "", "", "", "", "", "", "501"),
    ],
)
async def test_console_invalid_input_is_reported_not_raised(
    populated, monkeypatch, capsys, answers
):
    from app.admin import cli

    _script(monkeypatch, *answers)
    await cli._menu_logs()
    assert "Invalid input, nothing searched." in capsys.readouterr().out


# --- one service function behind both front ends ---


async def test_api_and_console_call_the_same_service_function(api, populated, monkeypatch):
    from app.admin import cli, service

    calls: list[dict] = []
    real = service.search_action_logs

    async def spy(session, **kwargs):
        calls.append(kwargs)
        return await real(session, **kwargs)

    monkeypatch.setattr(service, "search_action_logs", spy)

    r = await api.get("/logs", params={"user_id": 1, "keyword": "milk"}, headers=AUTH)
    assert r.status_code == 200
    api_ids = [e["id"] for e in r.json()]

    _script(monkeypatch, "1", "", "", "", "", "", "milk", "")
    await cli._menu_logs()

    assert len(calls) == 2, "exactly one service call per front end"
    for kwargs in calls:
        assert kwargs["user_id"] == 1 and kwargs["keyword"] == "milk"
    assert api_ids == await _search(user_id=1, keyword="milk") == [6, 2, 1]
