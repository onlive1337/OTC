import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import ujson
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest
from aiogram.methods import SendMessage
from aiogram.types import InlineQuery, User

from handlers import inline
from utils.middleware import TelegramRetryMiddleware


def test_flood_control_retries_only_failed_send(monkeypatch):
    async def scenario():
        session = AiohttpSession(json_dumps=ujson.dumps)
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
        monkeypatch.setattr(inline, 'user_data', data)
        monkeypatch.setattr(inline, 'get_exchange_rates', AsyncMock(return_value={'USD': 1, 'EUR': 0.9}))
        session = AiohttpSession(json_dumps=ujson.dumps)
        request = AsyncMock(return_value=True)
        monkeypatch.setattr(session, 'make_request', request)
        bot = Bot('123456:offline-test-token', session=session)
        query = InlineQuery(id='test', from_user=User(id=1, is_bot=False, first_name='Test'),
                            query=text, offset='').as_(bot)
        await inline.inline_query_handler(query)
        request.assert_awaited_once()
        method = request.await_args.args[1]
        assert method.is_personal is True
        assert method.results
        # Exercise the configured JSON codec with actual aiogram result models.
        assert session.json_loads is None
        encoded = session.json_dumps(method.model_dump(mode='json', exclude_defaults=True))
        assert ujson.loads(encoded)['is_personal'] is True
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
        close_logs_mock = AsyncMock()
        monkeypatch.setattr(main, 'user_data', UserData())
        monkeypatch.setattr(main, 'setup_telegram_logging', AsyncMock())
        monkeypatch.setattr(main, 'close_telegram_logging', close_logs_mock)
        monkeypatch.setattr(main, 'sync_bot_settings', AsyncMock())
        monkeypatch.setattr(main, 'get_exchange_rates', AsyncMock(return_value={'USD': 1.0}))
        await main.on_startup()
        session = get_http_session()
        assert session is not None and not session.closed
        assert await main.user_data.ping_db()
        await main.on_shutdown()
        close_logs_mock.assert_awaited_once()
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


def test_loader_session_uses_direct_pydantic_json_and_html_enum():
    import loader

    assert loader.session.json_loads is None
    assert loader.session.json_dumps is ujson.dumps
    assert loader.bot.default.parse_mode == ParseMode.HTML

    response = loader.session.check_response(
        loader.bot,
        SendMessage(chat_id=1, text='ok'),
        200,
        '{"ok": true, "result": {"message_id": 1, "date": 1763800000, "chat": {"id": 1, "type": "private"}, "text": "ok"}}',
    )
    assert response.result.text == 'ok'


def test_main_passes_polling_concurrency_and_shutdown_timeout(monkeypatch):
    import main

    fake_dp = Dispatcher()
    include_mock = MagicMock()
    start_mock = AsyncMock()
    monkeypatch.setattr(fake_dp, 'include_router', include_mock)
    monkeypatch.setattr(fake_dp, 'start_polling', start_mock)
    monkeypatch.setattr(main, 'dp', fake_dp)

    asyncio.run(main.main())

    assert include_mock.call_count == 6
    start_mock.assert_awaited_once()
    kwargs = start_mock.await_args.kwargs
    assert kwargs['tasks_concurrency_limit'] == main.POLLING_CONCURRENCY
    assert kwargs['tasks_shutdown_timeout'] == main.POLLING_SHUTDOWN_TIMEOUT
    assert 'allowed_updates' in kwargs


def test_sync_bot_settings_calls_api_and_warns_on_privacy_mode(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace
    from utils import bot_setup

    fake_me = SimpleNamespace(
        username='otc_test_bot',
        active_usernames=['otc_test_bot'],
        can_join_groups=True,
        can_read_all_group_messages=False,
        supports_inline_queries=False,
        inline_query_placeholder='100 USD',
        supports_guest_queries=False,
    )
    fake_bot = SimpleNamespace(
        set_my_settings=AsyncMock(return_value=True),
        set_my_commands=AsyncMock(return_value=True),
        me=AsyncMock(return_value=fake_me),
    )
    monkeypatch.setattr(bot_setup, 'SYNC_BOT_SETTINGS', True)
    monkeypatch.setattr(bot_setup.app_config, 'ENABLE_WIDGET_CALC', False)

    with caplog.at_level(logging.WARNING):
        diag = asyncio.run(bot_setup.sync_bot_settings(fake_bot))

    assert diag is not None
    assert diag['username'] == 'otc_test_bot'
    fake_bot.set_my_settings.assert_awaited_once()
    assert fake_bot.set_my_commands.await_count == 2
    private_cmd_call = fake_bot.set_my_commands.await_args_list[0]
    assert all(cmd.command != 'calc' for cmd in private_cmd_call.kwargs['commands'])
    group_cmd_call = fake_bot.set_my_commands.await_args_list[1]
    assert all(cmd.is_ephemeral is True for cmd in group_cmd_call.kwargs['commands'])
    assert 'privacy mode is ON' in caplog.text
    assert 'Inline mode is disabled' in caplog.text

    monkeypatch.setattr(bot_setup.app_config, 'ENABLE_WIDGET_CALC', True)
    fake_bot.set_my_commands.reset_mock()
    asyncio.run(bot_setup.sync_bot_settings(fake_bot))
    enabled_private_cmds = fake_bot.set_my_commands.await_args_list[0].kwargs['commands']
    assert any(cmd.command == 'calc' for cmd in enabled_private_cmds)


def test_telegram_log_handler_batches_and_flushes_on_close(monkeypatch):
    import logging
    from utils import log_handler

    async def scenario():
        fake_bot = SimpleNamespace(send_message=AsyncMock())
        monkeypatch.setattr(log_handler, 'LOG_CHAT_ID', '-100999')
        monkeypatch.setattr(log_handler, 'MIN_INTERVAL_SEC', 60)

        handler = await log_handler.setup_telegram_logging(fake_bot)
        assert handler is not None

        test_logger = logging.getLogger('test.tg_log_handler')
        test_logger.setLevel(logging.ERROR)
        test_logger.error('first <boom>')
        await asyncio.sleep(0)
        assert fake_bot.send_message.await_count == 1
        assert '&lt;boom&gt;' in fake_bot.send_message.await_args_list[0].args[1]

        # Second record falls inside MIN_INTERVAL_SEC -> scheduled via _flush_task
        test_logger.error('second error')
        assert handler._flush_task is not None

        await log_handler.close_telegram_logging()
        assert handler not in logging.getLogger().handlers
        assert log_handler._telegram_handler is None
        assert fake_bot.send_message.await_count == 2
        assert 'second error' in fake_bot.send_message.await_args_list[1].args[1]

    asyncio.run(scenario())
