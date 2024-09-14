from typing import Dict, Any, Tuple, Optional
import time
from config.config import CACHE_EXPIRATION_TIME, ACTIVE_CURRENCIES, CRYPTO_CURRENCIES, CURRENCY_ABBREVIATIONS, ALL_CURRENCIES
import logging
import aiohttp
import os
import math
import re


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