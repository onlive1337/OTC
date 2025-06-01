from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional, Union, List
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
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import io
from PIL import Image, ImageDraw, ImageFont
import numpy as np

user_data = user_data.UserData()

cache: Dict[str, Any] = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', filename='logs.txt', filemode='a')
logger = logging.getLogger(__name__)

EXTENDED_CURRENCY_ABBREVIATIONS = {
    'сум': 'UZS', 'сумов': 'UZS', 'сума': 'UZS', 'сумы': 'UZS',
    'лир': 'TRY', 'лиры': 'TRY', 'лира': 'TRY', 'лирах': 'TRY',
    'гривны': 'UAH', 'грн': 'UAH', 'гривен': 'UAH', 'гривна': 'UAH', 'гривень': 'UAH',
    'тон': 'TON', 'тонов': 'TON', 'тона': 'TON',
    'доллар': 'USD', 'долларов': 'USD', 'доллары': 'USD', 'доллара': 'USD', 'долл': 'USD', 'дол': 'USD',
    'юань': 'CNY', 'юаней': 'CNY', 'юаня': 'CNY',
    'рублей': 'RUB', 'рубль': 'RUB', 'рубля': 'RUB', 'руб': 'RUB', 'рублях': 'RUB',
    'тенге': 'KZT', 'тенге': 'KZT',
    'евро': 'EUR', 'евр': 'EUR',
    'фунт': 'GBP', 'фунтов': 'GBP', 'фунта': 'GBP',
    'йен': 'JPY', 'йены': 'JPY', 'иен': 'JPY', 'иены': 'JPY',
    'вон': 'KRW', 'воны': 'KRW', 'вона': 'KRW',
    'песо': 'MXN', 'песос': 'MXN',
    'реал': 'BRL', 'реалов': 'BRL', 'реала': 'BRL',
    'рэнд': 'ZAR', 'рэндов': 'ZAR', 'ранд': 'ZAR', 'рандов': 'ZAR',
    
    'dollar': 'USD', 'dollars': 'USD', 'usd': 'USD', 'бакс': 'USD', 'баксов': 'USD',
    'euro': 'EUR', 'euros': 'EUR', 'eur': 'EUR',
    'pound': 'GBP', 'pounds': 'GBP', 'gbp': 'GBP',
    'yen': 'JPY', 'yens': 'JPY', 'jpy': 'JPY',
    'yuan': 'CNY', 'cny': 'CNY',
    'ruble': 'RUB', 'rubles': 'RUB', 'rub': 'RUB',
    'hryvnia': 'UAH', 'hryvnias': 'UAH', 'uah': 'UAH',
    'sum': 'UZS', 'sums': 'UZS', 'uzs': 'UZS',
    'tenge': 'KZT', 'kzt': 'KZT',
    'lira': 'TRY', 'liras': 'TRY', 'try': 'TRY',
    
    'биткоин': 'BTC', 'биткоинов': 'BTC', 'биток': 'BTC', 'битков': 'BTC', 'битка': 'BTC',
    'эфир': 'ETH', 'эфира': 'ETH', 'эфиров': 'ETH', 'эфириум': 'ETH',
    'тезер': 'USDT', 'тезера': 'USDT', 'юсдт': 'USDT',
    'солана': 'SOL', 'соланы': 'SOL',
    'догикоин': 'DOGE', 'доги': 'DOGE', 'додж': 'DOGE',
    'нот': 'NOT', 'ноткоин': 'NOT', 'ноткоинов': 'NOT',
    'хамстер': 'HMSTR', 'хамстеров': 'HMSTR',
    
    'bitcoin': 'BTC', 'bitcoins': 'BTC', 'btc': 'BTC',
    'ethereum': 'ETH', 'eth': 'ETH', 'ether': 'ETH',
    'tether': 'USDT', 'usdt': 'USDT',
    'binance': 'BNB', 'bnb': 'BNB',
    'solana': 'SOL', 'sol': 'SOL',
    'dogecoin': 'DOGE', 'doge': 'DOGE',
    'notcoin': 'NOT', 'not': 'NOT',
    'hamster': 'HMSTR', 'hmstr': 'HMSTR',
}

EXTENDED_CURRENCY_ABBREVIATIONS.update(CURRENCY_ABBREVIATIONS)

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

def smart_number_parse(text: str) -> str:
    text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
    
    number_match = re.match(r'^([\d\s,\.]+)', text)
    if not number_match:
        return text
    
    number_str = number_match.group(1).strip()
    
    dots = number_str.count('.')
    commas = number_str.count(',')
    
    if dots == 0 and commas == 0:
        return number_str
    
    elif dots == 1 and commas == 0:
        return number_str
    
    elif dots == 0 and commas == 1:
        parts = number_str.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            return number_str.replace(',', '.')
        else:
            return number_str.replace(',', '')
    
    elif dots > 0 and commas > 0:
        last_dot = number_str.rfind('.')
        last_comma = number_str.rfind(',')
        
        if last_comma > last_dot:
            return number_str.replace('.', '').replace(',', '.')
        else:
            return number_str.replace(',', '')
    
    elif commas > 1:
        return number_str.replace(',', '')
    
    elif dots > 1:
        return number_str.replace('.', '')
    
    return number_str

def parse_mathematical_expression(expr: str) -> Optional[float]:
    try:
        expr = expr.replace('^', '**')
        expr = expr.replace('х', '*').replace('×', '*')
        expr = expr.replace('÷', '/').replace(':', '/')
        
        expr = expr.replace(' ', '')
        
        allowed_chars = '0123456789+-*/().'
        if not all(c in allowed_chars for c in expr):
            return None
        
        result = eval(expr, {"__builtins__": {}}, {})
        return float(result)
    except:
        return None

def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None
    
    original_text = text
    text = text.strip()
    
    multipliers = {
        'тыс': 1000, 'тысяч': 1000, 'тысячи': 1000, 'тысяча': 1000,
        'млн': 1000000, 'миллион': 1000000, 'миллионов': 1000000, 'миллиона': 1000000,
        'млрд': 1000000000, 'миллиард': 1000000000, 'миллиардов': 1000000000,
        'кк': 1000000, 'лям': 1000000, 'ляма': 1000000, 'лямов': 1000000,
        'к': 1000, 'k': 1000, 'm': 1000000, 'b': 1000000000,
        'thousand': 1000, 'million': 1000000, 'billion': 1000000000
    }
    
    text_lower = text.lower()
    
    currency = None
    currency_match = None
    
    all_currency_patterns = {}
    all_currency_patterns.update(CURRENCY_SYMBOLS)
    all_currency_patterns.update(EXTENDED_CURRENCY_ABBREVIATIONS)
    all_currency_patterns.update({k.upper(): k.upper() for k in ALL_CURRENCIES.keys()})
    
    sorted_patterns = sorted(all_currency_patterns.items(), key=lambda x: len(x[0]), reverse=True)
    
    for pattern, curr_code in sorted_patterns:
        regex = rf'\b{re.escape(pattern.lower())}\b'
        match = re.search(regex, text_lower)
        if match:
            currency = curr_code
            currency_match = match
            break
    
    if not currency:
        return None, None
    
    amount_text = text_lower[:currency_match.start()] + text_lower[currency_match.end():]
    amount_text = amount_text.strip()
    
    math_operators = ['+', '-', '*', '/', '(', ')', '^', 'х', '×', '÷', ':']
    has_math = any(op in amount_text for op in math_operators)
    
    if has_math:
        result = parse_mathematical_expression(amount_text)
        if result is not None:
            return result, currency
    
    for mult_text, mult_value in multipliers.items():
        pattern = rf'(\d+(?:[.,]\d+)?)\s*{mult_text}\b'
        match = re.search(pattern, amount_text, re.IGNORECASE)
        if match:
            base_number = smart_number_parse(match.group(1))
            try:
                amount = float(base_number) * mult_value
                return amount, currency
            except:
                pass
    
    number_pattern = r'[\d\s,\.]+'
    number_matches = re.findall(number_pattern, amount_text)
    
    for number_str in number_matches:
        cleaned_number = smart_number_parse(number_str)
        try:
            amount = float(cleaned_number)
            if amount > 0:
                return amount, currency
        except:
            continue
    
    try:
        simple_number = re.sub(r'[^\d.]', '', amount_text)
        if simple_number:
            amount = float(simple_number)
            if amount > 0:
                return amount, currency
    except:
        pass
    
    return None, None

def format_large_number(number, is_crypto=False, is_original_amount=False):
    if abs(number) > 1e100:
        return "♾️ Бесконечность"
    
    sign = "-" if number < 0 else ""
    number = abs(number)
    
    if is_original_amount:
        if number == int(number):
            return f"{sign}{int(number):,}".replace(',', ' ')
        else:
            formatted = f"{sign}{number:,.10f}".rstrip('0').rstrip('.')
            parts = formatted.split('.')
            if len(parts) == 2:
                return parts[0].replace(',', ' ') + '.' + parts[1]
            return parts[0].replace(',', ' ')
    
    if is_crypto:
        if number == 0:
            return "0"
        elif number < 0.00000001:
            return f"{sign}{number:.2e}"
        elif number < 0.01:
            return f"{sign}{number:.8f}".rstrip('0').rstrip('.')
        elif number < 1:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        elif number < 1000:
            return f"{sign}{number:.4f}".rstrip('0').rstrip('.')
        elif number < 1000000:
            return f"{sign}{number:,.2f}"
        elif number < 1000000000:
            return f"{sign}{number/1000000:.3f}M"
        elif number < 1000000000000:
            return f"{sign}{number/1000000000:.3f}B"
        else:
            return f"{sign}{number:.2e}"
    else:
        if number == 0:
            return "0"
        elif number < 0.01:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        elif number < 1:
            return f"{sign}{number:.4f}".rstrip('0').rstrip('.')
        elif number < 100:
            return f"{sign}{number:.2f}".rstrip('0').rstrip('.')
        elif number < 1000000:
            return f"{sign}{number:,.2f}".rstrip('0').rstrip('.')
        elif number < 1000000000:
            return f"{sign}{number/1000000:.2f}M"
        elif number < 1000000000000:
            return f"{sign}{number/1000000000:.2f}B"
        elif number < 1000000000000000:
            return f"{sign}{number/1000000000000:.2f}T"
        else:
            return f"{sign}{number:.2e}"

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

async def get_binance_symbol_info(crypto: str) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.binance.com/api/v3/ticker/24hr"
            params = {'symbol': f"{crypto}USDT"}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return f"{crypto}USDT"
                    
            params = {'symbol': f"{crypto}BUSD"}
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return f"{crypto}BUSD"
                    
            crypto_mapping = {
                'HMSTR': 'HMSTRUSDT',
                'NOT': 'NOTUSDT',
                'DUREV': None 
            }
            
            if crypto in crypto_mapping and crypto_mapping[crypto]:
                params = {'symbol': crypto_mapping[crypto]}
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return crypto_mapping[crypto]
                        
            return None
            
    except Exception as e:
        logger.error(f"Error checking Binance symbol: {e}")
        return None

async def get_crypto_history_binance(crypto: str, period: str = "7") -> Optional[dict]:
    try:
        symbol = await get_binance_symbol_info(crypto)
        if not symbol:
            return await get_crypto_history_coingecko(crypto, period)
        
        interval_map = {
            "1": ("15m", 96),
            "7": ("1h", 168),
            "30": ("4h", 180) 
        }
        
        interval, limit = interval_map.get(period, ("1h", 168))
        
        async with aiohttp.ClientSession() as session:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            
            logger.info(f"Requesting Binance data: {url} with params {params}")
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    return {
                        'prices': [[int(item[0]), float(item[4])] for item in data],
                        'volumes': [[int(item[0]), float(item[5])] for item in data],
                        'source': 'binance'
                    }
                else:
                    logger.error(f"Binance API error: {response.status}")
                    return await get_crypto_history_coingecko(crypto, period)
                    
    except Exception as e:
        logger.error(f"Error fetching from Binance: {e}")
        return await get_crypto_history_coingecko(crypto, period)

async def get_crypto_history_coingecko(crypto: str, period: str = "7") -> Optional[dict]:
    try:
        crypto_id_map = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether',
            'BNB': 'binancecoin',
            'XRP': 'ripple',
            'ADA': 'cardano',
            'SOL': 'solana',
            'DOT': 'polkadot',
            'DOGE': 'dogecoin',
            'MATIC': 'matic-network',
            'TON': 'the-open-network',
            'NOT': 'notcoin',
            'LTC': 'litecoin',
            'HMSTR': 'hamster-kombat',
            'DUREV': 'durev'
        }
        
        crypto_id = crypto_id_map.get(crypto)
        if not crypto_id:
            return None
            
        async with aiohttp.ClientSession() as session:
            url = f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
            params = {
                'vs_currency': 'usd',
                'days': period
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'prices': data.get('prices', []),
                        'volumes': data.get('total_volumes', []),
                        'source': 'coingecko'
                    }
                else:
                    logger.error(f"CoinGecko API error: {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error fetching from CoinGecko: {e}")
        return None

async def get_current_price_binance(crypto: str) -> tuple[Optional[float], Optional[float]]:
    try:
        symbol = await get_binance_symbol_info(crypto)
        if not symbol:
            return await get_current_price_coingecko(crypto)
            
        async with aiohttp.ClientSession() as session:
            url = "https://api.binance.com/api/v3/ticker/24hr"
            params = {'symbol': symbol}
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['lastPrice'])
                    change_percent = float(data['priceChangePercent'])
                    return price, change_percent
                else:
                    return await get_current_price_coingecko(crypto)
                    
    except Exception as e:
        logger.error(f"Error getting price from Binance: {e}")
        return await get_current_price_coingecko(crypto)

async def get_current_price_coingecko(crypto: str) -> tuple[Optional[float], Optional[float]]:
    try:
        crypto_id_map = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'USDT': 'tether',
            'BNB': 'binancecoin',
            'XRP': 'ripple',
            'ADA': 'cardano',
            'SOL': 'solana',
            'DOT': 'polkadot',
            'DOGE': 'dogecoin',
            'MATIC': 'matic-network',
            'TON': 'the-open-network',
            'NOT': 'notcoin',
            'LTC': 'litecoin',
            'HMSTR': 'hamster-kombat',
            'DUREV': 'durev'
        }
        
        crypto_id = crypto_id_map.get(crypto)
        if not crypto_id:
            return None, None
            
        async with aiohttp.ClientSession() as session:
            url = f"https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': crypto_id,
                'vs_currencies': 'usd',
                'include_24hr_change': 'true'
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if crypto_id in data:
                        price = data[crypto_id]['usd']
                        change = data[crypto_id].get('usd_24h_change', 0)
                        return price, change
                        
        return None, None
        
    except Exception as e:
        logger.error(f"Error getting price from CoinGecko: {e}")
        return None, None

async def get_crypto_history(crypto: str, period: str = "7") -> Optional[dict]:
    return await get_crypto_history_binance(crypto, period)

async def get_current_price(crypto: str) -> tuple[Optional[float], Optional[float]]:
    return await get_current_price_binance(crypto)

async def create_crypto_chart(crypto_id: str, period: str = "7d") -> Optional[bytes]:
    try:
        history_data = await get_crypto_history(crypto_id, period.replace('d', ''))
        if not history_data or not history_data['prices']:
            return None
        
        current_price, _ = await get_current_price(crypto_id)
        if current_price is None:
            return None
        
        prices = history_data['prices']
        timestamps = [datetime.fromtimestamp(p[0]/1000) for p in prices]
        values = [p[1] for p in prices]
        
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 7))
        fig.patch.set_facecolor('#0d1117')
        ax.set_facecolor('#0d1117')
        
        first_price = values[0]
        last_price = values[-1]
        period_change = ((last_price - first_price) / first_price) * 100
        
        if period_change >= 0:
            line_color = '#00d964'
            fill_color = '#00d96420'
        else:
            line_color = '#ff4747'
            fill_color = '#ff474720'
        
        ax.plot(timestamps, values, color=line_color, linewidth=2.5, zorder=3)
        ax.fill_between(timestamps, values, color=fill_color, alpha=0.3, zorder=2)
        
        ax.grid(True, alpha=0.1, color='#30363d', linestyle='-', linewidth=0.5)
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        if period == "1d":
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
        elif period == "7d":
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        
        ax.tick_params(colors='#8b949e', labelsize=10)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))
        
        period_names = {'1d': '24 часа', '7d': '7 дней', '30d': '30 дней'}
        ax.text(0.5, 0.98, f'{crypto_id}/USDT - {period_names.get(period, period)}',
                transform=ax.transAxes, ha='center', va='top',
                fontsize=18, fontweight='bold', color='#ffffff')
        
        price_y = 0.90
        ax.text(0.02, price_y, f'${current_price:,.4f}',
                transform=ax.transAxes, fontsize=24, fontweight='bold',
                color='#ffffff', va='top')
        
        change_color = '#00d964' if period_change >= 0 else '#ff4747'
        ax.text(0.02, price_y - 0.08, f'{period_change:+.2f}%',
                transform=ax.transAxes, fontsize=18, fontweight='bold',
                color=change_color, va='top')
        
        min_price = min(values)
        max_price = max(values)
        min_idx = values.index(min_price)
        max_idx = values.index(max_price)
        
        ax.scatter(timestamps[min_idx], min_price, color='#ff4747', s=60, zorder=5)
        ax.scatter(timestamps[max_idx], max_price, color='#00d964', s=60, zorder=5)
        
        ax.annotate(f'${min_price:.4f}',
                   xy=(timestamps[min_idx], min_price),
                   xytext=(10, -20), textcoords='offset points',
                   fontsize=10, color='#ff4747',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#0d1117', 
                            edgecolor='#ff4747', alpha=0.8))
        
        ax.annotate(f'${max_price:.4f}',
                   xy=(timestamps[max_idx], max_price),
                   xytext=(10, 20), textcoords='offset points',
                   fontsize=10, color='#00d964',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='#0d1117',
                            edgecolor='#00d964', alpha=0.8))
        
        source = history_data.get('source', 'unknown')
        ax.text(0.99, 0.01, f'OTC Bot • {source.capitalize()}',
                transform=ax.transAxes, ha='right', va='bottom',
                fontsize=9, color='#586069', alpha=0.7)
        
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=120, facecolor='#0d1117')
        buffer.seek(0)
        plt.close()
        
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error creating chart: {e}")
        return None