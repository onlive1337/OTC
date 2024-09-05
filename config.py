import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_IDS = [810587766]
USER_DATA_FILE = 'user_data.json'
CURRENT_VERSION = "0.9.1"

CACHE_EXPIRATION_TIME = 600

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
    '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY', '₽': 'RUB', '₣': 'CHF', '₹': 'INR', '₺': 'TRY',
    '₴': 'UAH', '₿': 'BTC', 'сум': 'UZS', 'грн': 'UAH', '₸': 'KZT'
}

CURRENCY_ABBREVIATIONS = {
    'сум': 'UZS',
    'лир': 'TRY',
    'лиры': 'TRY',
    'лира': 'TRY',
    'гривны': 'UAH',
    'грн': 'UAH',
    'тон': 'TON',
}