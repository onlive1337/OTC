from datetime import datetime
from typing import Dict, Any, Tuple, Optional, Union
import time
import logging
import aiohttp
import os
import math
import re
import operator
from aiogram.types import CallbackQuery, Message
from data import user_data
from config.config import CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CURRENCY_ABBREVIATIONS, ALL_CURRENCIES, CURRENCY_SYMBOLS
from config.languages import LANGUAGES

user_data = user_data.UserData()

cache: Dict[str, Any] = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

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

            async with session.get('https://min-api.cryptocompare.com/data/pricemulti?fsyms=NOT,DUREV,HMSTR&tsyms=USD') as response:
                additional_crypto_data = await response.json()
            for crypto in ['NOT', 'DUREV', 'HMSTR']:
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
    current_file = os.path.abspath(__file__)
    parent_dir = os.path.dirname(os.path.dirname(current_file))
    changelog_path = os.path.join(parent_dir, 'CHANGELOG.md')
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "Чейнджлог не найден."
    
def preprocess_number(text: str) -> str:
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    
    if re.match(r'^\d+,\d{1,2}$', text):
        return text.replace(',', '.')
    
    parts = re.split(r'[.,]', text)
    if len(parts) > 1:
        if len(parts[-1]) <= 2:
            return ''.join(parts[:-1]) + '.' + parts[-1]
        return ''.join(parts)
    
    return text

def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    text = text.strip().lower()
    
    if not text:
        return None, None
        
    replacements = {
        'кк': '*1000000',
        'млрд': '*1000000000',
        'млн': '*1000000',
        'к': '*1000',
        'b': '*1000000000',
        'm': '*1000000',
        'k': '*1000'
    }

    text = re.sub(r'(\d+)\s*(кк|к|млн|млрд|k|m|b)\b', r'\1\2', text, flags=re.IGNORECASE)
    
    for short, full in sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True):
        text = re.sub(rf'(\d+){short}\b', rf'\1{full}', text, flags=re.IGNORECASE)

    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)

    amount_pattern = r'\d+(?:[.,]\d+)?(?:\*\d+)?'
    currency_pattern = f'({"|".join(map(re.escape, CURRENCY_SYMBOLS.keys() | CURRENCY_ABBREVIATIONS.keys() | ALL_CURRENCIES.keys()))})'

    patterns = [
        rf'({amount_pattern})\s*{currency_pattern}',
        rf'{currency_pattern}\s*({amount_pattern})'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) == 2:
                if re.match(amount_pattern, match.group(1)):
                    amount_str = match.group(1)
                    currency_str = match.group(2)
                else:
                    amount_str = match.group(2)
                    currency_str = match.group(1)

                try:
                    amount_str = preprocess_number(amount_str)
                    
                    if '*' in amount_str:
                        amount = safe_eval(amount_str)
                    else:
                        amount = float(amount_str)
                    
                    currency = None
                    currency_str = currency_str.lower()
                    
                    if currency_str in CURRENCY_SYMBOLS:
                        currency = CURRENCY_SYMBOLS[currency_str]
                    elif currency_str in CURRENCY_ABBREVIATIONS:
                        currency = CURRENCY_ABBREVIATIONS[currency_str]
                    elif currency_str.upper() in ALL_CURRENCIES:
                        currency = currency_str.upper()

                    return amount, currency
                except Exception as e:
                    logger.error(f"Error processing amount: {str(e)}, input: {text}")

    return None, None

def safe_eval(expr):
    safe_dict = {
        "abs": abs,
        "round": round,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "pi": math.pi,
        "e": math.e,
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "/": operator.truediv,
        "**": operator.pow,
        "^": operator.pow
    }
    return eval(expr, {"__builtins__": None}, safe_dict)

def format_large_number(number, is_crypto=False):
    if abs(number) > 1e100:
        return "Число слишком большое"
    
    sign = "-" if number < 0 else ""
    number = abs(number)
    
    if is_crypto:
        if number < 1e-8:
            return f"{sign}{number:.8e}"
        elif number < 1:
            return f"{sign}{number:.8f}".rstrip('0').rstrip('.')
        elif number < 1000:
            return f"{sign}{number:.8f}".rstrip('0').rstrip('.')
        elif number >= 1e15:
            exponent = int(math.log10(number))
            mantissa = number / (10 ** exponent)
            return f"{sign}{mantissa:.2f}e{exponent}"
        else:
            return f"{sign}{number:,.8f}".rstrip('0').rstrip('.')
    else:
        if number < 0.01:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        elif number >= 1e15:
            exponent = int(math.log10(number))
            mantissa = number / (10 ** exponent)
            return f"{sign}{mantissa:.4f}e{exponent}"
        else:
            integer_part = int(number)
            decimal_places = max(2, min(4, 6 - len(str(integer_part))))
            formatted = f"{sign}{number:,.{decimal_places}f}"
            return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

def format_response(response: str, use_quote: bool) -> str:
    response = response.strip()
    if use_quote:
        return f"<blockquote expandable>{response}</blockquote>"
    return response

async def delete_conversion_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

async def save_settings(callback_query: CallbackQuery):
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()

async def check_admin_rights(message_or_callback: Union[Message, CallbackQuery], user_id: int, chat_id: int) -> bool:
    try:
        chat_member = await message_or_callback.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin rights: {e}")
        return False

async def show_not_admin_message(message_or_callback: Union[Message, CallbackQuery], user_id: int):
    user_lang = user_data.get_user_language(user_id)
    error_text = LANGUAGES[user_lang].get('not_admin_message', 'You need to be an admin to change these settings.')
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer(error_text, show_alert=True)
    else:
        await message_or_callback.reply(error_text)

async def get_crypto_history(crypto_id: str, days: str = "7") -> dict:
    try:
        symbol = f"{crypto_id}USDT"
        
        interval_mapping = {
            "1": "5m",
            "7": "15m",
            "30": "30m"
        }
        
        interval = interval_mapping.get(days, "15m")
        
        async with aiohttp.ClientSession() as session:
            url = "https://api.mexc.com/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval
            }
            
            logger.info(f"Requesting MEXC data: {url} with params {params}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'prices': [[int(item[0]), float(item[4])] for item in data[-100:]],
                        'volumes': [[int(item[0]), float(item[5])] for item in data[-100:]]
                    }
                else:
                    logger.error(f"MEXC API error: {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error fetching crypto history from MEXC: {e}")
        return None

async def get_current_price(crypto_id: str) -> tuple[float, float]:
    try:
        symbol = f"{crypto_id}USDT"
        
        async with aiohttp.ClientSession() as session:
            url = "https://api.mexc.com/api/v3/ticker/24hr"
            params = {'symbol': symbol}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['lastPrice'])
                    change_percent = float(data['priceChangePercent'])
                    return price, change_percent
                else:
                    return None, None
                    
    except Exception as e:
        logger.error(f"Error getting current price from MEXC: {e}")
        return None, None

async def get_chart_image(symbol: str) -> bytes:
    try:
        chart_url = f"https://api.cryptowat.ch/markets/mexc/{symbol.lower()}usdt/ohlc/png"
        params = {
            'width': 800,
            'height': 400,
            'theme': 'dark',
            'period': '1d'
        }
        
        logger.info(f"Requesting chart from CryptoWatch: {chart_url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(chart_url, params=params) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.info("Trying alternative API...")
                    alt_url = f"https://www.coingecko.com/coins/{symbol.lower()}/sparkline.svg"
                    async with session.get(alt_url) as alt_response:
                        if alt_response.status == 200:
                            return await alt_response.read()
                        else:
                            logger.error(f"Both APIs failed. CryptoWatch: {response.status}, Alternative: {alt_response.status}")
                            return None
    except Exception as e:
        logger.error(f"Error getting chart image: {e}")
        return None