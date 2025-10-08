import logging
import os
import re
import time
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, Union

import aiohttp
from aiogram.types import CallbackQuery, Message

from config.config import CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CURRENCY_ABBREVIATIONS, \
    ALL_CURRENCIES, CURRENCY_SYMBOLS, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT, HTTP_RETRIES, SEMAPHORE_LIMITS, STALE_WHILE_REVALIDATE
from config.languages import LANGUAGES
from data import user_data

user_data = user_data.UserData()

cache: Dict[str, Any] = {}

logger = logging.getLogger(__name__)

import asyncio, random, urllib.parse

_http_session: Optional[aiohttp.ClientSession] = None
_domain_semaphores: Dict[str, asyncio.Semaphore] = {}
_rates_refreshing = False

def set_http_session(session: aiohttp.ClientSession):
    global _http_session
    _http_session = session

async def close_http_session():
    global _http_session
    if _http_session is not None:
        try:
            await _http_session.close()
        finally:
            _http_session = None

def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc

def _get_semaphore(host: str) -> asyncio.Semaphore:
    if host not in _domain_semaphores:
        _domain_semaphores[host] = asyncio.Semaphore(SEMAPHORE_LIMITS.get(host, 5))
    return _domain_semaphores[host]

async def _with_retries(coro_factory, host: str, retries: int = HTTP_RETRIES):
    last_exc = None
    sem = _get_semaphore(host)
    for attempt in range(retries + 1):
        try:
            async with sem:
                return await coro_factory()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            last_exc = e
            if attempt == retries:
                break
            await asyncio.sleep(0.3 * (2 ** attempt) + random.random() * 0.2)
    if last_exc:
        raise last_exc
    raise RuntimeError("_with_retries failed without exception")

EXTENDED_CURRENCY_ABBREVIATIONS = {
    'сум': 'UZS', 'сумов': 'UZS', 'сума': 'UZS', 'сумы': 'UZS',
    'лир': 'TRY', 'лиры': 'TRY', 'лира': 'TRY', 'лирах': 'TRY',
    'гривны': 'UAH', 'грн': 'UAH', 'гривен': 'UAH', 'гривна': 'UAH', 'гривень': 'UAH',
    'тон': 'TON', 'тонов': 'TON', 'тона': 'TON',
    'доллар': 'USD', 'долларов': 'USD', 'доллары': 'USD', 'доллара': 'USD', 'долл': 'USD', 'дол': 'USD',
    'юань': 'CNY', 'юаней': 'CNY', 'юаня': 'CNY',
    'рублей': 'RUB', 'рубль': 'RUB', 'рубля': 'RUB', 'руб': 'RUB', 'рублях': 'RUB',
    'тенге': 'KZT', 'евро': 'EUR', 'евр': 'EUR',
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

async def get_cached_data(key: str) -> Optional[Any]:
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

        stale_item = cache.get('exchange_rates')  # (data, ts)
        now = time.time()
        if stale_item:
            data, ts = stale_item
            if now - ts < (CACHE_EXPIRATION_TIME + STALE_WHILE_REVALIDATE):
                if not _rates_refreshing:
                    asyncio.create_task(_refresh_rates())
                logger.info("Returning stale exchange rates while refreshing in background")
                return data

        return await _refresh_rates()
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return {}

async def _refresh_rates() -> Dict[str, float]:
    global _rates_refreshing
    if _rates_refreshing:
        for _ in range(10):
            await asyncio.sleep(0.2)
            fresh = await get_cached_data('exchange_rates')
            if fresh:
                return fresh
    _rates_refreshing = True
    session_to_close = None
    try:
        session = _http_session
        if session is None:
            session_to_close = aiohttp.ClientSession()
            session = session_to_close

        rates: Dict[str, float] = {}
        timeout = aiohttp.ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT)

        url_fiat = 'https://open.er-api.com/v6/latest/USD'
        host = _host_of(url_fiat)
        async def _fiat():
            resp = await session.get(url_fiat, timeout=timeout)
            async with resp:
                return await resp.json()
        fiat_data = await _with_retries(_fiat, host)
        if isinstance(fiat_data, dict) and fiat_data.get('result') == 'success' and 'rates' in fiat_data:
            rates.update(fiat_data['rates'])

        crypto_ids = "bitcoin,ethereum,tether,binancecoin,ripple,cardano,solana,polkadot,dogecoin,matic-network,the-open-network,litecoin"
        url_cg = f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd'
        host = _host_of(url_cg)
        async def _cg():
            resp = await session.get(url_cg, timeout=timeout)
            async with resp:
                return await resp.json()
        crypto_data = await _with_retries(_cg, host)

        crypto_mapping = {
            'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether', 'BNB': 'binancecoin',
            'XRP': 'ripple', 'ADA': 'cardano', 'SOL': 'solana', 'DOT': 'polkadot',
            'DOGE': 'dogecoin', 'MATIC': 'matic-network', 'TON': 'the-open-network',
            'LTC': 'litecoin'
        }
        for crypto, id in crypto_mapping.items():
            if isinstance(crypto_data, dict) and id in crypto_data and isinstance(crypto_data[id], dict):
                usd_price = crypto_data[id].get('usd')
                try:
                    usd_price = float(usd_price)
                except (TypeError, ValueError):
                    usd_price = None
                if usd_price and usd_price > 0:
                    rates[crypto] = 1.0 / usd_price

        url_cc = 'https://min-api.cryptocompare.com/data/pricemulti?fsyms=NOT,DUREV,HMSTR&tsyms=USD'
        host = _host_of(url_cc)
        async def _cc():
            resp = await session.get(url_cc, timeout=timeout)
            async with resp:
                return await resp.json()
        additional_crypto_data = await _with_retries(_cc, host)
        for crypto in ['NOT', 'DUREV', 'HMSTR']:
            if isinstance(additional_crypto_data, dict) and crypto in additional_crypto_data and isinstance(additional_crypto_data[crypto], dict):
                usd_price = additional_crypto_data[crypto].get('USD')
                try:
                    usd_price = float(usd_price)
                except (TypeError, ValueError):
                    usd_price = None
                if usd_price and usd_price > 0:
                    rates[crypto] = 1.0 / usd_price

        all_currencies = set(ACTIVE_CURRENCIES + CRYPTO_CURRENCIES)
        missing_currencies = all_currencies - set(rates.keys())
        if missing_currencies:
            logger.warning(f"Missing currencies: {missing_currencies}. Attempting to fetch from alternative sources.")

            missing_fiat = missing_currencies.intersection(set(ACTIVE_CURRENCIES))
            if missing_fiat:
                url_ex = 'https://api.exchangerate-api.com/v4/latest/USD'
                host = _host_of(url_ex)
                async def _ex():
                    resp = await session.get(url_ex, timeout=timeout)
                    async with resp:
                        return await resp.json()
                alt_fiat_data = await _with_retries(_ex, host)
                if isinstance(alt_fiat_data, dict) and 'rates' in alt_fiat_data:
                    for currency in missing_fiat:
                        if currency in alt_fiat_data['rates']:
                            rates[currency] = alt_fiat_data['rates'][currency]

            missing_crypto = missing_currencies.intersection(set(CRYPTO_CURRENCIES))
            for crypto in missing_crypto:
                url_cap = f'https://api.coincap.io/v2/assets/{crypto.lower()}'
                host = _host_of(url_cap)
                async def _cap(u=url_cap):
                    resp = await session.get(u, timeout=timeout)
                    async with resp:
                        return await resp.json()
                alt_crypto_data = await _with_retries(_cap, host)
                try:
                    price_usd = float(alt_crypto_data.get('data', {}).get('priceUsd'))
                except (TypeError, ValueError, AttributeError):
                    price_usd = None
                if price_usd and price_usd > 0:
                    rates[crypto] = 1.0 / price_usd

        await set_cached_data('exchange_rates', rates)
        logger.info("Successfully fetched and cached exchange rates")
        return rates
    except Exception as e:
        logger.error(f"Error refreshing exchange rates: {e}")
        return {}
    finally:
        _rates_refreshing = False
        if session_to_close is not None:
            await session_to_close.close()

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
    
    number_match = re.match(r'^([\d\s,.]+)', text)
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
        if number < 0.01:
            return f"{sign}{number:.6f}".rstrip('0').rstrip('.')
        if number < 1:
            return f"{sign}{number:.4f}".rstrip('0').rstrip('.')
        return f"{sign}{number:,.2f}"

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