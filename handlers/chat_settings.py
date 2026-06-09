from config.config import ACTIVE_CURRENCIES, CRYPTO_CURRENCIES
from utils.formatter import get_currency_symbol
from config.languages import LANGUAGES
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
import logging
from typing import Any
from utils.utils import check_admin_rights, show_not_admin_message
from utils.button_styles import primary_button, EMOJI
from utils.keyboards import build_chat_settings_kb, format_settings_text

logger = logging.getLogger(__name__)

from loader import user_data


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


async def _safe_edit_text(message: Any, text: str, reply_markup=None):
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise


async def _ensure_chat_initialized(chat_id: int):
    if chat_id not in user_data.chat_data:
        await user_data.initialize_chat_settings(chat_id)


def _add_back_to_chat_settings_button(kb: InlineKeyboardBuilder, user_lang: str, chat_id: int, emoji: str = EMOJI['back']):
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'], f"back_to_chat_settings_{chat_id}", emoji=emoji))

async def show_chat_currencies(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    parts = data.split('_')
    chat_id = int(parts[3])
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    chat_currencies = await user_data.get_chat_currencies(chat_id)
    user_lang = await user_data.get_chat_language(chat_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in chat_currencies else "❌"
        kb.row(primary_button(f"{get_currency_symbol(currency)}{currency} {status}",
                              f"toggle_chat_currency_{chat_id}_{currency}_{page}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['back'],
                 f"show_chat_currencies_{chat_id}_{page-1}", emoji=EMOJI['back']))
    if end < len(ACTIVE_CURRENCIES):
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['forward'],
                 f"show_chat_currencies_{chat_id}_{page+1}", emoji=EMOJI['forward']))
    if nav_buttons:
        kb.row(*nav_buttons)
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'],
              f"back_to_chat_settings_{chat_id}", emoji=EMOJI['settings']))
    
    await _safe_edit_text(callback_query.message, LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())

async def show_chat_crypto(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    chat_id = int(data.split('_')[3])
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    chat_crypto = await user_data.get_chat_crypto(chat_id)
    user_lang = await user_data.get_chat_language(chat_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in chat_crypto else "❌"
        kb.row(primary_button(f"{get_currency_symbol(crypto)}{crypto} {status}",
                              f"toggle_chat_crypto_{chat_id}_{crypto}"))
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'],
              f"back_to_chat_settings_{chat_id}", emoji=EMOJI['settings']))
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    
    await _safe_edit_text(callback_query.message, LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())

async def toggle_chat_currency(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    parts = data.split('_')
    chat_id = int(parts[3])
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    currency = parts[4]
    page = int(parts[5]) if len(parts) > 5 else 0
    
    await _ensure_chat_initialized(chat_id)
    
    chat_currencies = await user_data.get_chat_currencies(chat_id)
    
    if currency in chat_currencies:
        chat_currencies.remove(currency)
    else:
        chat_currencies.append(currency)
    
    await user_data.set_chat_currencies(chat_id, chat_currencies)
    
    new_data = f"show_chat_currencies_{chat_id}_{page}"
    new_callback_query = callback_query.model_copy(update={'data': new_data})
    await show_chat_currencies(new_callback_query)

async def toggle_chat_crypto(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    chat_id, crypto = data.split('_')[3:]
    chat_id = int(chat_id)
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    await _ensure_chat_initialized(chat_id)
    
    chat_crypto = await user_data.get_chat_crypto(chat_id)
    
    if crypto in chat_crypto:
        chat_crypto.remove(crypto)
    else:
        chat_crypto.append(crypto)
    
    await user_data.set_chat_crypto(chat_id, chat_crypto)
    
    await show_chat_crypto(callback_query)

async def toggle_chat_quote_format(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    parts = data.split('_')
    chat_id = int(parts[4])
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    use_quote = await user_data.get_chat_quote_format(chat_id)
    new_format = not use_quote
    await user_data.set_chat_quote_format(chat_id, new_format)
    
    user_lang = await user_data.get_chat_language(chat_id)
    kb = build_chat_settings_kb(user_lang, chat_id)
    
    await _safe_edit_text(
        callback_query.message,
        format_settings_text(user_lang, new_format, is_chat=True),
        reply_markup=kb.as_markup(),
    )

async def show_chat_settings(message: Message):
    from_user = message.from_user
    if from_user is None:
        return

    user_id = from_user.id
    chat_id = message.chat.id
    
    if not await check_admin_rights(message, user_id, chat_id):
        await show_not_admin_message(message, user_id)
        return
    
    user_lang = await user_data.get_chat_language(chat_id)
    use_quote = await user_data.get_chat_quote_format(chat_id)
    kb = build_chat_settings_kb(user_lang, chat_id)
    await message.answer(format_settings_text(user_lang, use_quote, is_chat=True), reply_markup=kb.as_markup())

async def save_chat_settings(callback_query: CallbackQuery):
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        await callback_query.answer()
        return

    chat_id = int(data.split('_')[3])
    user_id = from_user.id
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    user_lang = await user_data.get_chat_language(chat_id)
    await _safe_edit_text(callback_query.message, LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()

async def back_to_chat_settings(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer("Error. Please try again.")
        return

    parts = data.split('_')
    chat_id = next((part for part in parts if part.lstrip('-').isdigit()), None)
    
    if chat_id is None:
        logger.error("Invalid callback data for back_to_chat_settings: %s", callback_query.data)
        await callback_query.answer("Error. Please try again.")
        return

    chat_id = int(chat_id)
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    user_lang = await user_data.get_chat_language(chat_id)
    use_quote = await user_data.get_chat_quote_format(chat_id)
    kb = build_chat_settings_kb(user_lang, chat_id)
    
    await _safe_edit_text(
        callback_query.message,
        format_settings_text(user_lang, use_quote, is_chat=True),
        reply_markup=kb.as_markup(),
    )

async def change_chat_language(callback_query: CallbackQuery):
    data = callback_query.data
    if data is None:
        await callback_query.answer()
        return

    parts = data.split('_')
    chat_id = int(parts[3])
    if not await _ensure_chat_admin_and_answer(callback_query, chat_id):
        return

    user_lang = await user_data.get_chat_language(chat_id)
    
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button("Русский", f"set_chat_language_{chat_id}_ru"),
        primary_button("English", f"set_chat_language_{chat_id}_en")
    )
    _add_back_to_chat_settings_button(kb, user_lang, chat_id, emoji=EMOJI['back'])
    
    await _safe_edit_text(callback_query.message, LANGUAGES[user_lang]['language'], reply_markup=kb.as_markup())

async def set_chat_language(callback_query: CallbackQuery):
    data = callback_query.data
    from_user = callback_query.from_user
    if data is None or from_user is None:
        await callback_query.answer()
        return

    parts = data.split('_')
    chat_id = int(parts[3])
    new_lang = parts[4]
    user_id = from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return

    await user_data.set_chat_language(chat_id, new_lang)
    
    user_lang = await user_data.get_chat_language(chat_id)
    
    kb = InlineKeyboardBuilder()
    _add_back_to_chat_settings_button(kb, user_lang, chat_id, emoji=EMOJI['back'])
    
    await _safe_edit_text(callback_query.message, LANGUAGES[user_lang]['language_changed'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[user_lang]['language_changed'])