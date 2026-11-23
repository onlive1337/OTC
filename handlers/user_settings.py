from typing import Any

from aiogram.types import CallbackQuery, Message

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from loader import user_data
from utils.callbacks import (
    UserCurrenciesCB,
    UserFormatCB,
    UserLangCB,
    UserToggleCryptoCB,
    UserToggleCurrencyCB,
)
from utils.formatter import DISPLAY_FORMATS
from utils.keyboards import (
    build_back_to_settings_kb,
    build_crypto_kb,
    build_currencies_page_kb,
    build_display_format_kb,
    build_language_kb,
)
from utils.utils import safe_edit_text


async def _render_currencies_page(message: Any, user_id: int, page: int) -> None:
    if not isinstance(message, Message):
        return
    user_currencies = await user_data.get_user_currencies(user_id)
    user_lang = await user_data.get_user_language(user_id)
    kb = build_currencies_page_kb(user_lang, user_currencies, page)
    await safe_edit_text(message, LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())


async def _render_crypto_page(message: Any, user_id: int) -> None:
    if not isinstance(message, Message):
        return
    user_crypto = await user_data.get_user_crypto(user_id)
    user_lang = await user_data.get_user_language(user_id)
    kb = build_crypto_kb(user_lang, user_crypto)
    await safe_edit_text(message, LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())


async def _render_display_format_page(message: Any, user_id: int) -> None:
    if not isinstance(message, Message):
        return
    user_lang = await user_data.get_user_language(user_id)
    current_format = await user_data.get_user_display_format(user_id)
    kb = build_display_format_kb(user_lang, current_format)
    await safe_edit_text(message, LANGUAGES[user_lang]['display_format_title'], reply_markup=kb.as_markup())


async def change_display_format(callback_query: CallbackQuery):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None:
        return

    await _render_display_format_page(callback_query.message, from_user.id)


async def set_display_format(callback_query: CallbackQuery, callback_data: UserFormatCB):
    from_user = callback_query.from_user
    if from_user is None or callback_data.fmt not in DISPLAY_FORMATS:
        await callback_query.answer()
        return

    user_id = from_user.id
    await user_data.set_user_display_format(user_id, callback_data.fmt)
    await user_data.update_user_data(user_id)
    user_lang = await user_data.get_user_language(user_id)

    await _render_display_format_page(callback_query.message, user_id)
    await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])


async def show_currencies(callback_query: CallbackQuery, callback_data: UserCurrenciesCB):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None:
        return

    await _render_currencies_page(callback_query.message, from_user.id, callback_data.page)


async def show_crypto(callback_query: CallbackQuery):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None:
        return

    await _render_crypto_page(callback_query.message, from_user.id)


async def toggle_currency(callback_query: CallbackQuery, callback_data: UserToggleCurrencyCB):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None or callback_data.currency not in ACTIVE_CURRENCIES:
        return

    user_currencies = list(await user_data.get_user_currencies(from_user.id))
    if callback_data.currency in user_currencies:
        user_currencies.remove(callback_data.currency)
    else:
        user_currencies.append(callback_data.currency)

    await user_data.set_user_currencies(from_user.id, user_currencies)
    await user_data.update_user_data(from_user.id)
    await _render_currencies_page(callback_query.message, from_user.id, callback_data.page)


async def toggle_crypto(callback_query: CallbackQuery, callback_data: UserToggleCryptoCB):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None or callback_data.symbol not in CRYPTO_CURRENCIES:
        return

    user_id = from_user.id
    user_crypto = list(await user_data.get_user_crypto(user_id))
    if callback_data.symbol in user_crypto:
        user_crypto.remove(callback_data.symbol)
    else:
        user_crypto.append(callback_data.symbol)

    await user_data.set_user_crypto(user_id, user_crypto)
    await user_data.update_user_data(user_id)
    await _render_crypto_page(callback_query.message, user_id)


async def change_language(callback_query: CallbackQuery):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None or not isinstance(callback_query.message, Message):
        return

    current_lang = await user_data.get_user_language(from_user.id)
    kb = build_language_kb(current_lang)
    await safe_edit_text(callback_query.message, LANGUAGES[current_lang]['language'], reply_markup=kb.as_markup())


async def set_language(callback_query: CallbackQuery, callback_data: UserLangCB):
    from_user = callback_query.from_user
    if from_user is None or callback_data.lang not in LANGUAGES:
        await callback_query.answer()
        return

    user_id = from_user.id
    new_lang = callback_data.lang
    await user_data.set_user_language(user_id, new_lang)
    await user_data.update_user_data(user_id)

    kb = build_back_to_settings_kb(new_lang)
    await safe_edit_text(
        callback_query.message,
        LANGUAGES[new_lang]['language_changed'],
        reply_markup=kb.as_markup(),
    )
    await callback_query.answer(LANGUAGES[new_lang]['language_changed'])
