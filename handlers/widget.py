import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, WidgetQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config as app_config
from config.languages import LANGUAGES
from loader import user_data
from utils.button_styles import primary_button
from utils.rates import get_cached_rates_fallback, get_exchange_rates, refresh_rates
from utils.utils import reply_ephemeral_or_fallback
from utils.widget import WIDGET_HTML, build_widget_caption, build_widget_state

logger = logging.getLogger(__name__)

router = Router()

WIDGET_REFRESH_TIMEOUT = 10.0


async def send_calculator_widget(message: Message, user_id: int | None = None):
    uid = user_id or (message.from_user.id if message.from_user else 0)
    if not app_config.ENABLE_WIDGET_CALC:
        if message.chat.type != ChatType.PRIVATE:
            lang = await user_data.get_chat_language(message.chat.id)
            await reply_ephemeral_or_fallback(message, LANGUAGES[lang]['widget_disabled'])
        else:
            lang = await user_data.get_user_language(uid) if uid else 'ru'
            await message.answer(LANGUAGES[lang]['widget_disabled'])
        return

    if message.chat.type != ChatType.PRIVATE:
        chat_lang = await user_data.get_chat_language(message.chat.id)
        reply_markup = None
        if message.bot is not None:
            try:
                me = await message.bot.me()
                if me.username:
                    kb = InlineKeyboardBuilder()
                    kb.row(
                        primary_button(
                            LANGUAGES[chat_lang]['widget_open_dm_button'],
                            url=f"https://t.me/{me.username}?start=calc",
                        )
                    )
                    reply_markup = kb.as_markup()
            except TelegramAPIError:
                pass
        await reply_ephemeral_or_fallback(
            message,
            LANGUAGES[chat_lang]['widget_private_only'],
            reply_markup=reply_markup,
        )
        return

    data = await user_data.get_user_data(uid)
    user_lang = data.get('language', 'ru')
    rates = await get_exchange_rates()
    if not rates:
        await message.answer(LANGUAGES[user_lang]['error'])
        return

    chat_data = build_widget_state(
        rates,
        data.get('selected_currencies', []),
        data.get('selected_crypto', []),
        user_lang,
    )
    caption = build_widget_caption(user_lang)
    bot = message.bot
    if bot is None:
        return

    try:
        await bot.send_widget(
            chat_id=message.chat.id,
            html=WIDGET_HTML,
            chat_data=chat_data,
            caption=caption,
            allow_queries=True,
        )
    except TelegramAPIError as e:
        logger.warning("Failed to send calculator widget to user %s: %s", uid, e)
        await message.answer(LANGUAGES[user_lang]['widget_unavailable'])


@router.message(Command("calc"))
async def cmd_calc(message: Message):
    if message.from_user is None:
        return
    await user_data.update_user_data(message.from_user.id, language_code=message.from_user.language_code)
    await send_calculator_widget(message)


@router.callback_query(F.data == "open_calc")
async def open_calc_callback(callback_query: CallbackQuery):
    await callback_query.answer()
    if callback_query.from_user is None or not isinstance(callback_query.message, Message):
        return
    await user_data.update_user_data(
        callback_query.from_user.id,
        language_code=callback_query.from_user.language_code,
    )
    await send_calculator_widget(callback_query.message, user_id=callback_query.from_user.id)


@router.widget_query()
async def handle_widget_query(query: WidgetQuery, bot: Bot):
    uid = query.from_user.id
    data = await user_data.get_user_data(uid)
    user_lang = data.get('language', 'ru')

    rates = None
    try:
        rates = await asyncio.wait_for(refresh_rates(), timeout=WIDGET_REFRESH_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(
            "Widget rate refresh timed out after %.1fs, falling back to cached rates",
            WIDGET_REFRESH_TIMEOUT,
        )
    if not rates:
        rates = get_cached_rates_fallback()
    if not rates:
        try:
            rates = await asyncio.wait_for(get_exchange_rates(), timeout=2.0)
        except asyncio.TimeoutError:
            rates = {}

    if not rates:
        await query.answer()
        return

    state_json = build_widget_state(
        rates,
        data.get('selected_currencies', []),
        data.get('selected_crypto', []),
        user_lang,
    )
    await query.answer(data=state_json)

    if query.chat and query.message_id:
        try:
            await bot.edit_message_widget_data(
                chat_id=query.chat.id,
                message_id=query.message_id,
                chat_data=state_json,
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                logger.warning("Failed to update widget data: %s", e)
        except TelegramAPIError as e:
            logger.warning("Failed to update widget data: %s", e)
