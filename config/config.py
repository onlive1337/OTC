import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Put it into environment or .env")

# Logging and admin
_log_chat_id_raw = os.getenv('LOG_CHAT_ID', '')
LOG_CHAT_ID = int(_log_chat_id_raw) if _log_chat_id_raw.strip() else None
_admin_ids_raw = os.getenv('ADMIN_IDS', '')
ADMIN_IDS = [int(x) for x in _admin_ids_raw.split(',') if x.strip()] if _admin_ids_raw.strip() else []
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
COINCAP_API_KEY = os.getenv('COINCAP_API_KEY')
if not COINCAP_API_KEY:
    import logging as _log
    _log.getLogger(__name__).warning("COINCAP_API_KEY is not set. Fallback crypto sources will be used.")

# Storage
DB_PATH = os.getenv('DB_PATH', 'otc.db')

CURRENT_VERSION = "1.6.0"

# Cache
CACHE_EXPIRATION_TIME = 600  # seconds
STALE_WHILE_REVALIDATE = 300  # seconds

# HTTP defaults
HTTP_TOTAL_TIMEOUT = 5
HTTP_CONNECT_TIMEOUT = 2
HTTP_RETRIES = 2
SEMAPHORE_LIMITS = {
    'open.er-api.com': 5,
    'api.coingecko.com': 3,
    'min-api.cryptocompare.com': 3,
    'api.exchangerate-api.com': 3,
    'rest.coincap.io': 3,
}

ALL_CURRENCIES = {
    'USD': '🇺🇸', 'EUR': '🇪🇺', 'GBP': '🇬🇧', 'JPY': '🇯🇵', 'CHF': '🇨🇭', 'CNY': '🇨🇳', 'RUB': '🇷🇺',
    'AUD': '🇦🇺', 'CAD': '🇨🇦', 'NZD': '🇳🇿', 'SEK': '🇸🇪', 'NOK': '🇳🇴', 'DKK': '🇩🇰', 'ZAR': '🇿🇦',
    'INR': '🇮🇳', 'BRL': '🇧🇷', 'MXN': '🇲🇽', 'SGD': '🇸🇬', 'HKD': '🇭🇰', 'KRW': '🇰🇷', 'TRY': '🇹🇷',
    'PLN': '🇵🇱', 'THB': '🇹🇭', 'IDR': '🇮🇩', 'HUF': '🇭🇺', 'CZK': '🇨🇿', 'ILS': '🇮🇱', 'CLP': '🇨🇱',
    'PHP': '🇵🇭', 'AED': '🇦🇪', 'COP': '🇨🇴', 'SAR': '🇸🇦', 'MYR': '🇲🇾', 'RON': '🇷🇴',
    'UZS': '🇺🇿', 'UAH': '🇺🇦', 'KZT': '🇰🇿', 'ARS': '🇦🇷', 'VND': '🇻🇳', 'BGN': '🇧🇬', 'HRK': '🇭🇷',
    'BYN': '🇧🇾',
    'BTC': '₿', 'ETH': 'Ξ', 'USDT': '₮', 'BNB': 'BNB', 'XRP': 'XRP', 'ADA': 'ADA', 'SOL': 'SOL', 'DOT': 'DOT',
    'DOGE': 'Ð', 'TON': 'TON', 'NOT': 'NOT', 'DUREV': 'DUREV', 'LTC': 'Ł', 'HMSTR': 'HMSTR'
}

CRYPTO_CURRENCIES = ['BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE', 'TON', 'NOT', 'DUREV', 'LTC', 'HMSTR']
ACTIVE_CURRENCIES = [cur for cur in ALL_CURRENCIES if cur not in CRYPTO_CURRENCIES]

CURRENCY_SYMBOLS = {
    '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₽': 'RUB', '₣': 'CHF', '₹': 'INR', '₺': 'TRY',
    '₴': 'UAH', '₿': 'BTC', 'сум': 'UZS', 'грн': 'UAH', '₸': 'KZT', 'Br': 'BYN'
}

CURRENCY_ABBREVIATIONS = {
    # RU — фиат
    'доллар': 'USD', 'долларов': 'USD', 'доллары': 'USD', 'доллара': 'USD', 'долл': 'USD', 'бакс': 'USD', 'баксов': 'USD',
    'евро': 'EUR', 'евр': 'EUR',
    'рублей': 'RUB', 'рубль': 'RUB', 'рубля': 'RUB', 'руб': 'RUB',
    'гривны': 'UAH', 'грн': 'UAH', 'гривен': 'UAH', 'гривна': 'UAH',
    'сум': 'UZS', 'сумов': 'UZS',
    'тенге': 'KZT',
    'лир': 'TRY', 'лиры': 'TRY', 'лира': 'TRY',
    'юань': 'CNY', 'юаней': 'CNY',
    'фунт': 'GBP', 'фунтов': 'GBP',
    'белруб': 'BYN', 'белрублей': 'BYN',

    # EN — фиат
    'dollar': 'USD', 'dollars': 'USD',
    'euro': 'EUR', 'euros': 'EUR',
    'pound': 'GBP', 'pounds': 'GBP',
    'ruble': 'RUB', 'rubles': 'RUB',
    'hryvnia': 'UAH',
    'lira': 'TRY',
    'yuan': 'CNY',
    'tenge': 'KZT',

    # RU — крипта
    'тон': 'TON',
    'биткоин': 'BTC', 'биткоинов': 'BTC', 'биток': 'BTC',
    'эфир': 'ETH', 'эфира': 'ETH', 'эфириум': 'ETH',
    'тезер': 'USDT', 'юсдт': 'USDT',
    'солана': 'SOL',
    'додж': 'DOGE', 'доги': 'DOGE',
    'нот': 'NOT', 'ноткоин': 'NOT',
    'хамстер': 'HMSTR',

    # EN — крипта
    'bitcoin': 'BTC', 'btc': 'BTC',
    'ethereum': 'ETH', 'eth': 'ETH',
    'tether': 'USDT', 'usdt': 'USDT',
    'solana': 'SOL', 'sol': 'SOL',
    'dogecoin': 'DOGE', 'doge': 'DOGE',
    'notcoin': 'NOT',
    'hamster': 'HMSTR',
}