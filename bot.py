import os
import logging
from typing import Dict, List
import asyncio
import json
from datetime import datetime
from collections import defaultdict
import aiohttp
import traceback
import re
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, ChatMemberUpdated
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from word2number import w2n
from money2number import m2n
from dotenv import load_dotenv
import time
from typing import Dict, Any, List
import math

LANGUAGES = {
    'ru': {
        'welcome': "Добро пожаловать в Onlive Twilight Convert bot! 🌍💱\n\nДля конвертации валюты просто введите сумму и код валюты. Например:\n100 USD\n5000 RUB\n750 EUR\n\nВы также можете использовать этот бот inline в любом чате, набрав @onlive_twilight_bot, за которым следует сумма и валюта.\n\nИспользуйте кнопки ниже для получения дополнительной информации или настройки бота.",
        'help': "🤖 Как использовать бота:\n\n1. Для простой конвертации введите сумму и код валюты, например: 100 USD\n2. Для конвертации между двумя конкретными валютами используйте формат: 100 USD EUR\n3. Вы можете использовать бота inline в любом чате, набрав @onlive_twilight_bot 100 USD\n\nПоддерживаемые валюты: ",
        'feedback': "📬 Обратная связь:\n\nМы всегда рады вашим предложениям и замечаниям!\nCвяжитесь со мной в Telegram: @onswix",
        'settings': "Выберите раздел настроек:",
        'currencies': "Выберите валюты:",
        'cryptocurrencies': "Выберите криптовалюты:",
        'language': "Выберите язык:",
        'save_settings': "Настройки сохранены!",
        'invalid_input': "Неверный ввод. Пожалуйста, введите сумму и код валюты, например, '100 USD' или '100 USD EUR'.",
        'error': "Произошла ошибка. Пожалуйста, попробуйте снова.",
        'fiat_currencies': "Фиатные валюты:",
        'cryptocurrencies_output': "Криптовалюты:",
        'back': "Назад",
        'help_button': "❓ Помощь",
        'news_button': "🗞 Новости",
        'feedback_button': "💭 Обратная связь",
        'settings_button': "⚙️ Настройки",
        'save_button': "Сохранить настройки",
        'back_to_settings': "Назад к настройкам",
        'forward': "Вперёд",
        'stats_title': "📊 Статистика бота:",
        'total_users': "👥 Общее количество пользователей:",
        'active_users': "🔵 Активных пользователей сегодня:",
        'new_users': "🆕 Новых пользователей сегодня:",
        'no_currencies_selected': "Валюты не выбраны",
        'select_currencies_message': "Пожалуйста, выберите валюты в настройках",
        'select_currencies_full_message': "Вы не выбрали ни одной валюты. Пожалуйста, перейдите в настройки бота, чтобы выбрать валюты для конвертации.",
        'conversion_result': "Результат конвертации",
        'fiat_currencies': "Фиатные валюты",
        'cryptocurrencies': "Криптовалюты",
        'number_too_large': "Число слишком большое для обработки.",
        'about_button': "О боте",
        'about_message': "Информация о боте Onlive Twilight Convert",
        'current_version': "Текущая версия:",
        'view_changelog': "Посмотреть список изменений",
    },
    'en': {
        'welcome': "Welcome to Onlive Twilight Convert bot! 🌍💱\n\nTo convert currency, simply enter an amount and currency code. For example:\n100 USD\n5000 RUB\n750 EUR\n\nYou can also use this bot inline in any chat by typing @onlive_twilight_bot followed by an amount and currency.\n\nUse the buttons below for more information or to configure the bot.",
        'help': "🤖 How to use the bot:\n\n1. For simple conversion, enter an amount and currency code, e.g.: 100 USD\n2. To convert between two specific currencies, use the format: 100 USD EUR\n3. You can use the bot inline in any chat by typing @onlive_twilight_bot 100 USD\n\nSupported currencies: ",
        'feedback': "📬 Feedback:\n\nWe always appreciate your suggestions and comments!\nContact me on Telegram: @onswix",
        'settings': "Choose a settings section:",
        'currencies': "Select currencies:",
        'cryptocurrencies': "Select cryptocurrencies:",
        'language': "Select language:",
        'save_settings': "Settings saved!",
        'invalid_input': "Invalid input. Please enter an amount and currency code, e.g., '100 USD' or '100 USD EUR'.",
        'error': "An error occurred. Please try again.",
        'fiat_currencies': "Fiat currencies:",
        'cryptocurrencies_output': "Cryptocurrencies:",
        'back': "Back",
        'help_button': "❓ Help",
        'news_button': "🗞 News",
        'feedback_button': "💭 Feedback",
        'settings_button': "⚙️ Settings",
        'save_button': "Save settings",
        'back_to_settings': "Back to settings",
        'forward': "Next",
        'stats_title': "📊 Bot Statistics:",
        'total_users': "👥 Total number of users:",
        'active_users': "🔵 Active users today:",
        'new_users': "🆕 New users today:",
        'no_currencies_selected': "No currencies selected",
        'select_currencies_message': "Please select currencies in settings",
        'select_currencies_full_message': "You haven't selected any currencies. Please go to bot settings to select currencies for conversion.",
        'conversion_result': "Conversion Result",
        'fiat_currencies': "Fiat currencies",
        'cryptocurrencies': "Cryptocurrencies",
        'number_too_large': "The number is too large to process.",
        'about_button': "About",
        'about_message': "About Onlive Twilight Convert bot",
        'current_version': "Current version:",
        'view_changelog': "View changelog",
    }
}

cache: Dict[str, Any] = {}
CACHE_EXPIRATION_TIME = 600  



load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [810587766] 
USER_DATA_FILE = 'user_data.json'
CURRENT_VERSION = "0.9.0"


ALL_CURRENCIES = {
    'USD': '🇺🇸', 'EUR': '🇪🇺', 'GBP': '🇬🇧', 'JPY': '🇯🇵', 'CHF': '🇨🇭', 'CNY': '🇨🇳', 'RUB': '🇷🇺',
    'AUD': '🇦🇺', 'CAD': '🇨🇦', 'NZD': '🇳🇿', 'SEK': '🇸🇪', 'NOK': '🇳🇴', 'DKK': '🇩🇰', 'ZAR': '🇿🇦',
    'INR': '🇮🇳', 'BRL': '🇧🇷', 'MXN': '🇲🇽', 'SGD': '🇸🇬', 'HKD': '🇭🇰', 'KRW': '🇰🇷', 'TRY': '🇹🇷',
    'PLN': '🇵🇱', 'THB': '🇹🇭', 'IDR': '🇮🇩', 'HUF': '🇭🇺', 'CZK': '🇨🇿', 'ILS': '🇮🇱', 'CLP': '🇨🇱',
    'PHP': '🇵🇭', 'AED': '🇦🇪', 'COP': '🇨🇴', 'SAR': '🇸🇦', 'MYR': '🇲🇾', 'RON': '🇷🇴',
    'UZS': '🇺🇿', 'UAH': '🇺🇦', 'KZT': '🇰🇿',  
    'BTC': '₿', 'ETH': 'Ξ', 'USDT': '₮', 'BNB': 'BNB', 'XRP': 'XRP', 'ADA': 'ADA', 'SOL': 'SOL', 'DOT': 'DOT',
    'DOGE': 'Ð', 'MATIC': 'MATIC', 'TON': 'TON', 'NOT': 'NOT', 'DUREV': 'DUREV'  
}

CRYPTO_CURRENCIES = ['BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE', 'MATIC', 'TON', 'NOT', 'DUREV']
ACTIVE_CURRENCIES = [cur for cur in ALL_CURRENCIES if cur not in CRYPTO_CURRENCIES]

CURRENCY_SYMBOLS = {
    '$': 'USD',
    '€': 'EUR',
    '£': 'GBP',
    '¥': 'JPY',
    '₽': 'RUB',
    '₣': 'CHF',
    '₹': 'INR',
    '₺': 'TRY',
    '₴': 'UAH',
    '₿': 'BTC',
    'сум': 'UZS', 
    'грн': 'UAH',
    '₸': 'KZT'   
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

class UserStates(StatesGroup):
    selecting_crypto = State()
    selecting_settings = State()


class UserData:
    def __init__(self):
        self.user_data = self.load_user_data()
        self.chat_data = self.load_chat_data()
        self.bot_launch_date = datetime.now().strftime('%Y-%m-%d')

    def load_chat_data(self):
        try:
            with open('chat_data.json', 'r') as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_chat_data(self):
        with open('chat_data.json', 'w') as file:
            json.dump(self.chat_data, file, indent=4)

    def get_chat_currencies(self, chat_id):
        return self.chat_data.get(str(chat_id), {}).get("selected_currencies", ACTIVE_CURRENCIES[:5])

    def set_chat_currencies(self, chat_id, currencies):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]["selected_currencies"] = currencies
        self.save_chat_data()

    def get_chat_crypto(self, chat_id):
        return self.chat_data.get(str(chat_id), {}).get("selected_crypto", CRYPTO_CURRENCIES)

    def set_chat_crypto(self, chat_id, crypto_list):
        if str(chat_id) not in self.chat_data:
            self.chat_data[str(chat_id)] = {}
        self.chat_data[str(chat_id)]["selected_crypto"] = crypto_list
        self.save_chat_data()

    def load_user_data(self):
        try:
            with open(USER_DATA_FILE, 'r') as file:
                data = json.load(file)
                return defaultdict(lambda: {
                    "interactions": 0,
                    "last_seen": None,
                    "selected_crypto": CRYPTO_CURRENCIES,  
                    "selected_currencies": ACTIVE_CURRENCIES[:5],
                    "language": "ru",
                    "first_seen": self.bot_launch_date
                }, data)
        except (FileNotFoundError, json.JSONDecodeError):
            return defaultdict(lambda: {
                "interactions": 0,
                "last_seen": None,
                "selected_crypto": CRYPTO_CURRENCIES,  
                "selected_currencies": ACTIVE_CURRENCIES[:5],
                "language": "ru",
                "first_seen": self.bot_launch_date
            })

    def get_user_currencies(self, user_id):
        return self.user_data[str(user_id)].get("selected_currencies", ACTIVE_CURRENCIES[:5])

    def set_user_currencies(self, user_id, currencies):
        self.user_data[str(user_id)]["selected_currencies"] = currencies
        self.save_user_data()

    def save_user_data(self):
        with open(USER_DATA_FILE, 'w') as file:
            json.dump(self.user_data, file, indent=4)

    def update_user_data(self, user_id):
        today = datetime.now().strftime('%Y-%m-%d')
        if str(user_id) not in self.user_data:
            self.user_data[str(user_id)] = {
                "interactions": 0, 
                "last_seen": today, 
                "selected_crypto": CRYPTO_CURRENCIES,
                "selected_currencies": ACTIVE_CURRENCIES[:5],
                "language": "ru",
                "first_seen": today
            }
        self.user_data[str(user_id)]["interactions"] += 1
        self.user_data[str(user_id)]["last_seen"] = today
        self.save_user_data()

    def get_user_crypto(self, user_id: int) -> List[str]:
        user_id_str = str(user_id)
        if user_id_str not in self.user_data or "selected_crypto" not in self.user_data[user_id_str]:
            self.user_data[user_id_str]["selected_crypto"] = CRYPTO_CURRENCIES
        return self.user_data[user_id_str]["selected_crypto"]
    

    def set_user_crypto(self, user_id: int, crypto_list: List[str]):
        self.user_data[str(user_id)]["selected_crypto"] = crypto_list
        self.save_user_data()

    def get_statistics(self):
        today = datetime.now().strftime('%Y-%m-%d')
        total_users = len(self.user_data)
        active_today = sum(1 for user in self.user_data.values() if user['last_seen'] == today)
        new_today = sum(1 for user in self.user_data.values() if user['first_seen'] == today)

        
        if str(ADMIN_IDS[0]) in self.user_data and self.user_data[str(ADMIN_IDS[0])]['first_seen'] == today:
            new_today -= 1

        return {
            "total_users": total_users,
            "active_today": active_today,
            "new_today": new_today
        }
    
    def get_user_language(self, user_id):
        return self.user_data[str(user_id)].get("language", "ru")
    
    def set_user_language(self, user_id, language):
        self.user_data[str(user_id)]["language"] = language
        self.save_user_data()

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

            crypto_ids = "bitcoin,ethereum,tether,binancecoin,ripple,cardano,solana,polkadot,dogecoin,matic-network,the-open-network"
            async with session.get(f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd') as response:
                crypto_data = await response.json()
            
            crypto_mapping = {
                'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether', 'BNB': 'binancecoin',
                'XRP': 'ripple', 'ADA': 'cardano', 'SOL': 'solana', 'DOT': 'polkadot',
                'DOGE': 'dogecoin', 'MATIC': 'matic-network', 'TON': 'the-open-network'
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
    logger.info(f"User {message.from_user.id} started the bot")
    
    user_lang = user_data.get_user_language(message.from_user.id)
    
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
            kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
            kb.adjust(2, 1)
            
            await message.answer(LANGUAGES[user_lang]['settings'], reply_markup=kb.as_markup())
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
    
    chat_currencies = user_data.get_chat_currencies(chat_id)
    
    if currency in chat_currencies:
        chat_currencies.remove(currency)
    else:
        chat_currencies.append(currency)
    
    user_data.set_chat_currencies(chat_id, chat_currencies)
    
    new_data = f"show_chat_currencies_{chat_id}_{page}"
    new_callback_query = callback_query.model_copy(update={'data': new_data})
    await show_chat_currencies(new_callback_query)

async def toggle_chat_crypto(callback_query: CallbackQuery):
    chat_id, crypto = callback_query.data.split('_')[3:]
    chat_id = int(chat_id)
    chat_crypto = user_data.get_chat_crypto(chat_id)
    
    if crypto in chat_crypto:
        chat_crypto.remove(crypto)
    else:
        chat_crypto.append(crypto)
    
    user_data.set_chat_crypto(chat_id, chat_crypto)
    await show_chat_crypto(callback_query)

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
    howto_message = LANGUAGES[user_lang]['help'] + ', '.join(ACTIVE_CURRENCIES + user_data.get_user_crypto(callback_query.from_user.id))
    
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
    try:
        user_data.update_user_data(callback_query.from_user.id)
        await callback_query.answer()
        
        user_lang = user_data.get_user_language(callback_query.from_user.id)
        kb = InlineKeyboardBuilder()
        kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
        kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
        kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
        kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
        kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
        kb.adjust(2, 1, 1)
        
        await callback_query.message.edit_text(LANGUAGES[user_lang]['settings'], reply_markup=kb.as_markup())
        await state.set_state(UserStates.selecting_settings)
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Error in process_settings for user {callback_query.from_user.id}: {str(e)}\n{error_details}")
        user_lang = user_data.get_user_language(callback_query.from_user.id)
        await callback_query.message.answer(LANGUAGES[user_lang]['error'])
        
        admin_message = f"Ошибка в process_settings для пользователя {callback_query.from_user.id}:\n{str(e)}\n\nДетали:\n{error_details}"
        for admin_id in ADMIN_IDS:
            try:
                await callback_query.bot.send_message(admin_id, admin_message)
            except Exception as admin_error:
                logger.error(f"Failed to send error message to admin {admin_id}: {str(admin_error)}")

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
    args = query.query.split()

    if len(args) < 2:
        return

    try:
        amount = float(args[0])
        currency_input = args[1].upper()
        from_currency = CURRENCY_SYMBOLS.get(currency_input, currency_input)

        user_currencies = user_data.get_user_currencies(query.from_user.id)
        user_crypto = user_data.get_user_crypto(query.from_user.id)
        all_user_currencies = user_currencies + user_crypto

        if from_currency not in ALL_CURRENCIES:
            raise ValueError(f"Invalid currency: {from_currency}")

        rates = await get_exchange_rates()
        if not rates:
            return

        if not all_user_currencies:
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

        fiat_results = []
        crypto_results = []
        for to_cur in all_user_currencies:
            if to_cur != from_currency:
                converted = convert_currency(amount, from_currency, to_cur, rates)
                result_line = f"{converted:.2f} {ALL_CURRENCIES[to_cur]} {to_cur}"
                if to_cur in CRYPTO_CURRENCIES:
                    crypto_results.append(result_line)
                else:
                    fiat_results.append(result_line)

        result_content = f"{amount:.2f} {ALL_CURRENCIES[from_currency]} {from_currency}\n\n"
        if fiat_results:
            result_content += f"{LANGUAGES[user_lang].get('fiat_currencies', 'Fiat currencies')}:\n"
            result_content += "\n".join(fiat_results)
            result_content += "\n\n"
        if crypto_results:
            result_content += f"{LANGUAGES[user_lang].get('cryptocurrencies', 'Cryptocurrencies')}:\n"
            result_content += "\n".join(crypto_results)

        result = InlineQueryResultArticle(
            id=f"{from_currency}_all",
            title=LANGUAGES[user_lang].get('conversion_result', "Conversion Result"),
            description=f"{amount} {from_currency} to your selected currencies",
            input_message_content=InputTextMessageContent(message_text=result_content)
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

    match = re.match(r'^(\d+(?:\.\d+)?)\s*([A-Z]{3}|\$|€|£|¥|₽|₸|₣|₹|₺|₴|₿)$', message.text.upper())
    if match:
        try:
            amount = float(match.group(1))
            currency_input = match.group(2)
            from_currency = CURRENCY_SYMBOLS.get(currency_input, currency_input)
        except ValueError:
            await message.answer(LANGUAGES[user_lang].get('number_too_large', "The number is too large to process."))
            return
    else:
        try:
            parsed = m2n(message.text)
            amount = parsed['amount']
            from_currency = parsed['currency']
        except:
            try:
                words = message.text.split()
                amount = w2n.word_to_num(' '.join(words[:-1]))
                from_currency = words[-1].upper()
                if from_currency not in ALL_CURRENCIES:
                    raise ValueError("Invalid currency")
            except:
                logger.info(f"No valid currency conversion request found: {message.text} from user {user_id}")
                return

    if amount and from_currency and from_currency in ALL_CURRENCIES:
        logger.info(f"Valid conversion request: {amount} {from_currency} from user {user_id}")
        await process_conversion(message, amount, from_currency)
    else:
        logger.info(f"No valid currency conversion request found: {message.text} from user {user_id}")

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
        else:
            user_currencies = user_data.get_user_currencies(user_id)
            user_crypto = user_data.get_user_crypto(user_id)
        
        if not user_currencies:
            user_currencies = ACTIVE_CURRENCIES[:5]
        if not user_crypto:
            user_crypto = CRYPTO_CURRENCIES[:5]
        
        all_user_currencies = user_currencies + user_crypto
        
        response = f"{format_large_number(amount)} {ALL_CURRENCIES.get(from_currency, '')} {from_currency}\n\n"
        
        fiat_conversions = []
        crypto_conversions = []
        
        for to_cur in all_user_currencies:
            if to_cur != from_currency:
                try:
                    converted = convert_currency(amount, from_currency, to_cur, rates)
                    is_crypto = to_cur in CRYPTO_CURRENCIES
                    conversion_line = f"{format_large_number(converted, is_crypto)} {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
                    if is_crypto:
                        crypto_conversions.append(conversion_line)
                    else:
                        fiat_conversions.append(conversion_line)
                except KeyError:
                    logger.warning(f"Conversion failed for {to_cur}. It might not be in the rates.")
                except OverflowError:
                    conversion_line = f"Overflow {ALL_CURRENCIES.get(to_cur, '')} {to_cur}"
                    if to_cur in CRYPTO_CURRENCIES:
                        crypto_conversions.append(conversion_line)
                    else:
                        fiat_conversions.append(conversion_line)
        
        if fiat_conversions:
            response += f"{LANGUAGES[user_lang]['fiat_currencies']}\n"
            response += "\n".join(fiat_conversions)
            response += "\n\n"
        
        if crypto_conversions:
            response += f"{LANGUAGES[user_lang]['cryptocurrencies_output']}\n"
            response += "\n".join(crypto_conversions)
        
        logger.info(f"Sending conversion response for {amount} {from_currency} to user {user_id} in chat {chat_id}")
        await message.answer(response)
    except OverflowError:
        await message.answer(LANGUAGES[user_lang].get('number_too_large', "The number is too large to process."))
    except Exception as e:
        logger.error(f"Error in process_conversion for user {user_id}: {e}")
        logger.exception("Full traceback:")
        await message.answer(LANGUAGES[user_lang]['error'])


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
    
    kb = InlineKeyboardBuilder()
    kb.button(text=LANGUAGES[user_lang]['currencies'], callback_data="show_currencies_0")
    kb.button(text=LANGUAGES[user_lang]['cryptocurrencies'], callback_data="show_crypto")
    kb.button(text=LANGUAGES[user_lang]['language'], callback_data="change_language")
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data="save_settings")
    kb.button(text=LANGUAGES[user_lang]['back'], callback_data="back_to_main")
    kb.adjust(2, 1, 1)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['settings'], reply_markup=kb.as_markup())

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
    kb.button(text=LANGUAGES[user_lang]['save_button'], callback_data=f"save_chat_settings_{chat_id}")
    kb.adjust(2, 1)
    
    await callback_query.message.edit_text(LANGUAGES[user_lang]['settings'], reply_markup=kb.as_markup())

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
        if 'currency' in callback_query.data:
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

async def main():
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_stats, Command("stats"))
    dp.message.register(cmd_settings, Command("settings"))
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
    
    dp.callback_query.register(show_chat_currencies, F.data.startswith("show_chat_currencies_"))
    dp.callback_query.register(show_chat_crypto, F.data.startswith("show_chat_crypto_"))
    dp.callback_query.register(toggle_chat_currency, F.data.startswith("toggle_chat_currency_"))
    dp.callback_query.register(toggle_chat_crypto, F.data.startswith("toggle_chat_crypto_"))
    dp.callback_query.register(save_chat_settings, F.data.startswith("save_chat_settings_"))
    dp.callback_query.register(back_to_settings, F.data == "back_to_settings")
    dp.callback_query.register(back_to_chat_settings, F.data.startswith("back_to_chat_settings_"))
    dp.callback_query.register(process_callback)
    
    dp.inline_query.register(inline_query_handler)
    dp.my_chat_member.register(handle_my_chat_member)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())