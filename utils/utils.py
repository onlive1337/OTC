from typing import Dict, Any, Tuple, Optional
import time
from config.config import CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CURRENCY_ABBREVIATIONS, ALL_CURRENCIES, CURRENCY_SYMBOLS
from config.languages import LANGUAGES
import logging
import aiohttp
import os
import math
import re
import operator
from aiogram.types import CallbackQuery
from data import user_data

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

def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    text = text.strip().lower()
    
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    
    text = re.sub(r'(\d+)\s*(млн|млрд|m|k|к)', lambda m: m.group(1) + m.group(2), text)
    
    currency_pattern = '(' + '|'.join(map(re.escape, CURRENCY_SYMBOLS.keys() | CURRENCY_ABBREVIATIONS.keys() | ALL_CURRENCIES.keys())) + ')'
    pattern = rf'^{currency_pattern}\s*(.+)$|^(.+)\s*{currency_pattern}$'
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        if match.group(1):
            currency_str = match.group(1)
            amount_str = match.group(2)
        else:
            currency_str = match.group(4)
            amount_str = match.group(3)
    else:
        parts = text.split()
        if len(parts) < 2:
            return None, None
        currency_str = parts[-1]
        amount_str = ' '.join(parts[:-1])
    
    amount_str = amount_str.strip()
    if amount_str.endswith('кк'):
        amount_str = amount_str[:-2] + '*1000000'
    elif amount_str.endswith('к'):
        amount_str = amount_str[:-1] + '*1000'
    
    if ',' in amount_str and '.' not in amount_str:
        amount_str = amount_str.replace(',', '')
    else:
        amount_str = amount_str.replace(',', '.')
    
    amount_str = re.sub(r'(\d+)(млн|млрд|m)$', lambda m: str(float(m.group(1)) * {'млн': 1e6, 'млрд': 1e9, 'm': 1e6}[m.group(2)]), amount_str)
    
    try:
        amount = safe_eval(amount_str)
    except Exception:
        return None, None
    
    currency = None
    currency_str = currency_str.lower()
    if currency_str in CURRENCY_SYMBOLS:
        currency = CURRENCY_SYMBOLS[currency_str]
    elif currency_str in CURRENCY_ABBREVIATIONS:
        currency = CURRENCY_ABBREVIATIONS[currency_str]
    elif currency_str.upper() in ALL_CURRENCIES:
        currency = currency_str.upper()
    else:
        for abbr, curr in CURRENCY_ABBREVIATIONS.items():
            if abbr in currency_str:
                currency = curr
                break
        if not currency:
            return None, None

    return amount, currency

def safe_eval(expr):
    return eval(expr, {"__builtins__": None}, {
        "abs": abs,
        "round": round,
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "/": operator.truediv,
        "**": operator.pow,
        "^": operator.pow
    })

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
    if use_quote:
        return f"<blockquote expandable>{response}</blockquote>"
    else:
        return response 

async def delete_conversion_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

async def save_settings(callback_query: CallbackQuery):
    user_lang = user_data.get_user_language(callback_query.from_user.id)
    await callback_query.message.edit_text(LANGUAGES[user_lang]['save_settings'])
    await callback_query.answer()