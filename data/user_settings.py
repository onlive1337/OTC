from typing import Any

from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from loader import user_data
from utils.button_styles import primary_button, EMOJI
from utils.formatter import get_currency_symbol
from utils.keyboards import build_user_settings_kb, build_chat_settings_kb, format_settings_text


async def _safe_edit_text(message: Any, text: str, reply_markup=None):
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def toggle_quote_format(callback_query: CallbackQuery):
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        return

    parts = data.split('_')
    user_id = from_user.id
    user_lang = await user_data.get_user_language(user_id)
    
    if 'chat' in data:
        chat_id = int(parts[-1])
        current_setting = await user_data.get_chat_quote_format(chat_id)
        new_setting = not current_setting
        await user_data.set_chat_quote_format(chat_id, new_setting)
        
        kb = build_chat_settings_kb(user_lang, chat_id)
        message = callback_query.message
        if not isinstance(message, Message):
            await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
            return

        await _safe_edit_text(
            message,
            format_settings_text(user_lang, new_setting, is_chat=True),
            reply_markup=kb.as_markup(),
        )
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    else:
        current_setting = await user_data.get_user_quote_format(user_id)
        new_setting = not current_setting
        await user_data.set_user_quote_format(user_id, new_setting)
        
        kb = build_user_settings_kb(user_lang)
        message = callback_query.message
        if not isinstance(message, Message):
            await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
            return

        await _safe_edit_text(
            message,
            format_settings_text(user_lang, new_setting),
            reply_markup=kb.as_markup(),
        )
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    
    await user_data.update_user_data(user_id)

async def show_currencies(callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        return

    page = int(data.split('_')[-1])
    user_id = from_user.id
    user_currencies = await user_data.get_user_currencies(user_id)
    user_lang = await user_data.get_user_language(user_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in user_currencies else "❌"
        kb.row(primary_button(f"{get_currency_symbol(currency)}{currency} {status}", f"toggle_currency_{currency}_{page}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['back'], f"show_currencies_{page-1}", emoji=EMOJI['back']))
    if end < len(ACTIVE_CURRENCIES):
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['forward'], f"show_currencies_{page+1}", emoji=EMOJI['forward']))
    if nav_buttons:
        kb.row(*nav_buttons)
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['settings']))
    
    message = callback_query.message
    if not isinstance(message, Message):
        return

    await _safe_edit_text(message, LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())

async def show_crypto(callback_query: CallbackQuery):
    await callback_query.answer()
    from_user = callback_query.from_user
    if from_user is None:
        return

    user_id = from_user.id
    user_crypto = await user_data.get_user_crypto(user_id)
    user_lang = await user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in user_crypto else "❌"
        kb.row(primary_button(f"{get_currency_symbol(crypto)}{crypto} {status}", f"toggle_crypto_{crypto}"))
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['settings']))
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    
    message = callback_query.message
    if not isinstance(message, Message):
        return

    await _safe_edit_text(message, LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())

async def toggle_currency(callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        return

    currency, page = data.split('_')[2:]
    user_currencies = await user_data.get_user_currencies(from_user.id)

    if currency in user_currencies:
        user_currencies.remove(currency)
    else:
        user_currencies.append(currency)
    
    await user_data.set_user_currencies(from_user.id, user_currencies)
    await user_data.update_user_data(from_user.id)
    await show_currencies(callback_query)

async def toggle_crypto(callback_query: CallbackQuery):
    await callback_query.answer()
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        return

    crypto = data.split('_')[-1]
    user_id = from_user.id
    user_crypto = await user_data.get_user_crypto(user_id)
    
    if crypto in user_crypto:
        user_crypto.remove(crypto)
    else:
        user_crypto.append(crypto)
    
    await user_data.set_user_crypto(user_id, user_crypto)
    await user_data.update_user_data(user_id)
    await show_crypto(callback_query)

async def change_language(callback_query: CallbackQuery):
    from_user = callback_query.from_user
    if from_user is None:
        return

    user_id = from_user.id
    current_lang = await user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button("Русский", "set_language_ru"),
        primary_button("English", "set_language_en")
    )
    kb.row(primary_button(LANGUAGES[current_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['back']))
    
    message = callback_query.message
    if not isinstance(message, Message):
        return

    await _safe_edit_text(message, LANGUAGES[current_lang]['language'], reply_markup=kb.as_markup())

async def set_language(callback_query: CallbackQuery):
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        return

    user_id = from_user.id
    new_lang = data.split('_')[-1]
    await user_data.set_user_language(user_id, new_lang)
    await user_data.update_user_data(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[new_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['back']))
    
    message = callback_query.message
    if not isinstance(message, Message):
        return

    await _safe_edit_text(message, LANGUAGES[new_lang]['language_changed'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[new_lang]['language_changed'])