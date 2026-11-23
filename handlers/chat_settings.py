from typing import Any

from aiogram.types import CallbackQuery, Message

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from loader import user_data
from utils.callbacks import (
    ChatCurrenciesCB,
    ChatFormatCB,
    ChatLangCB,
    ChatSettingsActionCB,
    ChatToggleCryptoCB,
    ChatToggleCurrencyCB,
)
from utils.formatter import DISPLAY_FORMATS
from utils.keyboards import (
    build_back_to_settings_kb,
    build_chat_settings_kb,
    build_crypto_kb,
    build_currencies_page_kb,
    build_display_format_kb,
    build_language_kb,
    format_settings_text,
)
from utils.utils import check_admin_rights, safe_edit_text, show_not_admin_message


async def _ensure_chat_admin_and_answer(callback_query: CallbackQuery, chat_id: int) -> bool:
    from_user = callback_query.from_user
    if from_user is None:
        await callback_query.answer()
        return False

    user_id = from_user.id
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return False
    await callback_query.answer()
    return True


async def _render_chat_currencies_page(message: Any, chat_id: int, page: int) -> None:
    if not isinstance(message, Message):
        return
    chat_currencies = await user_data.get_chat_currencies(chat_id)
    user_lang = await user_data.get_chat_language(chat_id)
    kb = build_currencies_page_kb(user_lang, chat_currencies, page, chat_id=chat_id)
    await safe_edit_text(message, LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())


async def _render_chat_crypto_page(message: Any, chat_id: int) -> None:
    if not isinstance(message, Message):
        return
    chat_crypto = await user_data.get_chat_crypto(chat_id)
    user_lang = await user_data.get_chat_language(chat_id)
    kb = build_crypto_kb(user_lang, chat_crypto, chat_id=chat_id)
    await safe_edit_text(message, LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())


async def _render_chat_display_format_page(message: Any, chat_id: int) -> None:
    if not isinstance(message, Message):
        return
    user_lang = await user_data.get_chat_language(chat_id)
    current_format = await user_data.get_chat_display_format(chat_id)
    kb = build_display_format_kb(user_lang, current_format, chat_id=chat_id)
    await safe_edit_text(message, LANGUAGES[user_lang]['display_format_title'], reply_markup=kb.as_markup())


async def show_chat_currencies(callback_query: CallbackQuery, callback_data: ChatCurrenciesCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    await _render_chat_currencies_page(callback_query.message, chat_id, callback_data.page)


async def show_chat_crypto(callback_query: CallbackQuery, callback_data: ChatSettingsActionCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    await _render_chat_crypto_page(callback_query.message, chat_id)


async def toggle_chat_currency(callback_query: CallbackQuery, callback_data: ChatToggleCurrencyCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return
    if callback_data.currency not in ACTIVE_CURRENCIES:
        return

    chat_currencies = list(await user_data.get_chat_currencies(chat_id))
    if callback_data.currency in chat_currencies:
        chat_currencies.remove(callback_data.currency)
    else:
        chat_currencies.append(callback_data.currency)

    await user_data.set_chat_currencies(chat_id, chat_currencies)
    await _render_chat_currencies_page(callback_query.message, chat_id, callback_data.page)


async def toggle_chat_crypto(callback_query: CallbackQuery, callback_data: ChatToggleCryptoCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return
    if callback_data.symbol not in CRYPTO_CURRENCIES:
        return

    chat_crypto = list(await user_data.get_chat_crypto(chat_id))
    if callback_data.symbol in chat_crypto:
        chat_crypto.remove(callback_data.symbol)
    else:
        chat_crypto.append(callback_data.symbol)

    await user_data.set_chat_crypto(chat_id, chat_crypto)
    await _render_chat_crypto_page(callback_query.message, chat_id)


async def change_chat_display_format(callback_query: CallbackQuery, callback_data: ChatSettingsActionCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    await _render_chat_display_format_page(callback_query.message, chat_id)


async def set_chat_display_format(callback_query: CallbackQuery, callback_data: ChatFormatCB):
    from_user = callback_query.from_user
    if from_user is None or callback_data.fmt not in DISPLAY_FORMATS:
        await callback_query.answer()
        return

    chat_id = callback_data.chat_id
    user_id = from_user.id
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return

    await user_data.set_chat_display_format(chat_id, callback_data.fmt)
    user_lang = await user_data.get_chat_language(chat_id)
    await _render_chat_display_format_page(callback_query.message, chat_id)
    await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])


async def save_chat_settings(callback_query: CallbackQuery, callback_data: ChatSettingsActionCB):
    from_user = callback_query.from_user
    if from_user is None:
        await callback_query.answer()
        return

    chat_id = callback_data.chat_id
    user_id = from_user.id
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return

    user_lang = await user_data.get_chat_language(chat_id)
    await safe_edit_text(callback_query.message, LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()


async def back_to_chat_settings(callback_query: CallbackQuery, callback_data: ChatSettingsActionCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    user_lang = await user_data.get_chat_language(chat_id)
    display_format = await user_data.get_chat_display_format(chat_id)
    kb = build_chat_settings_kb(user_lang, chat_id)

    await safe_edit_text(
        callback_query.message,
        format_settings_text(user_lang, display_format, is_chat=True),
        reply_markup=kb.as_markup(),
    )


async def change_chat_language(callback_query: CallbackQuery, callback_data: ChatSettingsActionCB):
    chat_id = callback_data.chat_id
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    user_lang = await user_data.get_chat_language(chat_id)
    kb = build_language_kb(user_lang, chat_id=chat_id)
    await safe_edit_text(callback_query.message, LANGUAGES[user_lang]['language'], reply_markup=kb.as_markup())


async def set_chat_language(callback_query: CallbackQuery, callback_data: ChatLangCB):
    from_user = callback_query.from_user
    if from_user is None or callback_data.lang not in LANGUAGES:
        await callback_query.answer()
        return

    chat_id = callback_data.chat_id
    user_id = from_user.id
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return

    await user_data.set_chat_language(chat_id, callback_data.lang)
    user_lang = await user_data.get_chat_language(chat_id)
    kb = build_back_to_settings_kb(user_lang, chat_id=chat_id)

    await safe_edit_text(callback_query.message, LANGUAGES[user_lang]['language_changed'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[user_lang]['language_changed'])
