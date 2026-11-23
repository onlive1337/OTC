import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import ujson
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ButtonStyle, ChatMemberStatus, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    AnswerInlineQuery,
    AnswerWidgetQuery,
    CopyMessage,
    DeleteMessage,
    EditEphemeralMessageText,
    SendMessage,
    SendRichMessage,
    SendWidget,
)
from aiogram.test import Blueprint, build_environment, detach_router
from aiogram.types import InputRichMessageContent

import data.connection as connection
import loader
from config import config as app_config
from config.languages import LANGUAGES
from data.user_data import UserData
from handlers import admin, chat_settings, conversion, general, inline, settings, user_settings, widget
from utils import rates as rates_mod, utils
from utils.callbacks import (
    ChatCurrenciesCB,
    ChatFormatCB,
    ChatLangCB,
    ChatSettingsActionCB,
    ChatToggleCurrencyCB,
    UserCurrenciesCB,
    UserFormatCB,
    UserLangCB,
    UserToggleCryptoCB,
    UserToggleCurrencyCB,
)
from utils.middleware import ErrorBoundaryMiddleware, RateLimitMiddleware, get_metrics

DEFAULT_RATES = {
    'USD': 1.0,
    'EUR': 0.9,
    'RUB': 90.0,
    'GBP': 0.8,
    'JPY': 150.0,
    'CHF': 0.88,
    'BYN': 3.2,
    'BTC': 0.00001,
    'ETH': 0.0003,
    'USDT': 1.0,
    'BNB': 0.0015,
    'XRP': 0.5,
}

_ROUTERS = (general.router, admin.router, settings.router, widget.router, inline.router, conversion.router)


def _new_blueprint() -> Blueprint:
    return Blueprint(
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        bot_group_privacy=False,
    )


@asynccontextmanager
async def _otc_env(
    monkeypatch,
    tmp_path,
    blueprint: Blueprint,
    *,
    rates: dict | None = None,
    admin_ids: frozenset[int] = frozenset(),
    rate_limit: int = 100,
    enable_widget_calc: bool = False,
):
    monkeypatch.setattr(app_config, 'ENABLE_WIDGET_CALC', enable_widget_calc)
    monkeypatch.setattr(connection, 'DB_PATH', str(tmp_path / 'integration.db'))
    monkeypatch.setattr(connection, 'DB_BACKUP_INTERVAL_HOURS', 0)

    ud = UserData()
    await ud.init_db()

    for module in (
        loader,
        general,
        admin,
        settings,
        user_settings,
        chat_settings,
        widget,
        inline,
        conversion,
        utils,
    ):
        monkeypatch.setattr(module, 'user_data', ud)

    rates_dict = rates if rates is not None else dict(DEFAULT_RATES)
    monkeypatch.setattr(inline, 'get_exchange_rates', AsyncMock(return_value=rates_dict))
    monkeypatch.setattr(conversion, 'get_exchange_rates', AsyncMock(return_value=rates_dict))
    monkeypatch.setattr(widget, 'get_exchange_rates', AsyncMock(return_value=rates_dict))
    monkeypatch.setattr(widget, 'refresh_rates', AsyncMock(return_value=rates_dict))

    env = build_environment(blueprint)
    monkeypatch.setattr(admin, 'bot', env.bot)
    monkeypatch.setattr(admin, 'ADMIN_IDS', admin_ids)
    monkeypatch.setattr(admin, '_broadcast_in_progress', False)

    for observer in (
        env.dispatcher.message,
        env.dispatcher.callback_query,
        env.dispatcher.inline_query,
        env.dispatcher.widget_query,
    ):
        observer.middleware(ErrorBoundaryMiddleware())
        observer.middleware(RateLimitMiddleware(limit=rate_limit, window=3.0))

    for router in _ROUTERS:
        detach_router(router)
        env.dispatcher.include_router(router)

    try:
        yield env, ud
    finally:
        for router in _ROUTERS:
            detach_router(router)
        await ud.close()
        await env.dispose()


def test_start_and_menu_navigation_callbacks(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            actor = env.user(user).in_(chat)
            await actor.send('/start')

            bot_msg = env.chat(chat).messages[-1]
            assert bot_msg.text == LANGUAGES['ru']['welcome']
            buttons = [btn for row in bot_msg.reply_markup.inline_keyboard for btn in row]
            assert any(btn.style == ButtonStyle.PRIMARY.value for btn in buttons)
            assert any(btn.style == ButtonStyle.SUCCESS.value for btn in buttons)
            assert any(btn.icon_custom_emoji_id for btn in buttons)
            assert not any(btn.callback_data == 'open_calc' for btn in buttons)

            monkeypatch.setattr(app_config, 'ENABLE_WIDGET_CALC', True)
            await actor.send('/start')
            enabled_buttons = [
                btn for row in env.chat(chat).messages[-1].reply_markup.inline_keyboard for btn in row
            ]
            assert any(btn.callback_data == 'open_calc' for btn in enabled_buttons)

            await actor.click('howto')
            assert env.chat(chat).messages[-1].text == LANGUAGES['ru']['help']

            await actor.click('back_to_main')
            assert env.chat(chat).messages[-1].text == LANGUAGES['ru']['welcome']

            await actor.send('/start settings')
            assert LANGUAGES['ru']['settings'] in env.chat(chat).messages[-1].text

    asyncio.run(scenario())


def test_user_settings_callbacks_persist_to_db(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, ud):
            actor = env.user(user).in_(chat)
            await actor.send('/settings')
            assert await ud.get_user_display_format(user.id) == 'quote'
            assert await ud.get_user_quote_format(user.id) is True
            assert await ud.get_user_rich_format(user.id) is False

            await actor.click('change_display_format')
            await actor.click(UserFormatCB(fmt='plain').pack())
            assert await ud.get_user_display_format(user.id) == 'plain'
            assert await ud.get_user_quote_format(user.id) is False
            assert await ud.get_user_rich_format(user.id) is False

            await actor.click(UserFormatCB(fmt='table').pack())
            assert await ud.get_user_display_format(user.id) == 'table'
            assert await ud.get_user_quote_format(user.id) is False
            assert await ud.get_user_rich_format(user.id) is True

            await actor.click('back_to_settings')
            assert LANGUAGES['ru']['format_table'] in env.chat(chat).messages[-1].text

            answers_before = env.calls.count(AnswerCallbackQuery)
            await actor.click('change_language')
            assert env.calls.count(AnswerCallbackQuery) == answers_before + 1
            await actor.click(UserLangCB(lang='en').pack())
            assert await ud.get_user_language(user.id) == 'en'
            assert env.chat(chat).messages[-1].text == LANGUAGES['en']['language_changed']

    asyncio.run(scenario())


def test_currency_pagination_has_disabled_page_indicator(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        admin_user = bp.add_user(first_name='Admin', language_code='ru')
        private_chat = bp.add_private_chat(admin_user)
        group = bp.add_supergroup('OTC Group', bot_status=ChatMemberStatus.MEMBER)
        bp.set_member(group, admin_user, status=ChatMemberStatus.ADMINISTRATOR)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            priv_actor = env.user(admin_user).in_(private_chat)
            await priv_actor.send('/settings')
            await priv_actor.click(UserCurrenciesCB(page=0).pack())

            page1_buttons = [
                btn
                for row in env.chat(private_chat).messages[-1].reply_markup.inline_keyboard
                for btn in row
            ]
            indicator = next((b for b in page1_buttons if b.text == '1 / 8'), None)
            assert indicator is not None
            assert indicator.disabled is not None
            assert indicator.callback_data is None

            await priv_actor.click(UserCurrenciesCB(page=1).pack())
            page2_buttons = [
                btn
                for row in env.chat(private_chat).messages[-1].reply_markup.inline_keyboard
                for btn in row
            ]
            indicator2 = next((b for b in page2_buttons if b.text == '2 / 8'), None)
            assert indicator2 is not None and indicator2.disabled is not None

            grp_actor = env.user(admin_user).in_(group)
            await grp_actor.send('/settings')
            await grp_actor.click(ChatCurrenciesCB(chat_id=group.id, page=0).pack())
            chat_page1_buttons = [
                btn
                for row in env.chat(group).ephemeral_messages(admin_user)[-1].reply_markup.inline_keyboard
                for btn in row
            ]
            chat_indicator = next((b for b in chat_page1_buttons if b.text == '1 / 8'), None)
            assert chat_indicator is not None and chat_indicator.disabled is not None

    asyncio.run(scenario())


def test_ephemeral_group_responses_and_fallback(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        regular_user = bp.add_user(first_name='John', language_code='en')
        admin_user = bp.add_user(first_name='Boss', language_code='ru')
        admin_bot_group = bp.add_supergroup('Admin Bot Group', bot_status=ChatMemberStatus.ADMINISTRATOR)
        member_bot_group = bp.add_supergroup('Member Bot Group', bot_status=ChatMemberStatus.MEMBER)
        bp.set_member(admin_bot_group, regular_user, status=ChatMemberStatus.MEMBER)
        bp.set_member(member_bot_group, regular_user, status=ChatMemberStatus.MEMBER)
        bp.set_member(member_bot_group, admin_user, status=ChatMemberStatus.ADMINISTRATOR)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            # 1. Bot is administrator -> sends private ephemeral reply in group
            public_before = len(env.chat(admin_bot_group).messages)
            await env.user(regular_user).in_(admin_bot_group).send('/settings')
            assert len(env.chat(admin_bot_group).messages) == public_before + 1  # only user's /settings
            eph_list = env.chat(admin_bot_group).ephemeral_messages(regular_user)
            assert len(eph_list) == 1
            eph_reply = eph_list[-1]
            assert eph_reply.ephemeral_message_id is not None
            assert eph_reply.text == LANGUAGES['en']['admin_only']

            # 2. Bot is plain member, user sends ephemeral command -> bot replies & edits ephemerally
            member_actor = env.user(admin_user).in_(member_bot_group)
            await member_actor.send('/settings', ephemeral=True)
            admin_eph = env.chat(member_bot_group).ephemeral_messages(admin_user)
            assert len(admin_eph) == 1
            settings_eph = admin_eph[-1]
            await member_actor.click(
                ChatSettingsActionCB(chat_id=member_bot_group.id, action='format').pack(),
                message=settings_eph,
            )
            assert env.calls.count(EditEphemeralMessageText) == 1
            updated_eph = env.chat(member_bot_group).ephemeral_messages(admin_user)[-1]
            await member_actor.click(
                ChatFormatCB(chat_id=member_bot_group.id, fmt='table').pack(),
                message=updated_eph,
            )
            assert env.calls.count(EditEphemeralMessageText) == 2

            # 3. Bot is plain member and API rejects proactive ephemeral send -> falls back cleanly
            with (
                env.on(SendMessage, chat_id=member_bot_group.id)
                .where(lambda call: call.ephemeral_message_parameters is not None)
                .raises(TelegramBadRequest)
            ):
                await env.user(regular_user).in_(member_bot_group).send('/settings')
            assert env.chat(member_bot_group).messages[-1].text == LANGUAGES['en']['admin_only']

    asyncio.run(scenario())


def test_conversions_math_unknown_currency_and_delete(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            actor = env.user(user).in_(chat)

            await actor.send('100 USD')
            conv_msg = env.chat(chat).messages[-1]
            assert '90.00' in conv_msg.text
            assert 'EUR' in conv_msg.text
            assert '<blockquote expandable>' in env.calls.last(SendMessage).text
            assert any(e.type == 'expandable_blockquote' for e in (conv_msg.entities or []))
            del_btn = conv_msg.reply_markup.inline_keyboard[0][0]
            assert del_btn.callback_data == 'delete_conversion'
            assert del_btn.style == ButtonStyle.DANGER.value

            msg_count_before = len(env.chat(chat).messages)
            await actor.click('delete_conversion', message=conv_msg)
            assert env.calls.count(DeleteMessage) == 1
            assert len(env.chat(chat).messages) == msg_count_before - 1

            await actor.send('100 USD EUR')
            targeted_msg = env.chat(chat).messages[-1]
            assert '90.00' in targeted_msg.text
            assert 'EUR' in targeted_msg.text
            assert '<blockquote' not in env.calls.last(SendMessage).text

            await actor.send('50+50')
            math_msg = env.chat(chat).messages[-1]
            assert math_msg.text == '50+50 = 100.00'
            assert any(e.type == 'bold' for e in (math_msg.entities or []))

            await actor.send('300 bny')
            unknown_msg = env.chat(chat).messages[-1]
            assert 'BNY' in unknown_msg.text
            assert 'BYN' in unknown_msg.text

    asyncio.run(scenario())


def test_rich_message_conversion_toggle_and_output(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, ud):
            actor = env.user(user).in_(chat)
            await actor.send('/settings')
            await actor.click('change_display_format')
            await actor.click(UserFormatCB(fmt='table').pack())

            await actor.send('100 USD')
            rich_call = env.calls.last(SendRichMessage)
            assert rich_call.rich_message.html is not None
            assert '<table bordered striped compact>' in rich_call.rich_message.html
            assert '<details' not in rich_call.rich_message.html
            assert 'EUR' in rich_call.rich_message.html

            # Inline mode uses the exact same table view via InputRichMessageContent
            await env.user(user).inline_query('100 USD')
            inline_rich = env.calls.last(AnswerInlineQuery)
            inline_content = inline_rich.results[0].input_message_content
            assert isinstance(inline_content, InputRichMessageContent)
            assert '<table bordered striped compact>' in inline_content.rich_message.html

            # When Telegram rejects InputRichMessageContent in inline mode, fallback sends HTML text
            with (
                env.on(AnswerInlineQuery)
                .where(lambda call: isinstance(call.results[0].input_message_content, InputRichMessageContent))
                .raises(TelegramBadRequest)
            ):
                await env.user(user).inline_query('100 USD')
            inline_fallback = env.calls.last(AnswerInlineQuery)
            assert hasattr(inline_fallback.results[0].input_message_content, 'message_text')
            assert '<blockquote' not in inline_fallback.results[0].input_message_content.message_text

            # Plain mode removes <blockquote expandable> both in DM and in inline mode
            await ud.set_user_display_format(user.id, 'plain')
            await actor.send('100 USD')
            assert '<blockquote' not in env.calls.last(SendMessage).text
            await env.user(user).inline_query('100 USD')
            inline_plain = env.calls.last(AnswerInlineQuery)
            assert '<blockquote' not in inline_plain.results[0].input_message_content.message_text

    asyncio.run(scenario())


def test_calculator_widget_disabled_by_default_and_works_when_enabled(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)
        group = bp.add_supergroup('OTC Group', bot_status=ChatMemberStatus.MEMBER)
        bp.set_member(group, user, status=ChatMemberStatus.MEMBER)

        async with _otc_env(monkeypatch, tmp_path, bp, enable_widget_calc=False) as (env, _ud):
            priv_actor = env.user(user).in_(chat)
            await priv_actor.send('/calc')
            assert env.calls.count(SendWidget) == 0
            assert env.chat(chat).messages[-1].text == LANGUAGES['ru']['widget_disabled']

            await env.user(user).in_(group).send('/calc')
            assert env.chat(group).ephemeral_messages(user)[-1].text == LANGUAGES['en']['widget_disabled']

            monkeypatch.setattr(app_config, 'ENABLE_WIDGET_CALC', True)
            await priv_actor.send('/calc')
            widget_call = env.calls.last(SendWidget)
            assert widget_call.allow_queries is True
            assert widget_call.chat_data is not None
            assert len(widget_call.chat_data.encode('utf-8')) <= 1024
            assert widget_call.caption == LANGUAGES['ru']['widget_caption']

            await priv_actor.widget_query('refresh')
            wq_answer = env.calls.last(AnswerWidgetQuery)
            assert wq_answer.data is not None
            assert len(wq_answer.data.encode('utf-8')) <= 1024
            assert 'USD' in ujson.loads(wq_answer.data)['r']

            await env.user(user).in_(group).send('/calc')
            grp_msg = env.chat(group).ephemeral_messages(user)[-1]
            assert grp_msg.text == LANGUAGES['en']['widget_private_only']
            dm_btn = grp_msg.reply_markup.inline_keyboard[0][0]
            assert dm_btn.url is not None and dm_btn.url.endswith('?start=calc')

    asyncio.run(scenario())


def test_group_chat_language_and_admin_settings_enforcement(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        regular_user = bp.add_user(first_name='John', language_code='en')
        admin_user = bp.add_user(first_name='Admin', language_code='en')
        group = bp.add_supergroup('OTC Group', bot_status=ChatMemberStatus.MEMBER)
        bp.set_member(group, regular_user, status=ChatMemberStatus.MEMBER)
        bp.set_member(group, admin_user, status=ChatMemberStatus.ADMINISTRATOR)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, ud):
            await ud.set_chat_language(group.id, 'ru')

            await env.user(regular_user).in_(group).send('100 USD')
            conv_msg = env.chat(group).messages[-1]
            assert LANGUAGES['ru']['fiat_currencies'] in conv_msg.text
            assert LANGUAGES['en']['fiat_currencies'] not in conv_msg.text

            await env.user(regular_user).in_(group).send('/settings')
            denied_msg = env.chat(group).ephemeral_messages(regular_user)[-1]
            assert denied_msg.text == LANGUAGES['ru']['admin_only']

            await env.user(admin_user).in_(group).send('/settings')
            admin_settings_msg = env.chat(group).ephemeral_messages(admin_user)[-1]
            assert LANGUAGES['ru']['chat_settings'] in admin_settings_msg.text
            callbacks = [
                btn.callback_data
                for row in admin_settings_msg.reply_markup.inline_keyboard
                for btn in row
            ]
            assert ChatCurrenciesCB(chat_id=group.id, page=0).pack() in callbacks

    asyncio.run(scenario())


def test_inline_query_and_settings_button_through_real_dispatcher(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, ud):
            await env.user(user).inline_query('100 USD EUR')
            answer = env.calls.last(AnswerInlineQuery)
            assert answer.is_personal is True
            assert len(answer.results) == 1
            assert '90.00' in answer.results[0].input_message_content.message_text

            await ud.set_user_currencies(user.id, [])
            await ud.set_user_crypto(user.id, [])
            await env.user(user).inline_query('100 USD')
            empty_answer = env.calls.last(AnswerInlineQuery)
            assert empty_answer.button is not None
            assert empty_answer.button.start_parameter == 'settings'

    asyncio.run(scenario())


def test_admin_commands_diagnostics_and_broadcast_copy_message(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        admin_user = bp.add_user(first_name='Boss', language_code='en')
        regular_user = bp.add_user(first_name='Alice', language_code='en')
        admin_chat = bp.add_private_chat(admin_user)
        regular_chat = bp.add_private_chat(regular_user)

        async with _otc_env(
            monkeypatch,
            tmp_path,
            bp,
            admin_ids=frozenset({admin_user.id}),
        ) as (env, ud):
            await ud.update_user_data(admin_user.id, language_code='en')
            await ud.update_user_data(regular_user.id, language_code='en')

            regular_actor = env.user(regular_user).in_(regular_chat)
            await regular_actor.send('/stats')
            assert env.chat(regular_chat).messages[-1].text == LANGUAGES['en']['no_admin_rights']
            await regular_actor.send('/health')
            assert env.chat(regular_chat).messages[-1].text == LANGUAGES['en']['no_admin_rights']

            admin_actor = env.user(admin_user).in_(admin_chat)
            await admin_actor.send('/stats')
            assert '2' in env.chat(admin_chat).messages[-1].text

            await admin_actor.send('/health')
            health_text = env.chat(admin_chat).messages[-1].text
            assert 'Bot Health' in health_text
            assert '🗄 DB: ✅' in health_text
            assert 'Bot API (@test_bot)' in health_text
            assert 'Privacy OFF:' in health_text

            await admin_actor.send('/broadcast')
            await admin_actor.send('Release announcement')
            preview_msg = env.chat(admin_chat).messages[-1]
            preview_callbacks = [
                btn.callback_data
                for row in preview_msg.reply_markup.inline_keyboard
                for btn in row
            ]
            assert 'broadcast_confirm' in preview_callbacks

            await admin_actor.click('broadcast_confirm')
            assert env.calls.count(CopyMessage) == 2
            assert any(m.text == 'Release announcement' for m in env.chat(regular_chat).messages)
            report_msg = env.chat(admin_chat).find_message(preview_msg.message_id)
            assert report_msg is not None and '2' in report_msg.text
            assert await env.state(admin_user, admin_chat).get_state() is None

            await admin_actor.send('50+50')
            assert env.chat(admin_chat).messages[-1].text == '50+50 = 100.00'

    asyncio.run(scenario())


def test_rate_limit_middleware_throttles_burst(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp, rate_limit=2) as (env, _ud):
            actor = env.user(user).in_(chat)
            await actor.send('10 USD')
            await actor.send('20 USD')
            await actor.send('30 USD')

            assert env.calls.count(SendMessage) == 2

    asyncio.run(scenario())


def test_error_boundary_middleware_catches_exception_and_replies(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        def _boom(_text):
            raise RuntimeError('boom')

        monkeypatch.setattr(conversion, 'parse_amount_and_currency', _boom)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            before_errors = get_metrics()['total_errors']
            await env.user(user).in_(chat).send('100 USD')

            assert get_metrics()['total_errors'] == before_errors + 1
            assert env.chat(chat).messages[-1].text == LANGUAGES['ru']['error']

    asyncio.run(scenario())


def test_settings_currency_crypto_toggles_and_single_callback_answer(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        admin_user = bp.add_user(first_name='Admin', language_code='ru')
        private_chat = bp.add_private_chat(admin_user)
        group = bp.add_supergroup('OTC Group', bot_status=ChatMemberStatus.MEMBER)
        bp.set_member(group, admin_user, status=ChatMemberStatus.ADMINISTRATOR)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, ud):
            priv_actor = env.user(admin_user).in_(private_chat)
            await priv_actor.send('/settings')
            await priv_actor.click(UserCurrenciesCB(page=0).pack())

            initial_user_cur = list(await ud.get_user_currencies(admin_user.id))
            target_cur = initial_user_cur[0]
            answers_before = env.calls.count(AnswerCallbackQuery)
            await priv_actor.click(UserToggleCurrencyCB(currency=target_cur, page=0).pack())
            assert env.calls.count(AnswerCallbackQuery) == answers_before + 1
            assert target_cur not in await ud.get_user_currencies(admin_user.id)

            await priv_actor.click('back_to_settings')
            await priv_actor.click('show_crypto')
            initial_crypto = list(await ud.get_user_crypto(admin_user.id))
            target_crypto = initial_crypto[0]
            answers_before = env.calls.count(AnswerCallbackQuery)
            await priv_actor.click(UserToggleCryptoCB(symbol=target_crypto).pack())
            assert env.calls.count(AnswerCallbackQuery) == answers_before + 1
            assert target_crypto not in await ud.get_user_crypto(admin_user.id)

            grp_actor = env.user(admin_user).in_(group)
            await grp_actor.send('/settings')
            await grp_actor.click(ChatCurrenciesCB(chat_id=group.id, page=0).pack())
            initial_chat_cur = list(await ud.get_chat_currencies(group.id))
            chat_target_cur = initial_chat_cur[0]
            answers_before = env.calls.count(AnswerCallbackQuery)
            await grp_actor.click(
                ChatToggleCurrencyCB(chat_id=group.id, currency=chat_target_cur, page=0).pack()
            )
            assert env.calls.count(AnswerCallbackQuery) == answers_before + 1
            assert chat_target_cur not in await ud.get_chat_currencies(group.id)

            await grp_actor.click(ChatSettingsActionCB(chat_id=group.id, action='back').pack())
            await grp_actor.click(ChatSettingsActionCB(chat_id=group.id, action='lang').pack())
            await grp_actor.click(ChatLangCB(chat_id=group.id, lang='ru').pack())
            assert await ud.get_chat_language(group.id) == 'ru'

    asyncio.run(scenario())


def test_about_and_view_changelog_render_safely_in_html(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp) as (env, _ud):
            actor = env.user(user).in_(chat)
            await actor.send('/start')
            await actor.click('about')
            await actor.click('view_changelog')

            changelog_msg = env.chat(chat).messages[-1]
            assert '1.9.0' in changelog_msg.text
            assert len(changelog_msg.text) <= 4000

    asyncio.run(scenario())


def test_widget_query_slow_refresh_falls_back_to_cache_within_timeout(monkeypatch, tmp_path):
    async def scenario():
        bp = _new_blueprint()
        user = bp.add_user(first_name='Ivan', language_code='ru')
        chat = bp.add_private_chat(user)

        async with _otc_env(monkeypatch, tmp_path, bp, enable_widget_calc=True) as (env, _ud):
            async def slow_refresh():
                await asyncio.sleep(5)
                return DEFAULT_RATES

            monkeypatch.setattr(widget, 'WIDGET_REFRESH_TIMEOUT', 0.05)
            monkeypatch.setattr(widget, 'refresh_rates', slow_refresh)
            monkeypatch.setitem(rates_mod.cache, 'exchange_rates', (dict(DEFAULT_RATES), 0.0))

            actor = env.user(user).in_(chat)
            await actor.send('/calc')
            await actor.widget_query('refresh')

            wq_answer = env.calls.last(AnswerWidgetQuery)
            assert wq_answer.data is not None
            assert 'USD' in ujson.loads(wq_answer.data)['r']

    asyncio.run(scenario())
