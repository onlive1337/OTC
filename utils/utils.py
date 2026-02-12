import logging
import os
import re
import time
from typing import Dict, Any, Tuple, Optional, Union

import aiohttp
from aiogram.types import CallbackQuery, Message

from config.config import CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CURRENCY_ABBREVIATIONS, \
    ALL_CURRENCIES, CURRENCY_SYMBOLS, HTTP_TOTAL_TIMEOUT, HTTP_CONNECT_TIMEOUT, HTTP_RETRIES, SEMAPHORE_LIMITS, \
    STALE_WHILE_REVALIDATE
from config.languages import LANGUAGES

from loader import user_data

cache: Dict[str, Any] = {}

logger = logging.getLogger(__name__)

import asyncio
import random
import urllib.parse
import ujson
import ast
import operator

_http_session: Optional[aiohttp.ClientSession] = None
_domain_semaphores: Dict[str, asyncio.Semaphore] = {}
_rates_lock = asyncio.Lock()

_ALL_CURRENCY_PATTERNS = {}
_ALL_CURRENCY_PATTERNS.update(CURRENCY_SYMBOLS)
_ALL_CURRENCY_PATTERNS.update(CURRENCY_ABBREVIATIONS)
_ALL_CURRENCY_PATTERNS.update({k.upper(): k.upper() for k in ALL_CURRENCIES.keys()})

_SORTED_CURRENCY_PATTERNS = sorted(_ALL_CURRENCY_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True)

_REGEX_PARTS = []
for pattern, _ in _SORTED_CURRENCY_PATTERNS:
    is_symbol = pattern in CURRENCY_SYMBOLS or re.match(r'^\W+$', pattern, re.UNICODE) is not None
    if is_symbol:
        _REGEX_PARTS.append(re.escape(pattern.lower()))
    else:
        _REGEX_PARTS.append(rf'(?<!\w){re.escape(pattern.lower())}(?!\w)')

_CURRENCY_REGEX = re.compile('|'.join(_REGEX_PARTS), re.IGNORECASE)

_PATTERN_TO_CODE = {p.lower(): c for p, c in _ALL_CURRENCY_PATTERNS.items()}

_SPACE_DIGIT_REGEX = re.compile(r'(\d)\s+(\d)')
_STARTING_NUMBER_REGEX = re.compile(r'^([\d\s,.]+)')

_MULTIPLIERS = {
    'тыс': 1000, 'тысяч': 1000, 'тысячи': 1000, 'тысяча': 1000,
    'млн': 1000000, 'миллион': 1000000, 'миллионов': 1000000, 'миллиона': 1000000,
    'млрд': 1000000000, 'миллиард': 1000000000, 'миллиардов': 1000000000,
    'кк': 1000000, 'лям': 1000000, 'ляма': 1000000, 'лямов': 1000000,
    'к': 1000, 'k': 1000, 'm': 1000000, 'b': 1000000000,
    'thousand': 1000, 'million': 1000000, 'billion': 1000000000
}

_MULTIPLIER_REGEXES = {
    re.compile(rf'(\d+(?:[.,]\d+)?)\s*{txt}\b', re.IGNORECASE): val 
    for txt, val in _MULTIPLIERS.items()
}

_FIND_NUMBERS_REGEX = re.compile(r'[\d\s,\.]+')
_SIMPLE_NUMBER_REGEX = re.compile(r'[^\d.]')

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


async def get_cached_data(key: str) -> Optional[Any]:
    if key in cache:
        cached_data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_EXPIRATION_TIME:
            return cached_data
    return None

async def set_cached_data(key: str, data: Dict[str, float]):
    cache[key] = (data, time.time())

def _safe_bg_task(coro, name: str = "background"):
    task = asyncio.create_task(coro, name=name)
    def _on_done(t: asyncio.Task):
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"Background task '{name}' failed: {exc}", exc_info=exc)
    task.add_done_callback(_on_done)
    return task

async def get_exchange_rates() -> Dict[str, float]:
    try:
        cached_rates = await get_cached_data('exchange_rates')
        if cached_rates:
            logger.debug("Using cached exchange rates")
            return cached_rates

        stale_item = cache.get('exchange_rates')
        now = time.time()
        if stale_item:
            data, ts = stale_item
            if now - ts < (CACHE_EXPIRATION_TIME + STALE_WHILE_REVALIDATE):
                if not _rates_lock.locked():
                    _safe_bg_task(refresh_rates(force=True), name="stale_refresh_rates")
                logger.info("Returning stale exchange rates while refreshing in background")
                return data

        return await refresh_rates()
    except Exception as e:
        logger.error(f"Error fetching exchange rates: {e}")
        return {}

async def refresh_rates(force: bool = False) -> Dict[str, float]:
    if not force:
        if _rates_lock.locked():
            for _ in range(10):
                await asyncio.sleep(0.2)
                fresh = await get_cached_data('exchange_rates')
                if fresh:
                    return fresh

        async with _rates_lock:
            fresh = await get_cached_data('exchange_rates')
            if fresh:
                return fresh

            return await _fetch_rates_unlocked()
    
    async with _rates_lock:
        return await _fetch_rates_unlocked()

async def _fetch_rates_unlocked() -> Dict[str, float]:
    session_to_close = None

    try:
        from config.config import COINCAP_API_KEY

        session = _http_session
        if session is None:
            session_to_close = aiohttp.ClientSession(json_serialize=ujson.dumps)
            session = session_to_close

        rates: Dict[str, float] = {}
        timeout = aiohttp.ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT)

        fiat_sources = [
            'https://open.er-api.com/v6/latest/USD',
            'https://api.exchangerate-api.com/v4/latest/USD',
            'https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json'
        ]

        fiat_fetched = False
        for fiat_url in fiat_sources:
            try:
                host = _host_of(fiat_url)

                async def _fiat(url=fiat_url):
                    resp = await session.get(url, timeout=timeout)
                    async with resp:
                        return await resp.json(loads=ujson.loads)

                fiat_data = await _with_retries(_fiat, host)

                if isinstance(fiat_data, dict):
                    if fiat_data.get('result') == 'success' and 'rates' in fiat_data:
                        rates.update(fiat_data['rates'])
                        fiat_fetched = True
                        logger.info(f"Fetched fiat rates from {host}")
                        break
                    elif 'rates' in fiat_data:
                        rates.update(fiat_data['rates'])
                        fiat_fetched = True
                        logger.info(f"Fetched fiat rates from {host}")
                        break
                    elif 'usd' in fiat_data:
                        usd_rates = fiat_data['usd']
                        for curr_lower, rate in usd_rates.items():
                            curr_upper = curr_lower.upper()
                            if rate and rate > 0:
                                rates[curr_upper] = float(rate)
                        rates['USD'] = 1.0
                        fiat_fetched = True
                        logger.info(f"Fetched fiat rates from {host}")
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch fiat from {fiat_url}: {e}")
                continue

        if not fiat_fetched:
            logger.error("All fiat currency sources failed!")

        crypto_ids = "bitcoin,ethereum,tether,binancecoin,ripple,cardano,solana,polkadot,dogecoin,the-open-network,litecoin"
        url_cg = f'https://api.coingecko.com/api/v3/simple/price?ids={crypto_ids}&vs_currencies=usd'

        try:
            host = _host_of(url_cg)

            async def _cg():
                resp = await session.get(url_cg, timeout=timeout)
                async with resp:
                    return await resp.json(loads=ujson.loads)

            crypto_data = await _with_retries(_cg, host)

            crypto_mapping = {
                'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether', 'BNB': 'binancecoin',
                'XRP': 'ripple', 'ADA': 'cardano', 'SOL': 'solana', 'DOT': 'polkadot',
                'DOGE': 'dogecoin', 'TON': 'the-open-network',
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

            logger.info("Fetched main crypto rates from CoinGecko")
        except Exception as e:
            logger.error(f"CoinGecko failed: {e}")

        url_cc = 'https://min-api.cryptocompare.com/data/pricemulti?fsyms=NOT,DUREV,HMSTR&tsyms=USD'
        try:
            host = _host_of(url_cc)

            async def _cc():
                resp = await session.get(url_cc, timeout=timeout)
                async with resp:
                    return await resp.json(loads=ujson.loads)

            additional_crypto_data = await _with_retries(_cc, host)

            for crypto in ['NOT', 'DUREV', 'HMSTR']:
                if isinstance(additional_crypto_data, dict) and crypto in additional_crypto_data:
                    if isinstance(additional_crypto_data[crypto], dict):
                        usd_price = additional_crypto_data[crypto].get('USD')
                        try:
                            usd_price = float(usd_price)
                        except (TypeError, ValueError):
                            usd_price = None
                        if usd_price and usd_price > 0:
                            rates[crypto] = 1.0 / usd_price

            logger.info("Fetched additional crypto from CryptoCompare")
        except Exception as e:
            logger.warning(f"CryptoCompare failed: {e}")

        all_currencies = set(ACTIVE_CURRENCIES + CRYPTO_CURRENCIES)
        missing_currencies = all_currencies - set(rates.keys())

        if missing_currencies:
            logger.warning(f"Missing currencies after primary sources: {missing_currencies}")

            missing_crypto = missing_currencies.intersection(set(CRYPTO_CURRENCIES))
            if missing_crypto and COINCAP_API_KEY:
                logger.info(f"Trying CoinCap v3 for: {missing_crypto}")
                for crypto in missing_crypto:
                    coincap_mapping = {
                        'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether',
                        'BNB': 'binance-coin', 'XRP': 'xrp', 'ADA': 'cardano',
                        'SOL': 'solana', 'DOT': 'polkadot', 'DOGE': 'dogecoin',
                        'TON': 'toncoin', 'LTC': 'litecoin',
                        'NOT': 'notcoin', 'DUREV': 'durev', 'HMSTR': 'hamster-kombat'
                    }
                    asset_id = coincap_mapping.get(crypto, crypto.lower())
                    url_cap = f'https://rest.coincap.io/v3/assets/{asset_id}?apiKey={COINCAP_API_KEY}'
                    host = _host_of(url_cap)

                    async def _cap(u=url_cap):
                        resp = await session.get(u, timeout=timeout)
                        async with resp:
                            return await resp.json(loads=ujson.loads)

                    try:
                        alt_crypto_data = await _with_retries(_cap, host)
                        if isinstance(alt_crypto_data, dict) and 'data' in alt_crypto_data:
                            price_usd = float(alt_crypto_data['data'].get('priceUsd', 0))
                            if price_usd > 0:
                                rates[crypto] = 1.0 / price_usd
                                logger.info(f"Fetched {crypto} from CoinCap v3")
                    except Exception as e:
                        logger.warning(f"Failed to fetch {crypto} from CoinCap v3: {e}")

            elif missing_crypto:
                logger.info(f"Trying CoinGecko individual requests for: {missing_crypto}")
                gecko_mapping = {
                    'NOT': 'notcoin', 'DUREV': 'durev', 'HMSTR': 'hamster-kombat',
                    'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether',
                    'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano',
                    'SOL': 'solana', 'DOT': 'polkadot', 'DOGE': 'dogecoin',
                    'TON': 'the-open-network', 'LTC': 'litecoin'
                }

                for crypto in missing_crypto:
                    if crypto in gecko_mapping:
                        coin_id = gecko_mapping[crypto]
                        url_gecko = f'https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd'
                        host = _host_of(url_gecko)

                        async def _gecko(u=url_gecko):
                            resp = await session.get(u, timeout=timeout)
                            async with resp:
                                return await resp.json(loads=ujson.loads)

                        try:
                            gecko_data = await _with_retries(_gecko, host)
                            if isinstance(gecko_data, dict) and coin_id in gecko_data:
                                price_usd = float(gecko_data[coin_id].get('usd', 0))
                                if price_usd > 0:
                                    rates[crypto] = 1.0 / price_usd
                                    logger.info(f"Fetched {crypto} from CoinGecko")
                        except Exception as e:
                            logger.warning(f"Failed to fetch {crypto} from CoinGecko: {e}")

        final_missing = all_currencies - set(rates.keys())
        if final_missing:
            logger.error(f"Still missing currencies after all attempts: {final_missing}")

        await set_cached_data('exchange_rates', rates)
        logger.info(f"Successfully cached {len(rates)} exchange rates")
        return rates

    except Exception as e:
        logger.error(f"Critical error in _refresh_rates: {e}")
        return {}
    finally:
        if session_to_close is not None:
            await session_to_close.close()

def convert_currency(amount: float, from_currency: str, to_currency: str, rates: Dict[str, float]) -> float:
    if from_currency != 'USD' and from_currency not in rates:
        raise KeyError(f"Rate not available for {from_currency}")
    if to_currency != 'USD' and to_currency not in rates:
        raise KeyError(f"Rate not available for {to_currency}")
    if from_currency == 'USD':
        return amount * rates[to_currency]
    elif to_currency == 'USD':
        return amount / rates[from_currency]
    else:
        return amount / rates[from_currency] * rates[to_currency]

        return amount / rates[from_currency] * rates[to_currency]

_CHANGELOG_CACHE = None

def read_changelog():
    global _CHANGELOG_CACHE
    if _CHANGELOG_CACHE is not None:
        return _CHANGELOG_CACHE

    current_file = os.path.abspath(__file__)
    parent_dir = os.path.dirname(os.path.dirname(current_file))
    changelog_path = os.path.join(parent_dir, 'CHANGELOG.md')
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        versions = re.split(r'(?=^## \[)', content, flags=re.MULTILINE)
        header = versions[0] if versions else ''
        version_blocks = [v for v in versions[1:] if v.strip()]
        
        if len(version_blocks) > 2:
            result = header + ''.join(version_blocks[:2]).rstrip()
            result += '\n\n---\n_...и ещё старые версии_'
            _CHANGELOG_CACHE = result
            return result
            
        _CHANGELOG_CACHE = content
        return content
    except FileNotFoundError:
        return "Чейнджлог не найден."

def smart_number_parse(text: str) -> str:
    text = _SPACE_DIGIT_REGEX.sub(r'\1\2', text)
    
    number_match = _STARTING_NUMBER_REGEX.match(text)
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
    ops = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
    }
    
    def _safe_eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left = _safe_eval(node.left)
            right = _safe_eval(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("Division by zero")
            return ops[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_safe_eval(node.operand)
        raise ValueError("Unsafe expression")

    try:
        expr = expr.replace('х', '*').replace('×', '*')
        expr = expr.replace('÷', '/').replace(':', '/')
        expr = expr.replace(' ', '')
        
        allowed_chars = '0123456789+-*/().'
        if not all(c in allowed_chars for c in expr):
            return None
        
        tree = ast.parse(expr, mode='eval')
        return _safe_eval(tree.body)
    except Exception:
        return None

def parse_amount_and_currency(text: str) -> Tuple[Optional[float], Optional[str]]:
    if not text:
        return None, None

    original_text = text
    text = text.strip()
    
    text_lower = text.lower()
    
    currency = None
    currency_match = None
    
    match = _CURRENCY_REGEX.search(text_lower)
    if match:
        matched_text = match.group(0)
        currency = _PATTERN_TO_CODE.get(matched_text.lower())
        currency_match = match
        
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
    
    for pattern, mult_value in _MULTIPLIER_REGEXES.items():
        match = pattern.search(amount_text)
        if match:
            base_number = smart_number_parse(match.group(1))
            try:
                amount = float(base_number) * mult_value
                return amount, currency
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse multiplier number '{match.group(1)}': {e}")
                pass
    
    number_matches = _FIND_NUMBERS_REGEX.findall(amount_text)
    
    for number_str in number_matches:
        cleaned_number = smart_number_parse(number_str)
        try:
            amount = float(cleaned_number)
            if amount >= 0:
                return amount, currency
        except (ValueError, TypeError):
            continue
    
    try:
        simple_number = _SIMPLE_NUMBER_REGEX.sub('', amount_text)
        if simple_number:
            amount = float(simple_number)
            if amount >= 0:
                return amount, currency
    except (ValueError, TypeError):
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


async def delete_conversion_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
    await callback_query.answer()

async def save_settings(callback_query: CallbackQuery):
    user_lang = await user_data.get_user_language(callback_query.from_user.id)
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
    chat_id = None
    chat_type = None
    
    if isinstance(message_or_callback, Message):
        chat_id = message_or_callback.chat.id
        chat_type = message_or_callback.chat.type
    elif isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        chat_id = message_or_callback.message.chat.id
        chat_type = message_or_callback.message.chat.type

    if chat_type in ('group', 'supergroup') and chat_id:
        lang_code = await user_data.get_chat_language(chat_id)
    else:
        lang_code = await user_data.get_user_language(user_id)

    error_text = LANGUAGES[lang_code].get('not_admin_message', 'You need to be an admin to change these settings.')
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.answer(error_text, show_alert=True)
    else:
        await message_or_callback.reply(error_text)