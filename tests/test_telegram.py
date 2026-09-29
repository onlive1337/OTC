import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import ujson
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineQuery, User

from handlers import conversion
from utils.middleware import TelegramRetryMiddleware


def test_flood_control_retries_only_failed_send(monkeypatch):
    async def scenario():
        session = AiohttpSession(json_loads=ujson.loads, json_dumps=ujson.dumps)
        session.middleware(TelegramRetryMiddleware())
        bot = Bot('123456:offline-test-token', session=session)
        error = TelegramRetryAfter(method=SendMessage(chat_id=1, text='second'), message='retry', retry_after=0)
        request = AsyncMock(side_effect=[True, error, True])
        monkeypatch.setattr(session, 'make_request', request)
        writes = []
        async def handler():
            writes.append('saved once')
            await bot.send_message(1, 'first')
            await bot.send_message(1, 'second')
        await handler()
        assert writes == ['saved once']
        assert [call.args[1].text for call in request.await_args_list] == ['first', 'second', 'second']
        await session.close()
    asyncio.run(scenario())


def test_flood_retries_are_bounded():
    method = SendMessage(chat_id=1, text='test')
    error = TelegramRetryAfter(method=method, message='retry', retry_after=0)
    request = AsyncMock(side_effect=error)
    with pytest.raises(TelegramRetryAfter):
        asyncio.run(TelegramRetryMiddleware(max_retries=2)(request, None, method))
    assert request.await_count == 3


def test_bad_request_is_not_retried():
    method = SendMessage(chat_id=1, text='test')
    request = AsyncMock(side_effect=TelegramBadRequest(method=method, message='bad request'))
    with pytest.raises(TelegramBadRequest):
        asyncio.run(TelegramRetryMiddleware()(request, None, method))
    request.assert_awaited_once()


@pytest.mark.parametrize('text', ['', '100 USD', '100 USD EUR', '2+3', '100 bny',
                                 '0.00001 USD', '10000000000000 USD', 'abc'])
def test_inline_answers_use_personal_cache(monkeypatch, text):
    async def scenario():
        data = SimpleNamespace(
            update_user_data=AsyncMock(),
            get_user_data=AsyncMock(return_value={
                'language': 'ru', 'selected_currencies': ['EUR'],
                'selected_crypto': [], 'use_quote_format': True,
            }),
        )
        monkeypatch.setattr(conversion, 'user_data', data)
        monkeypatch.setattr(conversion, 'get_exchange_rates', AsyncMock(return_value={'USD': 1, 'EUR': 0.9}))
        session = AiohttpSession(json_loads=ujson.loads, json_dumps=ujson.dumps)
        request = AsyncMock(return_value=True)
        monkeypatch.setattr(session, 'make_request', request)
        bot = Bot('123456:offline-test-token', session=session)
        query = InlineQuery(id='test', from_user=User(id=1, is_bot=False, first_name='Test'),
                            query=text, offset='').as_(bot)
        await conversion.inline_query_handler(query)
        request.assert_awaited_once()
        method = request.await_args.args[1]
        assert method.is_personal is True
        assert method.results
        # Exercise the configured JSON codec with actual aiogram result models.
        encoded = session.json_dumps(method.model_dump(mode='json', exclude_defaults=True))
        assert session.json_loads(encoded)['is_personal'] is True
        await session.close()
    asyncio.run(scenario())


def test_startup_shutdown_with_temporary_database(monkeypatch, tmp_path):
    import main
    import data.connection as connection
    from data.user_data import UserData
    from utils.http import get_http_session

    async def scenario():
        monkeypatch.setattr(connection, 'DB_PATH', str(tmp_path / 'startup.db'))
        monkeypatch.setattr(connection, 'DB_BACKUP_INTERVAL_HOURS', 0)
        monkeypatch.setattr(main, 'user_data', UserData())
        monkeypatch.setattr(main, 'setup_telegram_logging', AsyncMock())
        monkeypatch.setattr(main, 'get_exchange_rates', AsyncMock(return_value={'USD': 1.0}))
        await main.on_startup()
        session = get_http_session()
        assert session is not None and not session.closed
        assert await main.user_data.ping_db()
        await main.on_shutdown()
        assert session.closed
        assert get_http_session() is None
        assert main.user_data._read_conn is None
        assert main.user_data._write_conn is None
        assert not main._bg_tasks
    asyncio.run(scenario())


@pytest.mark.parametrize('cached,expected_interval', [(None, 30), ({'USD': 1.0}, 540)])
def test_periodic_refresh_recovers_promptly_after_failure(monkeypatch, cached, expected_interval):
    import main

    waits = []
    async def sleep(delay):
        waits.append(delay)
        if len(waits) == 2:
            raise asyncio.CancelledError
    monkeypatch.setattr(main.asyncio, 'sleep', sleep)
    monkeypatch.setattr(main, 'refresh_rates', AsyncMock(return_value=cached or {}))
    monkeypatch.setattr(main, 'get_cached_data', lambda key: cached)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._periodic_refresh())
    assert waits == [30, expected_interval]


def test_production_runner_uses_uvloop(monkeypatch):
    import main
    uvloop = pytest.importorskip('uvloop')

    loops = []
    async def smoke():
        loops.append(asyncio.get_running_loop())
    monkeypatch.setattr(main, 'main', smoke)
    main.run_app()
    assert isinstance(loops[0], uvloop.Loop)
    assert loops[0].is_closed()
