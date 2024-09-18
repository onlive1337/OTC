from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from data import user_data
from data.chat_settings import back_to_chat_settings
from config.config import ACTIVE_CURRENCIES, ALL_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from aiogram.utils.keyboard import InlineKeyboardBuilder

user_data = user_data.UserData()

def get_process_settings():
    from main import process_settings
    return process_settings

async def toggle_quote_format(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    
    if 'chat' in callback_query.data:
        chat_id = int(parts[-1])
        current_setting = user_data.get_chat_quote_format(chat_id)
        new_setting = not current_setting
        user_data.set_chat_quote_format(chat_id, new_setting)
        quote_status = LANGUAGES[user_lang]['on'] if new_setting else LANGUAGES[user_lang]['off']
        settings_text = f"{LANGUAGES[user_lang]['chat_settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data=f"show_chat_currencies_{chat_id}_0")
        kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data=f"show_chat_crypto_{chat_id}")
        kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data=f"toggle_chat_quote_format_{chat_id}")
        kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
        kb.adjust(2, 1, 1)
        
        try:
            await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    else:
        current_setting = user_data.get_user_quote_format(user_id)
        new_setting = not current_setting
        user_data.set_user_quote_format(user_id, new_setting)
        quote_status = LANGUAGES[user_lang]['on'] if new_setting else LANGUAGES[user_lang]['off']
        settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
        kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
        kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
        kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
        kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
        kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
        kb.adjust(2, 2, 1, 1)
        
        try:
            await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                raise
        await callback_query.answer(LANGUAGES[user_lang]['setting_updated'])
    
    user_data.update_user_cache(user_id)

async def show_currencies(callback_query: CallbackQuery):
    page = int(callback_query.data.split('_')[-1])
    user_id = callback_query.from_user.id
    user_currencies = user_data.get_user_currencies(user_id)
    user_lang = user_data.get_user_language(user_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in user_currencies else "❌"
        kb.button(text=f"{ALL_CURRENCIES[currency]} {currency} {status}", callback_data=f"toggle_currency_{currency}_{page}")
    
    if page > 0:
        kb.button(text=f"⬅️ {LANGUAGES[user_lang]['back']}", callback_data=f"show_currencies_{page-1}")
    if end < len(ACTIVE_CURRENCIES):
        kb.button(text=f"{LANGUAGES[user_lang]['forward']} ➡️", callback_data=f"show_currencies_{page+1}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], callback_data="back_to_settings")
    kb.adjust(1)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())

async def show_crypto(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_crypto = user_data.get_user_crypto(user_id)
    user_lang = user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in user_crypto else "❌"
        kb.button(text=f"{ALL_CURRENCIES[crypto]} {crypto} {status}", callback_data=f"toggle_crypto_{crypto}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], callback_data="back_to_settings")
    kb.adjust(2)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())

async def toggle_currency(callback_query: CallbackQuery):
    currency, page = callback_query.data.split('_')[2:]
    page = int(page)
    user_currencies = user_data.get_user_currencies(callback_query.from_user.id)
    
    if currency in user_currencies:
        user_currencies.remove(currency)
    else:
        user_currencies.append(currency)
    
    user_data.set_user_currencies(callback_query.from_user.id, user_currencies)
    user_data.update_user_cache(callback_query.from_user.id)
    await show_currencies(callback_query)

async def toggle_crypto(callback_query: CallbackQuery):
    crypto = callback_query.data.split('_')[-1]
    user_id = callback_query.from_user.id
    user_crypto = user_data.get_user_crypto(user_id)
    
    if crypto in user_crypto:
        user_crypto.remove(crypto)
    else:
        user_crypto.append(crypto)
    
    user_data.set_user_crypto(user_id, user_crypto)
    user_data.update_user_cache(user_id)
    await show_crypto(callback_query)

async def change_language(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_lang = user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="set_language_ru")
    kb.button(text="🇬🇧 English", callback_data="set_language_en")
    kb.button(text=LANGUAGES[current_lang]['back_to_settings'], callback_data="back_to_settings")
    kb.adjust(2, 1)
    
    await callback_query.message.edit_text(LANGUAGES[current_lang]['language'], reply_markup=kb.as_markup())

async def set_language(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    new_lang = callback_query.data.split('_')[-1]
    user_data.set_user_language(user_id, new_lang)
    user_data.update_user_cache(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[new_lang]['back_to_settings'], callback_data="back_to_settings")
    
    await callback_query.message.edit_text(LANGUAGES[new_lang]['language_changed'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[new_lang]['language_changed'])