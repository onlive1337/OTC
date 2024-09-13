import asyncio
import logging
import os
import re
import time
import math
from typing import Dict, Any
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, CallbackQuery, ChatMemberUpdated
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandStart
from typing import Tuple, Optional
from config import (
    BOT_TOKEN, ADMIN_IDS, CURRENT_VERSION, CACHE_EXPIRATION_TIME,
    ALL_CURRENCIES, CRYPTO_CURRENCIES, ACTIVE_CURRENCIES, CURRENCY_SYMBOLS, CURRENCY_ABBREVIATIONS
)
from languages import LANGUAGES
from user_data import UserData

cache: Dict[str, Any] = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    selecting_crypto = State()
    selecting_settings = State()

user_data = UserData()

async def get_cached_data(key: str) -> Dict[str, float]:
    if key in cache:
        cached_data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_EXPIRATION_TIME:
            return cached_data
    return None

async def set_cached_data(key: str, data: Dict[str, float]):
    cache[key] = (data, time.time())

async def get_exchange_rates() -> Dict[str, float]:
    try:
        cached_rates = await get_cached_data('exchange_rates')
        if cached_rates:
            logger.info("Using cached exchange rates")
            return cached_rates

        rates = {}
        async with aiohttp.ClientSession() as session:
            async with session.get('https://open.er-api.com/v6/latest/USD') as response:
                fiat_data = await response.json()
            if fiat_data['result'] == 'success':
                rates.update(fiat_data['rates'])

            crypto_ids = "bitcoin,ethereum,tether,binancecoin,ripple,cardano,solana,polkadot,dogecoin,matic-network,the-open-network,litecoin"
            async with session.get(f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd') as response:
                crypto_data = await response.json()
            
            crypto_mapping = {
                'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether', 'BNB': 'binancecoin',
                'XRP': 'ripple', 'ADA': 'cardano', 'SOL': 'solana', 'DOT': 'polkadot',
                'DOGE': 'dogecoin', 'MATIC': 'matic-network', 'TON': 'the-open-network',
                'LTC': 'litecoin'
            }
            for crypto, id in crypto_mapping.items():
                if id in crypto_data:
                    rates[crypto] = 1 / crypto_data[id]['usd']

            async with session.get('https://min-api.cryptocompare.com/data/pricemulti?fsyms=NOT,DUREV&tsyms=USD') as response:
                additional_crypto_data = await response.json()
            for crypto in ['NOT', 'DUREV']:
                if crypto in additional_crypto_data:
                    rates[crypto] = 1 / additional_crypto_data[crypto]['USD']

        all_currencies = set(ACTIVE_CURRENCIES + CRYPTO_CURRENCIES)
        missing_currencies = all_currencies - set(rates.keys())
        
        if missing_currencies:
            logger.warning(f"Missing currencies: {missing_currencies}. Attempting to fetch from alternative sources.")
            
            missing_fiat = missing_currencies.intersection(set(ACTIVE_CURRENCIES))
            if missing_fiat:
                async with session.get(f'https://api.exchangerate-api.com/v4/latest/USD') as response:
                    alt_fiat_data = await response.json()
                for currency in missing_fiat:
                    if currency in alt_fiat_data['rates']:
                        rates[currency] = alt_fiat_data['rates'][currency]
            
            missing_crypto = missing_currencies.intersection(set(CRYPTO_CURRENCIES))
            if missing_crypto:
                for crypto in missing_crypto:
                    async with session.get(f'https://api.coincap.io/v2/assets/{crypto.lower()}') as response:
                        alt_crypto_data = await response.json()
                    if 'data' in alt_crypto_data and 'priceUsd' in alt_crypto_data['data']:
                        rates[crypto] = 1 / float(alt_crypto_data['data']['priceUsd'])

        await set_cached_data('exchange_rates', rates)
        logger.info("Successfully fetched and cached exchange rates")
        return rates
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return {}

def convert_currency(amount: float, from_currency: str, to_currency: str, rates: Dict[str, float]) -> float:
    if from_currency == 'USD':
        return amount * rates[to_currency]
    elif to_currency == 'USD':
        return amount / rates[from_currency]
    else:
        return amount / rates[from_currency] * rates[to_currency]
    
def read_changelog():
    changelog_path = os.path.join(os.path.dirname(__file__), 'CHANGELOG.md')
    try:
        with open(changelog_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "Чейнджлог не найден."    

async def cmd_start(message: Message):
    user_data.update_user_data(message.from_user.id)
    logger.info(f"User {message.from_user.id} started the bot in chat {message.chat.id}")
    
    user_lang = user_data.get_user_language(message.from_user.id)
    
    if message.chat.type in ['group', 'supergroup']:
        chat_member = await message.chat.get_member(message.from_user.id)
        if chat_member.status in ['creator', 'administrator']:
            await show_chat_settings(message)
        else:
            await message.answer(LANGUAGES[user_lang]['admin_only'])
    else:
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['help_button'], callback_data='howto')
        kb.button(text=LANGUAGES[user_lang]['news_button'], url="https://t.me/onswixdev")
        kb.button(text=LANGUAGES[user_lang]['feedback_button'], callback_data='feedback')
        kb.button(text=LANGUAGES[user_lang]['settings_button'], callback_data='settings')
        kb.button(text=LANGUAGES[user_lang]['about_button'], callback_data='about')
        kb.adjust(2)
        
        welcome_message = LANGUAGES[user_lang]['welcome']
        
        await message.answer(welcome_message, reply_markup=kb.as_markup())

async def cmd_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_lang = user_data.get_user_language(user_id)

    if message.chat.type == 'private':
        await process_settings(message, None)
    else:
        chat_member = await message.chat.get_member(user_id)
        if chat_member.status in ['creator', 'administrator']:
            kb = InlineKeyboardBuilder()
            kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data=f"show_chat_currencies_{chat_id}_0")
            kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data=f"show_chat_crypto_{chat_id}")
            kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data=f"toggle_chat_quote_format_{chat_id}")
            kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
            kb.adjust(2, 1, 1)
            
            use_quote = user_data.get_chat_quote_format(chat_id)
            quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
            settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
            
            await message.answer(settings_text, reply_markup=kb.as_markup())
        else:
            await message.answer("Только администраторы могут изменять настройки чата.")

async def show_chat_currencies(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = int(parts[3])
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
    user_id = callback_query.from_user.id
    chat_currencies = user_data.get_chat_currencies(chat_id)
    user_lang = user_data.get_user_language(user_id)
    
    currencies_per_page = 5
    start = page * currencies_per_page
    end = start + currencies_per_page
    current_currencies = ACTIVE_CURRENCIES[start:end]
    
    kb = InlineKeyboardBuilder()
    for currency in current_currencies:
        status = "✅" if currency in chat_currencies else "❌"
        kb.button(text=f"{ALL_CURRENCIES[currency]} {currency} {status}", callback_data=f"toggle_chat_currency_{chat_id}_{currency}_{page}")
    
    if page > 0:
        kb.button(text=f"⬅️ {LANGUAGES[user_lang]['back']}", callback_data=f"show_chat_currencies_{chat_id}_{page-1}")
    if end < len(ACTIVE_CURRENCIES):
        kb.button(text=f"{LANGUAGES[user_lang]['forward']} ➡️", callback_data=f"show_chat_currencies_{chat_id}_{page+1}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], callback_data=f"back_to_chat_settings_{chat_id}")
    kb.adjust(1)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['currencies'], reply_markup=kb.as_markup())
    
async def show_chat_crypto(callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split('_')[3])
    user_id = callback_query.from_user.id
    chat_crypto = user_data.get_chat_crypto(chat_id)
    user_lang = user_data.get_user_language(user_id)
    
    kb = InlineKeyboardBuilder()
    for crypto in CRYPTO_CURRENCIES:
        status = "✅" if crypto in chat_crypto else "❌"
        kb.button(text=f"{ALL_CURRENCIES[crypto]} {crypto} {status}", callback_data=f"toggle_chat_crypto_{chat_id}_{crypto}")
    
    kb.button(text=LANGUAGES[user_lang]['back_to_settings'], callback_data=f"back_to_chat_settings_{chat_id}")
    kb.adjust(2)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['cryptocurrencies'], reply_markup=kb.as_markup())


async def toggle_chat_currency(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = int(parts[3])
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
    
    new_data = f"show_chat_currencies_{chat_id}_{page}"
    new_callback_query = callback_query.model_copy(update={'data': new_data})
    await show_chat_currencies(new_callback_query)

async def toggle_chat_crypto(callback_query: CallbackQuery):
    chat_id, crypto = callback_query.data.split('_')[3:]
    chat_id = int(chat_id)
    
    if str(chat_id) not in user_data.chat_data:
        user_data.initialize_chat_settings(chat_id)
    
    chat_crypto = user_data.get_chat_crypto(chat_id)
    
    if crypto in chat_crypto:
        chat_crypto.remove(crypto)
    else:
        chat_crypto.append(crypto)
    
    user_data.set_chat_crypto(chat_id, chat_crypto)
    
    user_data.save_chat_data()
    
    await show_chat_crypto(callback_query)

async def show_chat_settings(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_lang = user_data.get_user_language(user_id)

    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data=f"show_chat_currencies_{chat_id}_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data=f"show_chat_crypto_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data=f"toggle_chat_quote_format_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
    kb.adjust(2, 1, 1)
    
    use_quote = user_data.get_chat_quote_format(chat_id)
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['chat_settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await message.answer(settings_text, reply_markup=kb.as_markup())

async def save_chat_settings(callback_query: CallbackQuery):
    chat_id = int(callback_query.data.split('_')[3])
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()

async def process_howto(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    howto_message = LANGUAGES[user_lang]['help']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(howto_message, reply_markup=kb.as_markup())

async def process_feedback(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    feedback_message = LANGUAGES[user_lang]['feedback']
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(feedback_message, reply_markup=kb.as_markup())

async def process_settings(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    use_quote = user_data.get_user_quote_format(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
    kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
    kb.adjust(2, 2, 1, 1)
    
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())

async def toggle_quote_format(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    
    if 'chat' in callback_query.data:
        chat_id = int(parts[-1])
        current_setting = user_data.get_chat_quote_format(chat_id)
        user_data.set_chat_quote_format(chat_id, not current_setting)
        await back_to_chat_settings(callback_query)
    else:
        current_setting = user_data.get_user_quote_format(user_id)
        user_data.set_user_quote_format(user_id, not current_setting)
        await process_settings(callback_query, None)

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
    await show_crypto(callback_query)

async def save_settings(callback_query: CallbackQuery):
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()


async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    user_lang = user_data.get_user_language(message.from_user.id)
    stats = user_data.get_statistics()
    stats_message = (
        f"{LANGUAGES[user_lang]['stats_title']}\n\n"
        f"{LANGUAGES[user_lang]['total_users']} {stats['total_users']}\n"
        f"{LANGUAGES[user_lang]['active_users']} {stats['active_today']}\n"
        f"{LANGUAGES[user_lang]['new_users']} {stats['new_today']}"
    )

    await message.answer(stats_message)

async def cmd_olivka(message: Message):
    user_id = message.from_user.id
    user_lang = user_data.get_user_language(user_id)
    
    easter_egg_message = "Вы нашли пасхалку, отпишите сюда за наградой @onswix"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    
    await message.answer(easter_egg_message, reply_markup=kb.as_markup())
    logger.info(f"User {user_id} found the Easter egg")

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
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[new_lang]['back_to_settings'], callback_data="back_to_settings")
    
    await callback_query.message.edit_text(LANGUAGES[new_lang]['save_settings'], reply_markup=kb.as_markup())
    await callback_query.answer(LANGUAGES[new_lang]['save_settings'])    

async def handle_conversion(message: Message):
    user_data.update_user_data(message.from_user.id)
    user_lang = user_data.get_user_language(message.from_user.id)
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError(LANGUAGES[user_lang]['invalid_input'])
        
        amount = float(parts[0])
        from_currency = parts[1].upper()

        user_currencies = user_data.get_user_currencies(message.from_user.id)
        user_crypto = user_data.get_user_crypto(message.from_user.id)

        rates = await get_exchange_rates()
        if not rates:
            await message.answer(LANGUAGES[user_lang]['error'])
            return

        response = f"{amount:.2f} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        
        response += f"{LANGUAGES[user_lang]['fiat_currencies']}\n"
        for to_cur in user_currencies:
            if to_cur != from_currency:
                converted = convert_currency(amount, from_currency, to_cur, rates)
                response += f"{converted:.2f} {ALL_CURRENCIES[to_cur]} {to_cur}\n"
        
        response += "\n"

        response += f"{LANGUAGES[user_lang]['cryptocurrencies_output']}\n"
        for to_cur in user_crypto:
            if to_cur != from_currency:
                converted = convert_currency(amount, from_currency, to_cur, rates)
                response += f"{converted:.8f} {ALL_CURRENCIES[to_cur]} {to_cur}\n"

        logger.info(f"Successful conversion for user {message.from_user.id}: {amount} {from_currency}")
        await message.answer(response)
    except ValueError as ve:
        await message.answer(str(ve))
    except Exception as e:
        logger.error(f"Error during conversion for user {message.from_user.id}: {str(e)}")
        await message.answer(LANGUAGES[user_lang]['error'])


async def inline_query_handler(query: InlineQuery):
    user_data.update_user_data(query.from_user.id)
    user_lang = user_data.get_user_language(query.from_user.id)
    use_quote = user_data.get_user_quote_format(query.from_user.id)
    args = query.query.split()

    if len(args) < 2:
        return

    try:
        amount = float(args[0])
        currency_input = args[1].upper()
        from_currency = CURRENCY_SYMBOLS.get(currency_input, currency_input)

        user_currencies = user_data.get_user_currencies(query.from_user.id)
        user_crypto = user_data.get_user_crypto(query.from_user.id)

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        rates = await get_exchange_rates()
        if not rates:
            return

        if not user_currencies and not user_crypto:
            no_currency_result = InlineQueryResultArticle(
                id="no_currencies",
                title=LANGUAGES[user_lang].get('no_currencies_selected', "No currencies selected"),
                description=LANGUAGES[user_lang].get('select_currencies_message', "Please select currencies in settings"),
                input_message_content=InputTextMessageContent(
                    message_text=LANGUAGES[user_lang].get('select_currencies_full_message', 
                    "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.")
                )
            )
            await query.answer(results=[no_currency_result], cache_time=1)
            return

        result_content = f"{format_large_number(amount)} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        
        if user_currencies:
            result_content += f"<b>{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}</b>\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    converted = convert_currency(amount, from_currency, to_cur, rates)
                    result_content += f"{format_large_number(converted)} {ALL_CURRENCIES[to_cur]} {to_cur}\n"
            if use_quote:
                result_content += "</blockquote>"
            result_content += "\n"

        if user_crypto:
            result_content += f"<b>{LANGUAGES[user_lang].get('cryptocurrencies_output', 'Cryptocurrencies')}</b>\n"
            if use_quote:
                result_content += "<blockquote expandable>"
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    converted = convert_currency(amount, from_currency, to_cur, rates)
                    result_content += f"{format_large_number(converted, True)} {ALL_CURRENCIES[to_cur]}\n"
            if use_quote:
                result_content += "</blockquote>"

        result = InlineQueryResultArticle(
            id=f"{from_currency}_all",
            title=LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
            description=f"{amount} {from_currency} to your selected currencies",
            input_message_content=InputTextMessageContent(
                message_text=result_content,
                parse_mode="HTML"
            )
        )

        logger.info(f"Successful inline conversion for user {query.from_user.id}: {amount} {from_currency}")
        await query.answer(results=[result], cache_time=1)
    except ValueError as ve:
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('invalid_input', "Invalid Input"),
            description=str(ve),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('invalid_input_message', 
                "Invalid input. Please enter amount and currency code, e.g., '100 USD'.")
            )
        )
        await query.answer(results=[error_result], cache_time=1)
    except Exception as e:
        logger.error(f"Error during inline conversion for user {query.from_user.id}: {str(e)}")
        error_result = InlineQueryResultArticle(
            id="error",
            title=LANGUAGES[user_lang].get('error', "Error"),
            description=LANGUAGES[user_lang].get('error_occurred', "An error occurred. Please try again."),
            input_message_content=InputTextMessageContent(
                message_text=LANGUAGES[user_lang].get('error_message', 
                "An error occurred. Please try again.")
            )
        )
        await query.answer(results=[error_result], cache_time=1)

def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    text = text.lower().replace(',', '.').replace('$', 'usd').replace('€', 'eur').replace('₽', 'rub')
    
    multipliers = {
        'к': 1000,
        'kk': 1000000,
        'к': 1000,
        'кк': 1000000,
        'м': 1000000,
        'млн': 1000000,
        'млрд': 1000000000
    }
    
    pattern = r'^(\d+(?:\.\d+)?)\s*(к|кк|м|млн|млрд)?\s*([a-zA-Zа-яА-Я]+)$|^([a-zA-Zа-яА-Я]+)\s*(\d+(?:\.\d+)?)\s*(к|кк|м|млн|млрд)?$'
    match = re.match(pattern, text)
    
    if not match:
        return None, None
    
    groups = match.groups()
    if groups[0] is not None:
        amount_str, multiplier, currency_str = groups[:3]
    else:
        currency_str, amount_str, multiplier = groups[3:]
    
    amount = float(amount_str)
    
    if multiplier:
        amount *= multipliers.get(multiplier, 1)
    
    currency = None
    for abbr, code in CURRENCY_ABBREVIATIONS.items():
        if abbr in currency_str:
            currency = code
            break
    
    if not currency:
        currency = currency_str.strip().upper()
        if currency not in ALL_CURRENCIES:
            return None, None
    
    return amount, currency

async def handle_all_messages(message: types.Message, bot: Bot):
    logger.info(f"Received message: {message.text} from user {message.from_user.id} in chat {message.chat.id}")
    logger.info(f"Message content: {message.model_dump_json()}")

    if message.new_chat_members:
        for member in message.new_chat_members:
            if member.id == bot.id:
                welcome_message = (
                    f"Привет! Я бот для конвертации валют. 🌍💱\n\n"
                    f"Чтобы конвертировать валюту, просто напишите сумму и код валюты. Например:\n"
                    f"100 USD\n5000 RUB\n750 EUR\nсто долларов\nпятьсот евро\n\n"
                    f"Я автоматически конвертирую в другие валюты."
                )
                await message.answer(welcome_message)
                logger.info(f"Bot added to chat {message.chat.id}. Welcome message sent.")
                return

async def handle_my_chat_member(event: ChatMemberUpdated, bot: Bot):
    logger.info(f"Bot status changed in chat {event.chat.id}")
    logger.info(f"Event content: {event.model_dump_json()}")
    
    if event.new_chat_member.status == "member":
        user_data.initialize_chat_settings(event.chat.id)
        
        welcome_message = (
            f"Привет! Я бот для конвертации валют. 🌍💱\n\n"
            f"Чтобы конвертировать валюту, просто напишите сумму и код валюты. Например:\n"
            f"100 USD\n5000 RUB\n750 EUR\nсто долларов\nпятьсот евро\n\n"
            f"Я автоматически конвертирую в другие валюты."
        )
        await bot.send_message(event.chat.id, welcome_message)
        logger.info(f"Welcome message sent to chat {event.chat.id}")

async def handle_message(message: types.Message):
    logger.info(f"Received message: {message.text} from user {message.from_user.id} in chat {message.chat.id}")
    
    if message.text is None:
        logger.info(f"Received message without text from user {message.from_user.id} in chat {message.chat.id}")
        return

    user_id = message.from_user.id
    user_data.update_user_data(user_id)
    user_lang = user_data.get_user_language(user_id)

    if message.text.startswith('/'):
        logger.info(f"Received command: {message.text} from user {user_id}")
        if message.text == '/start':
            await cmd_start(message)
        elif message.text == '/stats':
            await cmd_stats(message)
        return

    amount, currency = parse_amount_and_currency(message.text)

    if amount is not None and currency is not None:
        logger.info(f"Valid conversion request: {amount} {currency} from user {user_id}")
        await process_conversion(message, amount, currency)
    else:
        logger.info(f"Ignored message: {message.text} from user {user_id}")

def format_large_number(number, is_crypto=False):
    if abs(number) > 1e100:  
        return "Число слишком большое"
    
    if is_crypto:
        if abs(number) < 1e-8:
            return f"{number:.8e}"
        elif abs(number) < 1:
            return f"{number:.8f}".rstrip('0').rstrip('.')  
        elif abs(number) < 1000:
            return f"{number:.4f}".rstrip('0').rstrip('.')  
        elif abs(number) >= 1e15:
            exponent = int(math.log10(abs(number)))
            mantissa = number / (10 ** exponent)
            return f"{mantissa:.2f}e{exponent}"
        else:
            return f"{number:,.2f}"
    else:
        if abs(number) < 0.01:
            return f"{number:.4f}".rstrip('0').rstrip('.')  
        elif abs(number) >= 1e15:
            exponent = int(math.log10(abs(number)))
            mantissa = number / (10 ** exponent)
            return f"{mantissa:.2f}e{exponent}"
        elif abs(number) >= 1e3:
            return f"{number:,.2f}"
        else:
            return f"{number:.2f}"

def format_response(response: str, use_quote: bool) -> str:
    if use_quote:
        return f"<blockquote expandable>{response}</blockquote>"
    else:
        return response 

async def process_conversion(message: types.Message, amount: float, from_currency: str):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_lang = user_data.get_user_language(user_id)
    logger.info(f"Processing conversion: {amount} {from_currency} for user {user_id} in chat {chat_id}")
    
    try:
        if amount > 1e100 or amount < -1e100:
            await message.answer(LANGUAGES[user_lang].get('number_too_large', "The number is too large to process."))
            return

        rates = await get_exchange_rates()
        if not rates:
            logger.error(f"Failed to get exchange rates for user {user_id}")
            await message.answer(LANGUAGES[user_lang]['error'])
            return
        
        if message.chat.type in ['group', 'supergroup']:
            user_currencies = user_data.get_chat_currencies(chat_id)
            user_crypto = user_data.get_chat_crypto(chat_id)
            use_quote = user_data.get_chat_quote_format(chat_id)
        else:
            user_currencies = user_data.get_user_currencies(user_id)
            user_crypto = user_data.get_user_crypto(user_id)
            use_quote = user_data.get_user_quote_format(user_id)
        
        if not user_currencies and not user_crypto:
            no_currencies_message = LANGUAGES[user_lang].get('select_currencies_full_message', 
                "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.")
            await message.answer(no_currencies_message)
            return
        
        response = f"{format_large_number(amount)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n\n"
        
        fiat_conversions = []
        crypto_conversions = []
        
        if user_currencies:
            for to_cur in user_currencies:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
                        fiat_conversions.append(conversion_line)
                    except KeyError:
                        logger.warning(f"Conversion failed for {to_cur}. It might not be in the rates.")
                    except OverflowError:
                        fiat_conversions.append(f"Overflow {ALL_CURRENCIES.get(to_cur, '')} {to_cur}")
        
        if user_crypto:
            for to_cur in user_crypto:
                if to_cur != from_currency:
                    try:
                        converted = convert_currency(amount, from_currency, to_cur, rates)
                        conversion_line = f"{format_large_number(converted, True)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
                        crypto_conversions.append(conversion_line)
                    except KeyError:
                        logger.warning(f"Conversion failed for {to_cur}. It might not be in the rates.")
                    except OverflowError:
                        crypto_conversions.append(f"Overflow {ALL_CURRENCIES.get(to_cur, '')} {to_cur}")
        
        if fiat_conversions:
            response += f"<b>{LANGUAGES[user_lang]['fiat_currencies']}</b>\n"
            if use_quote:
                response += "<blockquote expandable>"
            response += "\n".join(fiat_conversions)
            if use_quote:
                response += "</blockquote>"
            response += "\n\n"
        
        if crypto_conversions:
            response += f"<b>{LANGUAGES[user_lang]['cryptocurrencies_output']}</b>\n"
            if use_quote:
                response += "<blockquote expandable>"
            crypto_formatted = []
            for conv in crypto_conversions:
                parts = conv.split()
                crypto_formatted.append(f"{parts[0]} {parts[1]}")
            response += "\n".join(crypto_formatted)
            if use_quote:
                response += "</blockquote>"
        
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang].get('delete_button', "Delete"), callback_data="delete_conversion")
        
        logger.info(f"Sending conversion response for {amount} {from_currency} to user {user_id} in chat {chat_id}")
        
        await message.answer(
            text=response,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except OverflowError:
        await message.answer(LANGUAGES[user_lang].get('number_too_large', "The number is too large to process."))
    except Exception as e:
        logger.error(f"Error in process_conversion for user {user_id}: {e}")
        logger.exception("Full traceback:")
        await message.answer(LANGUAGES[user_lang]['error'])

async def delete_conversion_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

async def process_about(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    about_message = f"{LANGUAGES[user_lang]['about_message']}\n\n" \
                    f"{LANGUAGES[user_lang]['current_version']} {CURRENT_VERSION}"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['view_changelog'], callback_data='view_changelog')
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='back_to_main')
    kb.adjust(1)
    
    await callback_query.message.edit_text(about_message, reply_markup=kb.as_markup())

async def view_changelog(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    await callback_query.answer()
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    changelog = read_changelog()
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data='about')
    
    await callback_query.message.edit_text(changelog, reply_markup=kb.as_markup())


async def back_to_main(callback_query: CallbackQuery):
    user_data.update_user_data(callback_query.from_user.id)
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['help_button'], callback_data='howto')
    kb.button(text=LANGUAGES[user_lang]['news_button'], url="https://t.me/onswixdev")
    kb.button(text=LANGUAGES[user_lang]['feedback_button'], callback_data='feedback')
    kb.button(text=LANGUAGES[user_lang]['settings_button'], callback_data='settings')
    kb.button(text=LANGUAGES[user_lang]['about_button'], callback_data='about')
    kb.adjust(2)
    welcome_message = LANGUAGES[user_lang]['welcome']
    await callback_query.message.edit_text(welcome_message, reply_markup=kb.as_markup())

async def back_to_settings(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)
    use_quote = user_data.get_user_quote_format(user_id)
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
    kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data="toggle_quote_format")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
    kb.adjust(2, 2, 1, 1)
    
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())

async def back_to_chat_settings(callback_query: CallbackQuery):
    parts = callback_query.data.split('_')
    chat_id = next((part for part in parts if part.lstrip('-').isdigit()), None)
    
    if chat_id is None:
        logger.error(f"Invalid callback data for back_to_chat_settings: {callback_query.data}")
        await callback_query.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")
        return

    chat_id = int(chat_id)
    user_id = callback_query.from_user.id
    user_lang = user_data.get_user_language(user_id)

    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data=f"show_chat_currencies_{chat_id}_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data=f"show_chat_crypto_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['quote_format'], callback_data=f"toggle_chat_quote_format_{chat_id}")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
    kb.adjust(2, 1, 1)
    
    use_quote = user_data.get_chat_quote_format(chat_id)
    quote_status = LANGUAGES[user_lang]['on'] if use_quote else LANGUAGES[user_lang]['off']
    settings_text = f"{LANGUAGES[user_lang]['settings']}\n\n{LANGUAGES[user_lang]['quote_format_status']}: {quote_status}"
    
    await callback_query.message.edit_text(settings_text, reply_markup=kb.as_markup())

async def process_callback(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[0]
    
    if action == 'howto':
        await process_howto(callback_query)
    elif action == 'feedback':
        await process_feedback(callback_query)
    elif action == 'settings':
        await process_settings(callback_query, state)
    elif action == 'show':
        if 'currencies' in callback_query.data:
            await show_currencies(callback_query)
        elif 'crypto' in callback_query.data:
            await show_crypto(callback_query)
    elif action == 'toggle':
        if callback_query.data.startswith('toggle_chat_quote_format'):
            await toggle_quote_format(callback_query)
        elif callback_query.data == 'toggle_quote_format':
            await toggle_quote_format(callback_query)
        elif 'currency' in callback_query.data:
            await toggle_currency(callback_query)
        elif 'crypto' in callback_query.data:
            await toggle_crypto(callback_query)
    elif action == 'save':
        if 'chat' in callback_query.data:
            await save_chat_settings(callback_query)
        else:
            await save_settings(callback_query)
    elif action == 'change':
        await change_language(callback_query)
    elif action == 'set':
        await set_language(callback_query)
    elif action == 'back':
        if 'main' in callback_query.data:
            await back_to_main(callback_query)
        elif 'settings' in callback_query.data:
            if 'chat' in callback_query.data:
                await back_to_chat_settings(callback_query)
            else:
                await back_to_settings(callback_query)
    elif action == 'about':
        await process_about(callback_query)
    elif action == 'view':
        await view_changelog(callback_query)
    elif action == 'delete':
        if callback_query.data == 'delete_conversion':
            await delete_conversion_message(callback_query)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_settings, Command("settings"))
    dp.message.register(cmd_olivka, Command("olivka"))
    dp.message.register(handle_message)
    dp.message.register(handle_conversion)
    dp.message.register(handle_all_messages)
    
    dp.callback_query.register(process_howto, F.data == "howto")
    dp.callback_query.register(process_feedback, F.data == "feedback")
    dp.callback_query.register(process_settings, F.data == "settings")
    dp.callback_query.register(show_currencies, F.data.startswith("show_currencies_"))
    dp.callback_query.register(show_crypto, F.data == "show_crypto")
    dp.callback_query.register(toggle_currency, F.data.startswith("toggle_currency_"))
    dp.callback_query.register(toggle_crypto, F.data.startswith("toggle_crypto_"))
    dp.callback_query.register(save_settings, F.data == "save_settings")
    dp.callback_query.register(change_language, F.data == "change_language")
    dp.callback_query.register(set_language, F.data.startswith("set_language_"))
    dp.callback_query.register(back_to_main, F.data == "back_to_main")
    dp.callback_query.register(process_about, F.data == "about")
    dp.callback_query.register(view_changelog, F.data == "view_changelog")
    dp.callback_query.register(toggle_quote_format, F.data == "toggle_quote_format")
    
    dp.callback_query.register(show_chat_currencies, F.data.startswith("show_chat_currencies_"))
    dp.callback_query.register(show_chat_crypto, F.data.startswith("show_chat_crypto_"))
    dp.callback_query.register(toggle_chat_currency, F.data.startswith("toggle_chat_currency_"))
    dp.callback_query.register(toggle_chat_crypto, F.data.startswith("toggle_chat_crypto_"))
    dp.callback_query.register(save_chat_settings, F.data.startswith("save_chat_settings_"))
    dp.callback_query.register(back_to_settings, F.data == "back_to_settings")
    dp.callback_query.register(back_to_chat_settings, F.data.startswith("back_to_chat_settings_"))
    dp.callback_query.register(delete_conversion_message, F.data == "delete_conversion")
    dp.callback_query.register(process_callback)
    
    dp.inline_query.register(inline_query_handler)
    dp.my_chat_member.register(handle_my_chat_member)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())