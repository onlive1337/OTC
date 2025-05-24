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

def format_large_number(number, is_crypto=False):
    if abs(number) > 1e100:
        return "♾️ Бесконечность"
    
    sign = "-" if number < 0 else ""
    number = abs(number)
    
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

async def create_crypto_chart(crypto_id: str, period: str = "7d") -> Optional[bytes]:
    try:
        history_data = await get_crypto_history(crypto_id, period.replace('d', ''))
        if not history_data or not history_data['prices']:
            return None
        
        current_price, price_change = await get_current_price(crypto_id)
        if current_price is None:
            return None
        
        prices = history_data['prices']
        timestamps = [datetime.fromtimestamp(p[0]/1000) for p in prices]
        values = [p[1] for p in prices]
        
        fig, ax = plt.subplots(figsize=(12, 6), facecolor='#1a1a1a')
        ax.set_facecolor('#1a1a1a')
        
        if values[-1] >= values[0]:
            line_color = '#00ff88' 
            fill_color = '#00ff8820' 
        else:
            line_color = '#ff3366' 
            fill_color = '#ff336620' 
        
        ax.plot(timestamps, values, color=line_color, linewidth=2.5)
        
        ax.fill_between(timestamps, values, color=fill_color)
        
        ax.grid(True, alpha=0.2, color='#ffffff', linestyle='-', linewidth=0.5)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('#333333')
        ax.spines['left'].set_color('#333333')
        
        if period == "1d":
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
        elif period == "7d":
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
        
        plt.xticks(rotation=45, ha='right', color='#cccccc')
        plt.yticks(color='#cccccc')
        
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.2f}'))
        
        period_text = {'1d': '24 часа', '7d': '7 дней', '30d': '30 дней'}.get(period, period)
        title = f'{crypto_id}/USDT - {period_text}'
        ax.set_title(title, color='#ffffff', fontsize=16, fontweight='bold', pad=20)
        
        price_text = f'${current_price:,.4f}'
        change_text = f'{price_change:+.2f}%'
        change_color = '#00ff88' if price_change >= 0 else '#ff3366'
        
        ax.text(0.02, 0.98, price_text, transform=ax.transAxes, 
                fontsize=20, fontweight='bold', color='#ffffff',
                verticalalignment='top', horizontalalignment='left')
        
        ax.text(0.02, 0.88, change_text, transform=ax.transAxes,
                fontsize=16, fontweight='bold', color=change_color,
                verticalalignment='top', horizontalalignment='left')
        
        min_price = min(values)
        max_price = max(values)
        min_idx = values.index(min_price)
        max_idx = values.index(max_price)
        
        ax.plot(timestamps[min_idx], min_price, 'o', color='#ff3366', markersize=8, zorder=5)
        ax.plot(timestamps[max_idx], max_price, 'o', color='#00ff88', markersize=8, zorder=5)
        
        ax.annotate(f'Min: ${min_price:.4f}', 
                    xy=(timestamps[min_idx], min_price),
                    xytext=(10, -20), textcoords='offset points',
                    color='#ff3366', fontsize=10,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a1a', edgecolor='#ff3366', alpha=0.8))
        
        ax.annotate(f'Max: ${max_price:.4f}',
                    xy=(timestamps[max_idx], max_price),
                    xytext=(10, 20), textcoords='offset points',
                    color='#00ff88', fontsize=10,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='#1a1a1a', edgecolor='#00ff88', alpha=0.8))
        
        ax.text(0.99, 0.01, 'OTC Bot', transform=ax.transAxes,
                fontsize=10, color='#666666', alpha=0.5,
                horizontalalignment='right', verticalalignment='bottom')
        
        plt.tight_layout()
        
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=150, facecolor='#1a1a1a', edgecolor='none')
        buffer.seek(0)
        
        plt.close(fig)
        
        return buffer.getvalue()
        
    except Exception as e:
        logger.error(f"Error creating crypto chart: {e}")
        return None

async def get_chart_image(symbol: str) -> bytes:
    return await create_crypto_chart(symbol, "7d")