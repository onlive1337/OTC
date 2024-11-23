from data import user_data
from config.config import ACTIVE_CURRENCIES, ALL_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import CallbackQuery, Message
import logging
from utils.utils import check_admin_rights, show_not_admin_message

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

user_data = user_data.UserData()

async def show_chat_currencies(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = int(parts[3])
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    chat_currencies = user_data.get_chat_currencies(chat_id)
    user_lang = user_data.get_user_language(user_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in chat_currencies else "❌"
        kb.button(text=f"{ALL_CURRENCIES[currency]} {currency} {status}", 
                 callback_data=f"toggle_chat_currency_{chat_id}_{currency}_{page}")
    
    if page > 0:
        kb.button(text=f"⬅️ {LANGUAGES[user_lang]['back']}", 
                 callback_data=f"show_chat_currencies_{chat_id}_{page-1}")
    if end < len(ACTIVE_CURRENCIES):
        kb.button(text=f"{LANGUAGES[user_lang]['forward']} ➡️", 
                 callback_data=f"show_chat_currencies_{chat_id}_{page+1}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], 
              callback_data=f"back_to_chat_settings_{chat_id}")
    kb.adjust(1)
    
    await callback_query.message.edit_text(
        LANGUAGES[user_lang]['currencies'], 
        reply_markup=kb.as_markup()
    )

async def show_chat_crypto(callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split('_')[3])
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    chat_crypto = user_data.get_chat_crypto(chat_id)
    user_lang = user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in chat_crypto else "❌"
        kb.button(text=f"{ALL_CURRENCIES[crypto]} {crypto} {status}", 
                 callback_data=f"toggle_chat_crypto_{chat_id}_{crypto}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], 
              callback_data=f"back_to_chat_settings_{chat_id}")
    kb.adjust(2)
    
    await callback_query.message.edit_text(
        LANGUAGES[user_lang]['cryptocurrencies'], 
        reply_markup=kb.as_markup()
    )

async def toggle_chat_currency(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = int(parts[3])
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    currency = parts[4]
    page = int(parts[5]) if len(parts) > 5 else 0
    
    if str(chat_id) not in user_data.chat_data:
        user_data.initialize_chat_settings(chat_id)
    
    chat_currencies = user_data.get_chat_currencies(chat_id)
    
    if currency in chat_currencies:
        chat_currencies.remove(currency)
    else:
        chat_currencies.append(currency)
    
    user_data.set_chat_currencies(chat_id, chat_currencies)
    user_data.save_chat_data()
    user_data.update_chat_cache(chat_id)
    
    new_data = f"show_chat_currencies_{chat_id}_{page}"
    new_callback_query = callback_query.model_copy(update={'data': new_data})
    await show_chat_currencies(new_callback_query)

async def toggle_chat_crypto(callback_query: CallbackQuery):
    chat_id, crypto = callback_query.data.split('_')[3:]
    chat_id = int(chat_id)
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    if str(chat_id) not in user_data.chat_data:
        user_data.initialize_chat_settings(chat_id)
    
    chat_crypto = user_data.get_chat_crypto(chat_id)
    
    if crypto in chat_crypto:
        chat_crypto.remove(crypto)
    else:
        chat_crypto.append(crypto)
    
    user_data.set_chat_crypto(chat_id, chat_crypto)
    user_data.save_chat_data()
    user_data.update_chat_cache(chat_id)
    
    await show_chat_crypto(callback_query)

async def show_chat_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not await check_admin_rights(message, user_id, chat_id):
        await show_not_admin_message(message, user_id)
        return
    
    user_lang = user_data.get_user_language(user_id)

    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], 
              callback_data=f"show_chat_currencies_{chat_id}_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], 
              callback_data=f"show_chat_crypto_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], 
              callback_data=f"toggle_chat_quote_format_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['save_button'], 
              callback_data=f"save_chat_settings_{chat_id}")
    kb.adjust(2, 1, 1)
    
    use_quote = user_data.get_chat_quote_format(chat_id)
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['chat_settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await message.answer(settings_text, reply_markup=kb.as_markup())

async def save_chat_settings(callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split('_')[3])
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    user_lang = user_data.get_user_language(user_id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()

async def back_to_chat_settings(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = next((part for part in parts if part.lstrip('-').isdigit()), None)
    
    if chat_id is None:
        logger.error(f"Invalid callback data for back_to_chat_settings: {callback_query.data}")
        await callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")
        return

    chat_id = int(chat_id)
    user_id = callback_query.from_user.id
    
    if not await check_admin_rights(callback_query, user_id, chat_id):
        await show_not_admin_message(callback_query, user_id)
        return
    
    user_lang = user_data.get_user_language(user_id)

    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], 
              callback_data=f"show_chat_currencies_{chat_id}_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], 
              callback_data=f"show_chat_crypto_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], 
              callback_data=f"toggle_chat_quote_format_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['save_button'], 
              callback_data=f"save_chat_settings_{chat_id}")
    kb.adjust(2, 1, 1)
    
    use_quote = user_data.get_chat_quote_format(chat_id)
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['chat_settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())