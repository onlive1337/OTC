from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from config.config import ACTIVE_CURRENCIES, ALL_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from aiogram.utils.keyboard import InlineKeyboardBuilder

from loader import user_data
from utils.button_styles import primary_button, success_button, EMOJI
from utils.keyboards import build_user_settings_kb, build_chat_settings_kb, format_settings_text

async def toggle_quote_format(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    user_id = callback_query.from_user.id
    user_lang = await user_data.get_user_language(user_id)
    
    if 'chat' in callback_query.data:
        chat_id = int(parts[-1])
        current_setting = await user_data.get_chat_quote_format(chat_id)
        new_setting = not current_setting
        await user_data.set_chat_quote_format(chat_id, new_setting)
        
        kb = build_chat_settings_kb(user_lang, chat_id)
        try:
            await callback_query.message.edit_text(
                format_settings_text(user_lang, new_setting, is_chat=True),
                reply_markup=kb.as_markup()
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    else:
        current_setting = await user_data.get_user_quote_format(user_id)
        new_setting = not current_setting
        await user_data.set_user_quote_format(user_id, new_setting)
        
        kb = build_user_settings_kb(user_lang)
        try:
            await callback_query.message.edit_text(
                format_settings_text(user_lang, new_setting),
                reply_markup=kb.as_markup()
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    
    await user_data.update_user_data(user_id)

async def show_currencies(callback_query: CallbackQuery):
    page = int(callback_query.data.split('_')[-1])
    user_id = callback_query.from_user.id
    user_currencies = await user_data.get_user_currencies(user_id)
    user_lang = await user_data.get_user_language(user_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in user_currencies else "❌"
        kb.row(primary_button(f"{ALL_CURRENCIES[currency]} {currency} {status}", f"toggle_currency_{currency}_{page}"))
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['back'], f"show_currencies_{page-1}", emoji=EMOJI['back']))
    if end < len(ACTIVE_CURRENCIES):
        nav_buttons.append(primary_button(LANGUAGES[user_lang]['forward'], f"show_currencies_{page+1}", emoji=EMOJI['forward']))
    if nav_buttons:
        kb.row(*nav_buttons)
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['settings']))
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())

async def show_crypto(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_crypto = await user_data.get_user_crypto(user_id)
    user_lang = await user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in user_crypto else "❌"
        kb.row(primary_button(f"{ALL_CURRENCIES[crypto]} {crypto} {status}", f"toggle_crypto_{crypto}"))
    
    kb.row(primary_button(LANGUAGES[user_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['settings']))
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())

async def toggle_currency(callback_query: CallbackQuery):
    currency, page = callback_query.data.split('_')[2:]
    page = int(page)
    user_currencies = await user_data.get_user_currencies(callback_query.from_user.id)
    
    if currency in user_currencies:
        user_currencies.remove(currency)
    else:
        user_currencies.append(currency)
    
    await user_data.set_user_currencies(callback_query.from_user.id, user_currencies)
    await user_data.update_user_data(callback_query.from_user.id)
    await show_currencies(callback_query)

async def toggle_crypto(callback_query: CallbackQuery):
    crypto = callback_query.data.split('_')[-1]
    user_id = callback_query.from_user.id
    user_crypto = await user_data.get_user_crypto(user_id)
    
    if crypto in user_crypto:
        user_crypto.remove(crypto)
    else:
        user_crypto.append(crypto)
    
    await user_data.set_user_crypto(user_id, user_crypto)
    await user_data.update_user_data(user_id)
    await show_crypto(callback_query)

async def change_language(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_lang = await user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.row(
        primary_button("Русский", "set_language_ru"),
        primary_button("English", "set_language_en")
    )
    kb.row(primary_button(LANGUAGES[current_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['back']))
    
    await callback_query.message.edit_text(LANGUAGES[current_lang]['language'], reply_markup=kb.as_markup())

async def set_language(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    new_lang = callback_query.data.split('_')[-1]
    await user_data.set_user_language(user_id, new_lang)
    await user_data.update_user_data(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.row(primary_button(LANGUAGES[new_lang]['back_to_settings'], "back_to_settings", emoji=EMOJI['back']))
    
    await callback_query.message.edit_text(LANGUAGES[new_lang]['language_changed'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[new_lang]['language_changed'])